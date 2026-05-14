from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from psycopg2.extras import Json, execute_values

from .connection import get_conn


IUCN_CACHE_SOURCE = "IUCN Red List v4 countries/AU"


def ensure_iucn_cache_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS iucn_redlist_cache (
            scientific_name TEXT PRIMARY KEY,
            category_code VARCHAR(10),
            category_name VARCHAR(80),
            iucn_url TEXT,
            source VARCHAR(120) NOT NULL DEFAULT 'IUCN Red List v4 countries/AU',
            raw_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            imported_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_iucn_redlist_cache_category
        ON iucn_redlist_cache(category_code);
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_iucn_redlist_cache_imported_at
        ON iucn_redlist_cache(imported_at DESC);
        """
    )


def _category_name(code: Optional[str]) -> Optional[str]:
    names = {
        "CR": "Critically Endangered",
        "EN": "Endangered",
        "VU": "Vulnerable",
        "NT": "Near Threatened",
        "LC": "Least Concern",
        "DD": "Data Deficient",
        "EX": "Extinct",
        "EW": "Extinct in the Wild",
    }
    return names.get((code or "").strip().upper())


def load_iucn_cache_from_db(max_age_hours: int = 0) -> Optional[Dict[str, Dict[str, str]]]:
    conn = None
    cur = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        ensure_iucn_cache_table(cur)
        if max_age_hours > 0:
            min_imported_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=max_age_hours)
            cur.execute(
                """
                SELECT scientific_name, category_code, iucn_url
                FROM iucn_redlist_cache
                WHERE imported_at >= %s
                ORDER BY scientific_name;
                """,
                (min_imported_at,),
            )
        else:
            cur.execute(
                """
                SELECT scientific_name, category_code, iucn_url
                FROM iucn_redlist_cache
                ORDER BY scientific_name;
                """
            )
        rows = cur.fetchall()
        conn.commit()
        if not rows:
            return None
        return {
            str(row["scientific_name"]).strip().lower(): {
                "category": row.get("category_code") or "",
                "url": row.get("iucn_url") or "",
            }
            for row in rows
            if row.get("scientific_name")
        }
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"  [IUCN DB] load skipped: {error}")
        return None
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def save_iucn_cache_to_db(
    cache: Dict[str, Dict[str, Any]],
    *,
    replace: bool = False,
    source: str = IUCN_CACHE_SOURCE,
) -> int:
    if not cache:
        return 0

    rows = []
    for scientific_name, payload in cache.items():
        name = str(scientific_name or "").strip().lower()
        if not name:
            continue
        category = str(payload.get("category") or "").strip().upper() or None
        url = str(payload.get("url") or "").strip() or None
        rows.append(
            (
                name,
                category,
                _category_name(category),
                url,
                source,
                Json(payload),
            )
        )

    if not rows:
        return 0

    conn = None
    cur = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        ensure_iucn_cache_table(cur)
        if replace:
            cur.execute("DELETE FROM iucn_redlist_cache;")
        execute_values(
            cur,
            """
            INSERT INTO iucn_redlist_cache (
                scientific_name,
                category_code,
                category_name,
                iucn_url,
                source,
                raw_json
            )
            VALUES %s
            ON CONFLICT (scientific_name) DO UPDATE SET
                category_code = EXCLUDED.category_code,
                category_name = EXCLUDED.category_name,
                iucn_url = EXCLUDED.iucn_url,
                source = EXCLUDED.source,
                raw_json = EXCLUDED.raw_json,
                imported_at = NOW(),
                updated_at = NOW();
            """,
            rows,
        )
        conn.commit()
        return len(rows)
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def get_iucn_cache_db_status() -> Dict[str, Any]:
    conn = None
    cur = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        ensure_iucn_cache_table(cur)
        cur.execute(
            """
            SELECT
                COUNT(*) AS count,
                MIN(imported_at) AS oldest_imported_at,
                MAX(imported_at) AS newest_imported_at,
                COUNT(*) FILTER (WHERE category_code IN ('CR', 'EN', 'VU')) AS threatened_count
            FROM iucn_redlist_cache;
            """
        )
        row = cur.fetchone() or {}
        cur.execute(
            """
            SELECT category_code, COUNT(*) AS count
            FROM iucn_redlist_cache
            GROUP BY category_code
            ORDER BY category_code;
            """
        )
        categories = {
            str(item["category_code"] or "unknown"): int(item["count"] or 0)
            for item in cur.fetchall()
        }
        conn.commit()
        return {
            "available": True,
            "count": int(row.get("count") or 0),
            "threatened_count": int(row.get("threatened_count") or 0),
            "oldest_imported_at": row.get("oldest_imported_at").isoformat() if row.get("oldest_imported_at") else None,
            "newest_imported_at": row.get("newest_imported_at").isoformat() if row.get("newest_imported_at") else None,
            "categories": categories,
        }
    except Exception as error:
        if conn:
            conn.rollback()
        return {
            "available": False,
            "count": 0,
            "error": str(error),
        }
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
