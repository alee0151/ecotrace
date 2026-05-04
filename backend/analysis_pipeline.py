"""
Company analysis helpers for EcoTrace.

This module adapts the news, report, and LLM evidence pipeline without folding
that logic back into main.py.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, UploadFile

try:
    from .abn_pipeline import clean_abn, is_abn, search_company_name_with_abr, verify_abn_with_abr
    from .run_ecotrace import (
        article_candidate_score,
        build_company_search_queries,
        company_search_name,
        dedupe_article_metadata,
        relevant_llm_candidates,
        resolve_report_paths,
        test_freenewsapi,
        test_guardian,
        test_newsapi,
        test_newsdata,
        test_nyt,
        test_openrouter_many,
        test_serpapi,
        test_uploaded_reports,
        test_webz,
    )
except ImportError:
    from abn_pipeline import clean_abn, is_abn, search_company_name_with_abr, verify_abn_with_abr
    from run_ecotrace import (
        article_candidate_score,
        build_company_search_queries,
        company_search_name,
        dedupe_article_metadata,
        relevant_llm_candidates,
        resolve_report_paths,
        test_freenewsapi,
        test_guardian,
        test_newsapi,
        test_newsdata,
        test_nyt,
        test_openrouter_many,
        test_serpapi,
        test_uploaded_reports,
        test_webz,
    )


REPO_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = REPO_ROOT / "reports"


def max_report_upload_bytes() -> int:
    try:
        limit_mb = int(os.getenv("MAX_REPORT_UPLOAD_MB", os.getenv("MAX_UPLOAD_MB", "10")))
    except ValueError:
        limit_mb = 10
    return limit_mb * 1024 * 1024

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

KNOWN_COMPANY_ABNS = {
    "bhp": "49004028077",
    "bhp group": "49004028077",
    "bhp group limited": "49004028077",
    "coles": "11004089936",
    "coles group": "11004089936",
    "coles group limited": "11004089936",
    "woolworths": "88000014675",
    "woolworths group": "88000014675",
    "woolworths group limited": "88000014675",
    "bega": "81008358503",
    "bega cheese": "81008358503",
}


def safe_report_filename(filename: str) -> str:
    name = Path(filename or "uploaded-report").name
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .")
    return name or "uploaded-report"


def save_uploaded_reports(files: Optional[List[UploadFile]]) -> List[str]:
    if not files:
        return []

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    saved_paths: List[str] = []
    max_bytes = max_report_upload_bytes()
    max_mb = max_bytes // (1024 * 1024)

    for upload in files:
        filename = safe_report_filename(upload.filename or "")
        extension = Path(filename).suffix.lower()
        if extension not in SUPPORTED_REPORT_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported report file type: {extension or 'none'}",
            )

        target = REPORTS_DIR / filename
        if target.exists():
            target = REPORTS_DIR / f"{target.stem}-{int(time.time())}{target.suffix}"

        bytes_written = 0
        try:
            with target.open("wb") as output:
                while True:
                    chunk = upload.file.read(1024 * 1024)
                    if not chunk:
                        break
                    bytes_written += len(chunk)
                    if bytes_written > max_bytes:
                        raise HTTPException(
                            status_code=413,
                            detail=(
                                "Report file exceeds the "
                                f"{max_mb} MB limit."
                            ),
                        )
                    output.write(chunk)
        except Exception:
            if target.exists():
                target.unlink()
            raise
        saved_paths.append(str(target))

    return saved_paths


def delete_temporary_reports(paths: List[str]) -> None:
    for path in paths:
        try:
            target = Path(path).resolve()
            if target.parent == REPORTS_DIR.resolve() and target.exists():
                target.unlink()
        except OSError:
            pass


def evidence_record_to_dict(record) -> Dict[str, Any]:
    if hasattr(record, "__dataclass_fields__"):
        return asdict(record)
    return dict(record)


def resolve_company_for_analysis(company_or_abn: str) -> Dict[str, Any]:
    value = company_or_abn.strip()
    if not value:
        raise HTTPException(status_code=400, detail="company_or_abn is required")

    alias_abn = KNOWN_COMPANY_ABNS.get(value.lower())
    if is_abn(value) or alias_abn:
        abn_result = verify_abn_with_abr(alias_abn or clean_abn(value))
        input_type = "abn"
    else:
        abn_result = search_company_name_with_abr(value)
        input_type = "company_name"

    legal_name = abn_result.get("legal_name") or value
    normalized_name = company_search_name(legal_name)

    return {
        "input_type": input_type,
        "input_value": value,
        "alias_abn": alias_abn,
        "abr": abn_result,
        "legal_name": legal_name,
        "normalized_name": normalized_name,
        "queries": build_company_search_queries(normalized_name),
    }


def collect_news_evidence(
    company_name: str,
    queries: List[str],
    limit: int = 3,
    max_llm_results: int = 3,
    australia_only: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    sample_articles = []
    providers = (
        test_serpapi,
        test_newsapi,
        test_guardian,
        test_nyt,
        test_freenewsapi,
        test_newsdata,
        test_webz,
    )

    for query in queries:
        for provider in providers:
            sample_articles.extend(provider(query, limit))

    articles = dedupe_article_metadata(sample_articles)
    candidates = relevant_llm_candidates(company_name, articles, australia_only)
    candidates = [
        article
        for article in candidates
        if article_candidate_score(company_name, article, australia_only) >= 90
    ][:max_llm_results]

    article_payloads = [asdict(article) for article in candidates]
    if not candidates or max_llm_results <= 0:
        return article_payloads, []

    records = test_openrouter_many(
        company_name,
        candidates,
        fetch_full_text=False,
        australia_only=australia_only,
    )
    return article_payloads, [evidence_record_to_dict(record) for record in records]


def collect_report_evidence(
    company_name: str,
    report_paths: List[str],
    max_report_chunks: int = 3,
) -> List[Dict[str, Any]]:
    records = test_uploaded_reports(
        company_name,
        report_paths,
        max_report_chars=3000,
        max_report_chunks=max(1, min(max_report_chunks, 10)),
        australia_only=False,
    )
    return [evidence_record_to_dict(record) for record in records]
