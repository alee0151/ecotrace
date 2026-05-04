"""
Seeco Step 3: API + LLM biodiversity evidence pipeline.

This module avoids scraping. API clients return article metadata and links; the
LLM extraction layer only receives provided snippets or explicitly supplied full
text from an allowed retrieval tool.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import date
from enum import Enum
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Protocol


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = BACKEND_ROOT / ".env"

CONFIG_PATH = os.getenv(
    "ECOTRACE_CONFIG",
    str(REPO_ROOT / "config" / "ecotrace_config.json"),
)


def load_config() -> dict[str, object]:
    with open(CONFIG_PATH, encoding="utf-8") as config_file:
        return json.load(config_file)


def config_value(config: dict[str, object], *keys: str) -> object:
    value: object = config
    for key in keys:
        if not isinstance(value, dict):
            raise KeyError(".".join(keys))
        value = value[key]
    return value


def config_tuple(config: dict[str, object], *keys: str) -> tuple[str, ...]:
    value = config_value(config, *keys)
    if not isinstance(value, list):
        raise TypeError(".".join(keys))
    return tuple(str(item) for item in value)


def config_set(config: dict[str, object], *keys: str) -> set[str]:
    return set(config_tuple(config, *keys))


def config_float_dict(config: dict[str, object], *keys: str) -> dict[str, float]:
    value = config_value(config, *keys)
    if not isinstance(value, dict):
        raise TypeError(".".join(keys))
    return {str(key): float(item) for key, item in value.items()}


def config_location_aliases(
    config: dict[str, object], *keys: str
) -> tuple[tuple[str, str], ...]:
    value = config_value(config, *keys)
    if not isinstance(value, list):
        raise TypeError(".".join(keys))
    aliases = []
    for item in value:
        if not isinstance(item, list) or len(item) != 2:
            raise TypeError(".".join(keys))
        aliases.append((str(item[0]), str(item[1])))
    return tuple(aliases)


CONFIG = load_config()


class EvidenceCategory(str, Enum):
    BIODIVERSITY_RISK = "biodiversity risk"
    BIODIVERSITY_ACTION = "biodiversity action"
    REGULATORY_SIGNAL = "regulatory signal"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ArticleMetadata:
    title: str
    snippet: str
    source: str
    published_date: str | None
    url: str
    source_type: str = "news"


@dataclass(frozen=True)
class ExtractionInput:
    company: str
    article: ArticleMetadata
    full_text: str | None = None


@dataclass
class EvidenceRecord:
    company: str
    location: str | None
    activity_type: str | None
    biodiversity_signal: str
    evidence_type: str
    source_type: str
    source: str
    source_url: str
    source_date: str | None
    llm_confidence: float
    confidence: float
    notes: str | None = None


@dataclass(frozen=True)
class ReportEvidenceExcerpt:
    page_number: int
    score: int
    matched_terms: list[str]
    text: str


@dataclass(frozen=True)
class LocationOption:
    index: int
    location: str
    record_count: int
    top_confidence: float
    evidence_types: list[str]
    sources: list[str]


AUSTRALIA_LOCATION_TERMS = config_tuple(
    CONFIG, "pipeline", "australia_location_terms"
)
GENERIC_LOCATION_VALUES = config_set(CONFIG, "pipeline", "generic_location_values")
BIODIVERSITY_TERMS = config_tuple(CONFIG, "pipeline", "biodiversity_terms")
NO_SIGNAL_VALUES = config_set(CONFIG, "pipeline", "no_signal_values")
WEAK_SIGNAL_VALUES = config_set(CONFIG, "pipeline", "weak_signal_values")
LOCATION_ALIASES = config_location_aliases(CONFIG, "pipeline", "location_aliases")


class NewsProvider(Protocol):
    name: str

    def search(self, query: str) -> list[ArticleMetadata]:
        """Return article metadata from a news/discovery API."""


class LLMExtractor(Protocol):
    def extract(self, item: ExtractionInput) -> EvidenceRecord:
        """Extract structured biodiversity evidence from supplied content only."""


class ArticleContentRetriever(Protocol):
    def fetch_text(self, url: str) -> str | None:
        """Return article/page text for LLM extraction, or None when unavailable."""


SOURCE_CREDIBILITY = config_float_dict(CONFIG, "pipeline", "source_credibility")

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_OPENROUTER_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
NVIDIA_NIM_API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
DEFAULT_NVIDIA_NIM_MODEL = "nvidia/nemotron-3-super-120b-a12b"


def load_env_file(path: str | os.PathLike[str] = DEFAULT_ENV_PATH) -> None:
    """
    Load simple KEY=VALUE pairs from a local .env file.

    This keeps the project dependency-light. Existing environment variables win,
    so deployment settings can override local development values.
    """

    env_path = os.fspath(path)
    if not os.path.exists(env_path):
        return

    with open(env_path, encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def generate_queries(company: str) -> list[str]:
    company = company.strip()
    return [
        f"{company} biodiversity",
        f"{company} conservation",
        f"{company} rehabilitation",
        f"{company} EPBC",
    ]


def dedupe_articles(articles: Iterable[ArticleMetadata]) -> list[ArticleMetadata]:
    seen: set[str] = set()
    output: list[ArticleMetadata] = []

    for article in articles:
        key = article.url.strip().lower() or article.title.strip().lower()
        if key and key not in seen:
            seen.add(key)
            output.append(article)

    return output


def source_weight(source: str) -> float:
    key = source.strip().lower()
    return SOURCE_CREDIBILITY.get(key, 0.65)


def australia_relevance_score(text: str) -> int:
    normalized = text.lower()
    score = 0
    for term in AUSTRALIA_LOCATION_TERMS:
        if len(term) <= 3:
            if re.search(rf"\b{re.escape(term)}\b", normalized):
                score += 1
        elif term in normalized:
            score += 1
    return score


def is_australia_linked(record: EvidenceRecord) -> bool:
    text = " ".join(
        value
        for value in (
            record.location,
            record.activity_type,
            record.biodiversity_signal,
            record.source,
            record.source_url,
            record.notes,
        )
        if value
    )
    return australia_relevance_score(text) > 0


def has_biodiversity_terms(text: str) -> bool:
    normalized = text.lower()
    return any(term in normalized for term in BIODIVERSITY_TERMS)


def combine_confidence(
    *,
    llm_confidence: float,
    source_count: int,
    credibility: float,
    full_text_used: bool,
) -> float:
    """
    Estimate confidence before dataset validation.

    Step 7 can still run without EPBC/protected-area/species matches, but the
    score should be treated as article/LLM confidence rather than final
    validated environmental confidence.
    """

    source_bonus = min(source_count, 4) * 0.04
    text_bonus = 0.10 if full_text_used else 0.0
    snippet_penalty = 0.12 if not full_text_used else 0.0

    score = (
        llm_confidence * 0.60
        + credibility * 0.28
        + source_bonus
        + text_bonus
        - snippet_penalty
    )
    return round(max(0.0, min(score, 0.90)), 2)


class EcoTracePipeline:
    def __init__(
        self,
        providers: list[NewsProvider],
        extractor: LLMExtractor,
        article_retriever: ArticleContentRetriever | None = None,
        australia_only: bool = False,
    ) -> None:
        self.providers = providers
        self.extractor = extractor
        self.article_retriever = article_retriever
        self.australia_only = australia_only

    def run(self, company: str) -> list[EvidenceRecord]:
        articles: list[ArticleMetadata] = []
        for query in generate_queries(company):
            for provider in self.providers:
                articles.extend(provider.search(query))

        deduped = dedupe_articles(articles)
        source_count_by_company = max(1, len({item.source for item in deduped}))
        records: list[EvidenceRecord] = []

        for article in deduped:
            full_text = self._fetch_full_text(article.url)
            extracted = self.extractor.extract(
                ExtractionInput(company=company, article=article, full_text=full_text)
            )
            evidence_text = evidence_context(article, full_text)
            quality_gate_record(extracted, evidence_text)

            if self.australia_only and not is_australia_linked(extracted):
                continue

            australia_bonus = 0.04 if is_australia_linked(extracted) else 0.0
            extracted.confidence = combine_confidence(
                llm_confidence=extracted.llm_confidence,
                source_count=source_count_by_company,
                credibility=source_weight(article.source),
                full_text_used=bool(full_text),
            ) + australia_bonus
            extracted.confidence = round(min(extracted.confidence, 0.90), 2)
            records.append(extracted)

        return sorted(records, key=lambda item: item.confidence, reverse=True)

    def run_json(self, company: str) -> list[dict[str, object]]:
        """Step 8 output: structured evidence only, with no article body text."""

        return [asdict(record) for record in self.run(company)]

    def _fetch_full_text(self, url: str) -> str | None:
        if not self.article_retriever or not url:
            return None
        return self.article_retriever.fetch_text(url)


class KeywordLLMExtractor:
    """
    Deterministic stand-in for an LLM extractor.

    Replace this with a real LLM call in production, keeping the same contract:
    pass in metadata/snippet/full text and request JSON-only structured output.
    """

    risk_terms = ("risk", "impact", "threat", "clearing", "habitat", "species")
    action_terms = ("conservation", "rehabilitation", "restoration", "offset")
    regulatory_terms = ("epbc", "approval", "compliance", "regulator")

    def extract(self, item: ExtractionInput) -> EvidenceRecord:
        text = f"{item.article.title} {item.article.snippet}".lower()
        category = EvidenceCategory.UNKNOWN
        signal = "biodiversity-related mention"

        if any(term in text for term in self.regulatory_terms):
            category = EvidenceCategory.REGULATORY_SIGNAL
            signal = "regulatory biodiversity signal"
        elif any(term in text for term in self.action_terms):
            category = EvidenceCategory.BIODIVERSITY_ACTION
            signal = "biodiversity conservation or rehabilitation action"
        elif any(term in text for term in self.risk_terms):
            category = EvidenceCategory.BIODIVERSITY_RISK
            signal = "potential biodiversity risk"

        location = _guess_location(text)
        confidence = 0.55 if location else 0.42

        return EvidenceRecord(
            company=item.company,
            location=location,
            activity_type=_guess_activity(text),
            biodiversity_signal=signal,
            evidence_type=category.value,
            source_type=item.article.source_type,
            source=item.article.source,
            source_url=item.article.url,
            source_date=item.article.published_date,
            llm_confidence=confidence,
            confidence=confidence,
            notes="Snippet-only extraction; confidence can increase if allowed full text is supplied.",
        )


class OpenRouterLLMExtractor:
    """
    LLM extractor for OpenRouter-hosted models such as NVIDIA Nemotron 3 Super.

    It sends only article metadata/snippet/full text supplied by the pipeline and
    expects JSON back. It does not browse or scrape by itself.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        api_url: str = OPENROUTER_API_URL,
        max_retries: int = 2,
        retry_delay_seconds: float = 8.0,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.model = model or os.getenv("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL)
        self.api_url = api_url
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds

        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY is required for OpenRouterLLMExtractor")

    @classmethod
    def from_env(
        cls, env_path: str | os.PathLike[str] = DEFAULT_ENV_PATH
    ) -> "OpenRouterLLMExtractor":
        load_env_file(env_path)
        return cls()

    def extract(self, item: ExtractionInput) -> EvidenceRecord:
        payload = self._call_model(item)
        return EvidenceRecord(
            company=item.company,
            location=normalize_location(payload.get("location"), item),
            activity_type=_clean_optional(payload.get("activity_type")),
            biodiversity_signal=str(
                payload.get("biodiversity_signal") or "biodiversity-related mention"
            ),
            evidence_type=normalize_evidence_type(payload.get("evidence_type")),
            source_type=item.article.source_type,
            source=item.article.source,
            source_url=item.article.url,
            source_date=item.article.published_date,
            llm_confidence=_clamp_float(payload.get("llm_confidence"), 0.0, 1.0),
            confidence=0.0,
            notes="Extracted by OpenRouter LLM from supplied content only.",
        )

    def _call_model(self, item: ExtractionInput) -> dict[str, object]:
        article_text = item.full_text or item.article.snippet
        content_type = "allowed full text" if item.full_text else "snippet"
        request_body = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Extract facts. Output one compact JSON object only. "
                        "No reasoning, no markdown."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Company: {item.company}\n"
                        f"Content type: {content_type}\n"
                        f"Source type: {item.article.source_type}\n"
                        f"Title: {item.article.title}\n"
                        f"Source: {item.article.source}\n"
                        f"Date: {item.article.published_date}\n"
                        f"URL: {item.article.url}\n"
                        f"Text: {article_text}\n\n"
                        "Rules: location should be suburb/state, region/state, "
                        "or Australian state/territory. Do not use country-only "
                        "locations such as Australia; return null if no more "
                        "specific location is available. "
                        "activity_type should be a short label such as mining, "
                        "rehabilitation, conservation, monitoring, clearing, or offset. "
                        "For uploaded reports, prefer biodiversity risk or impact "
                        "evidence over positive action evidence when both are present. "
                        "evidence_type must be one of: biodiversity risk, "
                        "biodiversity action, regulatory signal, unknown. "
                        "Use biodiversity risk when the text describes actual or "
                        "potential impacts, threats, habitat loss, disturbance, "
                        "deforestation, ecosystem damage, or threatened species risk. "
                        "Use regulatory signal when EPBC, approval, compliance, "
                        "or regulator is present. llm_confidence must be 0 to 1. "
                        "biodiversity_signal must be a short evidence phrase from "
                        "the supplied text, not a boolean such as true or false. "
                        "JSON keys: location, activity_type, biodiversity_signal, "
                        "evidence_type, llm_confidence."
                    ),
                },
            ],
            "temperature": 0,
            "max_tokens": 1200,
        }

        request = urllib.request.Request(
            self.api_url,
            data=json.dumps(request_body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "http://localhost"),
                "X-Title": os.getenv("OPENROUTER_APP_NAME", "Seeco"),
            },
            method="POST",
        )

        data = self._send_request_with_retries(request)

        if "choices" not in data:
            message = data.get("error", data)
            raise RuntimeError(f"OpenRouter response did not include choices: {message}")

        message = data["choices"][0]["message"]
        content = message.get("content") or message.get("reasoning") or ""
        try:
            return parse_json_object(content)
        except json.JSONDecodeError:
            return infer_payload_from_text(content, item)

    def _send_request_with_retries(
        self, request: urllib.request.Request
    ) -> dict[str, object]:
        last_error: urllib.error.HTTPError | None = None
        retryable_status_codes = {429, 502, 503, 504}
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                if error.code not in retryable_status_codes or attempt >= self.max_retries:
                    raise
                last_error = error
                retry_after = error.headers.get("Retry-After")
                delay = (
                    float(retry_after)
                    if retry_after
                    else self.retry_delay_seconds * (attempt + 1)
                )
                time.sleep(delay)

        if last_error:
            raise last_error
        raise RuntimeError("OpenRouter request failed before receiving a response")


class NvidiaNIMLLMExtractor(OpenRouterLLMExtractor):
    """LLM extractor for NVIDIA-hosted NIM APIs."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        api_url: str | None = None,
        max_retries: int = 2,
        retry_delay_seconds: float = 8.0,
    ) -> None:
        self.api_key = api_key or os.getenv("NVIDIA_API_KEY")
        self.model = normalize_nvidia_model_name(
            model or os.getenv("NVIDIA_NIM_MODEL", DEFAULT_NVIDIA_NIM_MODEL)
        )
        self.api_url = api_url or os.getenv("NVIDIA_NIM_API_URL", NVIDIA_NIM_API_URL)
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds

        if not self.api_key:
            raise ValueError("NVIDIA_API_KEY is required for NvidiaNIMLLMExtractor")

    @classmethod
    def from_env(
        cls, env_path: str | os.PathLike[str] = DEFAULT_ENV_PATH
    ) -> "NvidiaNIMLLMExtractor":
        load_env_file(env_path)
        return cls()


def create_llm_extractor_from_env(
    env_path: str | os.PathLike[str] = DEFAULT_ENV_PATH,
) -> LLMExtractor:
    load_env_file(env_path)
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()

    if provider in {"nvidia", "nvidia_nim", "nim"}:
        return NvidiaNIMLLMExtractor()
    if provider in {"openrouter", ""} and os.getenv("OPENROUTER_API_KEY"):
        return OpenRouterLLMExtractor()
    if os.getenv("NVIDIA_API_KEY"):
        return NvidiaNIMLLMExtractor()
    return OpenRouterLLMExtractor()


def normalize_nvidia_model_name(model: str) -> str:
    return model.removesuffix(":free")


class SimpleArticleTextRetriever:
    """
    Optional article-page retrieval for assignments where LLM-assisted page
    reading is allowed.

    It extracts visible text and returns it to the LLM layer. The pipeline still
    outputs only structured evidence, never the full article text.
    """

    def __init__(self, max_chars: int = 12000) -> None:
        self.max_chars = max_chars

    def fetch_text(self, url: str) -> str | None:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 Seeco/1.0 "
                    "(LLM-assisted biodiversity evidence extraction)"
                )
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                content_type = response.headers.get("Content-Type", "")
                if "html" not in content_type.lower():
                    return None
                html = response.read().decode("utf-8", errors="replace")
        except Exception:
            return None

        parser = VisibleTextParser()
        parser.feed(html)
        text = " ".join(parser.text_parts)
        return " ".join(text.split())[: self.max_chars] or None


class UploadedReportTextReader:
    """
    Reads user-supplied sustainability or annual reports for LLM verification.

    Text, Markdown, and HTML are supported without extra dependencies. PDF
    support is enabled when pypdf is installed in the local environment.
    """

    html_extensions = {".html", ".htm"}
    focus_terms = BIODIVERSITY_TERMS + (
        "epbc",
        "epbc act",
        "approval conditions",
        "nationally threatened flora",
        "nationally threatened flora and fauna",
        "fauna species",
        "nature",
        "natural capital",
        "ecosystem",
        "ecosystems",
        "habitat",
        "species",
        "threatened species",
        "iucn red list",
        "extinction",
        "land clearing",
        "deforestation",
        "risk",
        "impact",
        "threat",
        "rehabilitation",
        "restoration",
        "offset",
        "monitoring",
        "conservation",
        "disturbance",
    )
    risk_focus_terms = (
        "biodiversity risk",
        "nature risk",
        "nationally threatened flora and fauna",
        "risk of direct impacts",
        "direct impacts to ecosystems",
        "threatened species",
        "iucn red list",
        "extinction",
        "habitat loss",
        "land clearing",
        "deforestation",
        "disturbance",
        "impact",
        "risk",
        "threat",
    )
    generic_risk_terms = {"impact", "risk", "threat"}

    def __init__(self, max_chars: int = 12000) -> None:
        self.max_chars = max_chars

    def read_text(self, path: str) -> str:
        return self.read_chunks(path, max_chunks=1)[0]

    def read_chunks(self, path: str, max_chunks: int = 3) -> list[str]:
        excerpts = self.scan_evidence(path, max_excerpts=max_chunks)
        return [excerpt.text for excerpt in excerpts]

    def scan_evidence(self, path: str, max_excerpts: int = 5) -> list[ReportEvidenceExcerpt]:
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        if not os.path.isfile(path):
            raise ValueError(f"Report path is not a file: {path}")

        max_excerpts = max(1, max_excerpts)
        pages = self._read_report_pages(path)
        if not any(text.strip() for _page_number, text in pages):
            raise ValueError(f"No readable report text found in {path}")

        excerpts: list[ReportEvidenceExcerpt] = []
        normalized_pages = [
            (page_number, " ".join(text.split()))
            for page_number, text in pages
        ]

        for index, (page_number, normalized) in enumerate(normalized_pages):
            if not normalized:
                continue
            matched_terms = self._matched_terms(normalized)
            score = self._score_report_window(normalized.lower())
            if score <= 0:
                continue
            nearby_text = self._nearby_page_context(normalized_pages, index)
            excerpts.append(
                ReportEvidenceExcerpt(
                    page_number=page_number,
                    score=score,
                    matched_terms=matched_terms,
                    text=self._build_page_excerpt(normalized, nearby_text),
                )
            )

        if excerpts:
            return sorted(excerpts, key=lambda item: item.score, reverse=True)[
                :max_excerpts
            ]

        fallback_text = " ".join(pages[0][1].split())[: self.max_chars]
        return [
            ReportEvidenceExcerpt(
                page_number=pages[0][0],
                score=0,
                matched_terms=[],
                text=fallback_text,
            )
        ]

    def _read_report_pages(self, path: str) -> list[tuple[int, str]]:
        extension = os.path.splitext(path)[1].lower()
        if extension == ".pdf":
            return self._read_pdf_pages(path)
        if extension in self.html_extensions:
            return [(1, self._read_html_file(path))]
        return [(1, self._read_plain_text(path))]

    def _read_plain_text(self, path: str) -> str:
        with open(path, encoding="utf-8", errors="replace") as report_file:
            return report_file.read()

    def _read_html_file(self, path: str) -> str:
        html = self._read_plain_text(path)
        parser = VisibleTextParser()
        parser.feed(html)
        return " ".join(parser.text_parts)

    def _read_pdf_text(self, path: str) -> str:
        return "\n".join(text for _page_number, text in self._read_pdf_pages(path))

    def _read_pdf_pages(self, path: str) -> list[tuple[int, str]]:
        try:
            from pypdf import PdfReader
        except ImportError as error:
            raise RuntimeError(
                "PDF report reading requires pypdf. Install it or upload a text/HTML "
                "version of the sustainability or annual report."
            ) from error

        reader = PdfReader(path)
        pages = []
        for index, page in enumerate(reader.pages, start=1):
            pages.append((index, page.extract_text() or ""))
        return pages

    def _select_relevant_text(self, text: str) -> str:
        return "\n\n...\n\n".join(self._select_relevant_chunks(text, max_chunks=1))

    def _select_relevant_chunks(self, text: str, max_chunks: int = 3) -> list[str]:
        normalized = " ".join(text.split())
        if len(normalized) <= self.max_chars:
            return [normalized]

        windows = self._rank_relevant_windows(normalized)
        if not windows:
            return [normalized[: self.max_chars]]

        selected: list[tuple[int, str]] = []
        used_spans: list[tuple[int, int]] = []

        for _score, start, end in windows:
            if any(start < used_end and end > used_start for used_start, used_end in used_spans):
                continue
            snippet = normalized[start:end].strip(" .")
            if not snippet:
                continue
            if len(snippet) > self.max_chars:
                snippet = snippet[: self.max_chars].strip(" .")
            selected.append((start, snippet))
            used_spans.append((start, end))
            if len(selected) >= max_chunks:
                break

        if not selected:
            return [normalized[: self.max_chars]]

        selected.sort(key=lambda item: item[0])
        return [snippet for _start, snippet in selected]

    def _rank_relevant_windows(self, text: str) -> list[tuple[int, int, int]]:
        lowered = text.lower()
        window_size = min(2500, max(800, self.max_chars // 4))
        windows_by_bucket: dict[int, tuple[int, int, int]] = {}

        for term in self.focus_terms:
            for match in re.finditer(re.escape(term.lower()), lowered):
                start = max(0, match.start() - window_size // 2)
                end = min(len(text), start + window_size)
                start = max(0, end - window_size)
                bucketed_start = start - (start % 250)
                snippet = lowered[start:end]
                score = self._score_report_window(snippet)
                existing = windows_by_bucket.get(bucketed_start)
                if existing is None or score > existing[0]:
                    windows_by_bucket[bucketed_start] = (score, start, end)

        return sorted(windows_by_bucket.values(), key=lambda item: item[0], reverse=True)

    def _score_report_window(self, text: str) -> int:
        specific_risk_terms = tuple(
            term for term in self.risk_focus_terms if term not in self.generic_risk_terms
        )
        risk_score = sum(5 for term in specific_risk_terms if term in text)
        biodiversity_score = sum(2 for term in BIODIVERSITY_TERMS if term in text)
        focus_terms = tuple(
            term for term in self.focus_terms if term not in self.generic_risk_terms
        )
        focus_score = sum(1 for term in focus_terms if term in text)
        if risk_score or biodiversity_score or focus_score:
            risk_score += sum(1 for term in self.generic_risk_terms if term in text)
        else:
            return 0
        australia_score = 2 if australia_relevance_score(text) else 0
        return risk_score + biodiversity_score + focus_score + australia_score

    def _matched_terms(self, text: str) -> list[str]:
        lowered = text.lower()
        matched = []
        for term in self.risk_focus_terms + self.focus_terms:
            if term in lowered and term not in matched:
                matched.append(term)
        return matched[:12]

    def _nearby_page_context(
        self,
        pages: list[tuple[int, str]],
        page_index: int,
    ) -> str:
        context_parts = []
        for nearby_index in (page_index + 1, page_index - 1):
            if nearby_index < 0 or nearby_index >= len(pages):
                continue
            page_number, page_text = pages[nearby_index]
            if not page_text:
                continue
            context_parts.append(f"Nearby page {page_number}: {page_text[:1400]}")
        return " ".join(context_parts)

    def _build_page_excerpt(self, text: str, nearby_text: str = "") -> str:
        lowered = text.lower()
        center = -1
        best_term = ""
        for term in self._evidence_context_terms():
            index = lowered.find(term)
            if index >= 0:
                center = index
                best_term = term
                break

        if center < 0:
            center = 0

        excerpt_budget = self.max_chars
        if nearby_text:
            excerpt_budget = max(1200, int(self.max_chars * 0.7))

        start = max(0, center - excerpt_budget // 4)
        end = min(len(text), start + excerpt_budget)
        start = max(0, end - excerpt_budget)
        start = self._move_to_sentence_boundary(text, start, center, forward=True)
        end = min(len(text), start + excerpt_budget)
        end = self._move_to_sentence_boundary(text, end, center + len(best_term))
        if end <= start:
            end = min(len(text), start + excerpt_budget)
        excerpt = text[start:end].strip(" .")
        if not nearby_text:
            return excerpt

        remaining = max(0, self.max_chars - len(excerpt) - 34)
        if remaining <= 0:
            return excerpt
        return f"{excerpt}\n\nNearby report context: {nearby_text[:remaining].strip(' .')}"

    def _move_to_sentence_boundary(
        self,
        text: str,
        boundary: int,
        anchor: int,
        forward: bool = False,
    ) -> int:
        if boundary <= 0 or boundary >= len(text):
            return max(0, min(boundary, len(text)))

        punctuation = ".;:!?"
        if forward:
            search_start = max(0, boundary - 300)
            search_end = min(anchor, boundary + 300)
            candidates = [
                text.rfind(mark, search_start, search_end)
                for mark in punctuation
            ]
            candidate = max(candidates)
            if candidate >= 0:
                return min(len(text), candidate + 1)
            return boundary

        search_start = max(anchor, boundary - 300)
        candidates = [
            text.find(mark, search_start, boundary)
            for mark in punctuation
        ]
        candidates = [candidate for candidate in candidates if candidate >= 0]
        if candidates:
            return min(len(text), min(candidates) + 1)
        return boundary

    def _evidence_context_terms(self) -> tuple[str, ...]:
        return tuple(
            term
            for term in self.risk_focus_terms + BIODIVERSITY_TERMS + self.focus_terms
            if term not in self.generic_risk_terms
        )


class VisibleTextParser(HTMLParser):
    skipped_tags = {"script", "style", "noscript", "svg", "head"}

    def __init__(self) -> None:
        super().__init__()
        self.text_parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self.skipped_tags:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.skipped_tags and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if len(text) > 1:
            self.text_parts.append(text)


def _guess_location(text: str) -> str | None:
    for token, location in LOCATION_ALIASES:
        if re.search(rf"\b{re.escape(token)}\b", text):
            return location
    return None


def _guess_activity(text: str) -> str | None:
    activities = (
        "monitoring",
        "mining",
        "rehabilitation",
        "conservation",
        "clearing",
        "offset",
    )
    for activity in activities:
        if activity in text:
            return activity
    return None


def _clean_optional(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_location(value: object, item: ExtractionInput | None = None) -> str | None:
    raw = _clean_optional(value)

    if item:
        text = f"{item.article.title} {item.article.snippet} {item.full_text or ''}".lower()
        guessed = _guess_location(text)
        if guessed and (
            not raw
            or is_generic_location(raw)
            or _looks_like_reasoning(raw)
            or is_more_specific_location(guessed, raw)
        ):
            return guessed

    if raw and not _looks_like_reasoning(raw) and not is_generic_location(raw):
        raw_guess = _guess_location(raw.lower())
        if raw_guess:
            return raw_guess
        return raw

    if raw:
        cleaned = re.split(r"\?| wait| rule says", raw, flags=re.IGNORECASE)[0].strip(" .,")
        if cleaned and not is_generic_location(cleaned):
            return cleaned
    return None


def is_generic_location(value: str | None) -> bool:
    if not value:
        return True
    normalized = value.strip().lower()
    return normalized in GENERIC_LOCATION_VALUES


def is_more_specific_location(candidate: str, current: str | None) -> bool:
    if not current:
        return True
    candidate_normalized = candidate.strip().lower()
    current_normalized = current.strip().lower()
    if candidate_normalized == current_normalized:
        return False
    if is_generic_location(current):
        return True
    return current_normalized in candidate_normalized


def _looks_like_reasoning(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in ("wait", "rule says", "maybe", "should i"))


def parse_json_object(content: str) -> dict[str, object]:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(content[start : end + 1])


def infer_payload_from_text(
    content: str, item: ExtractionInput
) -> dict[str, object]:
    text = f"{item.article.title} {item.article.snippet} {item.full_text or ''}"
    reasoning = content.lower()

    location = _guess_location(text.lower()) or _extract_location_from_reasoning(
        reasoning
    )
    activity_type = _guess_activity(text.lower())
    if not activity_type:
        activity_type = _extract_activity_from_reasoning(reasoning)

    evidence_type = EvidenceCategory.UNKNOWN.value
    if any(term in text.lower() for term in ("epbc", "approval", "compliance", "regulator")):
        evidence_type = EvidenceCategory.REGULATORY_SIGNAL.value
    elif has_biodiversity_terms(text):
        evidence_type = EvidenceCategory.BIODIVERSITY_ACTION.value

    signal = _specific_signal_from_text(text)

    return {
        "location": location,
        "activity_type": activity_type,
        "biodiversity_signal": signal,
        "evidence_type": evidence_type,
        "llm_confidence": 0.65 if signal != "unknown" else 0.25,
    }


def _extract_location_from_reasoning(reasoning: str) -> str | None:
    patterns = (
        r'location (?:is|=|:)\s*"?([^"\n.]+)',
        r'"location"\s*:\s*"([^"]+)"',
    )
    for pattern in patterns:
        match = re.search(pattern, reasoning, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip(" .").title()
    return None


def _extract_activity_from_reasoning(reasoning: str) -> str | None:
    for activity in ("monitoring", "rehabilitation", "conservation", "mining", "offset"):
        if activity in reasoning:
            return activity
    return None


def _specific_signal_from_text(text: str) -> str:
    normalized = text.lower()
    signal_terms = [
        "edna monitoring",
        "species monitoring",
        "habitat rehabilitation",
        "biodiversity enhancement",
        "subterranean fauna",
        "conservation",
        "rehabilitation",
    ]
    matched = [term for term in signal_terms if term in normalized]
    return ", ".join(matched[:2]) if matched else "unknown"


def normalize_evidence_type(value: object) -> str:
    text = str(value or "").strip().lower().replace("_", " ").replace("-", " ")
    text = " ".join(text.split())

    aliases = {
        "biodiversity risk": EvidenceCategory.BIODIVERSITY_RISK.value,
        "risk": EvidenceCategory.BIODIVERSITY_RISK.value,
        "biodiversity action": EvidenceCategory.BIODIVERSITY_ACTION.value,
        "action": EvidenceCategory.BIODIVERSITY_ACTION.value,
        "regulatory signal": EvidenceCategory.REGULATORY_SIGNAL.value,
        "regulatory": EvidenceCategory.REGULATORY_SIGNAL.value,
        "unknown": EvidenceCategory.UNKNOWN.value,
    }
    return aliases.get(text, EvidenceCategory.UNKNOWN.value)


def evidence_context(article: ArticleMetadata, full_text: str | None = None) -> str:
    return " ".join(
        value
        for value in (article.title, article.snippet, full_text)
        if value
    )


def quality_gate_record(record: EvidenceRecord, evidence_text: str) -> EvidenceRecord:
    """
    Downgrade contradictory or weak LLM outputs before confidence scoring.

    This is not dataset validation. It only checks whether the supplied text and
    the extracted fields are internally consistent enough for pre-validation use.
    """

    signal = (record.biodiversity_signal or "").strip()
    normalized_signal = signal.lower()
    evidence_has_biodiversity = has_biodiversity_terms(evidence_text)
    signal_is_empty = normalized_signal in NO_SIGNAL_VALUES
    signal_has_biodiversity = has_biodiversity_terms(signal)
    signal_is_weak = normalized_signal in WEAK_SIGNAL_VALUES or (
        len(signal.split()) < 2 and not signal_has_biodiversity
    )

    notes = [record.notes] if record.notes else []

    if signal_is_empty:
        record.biodiversity_signal = "unknown"
        record.evidence_type = EvidenceCategory.UNKNOWN.value
        record.llm_confidence = min(record.llm_confidence, 0.25)
        notes.append("Quality gate: no biodiversity signal extracted.")

    elif signal_is_weak:
        record.llm_confidence = min(record.llm_confidence, 0.45)
        notes.append("Quality gate: biodiversity signal is too generic.")
        if record.evidence_type != EvidenceCategory.REGULATORY_SIGNAL.value:
            record.evidence_type = EvidenceCategory.UNKNOWN.value
            notes.append("Quality gate: weak non-regulatory evidence downgraded.")

    if not evidence_has_biodiversity:
        record.evidence_type = EvidenceCategory.UNKNOWN.value
        record.llm_confidence = min(record.llm_confidence, 0.30)
        notes.append("Quality gate: supplied text lacks biodiversity terms.")

    elif (
        record.evidence_type == EvidenceCategory.UNKNOWN.value
        and not signal_is_empty
        and not signal_is_weak
    ):
        inferred_type = infer_evidence_type_from_signal(record.biodiversity_signal)
        if inferred_type != EvidenceCategory.UNKNOWN.value:
            record.evidence_type = inferred_type
            notes.append("Quality gate: inferred evidence type from signal.")

    if (
        record.evidence_type != EvidenceCategory.UNKNOWN.value
        and record.biodiversity_signal == "unknown"
    ):
        record.evidence_type = EvidenceCategory.UNKNOWN.value
        record.llm_confidence = min(record.llm_confidence, 0.25)
        notes.append("Quality gate: evidence type contradicted empty signal.")

    record.notes = " ".join(notes) if notes else None
    return record


def infer_evidence_type_from_signal(signal: str) -> str:
    normalized = signal.lower()
    regulatory_terms = ("epbc", "approval", "regulator", "court", "law", "legal")
    risk_terms = (
        "deforestation",
        "land clearing",
        "clearing",
        "habitat loss",
        "risk",
        "fail",
        "failure",
        "threat",
    )
    action_terms = (
        "conservation",
        "rehabilitation",
        "restoration",
        "monitoring",
        "protect",
        "sustainable",
    )

    if any(term in normalized for term in regulatory_terms):
        return EvidenceCategory.REGULATORY_SIGNAL.value
    if any(term in normalized for term in risk_terms):
        return EvidenceCategory.BIODIVERSITY_RISK.value
    if any(term in normalized for term in action_terms):
        return EvidenceCategory.BIODIVERSITY_ACTION.value
    return EvidenceCategory.UNKNOWN.value


def group_records_by_location(
    records: Iterable[EvidenceRecord],
) -> dict[str, list[EvidenceRecord]]:
    grouped: dict[str, list[EvidenceRecord]] = {}
    for record in records:
        if is_generic_location(record.location):
            continue
        location = record.location.strip()
        grouped.setdefault(location, []).append(record)

    for location_records in grouped.values():
        location_records.sort(key=lambda item: item.confidence, reverse=True)
    return dict(
        sorted(
            grouped.items(),
            key=lambda item: max(record.confidence for record in item[1]),
            reverse=True,
        )
    )


def build_location_options(records: Iterable[EvidenceRecord]) -> list[LocationOption]:
    options: list[LocationOption] = []
    for index, (location, location_records) in enumerate(
        group_records_by_location(records).items(), start=1
    ):
        options.append(
            LocationOption(
                index=index,
                location=location,
                record_count=len(location_records),
                top_confidence=max(record.confidence for record in location_records),
                evidence_types=sorted(
                    {record.evidence_type for record in location_records}
                ),
                sources=sorted({record.source for record in location_records}),
            )
        )
    return options


def select_records_for_locations(
    records: Iterable[EvidenceRecord], selected_locations: Iterable[str]
) -> list[EvidenceRecord]:
    selected = {location.strip().lower() for location in selected_locations}
    return [
        record
        for record in records
        if (record.location or "Unknown location").strip().lower() in selected
    ]


def generate_location_analysis_report(
    company: str,
    selected_records: Iterable[EvidenceRecord],
) -> dict[str, object]:
    records = sorted(selected_records, key=lambda item: item.confidence, reverse=True)
    locations = sorted({record.location or "Unknown location" for record in records})
    evidence_types = sorted({record.evidence_type for record in records})
    sources = sorted({record.source for record in records})
    top_confidence = max((record.confidence for record in records), default=0.0)

    if not records:
        return {
            "company": company,
            "selected_locations": [],
            "summary": "No location evidence was selected for analysis.",
            "evidence_count": 0,
            "top_confidence": 0.0,
            "evidence_types": [],
            "sources": [],
            "findings": [],
        }

    findings = [
        {
            "location": record.location,
            "activity_type": record.activity_type,
            "biodiversity_signal": record.biodiversity_signal,
            "evidence_type": record.evidence_type,
            "confidence": record.confidence,
            "source": record.source,
            "source_url": record.source_url,
            "source_date": record.source_date,
        }
        for record in records
    ]

    return {
        "company": company,
        "selected_locations": locations,
        "summary": (
            f"{company} has {len(records)} extracted biodiversity evidence "
            f"record(s) across {', '.join(locations)}. The strongest "
            f"pre-validation confidence is {top_confidence:.2f}."
        ),
        "evidence_count": len(records),
        "top_confidence": top_confidence,
        "evidence_types": evidence_types,
        "sources": sources,
        "findings": findings,
    }


def _clamp_float(value: object, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return minimum
    return max(minimum, min(number, maximum))


def example_output() -> dict[str, object]:
    return {
        "company": "BHP",
        "location": "Pilbara WA",
        "evidence_type": "biodiversity risk",
        "source_type": "news",
        "confidence": 0.74,
        "generated_on": date.today().isoformat(),
    }
