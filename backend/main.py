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
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
from uuid import UUID, uuid4

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ------------------------------------------------------------------
# Pipeline modules
# ------------------------------------------------------------------
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace with frontend deployment URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router)


def warm_iucn_cache_in_background():
    """
    Start Layer A's IUCN Australia cache as soon as the backend is live.
    The cache is kept in memory for the lifetime of this backend process.
    """
    def _warm():
        try:
            count = ensure_iucn_cache_loaded()
            print(f"[Layer A] IUCN Australia cache ready: {count:,} species")
        except Exception as error:
            print(f"[Layer A] IUCN cache warmup failed: {error}")

    thread = threading.Thread(target=_warm, daemon=True)
    thread.start()


@app.on_event("startup")
def startup_tasks():
    warm_iucn_cache_in_background()


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


def spatial_context_for_query(query_id: str, persist_location: bool = False) -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()
    try:
        row = get_query_company_location(cur, query_id)
        location = infer_location_from_abn(row)
        location_id = persist_inferred_abn_location(cur, row, location) if persist_location else None
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
    saved_report_paths = save_uploaded_reports(reports)

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
            "uploaded_reports": [path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1] for path in saved_report_paths],
            "analysed_reports": [path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1] for path in report_paths],
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
def spatial_iucn_cache_status():
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
