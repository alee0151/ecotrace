#!/usr/bin/env python3
"""
Fetch all Australian IUCN Red List records and replace the Postgres cache table.

Usage:
    python backend_clean/scripts/migrate_iucn_cache_to_db.py

Required environment:
    IUCN_TOKEN or IUCN_API_TOKEN
    DB_HOST
    DB_PORT
    DB_NAME
    DB_USER
    DB_PASSWORD
    DB_SSLMODE        optional; use "disable" for local Postgres, "require" for cloud

Optional:
    IUCN_COUNTRY_CODE default AU
    IUCN_PAGE_DELAY_SECONDS default 0.5
    IUCN_TIMEOUT_SECONDS default 30
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import psycopg2
import requests
from psycopg2.extras import Json, execute_values


IUCN_BASE = "https://api.iucnredlist.org/api/v4"
TABLE_NAME = "iucn_redlist_cache"
CATEGORY_NAMES = {
    "CR": "Critically Endangered",
    "EN": "Endangered",
    "VU": "Vulnerable",
    "NT": "Near Threatened",
    "LC": "Least Concern",
    "DD": "Data Deficient",
    "EX": "Extinct",
    "EW": "Extinct in the Wild",
}


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def env(name: str, default: Optional[str] = None) -> str:
    value = os.getenv(name, default)
    if value is None or value == "":
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def get_iucn_token() -> str:
    token = os.getenv("IUCN_TOKEN") or os.getenv("IUCN_API_TOKEN")
    if not token:
        raise RuntimeError("Missing IUCN_TOKEN or IUCN_API_TOKEN")
    return token


def fetch_iucn_country_records(country_code: str) -> Dict[str, Dict[str, Any]]:
    token = get_iucn_token()
    timeout = int_env("IUCN_TIMEOUT_SECONDS", 30)
    delay = float_env("IUCN_PAGE_DELAY_SECONDS", 0.5)
    headers = {"Authorization": f"Bearer {token}"}
    records: Dict[str, Dict[str, Any]] = {}
    page = 1

    while True:
        url = f"{IUCN_BASE}/countries/{country_code}"
        params = {"latest": "true", "scope_code": 1, "page": page}
        print(f"[IUCN] Fetching {country_code} page {page}...")
        response = requests.get(url, headers=headers, params=params, timeout=timeout)
        if response.status_code != 200:
            raise RuntimeError(f"IUCN HTTP {response.status_code}: {response.text[:500]}")

        payload = response.json()
        assessments = payload.get("assessments") or []
        if not assessments:
            break

        for assessment in assessments:
            scientific_name = str(assessment.get("taxon_scientific_name") or "").strip().lower()
            if not scientific_name:
                continue
            category = str(assessment.get("red_list_category_code") or "").strip().upper()
            records[scientific_name] = {
                "category": category,
                "url": str(assessment.get("url") or "").strip(),
                "assessment_id": assessment.get("assessment_id"),
                "taxon_id": assessment.get("taxon_id"),
                "taxon_scientific_name": assessment.get("taxon_scientific_name"),
                "red_list_category_code": category,
                "raw": assessment,
            }

        print(f"[IUCN] Page {page}: {len(assessments)} rows, {len(records)} unique species")
        if len(assessments) < 100:
            break

        page += 1
        time.sleep(delay)

    return records


def get_conn():
    return psycopg2.connect(
        host=env("DB_HOST", "localhost"),
        port=env("DB_PORT", "5432"),
        dbname=env("DB_NAME", "seeco"),
        user=env("DB_USER", "postgres"),
        password=env("DB_PASSWORD"),
        sslmode=env("DB_SSLMODE", "require"),
    )


def ensure_table(cur) -> None:
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            scientific_name TEXT PRIMARY KEY,
            category_code VARCHAR(10),
            category_name VARCHAR(80),
            iucn_url TEXT,
            source VARCHAR(120) NOT NULL DEFAULT 'IUCN Red List v4 countries/AU',
            raw_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            imported_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """
    )
    cur.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_category
        ON {TABLE_NAME}(category_code);
        """
    )
    cur.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_imported_at
        ON {TABLE_NAME}(imported_at DESC);
        """
    )


def rows_for_insert(records: Dict[str, Dict[str, Any]], country_code: str) -> List[Tuple[Any, ...]]:
    rows = []
    source = f"IUCN Red List v4 countries/{country_code}"
    for scientific_name, payload in sorted(records.items()):
        category = payload.get("category") or None
        rows.append(
            (
                scientific_name,
                category,
                CATEGORY_NAMES.get(category or ""),
                payload.get("url") or None,
                source,
                Json(payload),
            )
        )
    return rows


def replace_iucn_table(records: Dict[str, Dict[str, Any]], country_code: str) -> int:
    rows = rows_for_insert(records, country_code)
    if not rows:
        raise RuntimeError("No IUCN records fetched; refusing to clear table")

    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                ensure_table(cur)
                print(f"[DB] Clearing {TABLE_NAME}...")
                cur.execute(f"DELETE FROM {TABLE_NAME};")
                print(f"[DB] Inserting {len(rows)} records...")
                execute_values(
                    cur,
                    f"""
                    INSERT INTO {TABLE_NAME} (
                        scientific_name,
                        category_code,
                        category_name,
                        iucn_url,
                        source,
                        raw_json
                    )
                    VALUES %s;
                    """,
                    rows,
                    page_size=1000,
                )
        return len(rows)
    finally:
        conn.close()


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    load_dotenv(repo_root / "backend_clean" / ".env")
    load_dotenv(repo_root / "backend_clean" / "env.example")

    country_code = os.getenv("IUCN_COUNTRY_CODE", "AU").strip().upper() or "AU"
    print(f"[IUCN] Starting full fetch for country={country_code}")
    records = fetch_iucn_country_records(country_code)
    print(f"[IUCN] Fetched {len(records)} unique species")

    inserted = replace_iucn_table(records, country_code)
    print(f"[DB] Migration complete: replaced {TABLE_NAME} with {inserted} records")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        raise SystemExit(1)
