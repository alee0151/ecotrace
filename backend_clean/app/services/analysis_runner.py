"""
Smoke-test configured Seeco APIs with a real company query.

This script prints API status, result counts, and a few titles only. It does not
print API keys or full article text.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ..pipelines.ecotrace_pipeline import (
    ArticleMetadata,
    ExtractionInput,
    SimpleArticleTextRetriever,
    UploadedReportTextReader,
    australia_relevance_score,
    build_location_options,
    combine_confidence,
    create_llm_extractor_from_env,
    evidence_context,
    foreign_relevance_score,
    is_australia_linked,
    is_countrywide_australia_location,
    load_env_file,
    quality_gate_record,
    source_weight,
)


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


CONFIG = load_config()
RUN_CONFIG = config_value(CONFIG, "run")
DEFAULT_REPORTS_DIR = "reports"
SUPPORTED_REPORT_EXTENSIONS = {
    ".pdf",
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".json",
    ".html",
    ".htm",
}
BIODIVERSITY_RANKING_TERMS = config_tuple(
    CONFIG, "run", "ranking_terms", "biodiversity"
)
ENVIRONMENT_RANKING_TERMS = BIODIVERSITY_RANKING_TERMS + config_tuple(
    CONFIG, "run", "ranking_terms", "environment_extra"
)
DEFAULT_QUERY_TOPICS = config_tuple(CONFIG, "run", "query_topics", "default")
FOOD_RETAIL_QUERY_TOPICS = config_tuple(CONFIG, "run", "query_topics", "food_retail")
AGRIBUSINESS_QUERY_TOPICS = config_tuple(CONFIG, "run", "query_topics", "agribusiness")
MINING_QUERY_TOPICS = config_tuple(CONFIG, "run", "query_topics", "mining")
FOOD_RETAIL_COMPANY_HINTS = config_tuple(CONFIG, "run", "company_hints", "food_retail")
AGRIBUSINESS_COMPANY_HINTS = config_tuple(
    CONFIG, "run", "company_hints", "agribusiness"
)
MINING_COMPANY_HINTS = config_tuple(CONFIG, "run", "company_hints", "mining")
LEGAL_NAME_STOPWORDS = config_set(CONFIG, "run", "legal_name", "stopwords")
COMPANY_ACRONYM_TOKENS = config_set(CONFIG, "run", "legal_name", "acronym_tokens")
HIGH_VALUE_SOURCE_HINTS = config_tuple(
    CONFIG, "run", "source_quality", "high_value_source_hints"
)
HIGH_VALUE_DOMAIN_HINTS = config_tuple(
    CONFIG, "run", "source_quality", "high_value_domain_hints"
)
LOW_VALUE_SOURCE_HINTS = config_tuple(
    CONFIG, "run", "source_quality", "low_value_source_hints"
)
LOW_VALUE_DOMAIN_HINTS = config_tuple(
    CONFIG, "run", "source_quality", "low_value_domain_hints"
)
LOW_VALUE_ARTICLE_TERMS = config_tuple(
    CONFIG, "run", "source_quality", "low_value_article_terms"
)


def main() -> None:
    configure_stdout()
    parser = argparse.ArgumentParser()
    parser.add_argument("--company")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--fetch-full-text", dest="fetch_full_text", action="store_true")
    parser.add_argument("--no-fetch-full-text", dest="fetch_full_text", action="store_false")
    parser.set_defaults(fetch_full_text=True)
    parser.add_argument("--australia-only", action="store_true")
    parser.add_argument("--max-llm-results", type=int, default=10)
    parser.add_argument(
        "--report-file",
        action="append",
        default=[],
        help=(
            "Path to an uploaded sustainability or annual report. Can be used "
            "more than once. If omitted, local files in --reports-dir are used."
        ),
    )
    parser.add_argument(
        "--reports-dir",
        default=DEFAULT_REPORTS_DIR,
        help="Folder containing local uploaded reports to process automatically.",
    )
    parser.add_argument(
        "--max-report-chars",
        type=int,
        default=3000,
        help="Maximum report text characters to send to the LLM per chunk.",
    )
    parser.add_argument(
        "--max-report-chunks",
        type=int,
        default=5,
        help="Maximum focused report chunks to verify per uploaded report.",
    )
    parser.add_argument(
        "--skip-news",
        action="store_true",
        help="Only process uploaded report files; do not call news/search APIs.",
    )
    parser.add_argument("--include-unknown", action="store_true")
    parser.add_argument("--show-candidates", action="store_true")
    args = parser.parse_args()

    load_env_file()
    company = args.company.strip() if args.company else prompt_company_name()
    search_company = company_search_name(company)
    queries = build_company_search_queries(company)
    report_paths = resolve_report_paths(args.report_file, args.reports_dir)

    print(f"Company: {company}")
    if search_company != company:
        print(f"Search name: {search_company}")
    print("Queries:")
    for query in queries:
        print(f"  - {query}")
    print()

    all_records = []
    if not args.skip_news:
        sample_articles = []
        for query in queries:
            print(f"=== Query: {query} ===")
            for test_provider in (
                test_serpapi,
                test_newsapi,
                test_guardian,
                test_nyt,
                test_freenewsapi,
                test_newsdata,
                test_mediastack,
                test_webz,
            ):
                sample_articles.extend(test_provider(query, args.limit))
            print()

        sample_articles = dedupe_article_metadata(sample_articles)
        if args.show_candidates:
            print()
            print_ranked_article_candidates(
                company, sample_articles, args.australia_only
            )

        candidate_articles = relevant_llm_candidates(
            company, sample_articles, args.australia_only
        )
        candidate_articles = [
            article
            for article in candidate_articles
            if article_candidate_score(company, article, args.australia_only) >= 80
        ][: args.max_llm_results]

        print()
        if args.max_llm_results <= 0:
            print("[LLM] skipped: --max-llm-results is 0")
        elif candidate_articles:
            all_records.extend(
                test_openrouter_many(
                    company,
                    candidate_articles,
                    args.fetch_full_text,
                    args.australia_only,
                )
            )
        else:
            print("[LLM] skipped: no article metadata returned by news APIs")
    else:
        print("[News APIs] skipped: --skip-news enabled")

    if report_paths:
        print()
        all_records.extend(
            test_uploaded_reports(
                company,
                report_paths,
                args.max_report_chars,
                args.max_report_chunks,
                args.australia_only,
            )
        )
    else:
        print(f"[Uploaded reports] skipped: no supported reports found in {args.reports_dir}")

    if all_records:
        present_ranked_locations(all_records, include_unknown=args.include_unknown)


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")


def prompt_company_name() -> str:
    while True:
        company = input("Enter company name: ").strip()
        if company:
            return company
        print("Company name is required.")


def resolve_report_paths(
    explicit_paths: list[str] | None,
    reports_dir: str = DEFAULT_REPORTS_DIR,
) -> list[str]:
    if explicit_paths:
        return dedupe_paths(explicit_paths)

    if not reports_dir or not os.path.isdir(reports_dir):
        return []

    report_paths = []
    for filename in sorted(os.listdir(reports_dir)):
        path = os.path.join(reports_dir, filename)
        if not os.path.isfile(path):
            continue
        extension = os.path.splitext(filename)[1].lower()
        if extension in SUPPORTED_REPORT_EXTENSIONS:
            report_paths.append(path)
    return dedupe_paths(report_paths)


def dedupe_paths(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    output = []
    for path in paths:
        normalized = os.path.abspath(path).lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        output.append(path)
    return output


def build_company_search_queries(company: str) -> list[str]:
    company = company_search_name(company)
    lowered = company.lower()
    if any(hint in lowered for hint in MINING_COMPANY_HINTS):
        topics = MINING_QUERY_TOPICS
    elif any(hint in lowered for hint in AGRIBUSINESS_COMPANY_HINTS):
        topics = AGRIBUSINESS_QUERY_TOPICS
    elif any(hint in lowered for hint in FOOD_RETAIL_COMPANY_HINTS):
        topics = FOOD_RETAIL_QUERY_TOPICS
    else:
        topics = DEFAULT_QUERY_TOPICS
    return [f"{company} {topic}" for topic in topics]


def company_search_name(company: str) -> str:
    normalized = " ".join(company.replace("&", " and ").split())
    tokens = [
        token.strip(".,()[]{}").lower()
        for token in normalized.split()
        if token.strip(".,()[]{}")
    ]
    useful_tokens = [
        token for token in tokens if token not in LEGAL_NAME_STOPWORDS
    ]
    if useful_tokens:
        tokens = useful_tokens
    return " ".join(format_company_token(token) for token in tokens)


def company_match_tokens(company: str) -> list[str]:
    search_name = company_search_name(company).lower()
    return [token for token in search_name.split() if token]


def token_in_text(token: str, text: str) -> bool:
    if not token:
        return False
    return re.search(rf"\b{re.escape(token.lower())}\b", text.lower()) is not None


def company_match_aliases(company: str) -> list[list[str]]:
    tokens = company_match_tokens(company)
    aliases: list[list[str]] = []
    if tokens:
        aliases.append(tokens)

    strong_tokens = [
        token
        for token in tokens
        if len(token) >= 5 or token.lower() in COMPANY_ACRONYM_TOKENS
    ]
    for token in strong_tokens:
        aliases.append([token])

    seen: set[tuple[str, ...]] = set()
    unique_aliases: list[list[str]] = []
    for alias in aliases:
        key = tuple(alias)
        if key not in seen:
            unique_aliases.append(alias)
            seen.add(key)
    return unique_aliases


def format_company_token(token: str) -> str:
    if token in COMPANY_ACRONYM_TOKENS:
        return token.upper()
    return token.capitalize()


def test_serpapi(query: str, limit: int) -> list[ArticleMetadata]:
    key = os.getenv("SERPAPI_KEY")
    if not key:
        skipped("SerpApi", "SERPAPI_KEY missing")
        return []

    url = build_url(
        "https://serpapi.com/search.json",
        {"engine": "google_news", "q": query, "api_key": key},
    )
    data = get_json("SerpApi", url)
    if not data:
        return []

    results = data.get("news_results", [])
    print_results("SerpApi", results, limit, title_key="title", url_key="link")

    return [
        ArticleMetadata(
            title=str(item.get("title") or ""),
            snippet=str(item.get("snippet") or ""),
            source=str((item.get("source") or {}).get("name") or "SerpApi"),
            published_date=str(item.get("date") or ""),
            url=str(item.get("link") or ""),
        )
        for item in ranked_metadata_items(
            query, results, title_key="title", snippet_key="snippet", url_key="link"
        )[:limit]
    ]


def test_newsapi(query: str, limit: int) -> list[ArticleMetadata]:
    key = os.getenv("NEWSAPI_KEY")
    if not key:
        skipped("NewsAPI", "NEWSAPI_KEY missing")
        return []

    url = build_url(
        "https://newsapi.org/v2/everything",
        {
            "q": query,
            "language": "en",
            "sortBy": "relevancy",
            "pageSize": str(limit),
            "apiKey": key,
        },
    )
    data = get_json("NewsAPI", url)
    if not data:
        return []

    articles = data.get("articles", [])
    print_results("NewsAPI", articles, limit, title_key="title", url_key="url")

    return [
        ArticleMetadata(
            title=str(item.get("title") or ""),
            snippet=str(item.get("description") or ""),
            source=str((item.get("source") or {}).get("name") or "NewsAPI"),
            published_date=str(item.get("publishedAt") or ""),
            url=str(item.get("url") or ""),
        )
        for item in ranked_metadata_items(
            query, articles, title_key="title", snippet_key="description", url_key="url"
        )[:limit]
    ]


def test_guardian(query: str, limit: int) -> list[ArticleMetadata]:
    key = os.getenv("GUARDIAN_API_KEY")
    if not key:
        skipped("Guardian", "GUARDIAN_API_KEY missing")
        return []

    url = build_url(
        "https://content.guardianapis.com/search",
        {"q": query, "page-size": str(limit), "api-key": key},
    )
    data = get_json("Guardian", url)
    if not data:
        return []

    results = ((data.get("response") or {}).get("results")) or []
    print_results("Guardian", results, limit, title_key="webTitle", url_key="webUrl")

    return [
        ArticleMetadata(
            title=str(item.get("webTitle") or ""),
            snippet="",
            source="Guardian",
            published_date=str(item.get("webPublicationDate") or ""),
            url=str(item.get("webUrl") or ""),
        )
        for item in ranked_metadata_items(
            query, results, title_key="webTitle", snippet_key=None, url_key="webUrl"
        )[:limit]
    ]


def test_nyt(query: str, limit: int) -> list[ArticleMetadata]:
    key = os.getenv("NYT_API_KEY")
    if not key:
        skipped("NYT", "NYT_API_KEY missing")
        return []

    url = build_url(
        "https://api.nytimes.com/svc/search/v2/articlesearch.json",
        {"q": query, "api-key": key},
    )
    data = get_json("NYT", url)
    if not data:
        return []

    docs = (((data.get("response") or {}).get("docs")) or [])[:limit]
    print_results("NYT", docs, limit, title_key=("headline", "main"), url_key="web_url")

    return [
        ArticleMetadata(
            title=str((item.get("headline") or {}).get("main") or ""),
            snippet=str(item.get("snippet") or ""),
            source="NYT",
            published_date=str(item.get("pub_date") or ""),
            url=str(item.get("web_url") or ""),
        )
        for item in ranked_metadata_items(
            query,
            docs,
            title_key=("headline", "main"),
            snippet_key="snippet",
            url_key="web_url",
        )[:limit]
    ]


def test_freenewsapi(query: str, limit: int) -> list[ArticleMetadata]:
    key = getenv_any("FREENEWSAPI_KEY", "FREENEWS_API_KEY")
    if not key:
        skipped("FreeNewsApi", "FREENEWSAPI_KEY/FREENEWS_API_KEY missing")
        return []

    url = build_url(
        "https://api.freenewsapi.io/v1/news",
        {
            "language": "en",
            "country": "au",
            "q": query,
            "limit": str(limit),
        },
    )
    data = get_json("FreeNewsApi", url, headers={"X-Api-Key": key})
    if not data:
        return []

    articles = _first_list(data, "data", "articles", "results")
    print_results("FreeNewsApi", articles, limit, title_key="title", url_key="uuid")

    output = []
    for item in ranked_metadata_items(
        query, articles, title_key="title", snippet_key="title", url_key="uuid"
    )[:limit]:
        details = get_freenewsapi_details(str(item.get("uuid") or ""), key)
        full_item = details or item
        output.append(
            ArticleMetadata(
                title=str(full_item.get("title") or item.get("title") or ""),
                snippet=str(
                    full_item.get("subtitle")
                    or full_item.get("description")
                    or full_item.get("summary")
                    or full_item.get("body")
                    or full_item.get("content")
                    or ""
                )[:500],
                source=str(
                    full_item.get("publisher")
                    or item.get("publisher")
                    or full_item.get("source")
                    or "FreeNewsApi"
                ),
                published_date=str(
                    full_item.get("published_at")
                    or item.get("published_at")
                    or full_item.get("publishedAt")
                    or ""
                ),
                url=str(
                    full_item.get("original_url")
                    or full_item.get("url")
                    or full_item.get("link")
                    or ""
                ),
            )
        )
    return output


def get_freenewsapi_details(uuid: str, key: str) -> dict[str, object] | None:
    if not uuid:
        return None

    url = build_url("https://api.freenewsapi.io/v1/details", {"uuid": uuid})
    data = get_json("FreeNewsApi details", url, headers={"X-Api-Key": key}, quiet=True)
    if not data:
        return None
    details = data.get("data")
    return details if isinstance(details, dict) else None


def test_newsdata(query: str, limit: int) -> list[ArticleMetadata]:
    key = getenv_any("NEWSDATA_API_KEY", "NEWSDATA_IO_API_KEY")
    if not key:
        skipped("NewsData.io", "NEWSDATA_API_KEY/NEWSDATA_IO_API_KEY missing")
        return []

    url = build_url(
        "https://newsdata.io/api/1/latest",
        {
            "apikey": key,
            "q": query,
            "language": "en",
            "country": "au",
            "size": str(min(limit, 10)),
        },
    )
    data = get_json("NewsData.io", url)
    if not data:
        return []

    articles = _first_list(data, "results", "data", "articles")
    print_results("NewsData.io", articles, limit, title_key="title", url_key="link")

    return [
        ArticleMetadata(
            title=str(item.get("title") or ""),
            snippet=str(
                item.get("description")
                or item.get("content")
                or item.get("summary")
                or ""
            )[:500],
            source=str(
                item.get("source_name")
                or item.get("source_id")
                or item.get("source")
                or "NewsData.io"
            ),
            published_date=str(item.get("pubDate") or item.get("published_at") or ""),
            url=str(item.get("link") or item.get("url") or ""),
        )
        for item in ranked_metadata_items(
            query, articles, title_key="title", snippet_key="description", url_key="link"
        )[:limit]
    ]


def test_mediastack(query: str, limit: int) -> list[ArticleMetadata]:
    key = os.getenv("MEDIASTACK_API_KEY")
    if not key:
        skipped("Mediastack", "MEDIASTACK_API_KEY missing")
        return []

    url = build_url(
        "https://api.mediastack.com/v1/news",
        {
            "access_key": key,
            "keywords": query,
            "countries": "au",
            "languages": "en",
            "sort": "published_desc",
            "limit": str(min(limit, 100)),
        },
    )
    data = get_json("Mediastack", url)
    if not data:
        return []

    articles = _first_list(data, "data", "articles", "results")
    print_results("Mediastack", articles, limit, title_key="title", url_key="url")

    return [
        ArticleMetadata(
            title=str(item.get("title") or ""),
            snippet=str(item.get("description") or item.get("content") or "")[:500],
            source=str(item.get("source") or "Mediastack"),
            published_date=str(item.get("published_at") or item.get("publishedAt") or ""),
            url=str(item.get("url") or ""),
        )
        for item in ranked_metadata_items(
            query,
            articles,
            title_key="title",
            snippet_key="description",
            url_key="url",
        )[:limit]
    ]


def test_webz(query: str, limit: int) -> list[ArticleMetadata]:
    key = os.getenv("WEBZ_API_KEY")
    if not key:
        skipped("Webz.io", "WEBZ_API_KEY missing")
        return []

    url = build_url(
        "https://api.webz.io/newsApiLite",
        {"q": query, "token": key, "size": str(limit)},
    )
    data = get_json("Webz.io", url)
    if not data:
        return []

    posts = data.get("posts", [])
    print_results("Webz.io", posts, limit, title_key="title", url_key="url")

    return [
        ArticleMetadata(
            title=str(item.get("title") or ""),
            snippet=str(item.get("text") or "")[:240],
            source="Webz.io",
            published_date=str(item.get("published") or ""),
            url=str(item.get("url") or ""),
        )
        for item in ranked_metadata_items(
            query, posts, title_key="title", snippet_key="text", url_key="url"
        )[:limit]
    ]


def test_uploaded_reports(
    company: str,
    report_paths: list[str],
    max_report_chars: int,
    max_report_chunks: int = 3,
    australia_only: bool = False,
):
    print("[Uploaded reports] verifying biodiversity risk with LLM")
    records = []
    reader = UploadedReportTextReader(max_chars=max_report_chars)
    source_count = max(1, len(report_paths))

    for index, path in enumerate(report_paths, start=1):
        print(f"[Report {index}] {path}")
        try:
            report_excerpts = reader.scan_evidence(
                path, max_excerpts=max_report_chunks
            )
        except Exception as error:
            print(f"[Report {index}] skipped: {type(error).__name__}: {error}")
            continue

        useful_excerpts = [excerpt for excerpt in report_excerpts if excerpt.score > 0]
        print(f"[Report {index}] local evidence candidates: {len(useful_excerpts)}")
        for excerpt_index, excerpt in enumerate(useful_excerpts, start=1):
            preview = " ".join(excerpt.text.split())
            if len(preview) > 220:
                preview = f"{preview[:217]}..."
            terms = ", ".join(excerpt.matched_terms[:5]) or "none"
            print(
                f"  - page {excerpt.page_number}, score {excerpt.score}, "
                f"terms: {terms}"
            )
            print(f"    {preview}")

        if not useful_excerpts:
            print(f"[Report {index}] skipped LLM: no local biodiversity evidence found")
            continue

        for chunk_index, excerpt in enumerate(useful_excerpts, start=1):
            report_text = excerpt.text
            article = report_article_metadata(
                path,
                report_text,
                chunk_index,
                page_number=excerpt.page_number,
            )
            print(
                f"[Report {index}.{chunk_index}] chars sent to LLM: "
                f"{len(report_text)}"
            )
            record = extract_one_record(
                company=company,
                article=article,
                full_text=report_text,
                australia_only=australia_only,
                source_count=source_count,
            )
            if record:
                records.append(record)

    return records


def report_article_metadata(
    path: str,
    report_text: str,
    chunk_index: int | None = None,
    page_number: int | None = None,
) -> ArticleMetadata:
    filename = os.path.basename(path)
    chunk_suffix = f" chunk {chunk_index}" if chunk_index else ""
    page_suffix = f", page {page_number}" if page_number else ""
    return ArticleMetadata(
        title=(
            f"Uploaded sustainability or annual report{chunk_suffix}{page_suffix}: "
            f"{filename}"
        ),
        snippet=report_text[:240],
        source=filename,
        published_date=None,
        url=os.path.abspath(path),
        source_type="report",
    )


def test_openrouter_many(
    company: str,
    articles: list[ArticleMetadata],
    fetch_full_text: bool = False,
    australia_only: bool = False,
):
    records = []
    source_count = max(1, len({article.source for article in articles}))
    for index, article in enumerate(articles, start=1):
        print(f"[Sample {index}] {article.title}")
        print(f"[Sample {index}] {article.url}")
        record = extract_one_record(
            company, article, fetch_full_text, australia_only, source_count
        )
        if record:
            records.append(record)
    return records


def extract_one_record(
    company: str,
    article: ArticleMetadata,
    fetch_full_text: bool = False,
    australia_only: bool = False,
    source_count: int = 1,
    full_text: str | None = None,
):
    if not (os.getenv("OPENROUTER_API_KEY") or os.getenv("NVIDIA_API_KEY")):
        print("[LLM] skipped: OPENROUTER_API_KEY/NVIDIA_API_KEY missing")
        return None

    provider = os.getenv("LLM_PROVIDER", "openrouter").strip() or "openrouter"
    print(f"[LLM:{provider}] testing structured extraction")
    if fetch_full_text:
        print("[Article retrieval] fetching page text for LLM extraction")
        full_text = SimpleArticleTextRetriever().fetch_text(article.url)
        status = "OK" if full_text else "unavailable"
        length = len(full_text) if full_text else 0
        print(f"[Article retrieval] {status}, chars sent to LLM: {length}")
        if not full_text:
            print("[LLM] skipped: article text unavailable")
            return None

    context_text = ""
    try:
        extractor = create_llm_extractor_from_env()
        record = extractor.extract(
            ExtractionInput(company=company, article=article, full_text=full_text)
        )
        context_text = evidence_context(article, full_text)
        quality_gate_record(record, context_text)
        context_is_australia_linked = australia_relevance_score(context_text) > 0
        context_is_foreign_linked = foreign_relevance_score(context_text) > 0
        context_supports_countrywide_australia = (
            context_is_australia_linked and not context_is_foreign_linked
        )
        if context_supports_countrywide_australia and not record.location:
            record.location = "Australia-wide"
        australia_bonus = (
            0.04
            if is_australia_linked(record) or context_supports_countrywide_australia
            else 0.0
        )
        record.confidence = combine_confidence(
            llm_confidence=record.llm_confidence,
            source_count=source_count,
            credibility=source_weight(article.source),
            full_text_used=bool(full_text),
        )
        record.confidence = round(min(record.confidence + australia_bonus, 0.90), 2)
    except Exception as error:
        print(f"[LLM:{provider}] ERROR: {type(error).__name__}: {error}")
        return None

    print(f"[LLM:{provider}] OK")
    if (
        australia_only
        and is_countrywide_australia_location(record.location)
        and foreign_relevance_score(context_text) > 0
    ):
        print("[Australia filter] excluded: countrywide Australia fallback conflicts with overseas source context")
        return None

    if (
        australia_only
        and not is_australia_linked(record)
        and australia_relevance_score(context_text) == 0
    ):
        print("[Australia filter] excluded: extracted evidence and source text are not Australia-linked")
        return None

    print_record(record)
    return record


def print_record(record) -> None:
    print(
        json.dumps(
            {
                "location": record.location,
                "activity_type": record.activity_type,
                "biodiversity_signal": record.biodiversity_signal,
                "evidence_type": record.evidence_type,
                "llm_confidence": record.llm_confidence,
            },
            indent=2,
        )
    )


def present_ranked_locations(records, include_unknown: bool = False) -> None:
    if not include_unknown:
        records = [
            record for record in records if record.evidence_type != "unknown"
        ]

    options = build_location_options(records)
    if not options:
        print("[Locations] no location options available")
        return

    print()
    print("[Locations] ranked by confidence")
    for option in options:
        print(
            f"  {option.index}. {option.location} "
            f"({option.record_count} record(s), top confidence {option.top_confidence:.2f})"
        )


def print_ranked_article_candidates(
    company: str, articles: list[ArticleMetadata], australia_only: bool
) -> None:
    ranked = ranked_llm_samples(company, articles, australia_only)
    print(f"[Candidates] deduped article candidates: {len(ranked)}")
    for index, article in enumerate(ranked, start=1):
        score = article_candidate_score(company, article, australia_only)
        quality = article_source_quality_score(company, article)
        llm_status = "yes" if article_is_llm_worthy(company, article) else "no"
        snippet = " ".join(article.snippet.split())
        if len(snippet) > 180:
            snippet = f"{snippet[:177]}..."
        print(
            f"  {index}. score={score} quality={quality} llm={llm_status} | "
            f"{article.source} | {article.published_date}"
        )
        print(f"     title: {article.title}")
        print(f"     url: {article.url}")
        if snippet:
            print(f"     snippet: {snippet}")


def build_url(base_url: str, params: dict[str, str]) -> str:
    return f"{base_url}?{urllib.parse.urlencode(params)}"


def getenv_any(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def get_json(
    label: str,
    url: str,
    headers: dict[str, str] | None = None,
    quiet: bool = False,
) -> dict[str, object] | None:
    request_headers = {"User-Agent": "Seeco/1.0"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        message = error.read().decode("utf-8", errors="replace")[:300]
        if not quiet:
            print(f"[{label}] HTTP {error.code}: {message}")
        return None
    except Exception as error:
        if not quiet:
            print(f"[{label}] ERROR: {type(error).__name__}: {error}")
        return None

    if not quiet:
        print(f"[{label}] OK")
    return data


def print_results(
    label: str,
    items: list[dict[str, object]],
    limit: int,
    *,
    title_key: str | tuple[str, str],
    url_key: str,
) -> None:
    print(f"[{label}] results: {len(items)}")
    for index, item in enumerate(items[:limit], start=1):
        title = nested_value(item, title_key)
        url = nested_value(item, url_key)
        print(f"  {index}. {title}")
        if url:
            print(f"     {url}")


def nested_value(item: dict[str, object], key: str | tuple[str, str]) -> str:
    if isinstance(key, tuple):
        parent = item.get(key[0]) or {}
        if isinstance(parent, dict):
            return str(parent.get(key[1]) or "")
        return ""
    return str(item.get(key) or "")


def _first_list(data: dict[str, object], *keys: str) -> list[dict[str, object]]:
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return value
    return []


def first_item(items: list[dict[str, object]]) -> dict[str, object] | None:
    return items[0] if items else None


def dedupe_article_metadata(articles: list[ArticleMetadata]) -> list[ArticleMetadata]:
    seen = set()
    output = []
    for article in articles:
        keys = {
            (article.url or "").strip().lower(),
            normalized_article_title(article.title),
        }
        keys.discard("")
        if keys and not seen.intersection(keys):
            seen.update(keys)
            output.append(article)
    return output


def normalized_article_title(title: str) -> str:
    return " ".join(title.strip().lower().split())


def best_metadata_item(
    query: str,
    items: list[dict[str, object]],
    *,
    title_key: str | tuple[str, str],
    snippet_key: str | None,
    url_key: str,
) -> dict[str, object] | None:
    ranked = ranked_metadata_items(
        query,
        items,
        title_key=title_key,
        snippet_key=snippet_key,
        url_key=url_key,
    )
    return ranked[0] if ranked else None


def ranked_metadata_items(
    query: str,
    items: list[dict[str, object]],
    *,
    title_key: str | tuple[str, str],
    snippet_key: str | None,
    url_key: str,
) -> list[dict[str, object]]:
    if not items:
        return []
    company = company_from_search_query(query)
    company_tokens = company_match_tokens(company)

    def score(item: dict[str, object]) -> int:
        text = f"{nested_value(item, title_key)} {nested_value(item, url_key)}"
        if snippet_key:
            text = f"{text} {nested_value(item, snippet_key)}"
        lowered = text.lower()
        company_score = sum(1000 for token in company_tokens if token in lowered)
        biodiversity_score = sum(
            250 for token in BIODIVERSITY_RANKING_TERMS if token in lowered
        )
        return (
            company_score
            + biodiversity_score
            + australia_relevance_score(text) * 100
            + len(text)
        )

    return sorted(items, key=score, reverse=True)


def company_from_search_query(query: str) -> str:
    normalized = " ".join(query.split())
    lowered = normalized.lower()
    topic_markers = sorted(
        {
            term
            for term in ENVIRONMENT_RANKING_TERMS
            if " " not in term and len(term) > 3
        }
        | {
            "biodiversity",
            "deforestation",
            "sustainable",
            "sustainability",
            "nature",
            "conservation",
            "rehabilitation",
            "epbc",
            "habitat",
            "supply chain",
            "beef",
            "land clearing",
        },
        key=len,
        reverse=True,
    )
    marker_positions = [
        lowered.find(f" {marker}")
        for marker in topic_markers
        if lowered.find(f" {marker}") > 0
    ]
    if not marker_positions:
        return company_search_name(normalized)
    return company_search_name(normalized[: min(marker_positions)].strip())


def best_llm_sample(
    company: str, articles: list[ArticleMetadata], australia_only: bool = False
) -> ArticleMetadata | None:
    ranked = ranked_llm_samples(company, articles, australia_only)
    return ranked[0] if ranked else None


def ranked_llm_samples(
    company: str, articles: list[ArticleMetadata], australia_only: bool = False
) -> list[ArticleMetadata]:
    if not articles:
        return []

    return sorted(
        articles,
        key=lambda article: article_candidate_score(company, article, australia_only),
        reverse=True,
    )


def relevant_llm_candidates(
    company: str, articles: list[ArticleMetadata], australia_only: bool = False
) -> list[ArticleMetadata]:
    ranked = ranked_llm_samples(company, articles, australia_only)
    company_matched = [
        article for article in ranked if article_mentions_company(company, article)
    ]
    if company_matched:
        ranked = company_matched

    environment_matched = [
        article for article in ranked if article_has_environment_signal(article)
    ]
    if environment_matched:
        ranked = environment_matched

    return [
        article for article in ranked if article_is_llm_worthy(company, article)
    ]


def article_candidate_score(
    company: str, article: ArticleMetadata, australia_only: bool = False
) -> int:
    company_tokens = company_match_tokens(company)

    text = f"{article.title} {article.snippet} {article.url}".lower()
    company_bonus = sum(40 for token in company_tokens if token_in_text(token, text))
    company_url_bonus = sum(
        50 for token in company_tokens if token_in_text(token, article.url)
    )
    australia_bonus = australia_relevance_score(text) * 30
    environment_bonus = sum(
        80 for token in ENVIRONMENT_RANKING_TERMS if token in text
    )
    location_bonus = australia_relevance_score(text) * 30
    regulatory_bonus = 120 if any(
        token in text for token in ("epbc", "approval", "strategic assessment", "offset")
    ) else 0
    snippet_bonus = min(len(article.snippet.strip()), 120)
    score_value = (
        company_url_bonus
        + company_bonus
        + australia_bonus
        + environment_bonus
        + location_bonus
        + regulatory_bonus
        + article_source_quality_score(company, article)
        + snippet_bonus
    )
    strong_company_environment_match = company_bonus > 0 and environment_bonus >= 80
    if (
        australia_only
        and australia_relevance_score(text) == 0
        and not strong_company_environment_match
    ):
        score_value -= 500
    return score_value


def article_is_llm_worthy(company: str, article: ArticleMetadata) -> bool:
    quality_score = article_source_quality_score(company, article)
    has_company = article_mentions_company(company, article)
    has_environment = article_has_environment_signal(article)
    return quality_score >= 60 and has_company and has_environment


def article_source_quality_score(company: str, article: ArticleMetadata) -> int:
    text = f"{article.title} {article.snippet} {article.url}".lower()
    source = article.source.lower()
    domain = urllib.parse.urlparse(article.url).netloc.lower()
    score = 45

    if any(hint in source for hint in HIGH_VALUE_SOURCE_HINTS):
        score += 25
    if any(hint in domain for hint in HIGH_VALUE_DOMAIN_HINTS):
        score += 25
    if any(hint in source for hint in LOW_VALUE_SOURCE_HINTS):
        score -= 25
    if any(hint in domain for hint in LOW_VALUE_DOMAIN_HINTS):
        score -= 25
    if article_mentions_company(company, article):
        score += 15
    if article_has_environment_signal(article):
        score += 15
    if australia_relevance_score(text) > 0:
        score += 10
    if len(article.snippet.strip()) >= 80:
        score += 5
    if any(term in text for term in LOW_VALUE_ARTICLE_TERMS):
        score -= 30
    if looks_like_generic_article(article):
        score -= 20

    return max(0, min(score, 100))


def looks_like_generic_article(article: ArticleMetadata) -> bool:
    text = f"{article.title} {article.snippet} {article.url}".lower()
    company_environment = article_has_environment_signal(article)
    if not company_environment:
        return True
    if "ng-interactive" in text or "/live/" in text:
        return True
    if article.source.lower() in {"nyt", "new york times"} and not article.snippet:
        return True
    return False


def article_mentions_company(company: str, article: ArticleMetadata) -> bool:
    text = f"{article.title} {article.snippet} {article.url}".lower()
    return any(
        all(token_in_text(token, text) for token in alias)
        for alias in company_match_aliases(company)
    )


def article_has_environment_signal(article: ArticleMetadata) -> bool:
    text = f"{article.title} {article.snippet} {article.url}".lower()
    return any(token in text for token in ENVIRONMENT_RANKING_TERMS)


def skipped(label: str, reason: str) -> None:
    print(f"[{label}] skipped: {reason}")
    return None


if __name__ == "__main__":
    main()
