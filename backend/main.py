"""
EcoTrace Backend API
====================

Purpose
-------
This backend implements the consumer search pipeline for EcoTrace.

Consumer flow
-------------
The consumer flow is query_id based:
- Consumers do not need to log in.
- Each valid search creates exactly one search_query record.
- The backend returns query_id to the frontend.
- The report module can later use query_id to generate the risk report.

Supported frontend inputs
-------------------------
Only ONE input type should be submitted per request:
1. barcode       -> barcode_pipeline.py   (EAN-13 validate, OpenFoodFacts, GS1, ABR)
2. brand         -> brand_pipeline.py     (IP Australia Trademark, ABR)
3. company_or_abn -> abn_pipeline.py      (ABN checksum, ABR ABN lookup / name search)

Pipeline modules
----------------
  barcode_pipeline.py  : EAN-13 checksum -> OpenFoodFacts -> IP Australia TM -> ABR
  brand_pipeline.py    : IP Australia Trade Mark Search -> ABR
  abn_pipeline.py      : ABN checksum (ATO mod-89) -> ABR ABN lookup
                         OR company name -> ABR name search

All ABR Web Services calls live in abn_pipeline.py.
Barcode and brand pipelines receive abr_lookup_fn as a dependency.

DB writes (db_writer.py)
------------------------
After each pipeline succeeds the following rows are upserted:

  company/ABN branch:
    abn_record, company
    -> search_query.resolved_company_id

  brand branch:
    abn_record, company, trademark, brand
    -> search_query.resolved_company_id + resolved_brand_id

  barcode branch:
    abn_record, company, trademark, brand, product
    -> search_query.resolved_company_id + resolved_brand_id + resolved_product_id

Not included in this file
-------------------------
Report generation is intentionally not implemented here. The report team can
use query_id and search_query records produced by this backend.

Main endpoint
-------------
POST /api/search

Diagnostic endpoints
--------------------
GET /api/debug/trademark-auth
    Runs the IP Australia OAuth token fetch in isolation and reports
    which method succeeded (Basic Auth header vs body params).
    Use this to validate .env credentials WITHOUT running a full search.

Version history
---------------
6.0.0 - db_writer.py added; all 3 pipeline branches now persist to DB
5.1.0 - /api/debug/trademark-auth added; diagnose_token() imported
5.0.0 - abn_pipeline.py extracted; ABR functions removed from main.py
4.0.0 - barcode and brand logic moved to dedicated pipeline modules
3.0.0 - initial pipeline implementation
"""

import os
import re
import hashlib
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
from uuid import UUID, uuid4
from urllib.parse import quote

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# ------------------------------------------------------------------
# Pipeline modules
# ------------------------------------------------------------------
try:
    from .abn_pipeline import (
        run_company_abn_phase,
        verify_abn_with_abr,
        search_company_name_with_abr,
        clean_abn,
        is_abn,
    )
    from .barcode_pipeline import run_barcode_phase
    from .brand_pipeline import run_brand_phase, get_ip_australia_access_token, diagnose_token
    from .upload_endpoint import router as upload_router
    from .analysis_pipeline import (
        collect_news_evidence,
        collect_report_evidence,
        delete_temporary_reports,
        resolve_company_for_analysis,
        save_uploaded_reports,
    )
    from .bio_diversity_scoring_enigne.ecotrace_layer_a import (
        SpeciesRecord,
        ensure_iucn_cache_loaded,
        get_iucn_cache_status,
        run_layer_a,
    )
except ImportError:
    from abn_pipeline import (
        run_company_abn_phase,
        verify_abn_with_abr,
        search_company_name_with_abr,
        clean_abn,
        is_abn,
    )
    from barcode_pipeline import run_barcode_phase
    from brand_pipeline import run_brand_phase, get_ip_australia_access_token, diagnose_token
    from upload_endpoint import router as upload_router
    from analysis_pipeline import (
        collect_news_evidence,
        collect_report_evidence,
        delete_temporary_reports,
        resolve_company_for_analysis,
        save_uploaded_reports,
    )
    from bio_diversity_scoring_enigne.ecotrace_layer_a import (
        SpeciesRecord,
        ensure_iucn_cache_loaded,
        get_iucn_cache_status,
        run_layer_a,
    )

# ------------------------------------------------------------------
# DB write helpers
# ------------------------------------------------------------------
try:
    from .db_writer import (
        upsert_company,
        upsert_trademark,
        upsert_brand,
        upsert_product,
        extract_abr_data,
    )
except ImportError:
    from db_writer import (
        upsert_company,
        upsert_trademark,
        upsert_brand,
        upsert_product,
        extract_abr_data,
    )


# ============================================================
# Environment
# ============================================================

load_dotenv(Path(__file__).resolve().with_name(".env"))


# ============================================================
# FastAPI App
# ============================================================

app = FastAPI(
    title="EcoTrace Backend API",
    version="6.0.0",
    description="""
EcoTrace consumer search API.

Pipeline modules:
- abn_pipeline.py     : ABN checksum (ATO mod-89) + ABR lookup / name search
- barcode_pipeline.py : EAN-13 validation -> OpenFoodFacts -> IP Australia TM -> ABR
- brand_pipeline.py   : IP Australia Trade Mark Search -> ABR

db_writer.py upserts pipeline results into the database after each search.
Every valid search creates a query_id and stores one search_query record.
"""
)


# ============================================================
# CORS
# ============================================================

def get_cors_origins() -> List[str]:
    raw = os.getenv(
        "CORS_ALLOW_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


cors_origins = get_cors_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials="*" not in cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
try:
    from .report_service import (
        build_query_report,
        create_persisted_report,
        deliver_report_email,
        get_persisted_report,
        refresh_persisted_report_content,
        render_report_html,
        send_persisted_report,
        valid_email,
    )
except ImportError:
    from report_service import (
        build_query_report,
        create_persisted_report,
        deliver_report_email,
        get_persisted_report,
        refresh_persisted_report_content,
        render_report_html,
        send_persisted_report,
        valid_email,
    )

app.include_router(upload_router)


def warm_iucn_cache_in_background():
    """
    Start Layer A's IUCN Australia cache as soon as the backend is live.
    The cache is kept in memory for the lifetime of this backend process.
    """
    status = get_iucn_cache_status()
    if status.get("state") in {"loading", "ready"}:
        return status

    def _warm():
        try:
            count = ensure_iucn_cache_loaded()
            print(f"[Layer A] IUCN Australia cache ready: {count:,} species")
        except Exception as error:
            print(f"[Layer A] IUCN cache warmup failed: {error}")

    thread = threading.Thread(target=_warm, daemon=True)
    thread.start()
    return get_iucn_cache_status()


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@app.on_event("startup")
def startup_tasks():
    if env_bool("WARM_IUCN_CACHE_ON_STARTUP", True):
        warm_iucn_cache_in_background()
    else:
        print("[Layer A] IUCN startup warmup disabled")


# ============================================================
# Database
# ============================================================

def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "ecotrace"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD"),
        sslmode=os.getenv("DB_SSLMODE", "require"),
        cursor_factory=RealDictCursor,
    )


def serialize_row(row):
    if row is None:
        return None
    return {k: str(v) if isinstance(v, UUID) else v for k, v in row.items()}


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verification_return_path(value: Optional[str]) -> str:
    if not value or not value.startswith("/app/"):
        return "/app/search"
    if value.startswith("/app/verify-email"):
        return "/app/search"
    return value


def frontend_base_url() -> str:
    return (os.getenv("FRONTEND_BASE_URL") or "http://127.0.0.1:5173").rstrip("/")


def ensure_email_verification_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS email_verification (
            verification_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES "user"(user_id) ON DELETE CASCADE,
            email VARCHAR(255) NOT NULL,
            token_hash CHAR(64) NOT NULL UNIQUE,
            return_to TEXT NOT NULL DEFAULT '/app/search',
            requested_at TIMESTAMP NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMP NOT NULL,
            verified_at TIMESTAMP,
            delivery_method VARCHAR(50)
        );
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_email_verification_email
        ON email_verification(email, requested_at DESC);
        """
    )


# ============================================================
# Request Models
# ============================================================

class SearchRequest(BaseModel):
    user_id:        Optional[str] = None
    barcode:        Optional[str] = None
    brand:          Optional[str] = None
    company_or_abn: Optional[str] = None


class CreateUserRequest(BaseModel):
    email:     str
    user_type: str = "consumer"


class SendReportEmailRequest(BaseModel):
    email: str
    query_id: str


class GenerateReportRequest(BaseModel):
    query_id: str
    analysis_payload: Optional[Dict[str, Any]] = None


class SendPersistedReportEmailRequest(BaseModel):
    email: str


class RequestEmailVerificationRequest(BaseModel):
    email: str
    return_to: Optional[str] = "/app/search"


class ConfirmEmailVerificationRequest(BaseModel):
    token: str


# ============================================================
# Input Cleaning and Validation
# ============================================================

def clean_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value if value else None


def get_single_input_type(
    barcode:        Optional[str],
    brand:          Optional[str],
    company_or_abn: Optional[str],
) -> Tuple[str, str, str]:
    provided = []
    if barcode:        provided.append(("barcode",      barcode,        "barcode"))
    if brand:          provided.append(("brand_name",   brand,          "brand"))
    if company_or_abn: provided.append(("company_name", company_or_abn, "company_or_abn"))

    if len(provided) == 0:
        raise HTTPException(
            status_code=400,
            detail="Please provide exactly one input: barcode, brand, or company_or_abn.",
        )
    if len(provided) > 1:
        raise HTTPException(
            status_code=400,
            detail="Please submit only one input type per search.",
        )

    input_type, input_value, frontend_type = provided[0]

    if input_type == "barcode":
        cleaned_bc = re.sub(r"[\s\-]", "", input_value)
        if not cleaned_bc.isdigit() or not (8 <= len(cleaned_bc) <= 14):
            raise HTTPException(
                status_code=400,
                detail="Invalid barcode. Must be 8-14 digits (EAN-8, EAN-13, ITF-14).",
            )

    if input_type == "brand_name" and len(input_value) < 2:
        raise HTTPException(status_code=400, detail="Brand name must be at least 2 characters.")

    if input_type == "company_name":
        cleaned = clean_abn(input_value)
        if cleaned.isdigit() and not is_abn(cleaned):
            raise HTTPException(status_code=400, detail="Invalid ABN — must be exactly 11 digits.")
        if not cleaned.isdigit() and len(input_value.strip()) < 2:
            raise HTTPException(status_code=400, detail="Company name must be at least 2 characters.")

    return input_type, input_value, frontend_type


# ============================================================
# search_query Lifecycle
# ============================================================

def create_search_query(cur, input_type: str, input_value: str, user_id: Optional[str] = None):
    cur.execute(
        """
        INSERT INTO search_query (user_id, input_type, input_value, resolution_status)
        VALUES (%s, %s, %s, 'pending')
        RETURNING query_id, submitted_at;
        """,
        (user_id, input_type, input_value),
    )
    return cur.fetchone()


def update_search_query(
    cur,
    query_id,
    status:              str,
    resolved_company_id: Optional[str] = None,
    resolved_brand_id:   Optional[str] = None,
    resolved_product_id: Optional[str] = None,
):
    if status not in ("resolved", "failed"):
        status = "failed"
    cur.execute(
        """
        UPDATE search_query
        SET resolution_status   = %s,
            resolved_company_id = %s,
            resolved_brand_id   = %s,
            resolved_product_id = %s
        WHERE query_id = %s;
        """,
        (status, resolved_company_id, resolved_brand_id, resolved_product_id, query_id),
    )


def company_data_from_resolution(resolution: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Convert a company/ABN resolution payload into the flat shape expected by
    upsert_company(), which writes both abn_record and company.
    """
    abr_data = extract_abr_data(resolution.get("abr") or {})
    if not abr_data:
        return None

    return {
        **abr_data,
        "legal_name": abr_data.get("legal_name") or resolution.get("legal_name"),
        "abn": abr_data.get("abn") or resolution.get("abn"),
    }


def persist_company_resolution(
    cur,
    input_value: str,
    resolution: Dict[str, Any],
    user_id: Optional[str] = None,
) -> Tuple[str, Optional[str], List[str]]:
    """
    Create a search_query, upsert abn_record + company, then attach the
    resolved company_id back to search_query.
    """
    query = create_search_query(
        cur,
        input_type="company_name",
        input_value=input_value.strip(),
        user_id=user_id,
    )
    query_id = query["query_id"]
    pipeline_steps = ["Search query generation"]

    resolved_company_id = None
    company_data = company_data_from_resolution(resolution)
    if company_data and company_data.get("abn"):
        resolved_company_id = upsert_company(cur, company_data)

    if resolved_company_id:
        pipeline_steps.append(
            f"DB: abn_record and company upserted (company_id={resolved_company_id})"
        )
    else:
        pipeline_steps.append("DB: company write failed or ABN missing")

    update_search_query(
        cur,
        query_id,
        "resolved" if resolved_company_id else "failed",
        resolved_company_id=resolved_company_id,
    )

    return str(query_id), resolved_company_id, pipeline_steps


SPATIAL_ANALYSIS_CACHE: Dict[str, Dict[str, Any]] = {}
SPATIAL_ANALYSIS_LOCK = threading.RLock()

POSTCODE_CENTROIDS: Dict[str, Tuple[float, float, str]] = {
    "2000": (-33.8688, 151.2093, "Sydney CBD"),
    "2153": (-33.7305, 150.9787, "Bella Vista NSW"),
    "3000": (-37.8136, 144.9631, "Melbourne CBD"),
    "3008": (-37.8152, 144.9483, "Docklands VIC"),
    "4000": (-27.4698, 153.0251, "Brisbane CBD"),
    "5000": (-34.9285, 138.6007, "Adelaide CBD"),
    "6000": (-31.9523, 115.8613, "Perth CBD"),
    "7000": (-42.8821, 147.3272, "Hobart CBD"),
    "0800": (-12.4634, 130.8456, "Darwin CBD"),
    "2600": (-35.2809, 149.1300, "Canberra ACT"),
}

STATE_CENTROIDS: Dict[str, Tuple[float, float, str]] = {
    "NSW": (-33.8688, 151.2093, "NSW registered address centroid"),
    "VIC": (-37.8136, 144.9631, "VIC registered address centroid"),
    "QLD": (-27.4698, 153.0251, "QLD registered address centroid"),
    "SA": (-34.9285, 138.6007, "SA registered address centroid"),
    "WA": (-31.9523, 115.8613, "WA registered address centroid"),
    "TAS": (-42.8821, 147.3272, "TAS registered address centroid"),
    "NT": (-12.4634, 130.8456, "NT registered address centroid"),
    "ACT": (-35.2809, 149.1300, "ACT registered address centroid"),
}

EVIDENCE_LOCATION_CENTROIDS: List[Tuple[str, Tuple[float, float, str, str, float]]] = [
    ("olympic dam", (-30.4430, 136.8830, "Olympic Dam SA", "SA", 25.0)),
    ("pilbara", (-22.1000, 118.7000, "Pilbara WA", "WA", 50.0)),
    ("port hedland", (-20.3107, 118.5878, "Port Hedland WA", "WA", 25.0)),
    ("mt arthur", (-32.3860, 150.8910, "Mt Arthur NSW", "NSW", 25.0)),
    ("mount arthur", (-32.3860, 150.8910, "Mt Arthur NSW", "NSW", 25.0)),
    ("bowen basin", (-22.0000, 148.0000, "Bowen Basin QLD", "QLD", 50.0)),
    ("queensland", (-22.5752, 144.0848, "Queensland evidence region", "QLD", 75.0)),
    ("south australia", (-30.0000, 135.0000, "South Australia evidence region", "SA", 75.0)),
    ("western australia", (-25.0000, 122.0000, "Western Australia evidence region", "WA", 75.0)),
    (" wa", (-25.0000, 122.0000, "Western Australia evidence region", "WA", 75.0)),
    (" sa", (-30.0000, 135.0000, "South Australia evidence region", "SA", 75.0)),
    (" qld", (-22.5752, 144.0848, "Queensland evidence region", "QLD", 75.0)),
]


def postcode_prefix_centroid(postcode: Optional[str]) -> Optional[Tuple[float, float, str]]:
    if not postcode:
        return None
    postcode = str(postcode).strip().zfill(4)
    first = postcode[0]
    if first == "2":
        return (-33.8688, 151.2093, f"NSW postcode {postcode} centroid")
    if first == "3":
        return (-37.8136, 144.9631, f"VIC postcode {postcode} centroid")
    if first == "4":
        return (-27.4698, 153.0251, f"QLD postcode {postcode} centroid")
    if first == "5":
        return (-34.9285, 138.6007, f"SA postcode {postcode} centroid")
    if first == "6":
        return (-31.9523, 115.8613, f"WA postcode {postcode} centroid")
    if first == "7":
        return (-42.8821, 147.3272, f"TAS postcode {postcode} centroid")
    if postcode.startswith("08"):
        return (-12.4634, 130.8456, f"NT postcode {postcode} centroid")
    if postcode.startswith("26"):
        return (-35.2809, 149.1300, f"ACT postcode {postcode} centroid")
    return None


def evidence_location_centroid(location: Optional[str]) -> Optional[Dict[str, Any]]:
    if not location:
        return None
    normalized = f" {str(location).strip().lower()} "
    for token, (lat, lon, label, state, radius_km) in EVIDENCE_LOCATION_CENTROIDS:
        if token in normalized:
            return {
                "label": label,
                "address_raw": f"Evidence extracted location: {location}",
                "state": state,
                "postcode": None,
                "country": "AU",
                "lat": lat,
                "lon": lon,
                "radius_km": radius_km,
                "confidence": "medium",
                "method": "evidence extracted location centroid",
                "source": "report_or_news_evidence",
                "evidence_location": location,
            }
    return None


def latest_report_metadata_for_query(cur, query_id: str) -> Optional[Dict[str, Any]]:
    cur.execute(
        """
        SELECT report_id, metadata_json
        FROM report
        WHERE query_id = %s
        ORDER BY generated_at DESC
        LIMIT 1;
        """,
        (query_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    metadata = row.get("metadata_json")
    if not isinstance(metadata, dict):
        return None
    return {"report_id": str(row["report_id"]), "metadata": metadata}


def evidence_location_candidates(metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    analysis = metadata.get("analysis_evidence") or {}
    records = []
    if isinstance(analysis, dict):
        for section in ("reports", "news"):
            section_records = analysis.get(section) or []
            if isinstance(section_records, list):
                records.extend(record for record in section_records if isinstance(record, dict))

    candidates: List[Dict[str, Any]] = []
    for record in records:
        location_text = record.get("location")
        centroid = evidence_location_centroid(location_text)
        if not centroid:
            continue
        confidence = record.get("confidence") or record.get("llm_confidence") or 0
        try:
            confidence_value = float(confidence)
        except (TypeError, ValueError):
            confidence_value = 0
        if confidence_value > 1:
            confidence_value = confidence_value / 100
        specificity = 2 if any(
            token in str(location_text).lower()
            for token in ("pilbara", "olympic dam", "port hedland", "mt arthur", "mount arthur", "bowen basin")
        ) else 1
        candidates.append(
            {
                **centroid,
                "source_record": record,
                "rank": specificity * 10 + confidence_value,
            }
        )

    candidates.sort(key=lambda item: item["rank"], reverse=True)
    return candidates


def infer_location_from_latest_report(cur, query_id: str) -> Optional[Dict[str, Any]]:
    latest = latest_report_metadata_for_query(cur, query_id)
    if not latest:
        return None
    candidates = evidence_location_candidates(latest["metadata"])
    if not candidates:
        return None

    selected = dict(candidates[0])
    selected.pop("rank", None)
    selected["report_id"] = latest["report_id"]
    selected["confidence"] = "high" if len(candidates) > 1 else selected["confidence"]
    return selected


def infer_location_from_abn(row: Dict[str, Any]) -> Dict[str, Any]:
    postcode = str(row.get("postcode") or "").strip().zfill(4)
    state = str(row.get("state") or "").strip().upper()

    exact = POSTCODE_CENTROIDS.get(postcode)
    if exact:
        lat, lon, label = exact
        confidence = "high"
        method = "exact postcode centroid"
    else:
        prefixed = postcode_prefix_centroid(postcode)
        if prefixed:
            lat, lon, label = prefixed
            confidence = "medium"
            method = "postcode range centroid"
        elif state in STATE_CENTROIDS:
            lat, lon, label = STATE_CENTROIDS[state]
            confidence = "low"
            method = "state centroid"
        else:
            lat, lon, label = STATE_CENTROIDS["VIC"]
            confidence = "low"
            method = "fallback Australia business centroid"

    return {
        "label": label,
        "address_raw": f"ABN registered address: {state or 'AU'} {postcode}".strip(),
        "state": state or None,
        "postcode": postcode if postcode and postcode != "0000" else None,
        "country": "AU",
        "lat": lat,
        "lon": lon,
        "radius_km": 10.0,
        "confidence": confidence,
        "method": method,
        "source": "abn_record",
    }


def get_query_company_location(cur, query_id: str) -> Dict[str, Any]:
    cur.execute(
        """
        SELECT
            sq.query_id,
            sq.input_type,
            sq.input_value,
            sq.resolution_status,
            sq.resolved_company_id,
            c.company_id,
            c.legal_name,
            c.abn,
            c.entity_type,
            c.company_status,
            ar.state,
            ar.postcode,
            ar.gst_registered
        FROM search_query sq
        LEFT JOIN company c ON c.company_id = sq.resolved_company_id
        LEFT JOIN abn_record ar ON ar.abn = c.abn
        WHERE sq.query_id = %s;
        """,
        (query_id,),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Search query not found")
    if not row.get("resolved_company_id"):
        raise HTTPException(status_code=409, detail="Search query has no resolved company_id yet")
    return row


def persist_inferred_abn_location(cur, row: Dict[str, Any], location: Dict[str, Any]) -> Optional[str]:
    try:
        cur.execute("SAVEPOINT inferred_location_write;")
        cur.execute(
            """
            INSERT INTO inferred_location
                (company_id, source_type, abn_ref, label, address_raw, state, postcode,
                 country, latitude, longitude, confidence, prov_agent)
            VALUES (%s, 'abn', %s, %s, %s, %s, %s, %s, %s, %s, %s, 'EcoTrace ABN postcode centroid')
            ON CONFLICT ON CONSTRAINT uq_inferred_location_source DO UPDATE SET
                label = EXCLUDED.label,
                address_raw = EXCLUDED.address_raw,
                state = EXCLUDED.state,
                postcode = EXCLUDED.postcode,
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude,
                confidence = EXCLUDED.confidence,
                extracted_at = NOW()
            RETURNING location_id;
            """,
            (
                row["company_id"],
                row["abn"],
                location["label"],
                location["address_raw"],
                location["state"],
                location["postcode"],
                location["country"],
                location["lat"],
                location["lon"],
                location["confidence"],
            ),
        )
        saved = cur.fetchone()
        cur.execute("RELEASE SAVEPOINT inferred_location_write;")
        return str(saved["location_id"]) if saved else None
    except Exception as error:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT inferred_location_write;")
        except Exception:
            pass
        print(f"[Spatial] inferred_location write skipped: {error}")
        return None


def persist_inferred_evidence_location(cur, row: Dict[str, Any], location: Dict[str, Any]) -> Optional[str]:
    try:
        cur.execute("SAVEPOINT inferred_evidence_location_write;")
        cur.execute(
            """
            INSERT INTO inferred_location
                (company_id, source_type, report_id, label, address_raw, state, postcode,
                 country, latitude, longitude, confidence, prov_agent)
            VALUES (%s, 'report', %s, %s, %s, %s, %s, %s, %s, %s, %s, 'EcoTrace extracted evidence centroid')
            ON CONFLICT ON CONSTRAINT uq_inferred_location_source DO UPDATE SET
                report_id = COALESCE(EXCLUDED.report_id, inferred_location.report_id),
                label = EXCLUDED.label,
                address_raw = EXCLUDED.address_raw,
                state = EXCLUDED.state,
                postcode = EXCLUDED.postcode,
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude,
                confidence = EXCLUDED.confidence,
                extracted_at = NOW()
            RETURNING location_id;
            """,
            (
                row["company_id"],
                location.get("report_id"),
                location["label"],
                location["address_raw"],
                location["state"],
                location["postcode"],
                location["country"],
                location["lat"],
                location["lon"],
                location["confidence"],
            ),
        )
        saved = cur.fetchone()
        cur.execute("RELEASE SAVEPOINT inferred_evidence_location_write;")
        return str(saved["location_id"]) if saved else None
    except Exception as error:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT inferred_evidence_location_write;")
        except Exception:
            pass
        print(f"[Spatial] evidence inferred_location write skipped: {error}")
        return None


def persist_report_evidence_locations(
    cur,
    query_id: str,
    report_id: str,
    metadata: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not isinstance(metadata, dict):
        return []

    row = get_query_company_location(cur, query_id)
    persisted: List[Dict[str, Any]] = []
    seen = set()
    for candidate in evidence_location_candidates(metadata):
        key = (
            round(float(candidate["lat"]), 5),
            round(float(candidate["lon"]), 5),
            str(candidate.get("label") or "").lower(),
        )
        if key in seen:
            continue
        seen.add(key)

        location = dict(candidate)
        location.pop("rank", None)
        location["report_id"] = report_id
        location_id = persist_inferred_evidence_location(cur, row, location)
        if location_id:
            persisted.append(
                {
                    "location_id": location_id,
                    "report_id": report_id,
                    "label": location.get("label"),
                    "state": location.get("state"),
                    "lat": location.get("lat"),
                    "lon": location.get("lon"),
                    "radius_km": location.get("radius_km"),
                    "confidence": location.get("confidence"),
                    "source": location.get("source"),
                    "method": location.get("method"),
                    "evidence_location": location.get("evidence_location"),
                }
            )
    return persisted


def best_persisted_inferred_location(cur, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    cur.execute(
        """
        SELECT location_id, source_type::text AS source_type, report_id, article_id,
               label, address_raw, state, postcode, country, latitude, longitude,
               confidence::text AS confidence, prov_agent, extracted_at
        FROM inferred_location
        WHERE company_id = %s
          AND valid_to IS NULL
          AND latitude IS NOT NULL
          AND longitude IS NOT NULL
        ORDER BY
          CASE source_type WHEN 'report' THEN 1 WHEN 'news' THEN 2 WHEN 'abn' THEN 3 ELSE 4 END,
          CASE
            WHEN lower(COALESCE(label, '') || ' ' || COALESCE(address_raw, '')) LIKE '%%pilbara%%' THEN 1
            WHEN lower(COALESCE(label, '') || ' ' || COALESCE(address_raw, '')) LIKE '%%olympic dam%%' THEN 1
            WHEN lower(COALESCE(label, '') || ' ' || COALESCE(address_raw, '')) LIKE '%%port hedland%%' THEN 1
            WHEN lower(COALESCE(label, '') || ' ' || COALESCE(address_raw, '')) LIKE '%%mt arthur%%' THEN 1
            WHEN lower(COALESCE(label, '') || ' ' || COALESCE(address_raw, '')) LIKE '%%mount arthur%%' THEN 1
            WHEN lower(COALESCE(label, '') || ' ' || COALESCE(address_raw, '')) LIKE '%%bowen basin%%' THEN 1
            ELSE 2
          END,
          CASE confidence WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END,
          extracted_at DESC
        LIMIT 1;
        """,
        (row["company_id"],),
    )
    saved = cur.fetchone()
    if not saved:
        return None

    source_type = saved.get("source_type")
    evidence_derived = source_type in {"report", "news"}
    method = (
        "persisted extracted evidence location"
        if evidence_derived
        else "persisted ABN location"
    )
    return {
        "location_id": str(saved["location_id"]),
        "report_id": str(saved["report_id"]) if saved.get("report_id") else None,
        "article_id": str(saved["article_id"]) if saved.get("article_id") else None,
        "label": saved.get("label") or saved.get("address_raw") or "Inferred company location",
        "address_raw": saved.get("address_raw"),
        "state": saved.get("state"),
        "postcode": saved.get("postcode"),
        "country": saved.get("country") or "AU",
        "lat": float(saved["latitude"]),
        "lon": float(saved["longitude"]),
        "radius_km": 50.0 if evidence_derived else 10.0,
        "confidence": saved.get("confidence") or "medium",
        "method": method,
        "source": f"inferred_location_{source_type}",
    }


def spatial_context_for_query(query_id: str, persist_location: bool = False) -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()
    try:
        row = get_query_company_location(cur, query_id)
        location = best_persisted_inferred_location(cur, row)
        location_source = "persisted"
        if not location:
            location = infer_location_from_latest_report(cur, query_id)
            location_source = "evidence"
        if not location:
            location = infer_location_from_abn(row)
            location_source = "abn"

        if persist_location and location_source == "evidence":
            location_id = persist_inferred_evidence_location(cur, row, location)
        elif persist_location and location_source == "abn":
            location_id = persist_inferred_abn_location(cur, row, location)
        else:
            location_id = location.get("location_id")
        if persist_location:
            conn.commit()
        return {
            "query_id": str(row["query_id"]),
            "input_type": row["input_type"],
            "input_value": row["input_value"],
            "resolution_status": row["resolution_status"],
            "company": {
                "company_id": str(row["company_id"]),
                "legal_name": row["legal_name"],
                "abn": row["abn"],
                "entity_type": row["entity_type"],
                "company_status": row["company_status"],
                "state": row["state"],
                "postcode": row["postcode"],
                "gst_registered": row["gst_registered"],
            },
            "location": {**location, "location_id": location_id},
        }
    except Exception:
        if persist_location:
            conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def build_layer_a_response(result, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    all_species = [serialize_species_record(species) for species in result.unique_species]
    threatened_species = [
        serialize_species_record(species)
        for species in result.threatened_species
    ]
    iucn_assessed_species = sum(
        1 for species in result.unique_species if species.iucn_category
    )

    response = {
        "status": "success",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "location": {
            "lat": result.lat,
            "lon": result.lon,
            "radius_km": result.radius_km,
        },
        "data_sources": [
            "Atlas of Living Australia Biocache",
            "IUCN Red List v4",
        ],
        "total_ala_records": result.total_ala_records,
        "unique_species_count": len(result.unique_species),
        "iucn_assessed_species": iucn_assessed_species,
        "threatened_species_count": len(result.threatened_species),
        "species_threat_score": result.species_threat_score,
        "score_breakdown": result.score_breakdown,
        "threatened_species": threatened_species,
        "all_species": all_species,
    }
    if context:
        response["query"] = {
            "query_id": context["query_id"],
            "input_type": context["input_type"],
            "input_value": context["input_value"],
            "resolution_status": context["resolution_status"],
        }
        response["company"] = context["company"]
        response["inferred_location"] = context["location"]
    return response


def refresh_latest_report_with_spatial(query_id: str, spatial_payload: Dict[str, Any]) -> None:
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT report_id, metadata_json
            FROM report
            WHERE query_id = %s
            ORDER BY generated_at DESC
            LIMIT 1;
            """,
            (query_id,),
        )
        row = cur.fetchone()
        if not row:
            return
        metadata = row.get("metadata_json") if isinstance(row.get("metadata_json"), dict) else {}
        metadata = {**metadata, "spatial_analysis": spatial_payload}
        refresh_persisted_report_content(cur, str(row["report_id"]), metadata)
        conn.commit()
    except Exception as error:
        conn.rollback()
        print(f"[Report] Spatial report refresh skipped: {error}")
    finally:
        cur.close()
        conn.close()


def run_spatial_analysis_for_query(query_id: str, force: bool = False) -> Dict[str, Any]:
    with SPATIAL_ANALYSIS_LOCK:
        cached = SPATIAL_ANALYSIS_CACHE.get(query_id)
        if cached and cached.get("status") == "success" and not force:
            return cached
        SPATIAL_ANALYSIS_CACHE[query_id] = {
            "status": "loading",
            "query_id": query_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

    try:
        context = spatial_context_for_query(query_id, persist_location=True)
        location = context["location"]
        result = run_layer_a(
            lat=location["lat"],
            lon=location["lon"],
            radius_km=location["radius_km"],
            max_species=50,
        )
        payload = build_layer_a_response(result, context)
        with SPATIAL_ANALYSIS_LOCK:
            SPATIAL_ANALYSIS_CACHE[query_id] = payload
        refresh_latest_report_with_spatial(query_id, payload)
        return payload
    except Exception as error:
        payload = {
            "status": "failed",
            "query_id": query_id,
            "error": str(error),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        with SPATIAL_ANALYSIS_LOCK:
            SPATIAL_ANALYSIS_CACHE[query_id] = payload
        raise


def start_spatial_analysis_for_query(query_id: Optional[str], force: bool = False):
    if not query_id:
        return

    with SPATIAL_ANALYSIS_LOCK:
        cached = SPATIAL_ANALYSIS_CACHE.get(query_id)
        if cached and cached.get("status") in ("loading", "success") and not force:
            return

    def _run():
        try:
            run_spatial_analysis_for_query(query_id, force=force)
            print(f"[Spatial] Layer A ready for query {query_id}")
        except Exception as error:
            print(f"[Spatial] Layer A failed for query {query_id}: {error}")

    threading.Thread(target=_run, daemon=True).start()


# ============================================================
# Basic Endpoints
# ============================================================

@app.get("/")
def root():
    return {
        "message":       "EcoTrace backend is running",
        "main_endpoint": "POST /api/search",
        "consumer_flow": "query_id based, no login required",
        "version":       "6.0.0",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


# ============================================================
# Development User Endpoint
# ============================================================

@app.post("/api/users/test")
def create_test_user(payload: CreateUserRequest):
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO "user" (user_type, email)
            VALUES (%s, %s)
            ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email
            RETURNING user_id, user_type, email, created_at;
            """,
            (payload.user_type, payload.email),
        )
        user = cur.fetchone()
        conn.commit()
        return {"message": "User ready", "user": serialize_row(user)}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@app.post("/api/auth/request-verification")
def request_email_verification(payload: RequestEmailVerificationRequest):
    email = payload.email.strip().lower()
    if not valid_email(email):
        raise HTTPException(status_code=400, detail="Please provide a valid email address")

    return_to = verification_return_path(payload.return_to)
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    verify_url = (
        f"{frontend_base_url()}/app/verify-email"
        f"?token={quote(token)}&return_to={quote(return_to, safe='')}"
    )
    html_body = f"""<!doctype html>
<html>
<body style="font-family:Arial,sans-serif;color:#1c1917;line-height:1.5">
  <h2>Verify your EcoTrace email</h2>
  <p>Click the button below to unlock your EcoTrace workspace. This link expires in 30 minutes.</p>
  <p>
    <a href="{verify_url}" style="display:inline-block;background:#047857;color:white;padding:12px 18px;border-radius:8px;text-decoration:none">
      Verify email
    </a>
  </p>
  <p>If the button does not work, open this link:</p>
  <p><a href="{verify_url}">{verify_url}</a></p>
</body>
</html>"""

    conn = get_conn()
    cur = conn.cursor()
    try:
        ensure_email_verification_table(cur)
        cur.execute(
            """
            INSERT INTO "user" (user_type, email)
            VALUES ('consumer', %s)
            ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email
            RETURNING user_id;
            """,
            (email,),
        )
        user_id = cur.fetchone()["user_id"]
        delivery = deliver_report_email(email, "Verify your EcoTrace email", html_body)
        cur.execute(
            """
            INSERT INTO email_verification
                (user_id, email, token_hash, return_to, expires_at, delivery_method)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING verification_id, requested_at, expires_at;
            """,
            (user_id, email, token_hash(token), return_to, expires_at, delivery["delivery"]),
        )
        verification = serialize_row(cur.fetchone())
        conn.commit()
        return {
            "status": "sent",
            "email": email,
            "delivery": delivery["delivery"],
            "path": delivery.get("path"),
            "verification": verification,
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=502, detail=f"Verification email failed: {e}")
    finally:
        cur.close()
        conn.close()


@app.post("/api/auth/confirm-verification")
def confirm_email_verification(payload: ConfirmEmailVerificationRequest):
    token = payload.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Verification token is required")

    conn = get_conn()
    cur = conn.cursor()
    try:
        ensure_email_verification_table(cur)
        cur.execute(
            """
            UPDATE email_verification
            SET verified_at = NOW()
            WHERE token_hash = %s
              AND verified_at IS NULL
              AND expires_at > NOW()
            RETURNING verification_id, user_id, email, return_to, verified_at;
            """,
            (token_hash(token),),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=400, detail="Verification link is invalid or expired")
        conn.commit()
        return {"status": "verified", "verification": serialize_row(row)}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


# ============================================================
# Main Consumer Search Endpoint
# ============================================================

@app.post("/api/search")
def search_entity(payload: SearchRequest):
    """
    Main consumer search endpoint.

    Steps
    -----
    1. Validate exactly one input type.
    2. Insert a pending search_query record (obtains query_id).
    3. Dispatch to the appropriate pipeline module.
    4. Persist pipeline results to DB (abn_record, company, trademark, brand, product).
    5. Update search_query to resolved / failed with resolved entity IDs.
    6. Return a unified JSON response.
    """
    barcode        = clean_text(payload.barcode)
    brand          = clean_text(payload.brand)
    company_or_abn = clean_text(payload.company_or_abn)

    input_type, input_value, frontend_type = get_single_input_type(
        barcode, brand, company_or_abn
    )

    conn = get_conn()
    cur  = conn.cursor()

    try:
        query    = create_search_query(cur, input_type, input_value, payload.user_id)
        query_id = query["query_id"]

        pipeline_steps: List[str] = []
        result:         Dict[str, Any] = {}
        db_status = "failed"

        # resolved entity IDs — populated by each branch if DB write succeeds
        resolved_company_id: Optional[str] = None
        resolved_brand_id:   Optional[str] = None
        resolved_product_id: Optional[str] = None

        # --------------------------------------------------------
        # Branch 1 — Company name / ABN
        # Writes: abn_record, company
        # --------------------------------------------------------
        if input_type == "company_name":
            phase = run_company_abn_phase(company_or_abn)

            pipeline_steps = phase.get("pipeline", [])
            db_status      = "resolved" if phase["success"] else "failed"

            company_block = phase.get("company") or {
                "legal_name":     phase.get("legal_name"),
                "abn":            phase.get("abn"),
                "entity_type":    phase.get("entity_type"),
                "acn":            phase.get("acn"),
                "state":          phase.get("state"),
                "postcode":       phase.get("postcode"),
                "abn_status":     phase.get("abn_status"),
                "gst_registered": phase.get("gst_registered", False),
                "main_activity":  phase.get("main_activity"),
            }

            result = {
                "input_type":     "abn" if phase.get("valid_format") is not None else "company_name",
                "input_value":    input_value,
                "status":         phase.get("status", "not_found"),
                "source":         "ABR",
                "company":        company_block,
                "all_results":    phase.get("all_results", []),
                "total_results":  phase.get("total", 0),
                "valid_checksum": phase.get("valid_checksum"),
                "confidence":     phase.get("confidence", 0),
                "errors":         phase.get("errors", []),
                "message":        phase.get("error"),
            }

            # --- DB write ---
            if phase["success"] and company_block.get("abn"):
                resolved_company_id = upsert_company(cur, company_block)
                if resolved_company_id:
                    pipeline_steps.append(
                        f"DB: abn_record and company upserted (company_id={resolved_company_id})"
                    )
                else:
                    pipeline_steps.append("DB: company write failed (see server log)")

            db_status = "resolved" if resolved_company_id else "failed"

        # --------------------------------------------------------
        # Branch 2 — Barcode
        # Writes: abn_record, company, trademark, brand, product
        # --------------------------------------------------------
        elif input_type == "barcode":
            phase = run_barcode_phase(
                barcode,
                abr_lookup_fn=search_company_name_with_abr,
            )
            pipeline_steps = phase.get("pipeline", [])
            db_status      = "resolved" if phase["success"] else "failed"

            result = {
                "input_type":       "barcode",
                "input_value":      barcode,
                "status":           phase.get("status", "not_found"),
                "source":           phase.get("source"),
                "product":          phase.get("product"),
                "brand_raw":        phase.get("brand_raw"),
                "brand_clean":      phase.get("brand_clean"),
                "brand_owner":      phase.get("brand_owner"),
                "manufacturer":     phase.get("manufacturer"),
                "abn_verification": phase.get("abr"),
                "confidence":       phase.get("confidence", 0),
                "errors":           phase.get("errors", []),
                "message":          phase.get("error"),
            }

            # --- DB write ---
            if phase["success"]:
                # 1. Company from ABR result
                abr_data = extract_abr_data(phase.get("abr") or {})
                if abr_data:
                    resolved_company_id = upsert_company(cur, abr_data)
                    if resolved_company_id:
                        pipeline_steps.append(
                            f"DB: company upserted (company_id={resolved_company_id})"
                        )

                # 2. Trademark
                tm = phase.get("trademark") or {}
                trademark_id: Optional[str] = None
                if tm.get("number"):
                    trademark_id = upsert_trademark(cur, tm)
                    if trademark_id:
                        pipeline_steps.append(
                            f"DB: trademark upserted (trademark_id={trademark_id})"
                        )

                # 3. Brand
                brand_name_for_db = (
                    phase.get("brand_clean")
                    or phase.get("brand_owner")
                    or phase.get("brand_raw")
                )
                if resolved_company_id and brand_name_for_db:
                    resolved_brand_id = upsert_brand(
                        cur, brand_name_for_db, resolved_company_id, trademark_id
                    )
                    if resolved_brand_id:
                        pipeline_steps.append(
                            f"DB: brand upserted (brand_id={resolved_brand_id})"
                        )

                # 4. Product
                product_block = phase.get("product") or {}
                barcode_clean = phase.get("barcode") or barcode
                if resolved_brand_id and barcode_clean:
                    resolved_product_id = upsert_product(
                        cur,
                        {
                            "barcode":           barcode_clean,
                            "product_name":      product_block.get("product_name"),
                            "manufacturer_name": phase.get("manufacturer"),
                            "data_source":       "open_food_facts",
                        },
                        resolved_brand_id,
                    )
                    if resolved_product_id:
                        pipeline_steps.append(
                            f"DB: product upserted (product_id={resolved_product_id})"
                        )

        # --------------------------------------------------------
        # Branch 3 — Brand name
        # Writes: abn_record, company, trademark, brand
        # --------------------------------------------------------
        elif input_type == "brand_name":
            phase = run_brand_phase(
                brand,
                abr_lookup_fn=search_company_name_with_abr,
            )
            pipeline_steps = phase.get("pipeline", [])
            db_status      = "resolved" if phase["success"] else "failed"

            result = {
                "input_type":       "brand",
                "input_value":      brand,
                "status":           phase.get("status", "not_found"),
                "source":           "IP Australia Trade Mark + ABR",
                "brand_name":       brand,
                "trademark":        phase.get("trademark"),
                "legal_owner":      phase.get("legal_owner"),
                "abn_verification": phase.get("abr"),
                "confidence":       phase.get("confidence", 0),
                "errors":           phase.get("errors", []),
                "message":          phase.get("error"),
            }

            # --- DB write ---
            if phase["success"]:
                # 1. Company — prefer full ABR result, fall back to owner_abn from TM record
                abr_data = extract_abr_data(phase.get("abr") or {})
                if abr_data:
                    resolved_company_id = upsert_company(cur, abr_data)
                elif phase.get("owner_abn"):
                    resolved_company_id = upsert_company(cur, {
                        "abn":            phase["owner_abn"],
                        "legal_name":     phase.get("legal_owner") or "Unknown",
                        "entity_type":    "OTHER",
                        "gst_registered": False,
                    })

                if resolved_company_id:
                    pipeline_steps.append(
                        f"DB: company upserted (company_id={resolved_company_id})"
                    )

                # 2. Trademark
                tm = phase.get("trademark") or {}
                trademark_id = None
                if tm.get("number"):
                    trademark_id = upsert_trademark(
                        cur,
                        {**tm, "legal_owner": phase.get("legal_owner")},
                    )
                    if trademark_id:
                        pipeline_steps.append(
                            f"DB: trademark upserted (trademark_id={trademark_id})"
                        )

                # 3. Brand
                if resolved_company_id:
                    resolved_brand_id = upsert_brand(
                        cur, brand, resolved_company_id, trademark_id
                    )
                    if resolved_brand_id:
                        pipeline_steps.append(
                            f"DB: brand upserted (brand_id={resolved_brand_id})"
                        )

        # --------------------------------------------------------
        # Finalise: update search_query with resolved IDs
        # --------------------------------------------------------
        if db_status == "resolved" and not resolved_company_id:
            db_status = "failed"

        update_search_query(
            cur,
            query_id,
            db_status,
            resolved_company_id,
            resolved_brand_id,
            resolved_product_id,
        )
        conn.commit()
        if db_status == "resolved" and resolved_company_id:
            start_spatial_analysis_for_query(str(query_id))

        return {
            "query_id":          str(query_id),
            "status":            "success",
            "input_type":        frontend_type,
            "input_value":       input_value,
            "resolution_status": db_status,
            "resolved_ids": {
                "company_id": resolved_company_id,
                "brand_id":   resolved_brand_id,
                "product_id": resolved_product_id,
            },
            "pipeline_steps": pipeline_steps,
            "result":         result,
        }

    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


# ============================================================
# Company Evidence Analysis
# ============================================================

def _basename(path: str) -> str:
    return path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]


def original_report_names(reports: Optional[List[UploadFile]]) -> List[str]:
    if not reports:
        return []
    return [Path(report.filename or "uploaded-report").name for report in reports]


def remap_report_record_sources(
    records: List[Dict[str, Any]],
    saved_to_original: Dict[str, str],
) -> List[Dict[str, Any]]:
    remapped = []
    for record in records:
        next_record = dict(record)
        source = next_record.get("source")
        if isinstance(source, str):
            source_name = _basename(source)
            if source_name in saved_to_original:
                next_record["source"] = saved_to_original[source_name]
                next_record["source_saved_name"] = source_name
        remapped.append(next_record)
    return remapped


@app.post("/api/analyse/company")
def analyse_company_with_reports(
    company_or_abn: str = Form(...),
    reports: Optional[List[UploadFile]] = File(default=None),
    news_limit: int = Form(3),
    max_llm_results: int = Form(3),
    max_report_chunks: int = Form(3),
    australia_only: bool = Form(True),
):
    """
    Resolve a company/ABN, then analyse news evidence and uploaded reports.

    This endpoint keeps the LLM/report flow separate from the consumer
    barcode/brand/company resolver used by POST /api/search.
    """
    original_names = original_report_names(reports)
    saved_report_paths = save_uploaded_reports(reports)
    saved_to_original = {
        _basename(saved_path): original_name
        for saved_path, original_name in zip(saved_report_paths, original_names)
    }

    try:
        resolution = resolve_company_for_analysis(company_or_abn)
        normalized_name = resolution["normalized_name"]
        query_id = None
        resolved_company_id = None
        database_error = None
        db_pipeline_steps: List[str] = []

        try:
            conn = get_conn()
            cur = conn.cursor()
            try:
                query_id, resolved_company_id, db_pipeline_steps = persist_company_resolution(
                    cur,
                    input_value=company_or_abn,
                    resolution=resolution,
                )
                conn.commit()
                if query_id and resolved_company_id:
                    start_spatial_analysis_for_query(query_id)
            finally:
                cur.close()
                conn.close()
        except Exception as error:
            database_error = str(error)
            query_id = str(uuid4())

        pipeline_steps = [
            "ABR company lookup" if resolution["input_type"] == "company_name" else "ABR ABN verification",
            "Legal name normalization",
            *db_pipeline_steps,
            "News API search",
            "Uploaded report scan",
            "LLM evidence extraction",
        ]

        news_candidates, news_records = collect_news_evidence(
            normalized_name,
            resolution["queries"],
            limit=max(1, min(news_limit, 10)),
            max_llm_results=max(0, min(max_llm_results, 10)),
            australia_only=australia_only,
        )

        report_paths = saved_report_paths
        report_records = collect_report_evidence(
            normalized_name,
            report_paths,
            max_report_chunks=max_report_chunks,
        )
        report_records = remap_report_record_sources(report_records, saved_to_original)

        return {
            "query_id": query_id,
            "status": "success",
            "database_error": database_error,
            "resolved_company_id": resolved_company_id,
            "pipeline_steps": pipeline_steps,
            "resolution": {
                "input_type": resolution["input_type"],
                "input_value": resolution["input_value"],
                "alias_abn": resolution["alias_abn"],
                "legal_name": resolution["legal_name"],
                "normalized_name": normalized_name,
                "abn": resolution["abr"].get("abn"),
                "state": resolution["abr"].get("state"),
                "postcode": resolution["abr"].get("postcode"),
                "abn_status": resolution["abr"].get("abn_status"),
                "abr": resolution["abr"],
            },
            "search_queries": resolution["queries"],
            "uploaded_reports": [
                saved_to_original.get(_basename(path), _basename(path))
                for path in saved_report_paths
            ],
            "analysed_reports": [
                saved_to_original.get(_basename(path), _basename(path))
                for path in report_paths
            ],
            "saved_report_files": [_basename(path) for path in saved_report_paths],
            "reports_deleted_after_analysis": bool(saved_report_paths),
            "news": {
                "candidate_count": len(news_candidates),
                "candidates": news_candidates,
                "evidence": news_records,
            },
            "reports": {
                "evidence_count": len(report_records),
                "evidence": report_records,
            },
        }
    finally:
        delete_temporary_reports(saved_report_paths)


@app.post("/api/analyse/company/resolve")
def resolve_company_analysis_target(company_or_abn: str = Form(...)):
    """
    Resolve company identity quickly before slower news/report evidence extraction.
    """
    resolution = resolve_company_for_analysis(company_or_abn)
    query_id = None
    resolved_company_id = None
    database_error = None
    db_pipeline_steps: List[str] = []

    try:
        conn = get_conn()
        cur = conn.cursor()
        try:
            query_id, resolved_company_id, db_pipeline_steps = persist_company_resolution(
                cur,
                input_value=company_or_abn,
                resolution=resolution,
            )
            conn.commit()
            if query_id and resolved_company_id:
                start_spatial_analysis_for_query(query_id)
        finally:
            cur.close()
            conn.close()
    except Exception as error:
        database_error = str(error)
        query_id = str(uuid4())

    return {
        "status": "success",
        "query_id": query_id,
        "resolved_company_id": resolved_company_id,
        "database_error": database_error,
        "pipeline_steps": db_pipeline_steps,
        "resolution": {
            "input_type": resolution["input_type"],
            "input_value": resolution["input_value"],
            "alias_abn": resolution["alias_abn"],
            "legal_name": resolution["legal_name"],
            "normalized_name": resolution["normalized_name"],
            "abn": resolution["abr"].get("abn"),
            "state": resolution["abr"].get("state"),
            "postcode": resolution["abr"].get("postcode"),
            "abn_status": resolution["abr"].get("abn_status"),
            "abr": resolution["abr"],
        },
        "search_queries": resolution["queries"],
    }


# ============================================================
# Spatial Biodiversity Analysis
# ============================================================

def serialize_species_record(species: SpeciesRecord) -> Dict[str, Any]:
    return {
        "scientific_name": species.scientific_name,
        "common_name": species.common_name,
        "taxon_rank": species.taxon_rank,
        "record_count": species.record_count,
        "iucn_category": species.iucn_category,
        "iucn_category_name": species.iucn_category_name,
        "threat_weight": species.threat_weight,
        "iucn_url": species.iucn_url,
    }


@app.get("/api/spatial/layer-a")
def spatial_layer_a_analysis(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(10.0, gt=0, le=100),
    max_species: int = Query(50, ge=1, le=1000),
):
    """
    Run Layer A spatial biodiversity analysis for a WGS84 point.

    Layer A queries ALA Biocache for local species occurrences, enriches
    species with IUCN Red List categories, and returns a 0-100 threat score.
    """
    try:
        result = run_layer_a(
            lat=lat,
            lon=lon,
            radius_km=radius_km,
            max_species=max_species,
        )
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Layer A spatial analysis failed: {error}",
        )

    return build_layer_a_response(result)


@app.get("/api/spatial/query/{query_id}")
def spatial_analysis_for_query(query_id: str, force: bool = Query(False)):
    """
    Return Layer A spatial analysis for a resolved search query.
    If the analysis is not ready, start it in the background and return
    the inferred ABN location context immediately.
    """
    query_id = query_id.strip()
    if not query_id:
        raise HTTPException(status_code=400, detail="query_id is required")

    with SPATIAL_ANALYSIS_LOCK:
        cached = SPATIAL_ANALYSIS_CACHE.get(query_id)

    if cached and cached.get("status") == "success" and not force:
        return cached
    if cached and cached.get("status") == "failed" and not force:
        return cached
    if cached and cached.get("status") == "loading" and not force:
        try:
            context = spatial_context_for_query(query_id)
            return {**cached, **context}
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(status_code=500, detail=str(error))

    try:
        context = spatial_context_for_query(query_id)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))

    start_spatial_analysis_for_query(query_id, force=force)
    return {
        "status": "loading",
        "query_id": query_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        **context,
    }


@app.get("/api/spatial/iucn-cache")
def spatial_iucn_cache_status(warm: bool = Query(True)):
    if warm:
        warm_iucn_cache_in_background()
    return get_iucn_cache_status()


# ============================================================
# Standalone Test / Diagnostic Endpoints
# ============================================================

@app.get("/api/debug/trademark-auth")
def debug_trademark_auth():
    return diagnose_token()


@app.get("/api/abn/verify/{abn}")
def verify_abn_endpoint(abn: str):
    from abn_pipeline import validate_abn_checksum, run_abn_phase
    cleaned = clean_abn(abn)
    if not is_abn(cleaned):
        raise HTTPException(status_code=400, detail="ABN must be 11 digits")
    return run_abn_phase(cleaned)


@app.get("/api/company/search/{company_name}")
def lookup_company_name(company_name: str):
    from abn_pipeline import run_company_phase
    cleaned = clean_text(company_name)
    if not cleaned or len(cleaned) < 2:
        raise HTTPException(status_code=400, detail="Company name must be at least 2 characters")
    return run_company_phase(cleaned)


@app.get("/api/barcode/{barcode}")
def lookup_barcode(barcode: str):
    return run_barcode_phase(barcode, abr_lookup_fn=search_company_name_with_abr)


@app.get("/api/trademark/token-test")
def test_ip_australia_token():
    token = get_ip_australia_access_token()
    if not token:
        return {
            "status":  "error",
            "message": "Unable to obtain token — check IP_AUSTRALIA_CLIENT_ID "
                       "and IP_AUSTRALIA_CLIENT_SECRET in .env",
        }
    return {"status": "success", "token_preview": token[:20] + "..."}


@app.get("/api/trademark/search/{brand}")
def lookup_trademark(brand: str):
    cleaned = clean_text(brand)
    if not cleaned or len(cleaned) < 2:
        raise HTTPException(status_code=400, detail="Brand must be at least 2 characters")
    return run_brand_phase(cleaned, abr_lookup_fn=search_company_name_with_abr)


# ============================================================
# Search History
# ============================================================

@app.get("/api/search/history/{user_id}")
def get_search_history(user_id: str):
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute(
            """
            SELECT query_id, input_type, input_value, resolution_status,
                   resolved_company_id, resolved_brand_id, resolved_product_id, submitted_at
            FROM search_query
            WHERE user_id = %s
            ORDER BY submitted_at DESC;
            """,
            (user_id,),
        )
        rows = cur.fetchall()
        return {"user_id": user_id, "history": [serialize_row(r) for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@app.get("/api/search/query/{query_id}")
def get_search_query(query_id: str):
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute(
            """
            SELECT query_id, user_id, input_type, input_value, resolution_status,
                   resolved_company_id, resolved_brand_id, resolved_product_id, submitted_at
            FROM search_query
            WHERE query_id = %s;
            """,
            (query_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Query not found")
        return {"query": serialize_row(row)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


# ============================================================
# Report Generation and Email
# ============================================================

@app.post("/api/report/generate")
def generate_report(payload: GenerateReportRequest):
    query_id = payload.query_id.strip()
    if not query_id:
        raise HTTPException(status_code=400, detail="query_id is required")

    conn = get_conn()
    cur = conn.cursor()
    try:
        saved = create_persisted_report(cur, query_id, payload.analysis_payload)
        if not saved:
            raise HTTPException(status_code=404, detail="Query not found")
        persisted_locations = persist_report_evidence_locations(
            cur,
            query_id,
            saved["report_id"],
            saved.get("metadata_json"),
        )
        if persisted_locations:
            saved = refresh_persisted_report_content(
                cur,
                saved["report_id"],
                {
                    **(saved.get("metadata_json") or {}),
                    "spatial_analysis": SPATIAL_ANALYSIS_CACHE.get(query_id, {}),
                },
            ) or saved
        conn.commit()
        start_spatial_analysis_for_query(query_id, force=True)
        return {
            "status": "success",
            "report": saved,
            "report_id": saved["report_id"],
            "persisted_locations": persisted_locations,
        }
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@app.get("/api/report/{report_id}")
def get_report(report_id: str):
    conn = get_conn()
    cur = conn.cursor()
    try:
        report = get_persisted_report(cur, report_id.strip())
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")
        return {
            "status": "success",
            "report": {
                key: value
                for key, value in report.items()
                if key != "html_content"
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@app.get("/api/report/{report_id}/html", response_class=HTMLResponse)
def get_report_html(report_id: str):
    conn = get_conn()
    cur = conn.cursor()
    try:
        report = get_persisted_report(cur, report_id.strip())
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")
        return HTMLResponse(report["html_content"])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@app.post("/api/report/{report_id}/email")
def email_report(report_id: str, payload: SendPersistedReportEmailRequest):
    email = payload.email.strip()
    if not valid_email(email):
        raise HTTPException(status_code=400, detail="Please provide a valid email address")

    conn = get_conn()
    cur = conn.cursor()
    try:
        delivery = send_persisted_report(cur, report_id.strip(), email)
        if not delivery:
            raise HTTPException(status_code=404, detail="Report not found")
        conn.commit()
        return {"status": "success", **delivery}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=502, detail=f"Report email failed: {e}")
    finally:
        cur.close()
        conn.close()


@app.get("/api/report/query/{query_id}")
def get_query_report(query_id: str):
    conn = get_conn()
    cur = conn.cursor()
    try:
        report = build_query_report(cur, query_id)
        if not report:
            raise HTTPException(status_code=404, detail="Query not found")
        return {"status": "success", "report": report}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@app.get("/api/report/query/{query_id}/html", response_class=HTMLResponse)
def get_query_report_html(query_id: str):
    conn = get_conn()
    cur = conn.cursor()
    try:
        report = build_query_report(cur, query_id)
        if not report:
            raise HTTPException(status_code=404, detail="Query not found")
        return HTMLResponse(render_report_html(report))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@app.post("/api/report/email")
def email_query_report(payload: SendReportEmailRequest):
    email = payload.email.strip()
    query_id = payload.query_id.strip()
    if not valid_email(email):
        raise HTTPException(status_code=400, detail="Please provide a valid email address")
    if not query_id:
        raise HTTPException(status_code=400, detail="query_id is required")

    conn = get_conn()
    cur = conn.cursor()
    try:
        saved = create_persisted_report(cur, query_id)
        if not saved:
            raise HTTPException(status_code=404, detail="Query not found")
        delivery = send_persisted_report(cur, saved["report_id"], email)
        conn.commit()
        return {
            "status": "success",
            "report_id": saved["report_id"],
            "report_title": saved["title"],
            **delivery,
        }
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=502, detail=f"Report email failed: {e}")
    finally:
        cur.close()
        conn.close()
