"""
db_writer.py
============

Upsert helpers for each EcoTrace entity table.
Called from main.py after each pipeline phase completes.

Design rules
-------------
- Every function accepts an open psycopg2 cursor.
- Caller is responsible for commit / rollback.
- Every function is wrapped in try/except so a DB write failure
  never crashes the API response — it logs and returns None.
- ON CONFLICT upsert for tables with natural unique keys
  (abn_record, company, trademark, product).
- SELECT + INSERT for brand (no UNIQUE constraint in schema).

Table dependency order
-----------------------
  abn_record  (no FK deps)
      └── company      (FK → abn_record.abn)
           └── brand        (FK → company.company_id)
  trademark   (no FK deps)   └── brand.trademark_id (nullable FK)
  product     (FK → brand.brand_id)
"""

import traceback
from typing import Any, Dict, Optional


# ============================================================
# Helpers
# ============================================================

_ENTITY_TYPE_MAP = {
    "PTY LTD":     "PTY LTD",
    "PROPRIETARY": "PTY LTD",
    "LTD":         "LTD",
    "LIMITED":     "LTD",
    "TRUST":       "TRUST",
    "PARTNERSHIP": "PARTNERSHIP",
    "SOLE TRADER": "SOLE TRADER",
    "INDIVIDUAL":  "SOLE TRADER",
}


def _entity_type(raw: Optional[str]) -> str:
    if not raw:
        return "OTHER"
    upper = raw.upper().strip()
    for key, val in _ENTITY_TYPE_MAP.items():
        if key in upper:
            return val
    return "OTHER"


def _clean_abn(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = str(value).replace(" ", "").strip()
    return cleaned if len(cleaned) == 11 and cleaned.isdigit() else None


def _str(value: Any, max_len: int = 255) -> Optional[str]:
    """Safe string coerce and truncate."""
    if value is None:
        return None
    s = str(value).strip()
    return s[:max_len] if s else None


# ============================================================
# 1. abn_record
# ============================================================

def upsert_abn_record(cur, data: Dict[str, Any]) -> Optional[str]:
    """
    INSERT ... ON CONFLICT (abn) DO UPDATE.
    Returns the abn string on success, None on failure.

    Expected keys in data:
        abn, legal_name, entity_type, gst_registered, state, postcode
    """
    try:
        abn = _clean_abn(data.get("abn"))
        if not abn:
            return None

        legal_name  = _str(data.get("legal_name")) or "Unknown"
        entity_type = _entity_type(data.get("entity_type"))
        gst_reg     = bool(data.get("gst_registered", False))
        state       = _str(data.get("state"),    3)
        postcode    = _str(data.get("postcode"), 4)

        cur.execute(
            """
            INSERT INTO abn_record
                (abn, legal_name, entity_type, gst_registered, state, postcode, last_updated)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (abn) DO UPDATE SET
                legal_name     = EXCLUDED.legal_name,
                entity_type    = EXCLUDED.entity_type,
                gst_registered = EXCLUDED.gst_registered,
                state          = COALESCE(EXCLUDED.state,     abn_record.state),
                postcode       = COALESCE(EXCLUDED.postcode,  abn_record.postcode),
                last_updated   = NOW()
            RETURNING abn;
            """,
            (abn, legal_name, entity_type, gst_reg, state, postcode),
        )
        row = cur.fetchone()
        return row["abn"] if row else None

    except Exception:
        print("[db_writer] upsert_abn_record failed:")
        traceback.print_exc()
        return None


# ============================================================
# 2. company
# ============================================================

def upsert_company(cur, data: Dict[str, Any]) -> Optional[str]:
    """
    Upserts abn_record first, then company.
    Returns company_id (str UUID) or None on failure.

    Expected keys in data (same as abn_record + extras):
        abn, legal_name, entity_type, gst_registered, state, postcode,
        acn, abn_status, main_activity, anzsic_code
    """
    abn = upsert_abn_record(cur, data)
    if not abn:
        return None

    try:
        legal_name  = _str(data.get("legal_name")) or "Unknown"
        entity_type = _entity_type(data.get("entity_type"))
        acn         = _str(
            (data.get("acn") or "").replace(" ", "") or None, 9
        )
        status_raw  = _str(
            data.get("company_status") or data.get("abn_status") or "registered"
        ).lower()
        status      = (
            status_raw
            if status_raw in ("registered", "deregistered", "suspended")
            else "registered"
        )
        anzsic = _str(
            data.get("anzsic_code") or data.get("main_activity"), 10
        )

        cur.execute(
            """
            INSERT INTO company
                (abn, acn, legal_name, entity_type, company_status, anzsic_code)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (abn) DO UPDATE SET
                legal_name     = EXCLUDED.legal_name,
                entity_type    = EXCLUDED.entity_type,
                company_status = EXCLUDED.company_status,
                acn            = COALESCE(EXCLUDED.acn,        company.acn),
                anzsic_code    = COALESCE(EXCLUDED.anzsic_code, company.anzsic_code)
            RETURNING company_id;
            """,
            (abn, acn, legal_name, entity_type, status, anzsic),
        )
        row = cur.fetchone()
        return str(row["company_id"]) if row else None

    except Exception:
        print("[db_writer] upsert_company failed:")
        traceback.print_exc()
        return None


# ============================================================
# 3. trademark
# ============================================================

def upsert_trademark(cur, data: Dict[str, Any]) -> Optional[str]:
    """
    INSERT ... ON CONFLICT (trademark_number) DO UPDATE.
    Returns trademark_id (str UUID) or None on failure.

    Expected keys in data (from brand_pipeline._build_trademark_summary):
        number, word_mark, status, registration_date, legal_owner, class_code
    """
    try:
        tm_number = _str(data.get("number") or data.get("trademark_number"), 50)
        if not tm_number:
            return None

        tm_name    = _str(
            data.get("word_mark") or data.get("trademark_name") or tm_number
        )
        owner_name = _str(
            data.get("legal_owner") or data.get("owner_legal_name") or "Unknown"
        )
        status_raw = _str(data.get("status") or "registered").lower()
        status     = (
            status_raw
            if status_raw in ("registered", "pending", "lapsed", "removed")
            else "registered"
        )
        reg_date   = data.get("registration_date") or None
        class_code = _str(data.get("class_code"), 10)

        cur.execute(
            """
            INSERT INTO trademark
                (trademark_number, trademark_name, owner_legal_name,
                 class_code, status, registration_date)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (trademark_number) DO UPDATE SET
                trademark_name    = EXCLUDED.trademark_name,
                owner_legal_name  = EXCLUDED.owner_legal_name,
                status            = EXCLUDED.status,
                registration_date = COALESCE(EXCLUDED.registration_date,
                                            trademark.registration_date),
                class_code        = COALESCE(EXCLUDED.class_code, trademark.class_code)
            RETURNING trademark_id;
            """,
            (tm_number, tm_name, owner_name, class_code, status, reg_date),
        )
        row = cur.fetchone()
        return str(row["trademark_id"]) if row else None

    except Exception:
        print("[db_writer] upsert_trademark failed:")
        traceback.print_exc()
        return None


# ============================================================
# 4. brand
# ============================================================

def upsert_brand(
    cur,
    brand_name:   str,
    company_id:   str,
    trademark_id: Optional[str] = None,
) -> Optional[str]:
    """
    SELECT first (LOWER match on brand_name + company_id).
    INSERT if missing; UPDATE trademark_id if we now have one.
    Returns brand_id (str UUID) or None on failure.

    Note: brand has no UNIQUE constraint in schema.sql, so we cannot
    use ON CONFLICT — use explicit SELECT + INSERT instead.
    """
    try:
        brand_name = (brand_name or "").strip()
        if not brand_name or not company_id:
            return None

        cur.execute(
            """
            SELECT brand_id, trademark_id
            FROM brand
            WHERE LOWER(brand_name) = LOWER(%s)
              AND company_id = %s
            LIMIT 1;
            """,
            (brand_name, company_id),
        )
        existing = cur.fetchone()

        if existing:
            brand_id = str(existing["brand_id"])
            # Fill in trademark_id if we now have one and it was missing
            if trademark_id and not existing["trademark_id"]:
                cur.execute(
                    "UPDATE brand SET trademark_id = %s WHERE brand_id = %s;",
                    (trademark_id, brand_id),
                )
            return brand_id

        cur.execute(
            """
            INSERT INTO brand (brand_name, company_id, trademark_id)
            VALUES (%s, %s, %s)
            RETURNING brand_id;
            """,
            (brand_name, company_id, trademark_id),
        )
        row = cur.fetchone()
        return str(row["brand_id"]) if row else None

    except Exception:
        print("[db_writer] upsert_brand failed:")
        traceback.print_exc()
        return None


# ============================================================
# 5. product
# ============================================================

def upsert_product(
    cur,
    data:     Dict[str, Any],
    brand_id: str,
) -> Optional[str]:
    """
    INSERT ... ON CONFLICT (barcode) DO UPDATE.
    Returns product_id (str UUID) or None on failure.

    Expected keys in data:
        barcode, product_name, manufacturer_name, data_source
    data_source must be 'open_food_facts' or 'gs1'.
    """
    try:
        barcode = _str(data.get("barcode"), 20)
        if not barcode or not brand_id:
            return None

        product_name = _str(
            data.get("product_name") or data.get("name") or "Unknown"
        )
        manufacturer = _str(
            data.get("manufacturer_name") or data.get("manufacturer")
        )
        source_raw  = _str(data.get("data_source") or data.get("source") or "open_food_facts").lower()
        data_source = source_raw if source_raw in ("open_food_facts", "gs1") else "open_food_facts"

        cur.execute(
            """
            INSERT INTO product
                (barcode, product_name, brand_id, manufacturer_name, data_source)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (barcode) DO UPDATE SET
                product_name      = EXCLUDED.product_name,
                brand_id          = EXCLUDED.brand_id,
                manufacturer_name = COALESCE(EXCLUDED.manufacturer_name,
                                             product.manufacturer_name),
                data_source       = EXCLUDED.data_source
            RETURNING product_id;
            """,
            (barcode, product_name, brand_id, manufacturer, data_source),
        )
        row = cur.fetchone()
        return str(row["product_id"]) if row else None

    except Exception:
        print("[db_writer] upsert_product failed:")
        traceback.print_exc()
        return None


# ============================================================
# Helper: extract flat ABR data dict from pipeline result
# ============================================================

def extract_abr_data(phase_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    ABR results can be nested under 'company' or flat at the top level.
    Normalises both shapes into one flat dict for upsert_company.
    Returns None if no usable ABN found.
    """
    # Shape A: abr_result = {"success": True, "company": {"abn": ..., ...}, ...}
    company_block = phase_result.get("company")
    if isinstance(company_block, dict) and _clean_abn(company_block.get("abn")):
        return company_block

    # Shape B: flat  {"success": True, "abn": ..., "legal_name": ..., ...}
    if _clean_abn(phase_result.get("abn")):
        return phase_result

    return None
