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
1. barcode
2. brand
3. company_or_abn

Pipeline design
---------------
Company name / ABN:
    User enters company name or ABN
    -> ABR Web Services lookup / verification
    -> return legal name, ABN, state, postcode, GST status, ABN status

Barcode:
    User scans / enters barcode
    -> OpenFoodFacts lookup
    -> extract product, brand and manufacturer
    -> IP Australia Trade Mark Search API lookup using extracted brand
    -> extract possible legal owner
    -> ABR lookup by legal owner name if available

Brand name:
    User enters brand name
    -> IP Australia Trade Mark Search API lookup
    -> extract possible legal owner
    -> ABR lookup by legal owner name if available

Not included in this file
-------------------------
Report generation is intentionally not implemented here. The report team can
use query_id and search_query records produced by this backend.

Main endpoint
-------------
POST /api/search
"""

import os
import re
import shutil
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
from uuid import UUID, uuid4

import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Import pipeline utility functions from sibling module
from backend.run_ecotrace import (
    article_candidate_score,
    build_company_search_queries,
    company_search_name,
    dedupe_article_metadata,
    relevant_llm_candidates,
    resolve_report_paths,
    test_guardian,
    test_newsapi,
    test_newsdata,
    test_nyt,
    test_openrouter_many,
    test_serpapi,
    test_uploaded_reports,
    test_webz,
    test_freenewsapi,
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
    version="3.0.0",
    description="""
EcoTrace consumer search API.

This version follows the pipeline agreed by the team:
- Company name / ABN -> ABR Web Services
- Barcode -> OpenFoodFacts -> IP Australia Trade Mark Search -> ABR
- Brand -> IP Australia Trade Mark Search -> ABR

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


# ============================================================
# Database
# ============================================================

def get_conn():
    """
    Create a PostgreSQL database connection.

    Required .env variables:
    - DB_HOST
    - DB_PORT
    - DB_NAME
    - DB_USER
    - DB_PASSWORD
    """
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "ecotrace"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD"),
        cursor_factory=RealDictCursor,
    )


def serialize_row(row):
    """
    Convert a database row into a JSON-safe dictionary.

    UUID values are converted into strings because UUID objects are not directly
    JSON serializable.
    """
    if row is None:
        return None

    result = {}
    for key, value in row.items():
        result[key] = str(value) if isinstance(value, UUID) else value
    return result


REPORTS_DIR = REPO_ROOT / "reports"
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
    """
    Keep uploaded report filenames local to reports/ and filesystem-safe.
    """
    name = Path(filename or "uploaded-report").name
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .")
    return name or "uploaded-report"


def save_uploaded_reports(files: Optional[List[UploadFile]]) -> List[str]:
    """
    Save report uploads into reports/ temporarily and return their paths for analysis.
    """
    if not files:
        return []

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    saved_paths: List[str] = []

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
            stem = target.stem
            suffix = target.suffix
            target = REPORTS_DIR / f"{stem}-{int(time.time())}{suffix}"

        with target.open("wb") as output:
            shutil.copyfileobj(upload.file, output)
        saved_paths.append(str(target))

    return saved_paths


def delete_temporary_reports(paths: List[str]) -> None:
    """
    Remove uploaded report copies after analysis. Existing reports/ fixtures are not passed here.
    """
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
    """
    Resolve a company name or ABN through ABR, then prepare search terms.
    """
    value = company_or_abn.strip()
    if not value:
        raise HTTPException(status_code=400, detail="company_or_abn is required")

    alias_abn = KNOWN_COMPANY_ABNS.get(value.lower())

    if is_abn(value) or alias_abn:
        abn = alias_abn or clean_abn(value)
        abn_result = verify_abn_with_abr(abn)
        input_type = "abn"
    else:
        abn_result = search_company_name_with_abr(value)
        input_type = "company_name"

    legal_name = abn_result.get("legal_name") or value
    normalized_name = company_search_name(legal_name)
    queries = build_company_search_queries(normalized_name)

    return {
        "input_type": input_type,
        "input_value": value,
        "alias_abn": alias_abn,
        "abr": abn_result,
        "legal_name": legal_name,
        "normalized_name": normalized_name,
        "queries": queries,
    }


def collect_news_evidence(
    company_name: str,
    queries: List[str],
    limit: int = 3,
    max_llm_results: int = 3,
    australia_only: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Query configured news APIs and run the strongest candidates through the LLM.
    """
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


# ============================================================
# Request Models
# ============================================================

class SearchRequest(BaseModel):
    """
    Main frontend search request.

    Exactly one of barcode, brand, or company_or_abn should be provided.

    Consumer flow:
    - user_id is optional and normally not required.
    - query_id is generated by the backend for every valid search.

    Example barcode request:
    {
        "barcode": "5449000000996",
        "brand": "",
        "company_or_abn": ""
    }
    """
    user_id: Optional[str] = None
    barcode: Optional[str] = None
    brand: Optional[str] = None
    company_or_abn: Optional[str] = None


class CreateUserRequest(BaseModel):
    """
    Optional development endpoint request.

    This is kept for backward compatibility, but the current consumer search
    flow does not require user_id.
    """
    email: str
    user_type: str = "consumer"


# ============================================================
# Input Cleaning and Validation
# ============================================================

def clean_text(value: Optional[str]) -> Optional[str]:
    """
    Strip whitespace from frontend input.

    Empty strings are normalized to None.
    """
    if value is None:
        return None
    value = value.strip()
    return value if value else None


def clean_abn(value: str) -> str:
    """
    Remove spaces from an ABN input.
    """
    return re.sub(r"\s+", "", value or "")


def is_abn(value: str) -> bool:
    """
    Check whether input looks like an ABN.

    ABN must be exactly 11 digits.
    """
    value = clean_abn(value)
    return value.isdigit() and len(value) == 11


def is_barcode(value: str) -> bool:
    """
    Basic retail barcode validation.

    Most consumer product barcodes are numeric and between 8 and 14 digits.
    """
    value = (value or "").strip()
    return value.isdigit() and 8 <= len(value) <= 14


def get_single_input_type(
    barcode: Optional[str],
    brand: Optional[str],
    company_or_abn: Optional[str],
) -> Tuple[str, str, str]:
    """
    Validate that exactly one consumer input type is provided.

    Returns:
    - input_type: value compatible with search_query.input_type_enum
    - input_value: value stored in search_query.input_value
    - frontend_type: value returned to frontend

    Database enum compatibility:
    - barcode
    - brand_name
    - company_name

    Note:
    ABN is stored as company_name because the current input_type_enum does not
    include a separate 'abn' value.
    """
    provided = []

    if barcode:
        provided.append(("barcode", barcode, "barcode"))
    if brand:
        provided.append(("brand_name", brand, "brand"))
    if company_or_abn:
        provided.append(("company_name", company_or_abn, "company_or_abn"))

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

    if input_type == "barcode" and not is_barcode(input_value):
        raise HTTPException(
            status_code=400,
            detail="Invalid barcode. Barcode must be numeric and 8 to 14 digits long.",
        )

    if input_type == "brand_name" and len(input_value) < 2:
        raise HTTPException(
            status_code=400,
            detail="Invalid brand name. Brand name must contain at least 2 characters.",
        )

    if input_type == "company_name":
        cleaned = clean_abn(input_value)
        if cleaned.isdigit() and not is_abn(cleaned):
            raise HTTPException(status_code=400, detail="Invalid ABN. ABN must be 11 digits.")
        if not cleaned.isdigit() and len(input_value) < 2:
            raise HTTPException(
                status_code=400,
                detail="Invalid company name. Company name must contain at least 2 characters.",
            )

    return input_type, input_value, frontend_type


# ============================================================
# search_query Lifecycle
# ============================================================

def create_search_query(cur, input_type: str, input_value: str, user_id: Optional[str] = None):
    """
    Create a search_query record before calling external APIs.

    This guarantees every valid consumer search has a query_id even before
    resolution is complete.

    Initial status:
    - pending

    Later update_search_query changes the status to:
    - resolved
    - failed
    """
    cur.execute(
        """
        INSERT INTO search_query (
            user_id,
            input_type,
            input_value,
            resolution_status
        )
        VALUES (%s, %s, %s, 'pending')
        RETURNING query_id, submitted_at;
        """,
        (user_id, input_type, input_value),
    )
    return cur.fetchone()


def update_search_query(
    cur,
    query_id,
    status: str,
    resolved_company_id: Optional[str] = None,
    resolved_brand_id: Optional[str] = None,
    resolved_product_id: Optional[str] = None,
):
    """
    Update search_query after the pipeline finishes.

    The database enum supports:
    - pending
    - resolved
    - failed

    This function only writes database-safe status values.
    """
    if status not in ["resolved", "failed"]:
        status = "failed"

    cur.execute(
        """
        UPDATE search_query
        SET
            resolution_status = %s,
            resolved_company_id = %s,
            resolved_brand_id = %s,
            resolved_product_id = %s
        WHERE query_id = %s;
        """,
        (status, resolved_company_id, resolved_brand_id, resolved_product_id, query_id),
    )


# ============================================================
# ABR Web Services
# ============================================================

def verify_abn_with_abr(abn: str) -> Dict[str, Any]:
    """
    Verify an ABN using ABR Web Services SearchByABN.

    Required .env:
    - ABR_GUID

    Returns structured company information when found.
    """
    guid = os.getenv("ABR_GUID")

    if not guid:
        return {"success": False, "source": "ABR", "message": "ABR_GUID is missing in .env"}

    abn = clean_abn(abn)
    if not is_abn(abn):
        return {"success": False, "source": "ABR", "message": "Invalid ABN format. ABN must be 11 digits."}

    url = "https://abr.business.gov.au/abrxmlsearch/AbrXmlSearch.asmx/SearchByABNv202001"
    params = {
        "searchString": abn,
        "includeHistoricalDetails": "N",
        "authenticationGuid": guid,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()

        root = ET.fromstring(response.text)
        ns = {"abr": "http://abr.business.gov.au/ABRXMLSearch/"}

        abn_node = root.find(".//abr:identifierValue", ns)
        name_node = root.find(".//abr:organisationName", ns)
        state_node = root.find(".//abr:stateCode", ns)
        postcode_node = root.find(".//abr:postcode", ns)
        status_node = root.find(".//abr:entityStatusCode", ns)
        gst_node = root.find(".//abr:goodsAndServicesTax", ns)

        if abn_node is None:
            return {"success": False, "source": "ABR", "message": "ABN not found"}

        return {
            "success": True,
            "source": "ABR",
            "abn": abn_node.text,
            "legal_name": name_node.text if name_node is not None else None,
            "state": state_node.text if state_node is not None else None,
            "postcode": postcode_node.text if postcode_node is not None else None,
            "abn_status": status_node.text if status_node is not None else None,
            "gst_registered": gst_node is not None,
            "verified": True,
        }

    except Exception as e:
        return {"success": False, "source": "ABR", "message": str(e)}


def search_company_name_with_abr(company_name: str) -> Dict[str, Any]:
    """
    Search ABR by company/business name.

    Pipeline use:
    - User enters company name directly
    - Trademark API returns a legal owner name

    Required .env:
    - ABR_GUID

    This uses ABRSearchByNameAdvancedSimpleProtocol2017 and returns the first
    matching business entity when available.
    """
    guid = os.getenv("ABR_GUID")

    if not guid:
        return {"success": False, "source": "ABR", "message": "ABR_GUID is missing in .env"}

    if not company_name or len(company_name.strip()) < 2:
        return {"success": False, "source": "ABR", "message": "Company name is too short"}

    url = "https://abr.business.gov.au/abrxmlsearch/AbrXmlSearch.asmx/ABRSearchByNameAdvancedSimpleProtocol2017"
    params = {
        "name": company_name.strip(),
        "postcode": "",
        "legalName": "Y",
        "tradingName": "Y",
        "NSW": "Y",
        "SA": "Y",
        "ACT": "Y",
        "VIC": "Y",
        "WA": "Y",
        "NT": "Y",
        "QLD": "Y",
        "TAS": "Y",
        "authenticationGuid": guid,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()

        root = ET.fromstring(response.text)
        ns = {"abr": "http://abr.business.gov.au/ABRXMLSearch/"}

        business = root.find(".//abr:businessEntity", ns)
        if business is None:
            return {"success": False, "source": "ABR", "message": "No company found from ABR"}

        abn_node = business.find(".//abr:identifierValue", ns)
        name_node = business.find(".//abr:organisationName", ns)
        state_node = business.find(".//abr:stateCode", ns)
        postcode_node = business.find(".//abr:postcode", ns)
        status_node = business.find(".//abr:entityStatusCode", ns)

        return {
            "success": True,
            "source": "ABR",
            "abn": abn_node.text if abn_node is not None else None,
            "legal_name": name_node.text if name_node is not None else company_name,
            "state": state_node.text if state_node is not None else None,
            "postcode": postcode_node.text if postcode_node is not None else None,
            "abn_status": status_node.text if status_node is not None else None,
            "verified": abn_node is not None,
        }

    except Exception as e:
        return {"success": False, "source": "ABR", "message": str(e)}


# ============================================================
# OpenFoodFacts Barcode Lookup
# ============================================================

def lookup_barcode_openfoodfacts(barcode: str) -> Dict[str, Any]:
    """
    Look up product information from OpenFoodFacts.

    Pipeline use:
    - Barcode input
    - Extract product name, brand, manufacturer, image, and categories

    OpenFoodFacts can reject requests without a User-Agent header, so a
    project-specific User-Agent is included.
    """
    if not is_barcode(barcode):
        return {"success": False, "source": "OpenFoodFacts", "message": "Invalid barcode format"}

    url = f"https://world.openfoodfacts.org/api/v2/product/{barcode}.json"
    headers = {
        "User-Agent": "EcoTrace-App/1.0 (student project)",
        "Accept": "application/json",
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get("status") != 1:
            return {"success": False, "source": "OpenFoodFacts", "message": "Product not found"}

        product = data.get("product", {})
        return {
            "success": True,
            "source": "OpenFoodFacts",
            "barcode": barcode,
            "product_name": product.get("product_name"),
            "brand": product.get("brands"),
            "manufacturer": product.get("manufacturing_places"),
            "categories": product.get("categories"),
            "image_url": product.get("image_url"),
        }

    except Exception as e:
        return {"success": False, "source": "OpenFoodFacts", "message": str(e)}


# ============================================================
# IP Australia Trade Mark Search API
# ============================================================

_IP_AUS_TOKEN_CACHE = {
    "access_token": None,
    "expires_at": 0,
}


def get_ip_australia_access_token() -> Optional[str]:
    now = int(time.time())
    cached_token = _IP_AUS_TOKEN_CACHE.get("access_token")
    expires_at = int(_IP_AUS_TOKEN_CACHE.get("expires_at") or 0)

    if cached_token and now < expires_at - 60:
        return cached_token

    client_id = (os.getenv("IP_AUSTRALIA_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("IP_AUSTRALIA_CLIENT_SECRET") or "").strip()

    if not client_id or not client_secret:
        print("IP Australia token error: missing client_id or client_secret")
        return None

    token_url = (
        os.getenv(
            "IP_AUSTRALIA_TOKEN_URL",
            "https://test.api.ipaustralia.gov.au/public/external-token-api/v1/access_token",
        )
        or ""
    ).strip()

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }

    form_data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }

    try:
        response = requests.post(
            token_url,
            headers=headers,
            data=form_data,
            timeout=20,
        )

        if not response.ok:
            print("IP Australia token error status:", response.status_code)
            print("IP Australia token error body:", response.text)
            print("Token URL:", token_url)
            print("Client ID starts with:", client_id[:6])
            return None

        token_data = response.json()
        access_token = token_data.get("access_token")
        expires_in = int(token_data.get("expires_in", 3600))

        if not access_token:
            print("IP Australia token error: no access_token in response")
            print("Response JSON:", token_data)
            return None

        _IP_AUS_TOKEN_CACHE["access_token"] = access_token
        _IP_AUS_TOKEN_CACHE["expires_at"] = now + expires_in

        return access_token

    except Exception as e:
        print("IP Australia token exception:", repr(e))
        return None


def extract_first_legal_owner_from_trademark(raw_data: Any) -> Optional[str]:
    """
    Best-effort extraction of legal owner / applicant name from IP Australia data.

    The exact response shape can vary, so this function checks multiple common
    fields recursively:
    - owner
    - owners
    - applicant
    - applicants
    - holder
    - name
    - organisationName

    If no owner-like value is found, None is returned.
    """
    owner_keys = {
        "owner",
        "owners",
        "applicant",
        "applicants",
        "holder",
        "holders",
        "legalOwner",
        "legal_owner",
        "organisationName",
        "organizationName",
    }

    def recursive_find(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in owner_keys:
                    if isinstance(child, str) and child.strip():
                        return child.strip()
                    if isinstance(child, list) and child:
                        found = recursive_find(child[0])
                        if found:
                            return found
                    if isinstance(child, dict):
                        found = recursive_find(child)
                        if found:
                            return found

            # Many APIs store names under generic 'name' fields inside owner/applicant objects.
            if "name" in value and isinstance(value["name"], str) and value["name"].strip():
                return value["name"].strip()

            for child in value.values():
                found = recursive_find(child)
                if found:
                    return found

        if isinstance(value, list):
            for item in value:
                found = recursive_find(item)
                if found:
                    return found

        return None

    return recursive_find(raw_data)


def search_trademark_ip_australia(brand_name: str) -> Dict[str, Any]:
    """
    Search IP Australia Trade Mark Search API by brand name.

    Pipeline use:
    - Brand input -> Trade Mark API -> possible legal owner
    - Barcode input -> OpenFoodFacts extracts brand -> Trade Mark API -> possible legal owner

    Required .env variables for live API:
    - IP_AUSTRALIA_CLIENT_ID
    - IP_AUSTRALIA_CLIENT_SECRET

    If OAuth credentials are missing or the live API fails, the function returns
    success=False with a clear message. The search_query will still be created
    and updated by /api/search.
    """
    base_url = os.getenv(
    "IP_AUSTRALIA_TRADEMARK_URL",
    "https://test.api.ipaustralia.gov.au/public/australian-trade-mark-search-api/v1",
    ).rstrip("/")

    access_token = get_ip_australia_access_token()
    if not access_token:
        return {
            "success": False,
            "source": "IP Australia Trade Mark Search API",
            "message": "Unable to obtain IP Australia OAuth access token. Check client ID and client secret.",
        }

    url = f"{base_url}/search/quick"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "User-Agent": "EcoTrace-App/1.0 (student project)",
    }

    # Based on the quick search documentation: users can search by query, type, status,
    # and updated-since criteria. Keep the payload minimal first for compatibility.
    payload = {
        "query": brand_name,
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)

        if response.status_code >= 400:
            return {
                "success": False,
                "source": "IP Australia Trade Mark Search API",
                "status_code": response.status_code,
                "message": response.text,
            }

        data = response.json()
        legal_owner = extract_first_legal_owner_from_trademark(data)

        return {
            "success": True,
            "source": "IP Australia Trade Mark Search API",
            "brand": brand_name,
            "legal_owner": legal_owner,
            "raw": data,
        }

    except Exception as e:
        return {"success": False, "source": "IP Australia Trade Mark Search API", "message": str(e)}


# ============================================================
# Pipeline Helper
# ============================================================

def verify_owner_with_abr(owner_name: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Verify a legal owner name with ABR name search when possible.

    If owner_name is missing, returns None rather than failing the whole pipeline.
    """
    if not owner_name:
        return None
    return search_company_name_with_abr(owner_name)


# ============================================================
# Basic Endpoints
# ============================================================

@app.get("/")
def root():
    """
    Root endpoint.
    """
    return {
        "message": "EcoTrace backend is running",
        "main_endpoint": "POST /api/search",
        "consumer_flow": "query_id based",
        "version": "3.0.0",
    }


@app.get("/health")
def health():
    """
    Health check endpoint.
    """
    return {"status": "ok"}


# ============================================================
# Development User Endpoint
# ============================================================

@app.post("/api/users/test")
def create_test_user(payload: CreateUserRequest):
    """
    Create or reuse a test user.

    This endpoint is kept for development/backward compatibility. The current
    consumer search pipeline does not require user_id.
    """
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            INSERT INTO "user" (user_type, email)
            VALUES (%s, %s)
            ON CONFLICT (email)
            DO UPDATE SET email = EXCLUDED.email
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
# Main Frontend Search Endpoint
# ============================================================

@app.post("/api/search")
def search_entity(payload: SearchRequest):
    """
    Main consumer search endpoint.

    Responsibilities:
    1. Validate exactly one frontend input.
    2. Create search_query and return query_id.
    3. Execute the pipeline according to input type.
    4. Update search_query to resolved or failed.
    5. Return a unified response to the frontend.

    This endpoint does not perform report generation.
    """
    barcode = clean_text(payload.barcode)
    brand = clean_text(payload.brand)
    company_or_abn = clean_text(payload.company_or_abn)

    input_type, input_value, frontend_type = get_single_input_type(barcode, brand, company_or_abn)

    conn = None
    cur = None
    database_error = None

    try:
        try:
            conn = get_conn()
            cur = conn.cursor()
            query = create_search_query(
                cur,
                input_type=input_type,
                input_value=input_value,
                user_id=payload.user_id,
            )
            query_id = query["query_id"]
        except Exception as error:
            database_error = str(error)
            query_id = uuid4()
            conn = None
            cur = None

        pipeline_steps: List[str] = []
        result: Dict[str, Any] = {}
        db_status = "failed"

        # ----------------------------------------------------
        # 1. Company name / ABN flow
        # ----------------------------------------------------
        if input_type == "company_name":
            if is_abn(company_or_abn):
                abn = clean_abn(company_or_abn)
                pipeline_steps.append("ABR ABN verification")
                abn_result = verify_abn_with_abr(abn)
                db_status = "resolved" if abn_result.get("success") else "failed"

                # Normalize and generate search queries if ABR lookup succeeds
                legal_name = abn_result.get("legal_name")
                normalized_name = company_search_name(legal_name) if legal_name else None
                search_queries = build_company_search_queries(normalized_name) if normalized_name else []

                if normalized_name:
                    pipeline_steps.append("Company name normalization")
                    pipeline_steps.append("Search query generation")

                result = {
                    "input_type": "abn",
                    "input_value": abn,
                    "status": "external_resolved" if abn_result.get("success") else "not_found",
                    "source": "ABR",
                    "company": {
                        "legal_name": abn_result.get("legal_name"),
                        "normalized_name": normalized_name,
                        "abn": abn_result.get("abn"),
                        "state": abn_result.get("state"),
                        "postcode": abn_result.get("postcode"),
                        "abn_status": abn_result.get("abn_status"),
                        "gst_registered": abn_result.get("gst_registered"),
                    },
                    "search_queries": search_queries,
                    "abn_verification": abn_result,
                    "confidence": 95 if abn_result.get("success") else 0,
                }

            else:
                pipeline_steps.append("ABR company name lookup")
                abr_name_result = search_company_name_with_abr(company_or_abn)
                db_status = "resolved" if abr_name_result.get("success") else "failed"

                # Normalize and generate search queries if ABR lookup succeeds
                legal_name = abr_name_result.get("legal_name")
                normalized_name = company_search_name(legal_name) if legal_name else None
                search_queries = build_company_search_queries(normalized_name) if normalized_name else []

                if normalized_name:
                    pipeline_steps.append("Company name normalization")
                    pipeline_steps.append("Search query generation")

                result = {
                    "input_type": "company_name",
                    "input_value": company_or_abn,
                    "status": "external_resolved" if abr_name_result.get("success") else "not_found",
                    "source": "ABR",
                    "company": {
                        "legal_name": abr_name_result.get("legal_name"),
                        "normalized_name": normalized_name,
                        "abn": abr_name_result.get("abn"),
                        "state": abr_name_result.get("state"),
                        "postcode": abr_name_result.get("postcode"),
                        "abn_status": abr_name_result.get("abn_status"),
                    },
                    "search_queries": search_queries,
                    "abn_verification": abr_name_result,
                    "message": abr_name_result.get("message"),
                    "confidence": 90 if abr_name_result.get("success") else 0,
                }

            if cur is not None:
                update_search_query(cur, query_id, db_status)

        # ----------------------------------------------------
        # 2. Barcode flow
        # ----------------------------------------------------
        elif input_type == "barcode":
            pipeline_steps.append("OpenFoodFacts barcode lookup")
            product_result = lookup_barcode_openfoodfacts(barcode)

            extracted_brand = None
            if product_result.get("success"):
                extracted_brand = product_result.get("brand")

            trademark_result = None
            owner_name = None
            abr_owner_result = None

            if extracted_brand:
                first_brand = extracted_brand.split(",")[0].strip()
                pipeline_steps.append("IP Australia Trade Mark Search using extracted brand")
                trademark_result = search_trademark_ip_australia(first_brand)
                owner_name = trademark_result.get("legal_owner") if trademark_result else None

                if owner_name:
                    pipeline_steps.append("ABR company name lookup using trademark legal owner")
                    abr_owner_result = verify_owner_with_abr(owner_name)

            db_status = "resolved" if product_result.get("success") else "failed"

            result = {
                "input_type": "barcode",
                "input_value": barcode,
                "status": "external_resolved" if product_result.get("success") else "not_found",
                "source": "OpenFoodFacts + IP Australia + ABR",
                "product": {
                    "barcode": barcode,
                    "product_name": product_result.get("product_name"),
                    "image_url": product_result.get("image_url"),
                    "categories": product_result.get("categories"),
                },
                "brand": {
                    "brand_name": extracted_brand,
                },
                "manufacturer": product_result.get("manufacturer"),
                "trademark": trademark_result,
                "legal_owner": owner_name,
                "abn_verification": abr_owner_result,
                "message": product_result.get("message"),
                "confidence": 75 if product_result.get("success") else 0,
            }

            if cur is not None:
                update_search_query(cur, query_id, db_status)

        # ----------------------------------------------------
        # 3. Brand flow
        # ----------------------------------------------------
        elif input_type == "brand_name":
            pipeline_steps.append("IP Australia Trade Mark Search")
            trademark_result = search_trademark_ip_australia(brand)
            owner_name = trademark_result.get("legal_owner") if trademark_result else None
            abr_owner_result = None

            if owner_name:
                pipeline_steps.append("ABR company name lookup using trademark legal owner")
                abr_owner_result = verify_owner_with_abr(owner_name)

            # The brand pipeline is considered resolved when trademark lookup succeeds.
            db_status = "resolved" if trademark_result.get("success") else "failed"

            result = {
                "input_type": "brand",
                "input_value": brand,
                "status": "external_resolved" if trademark_result.get("success") else "not_found",
                "source": "IP Australia + ABR",
                "brand": {
                    "brand_name": brand,
                },
                "trademark": trademark_result,
                "legal_owner": owner_name,
                "abn_verification": abr_owner_result,
                "message": trademark_result.get("message"),
                "confidence": 80 if trademark_result.get("success") else 0,
            }

            if cur is not None:
                update_search_query(cur, query_id, db_status)

        if conn is not None:
            conn.commit()

        return {
            "query_id": str(query_id),
            "status": "success",
            "database_error": database_error,
            "input_type": frontend_type,
            "input_value": input_value,
            "resolution_status": db_status,
            "pipeline_steps": pipeline_steps,
            "result": result,
        }

    except HTTPException:
        if conn is not None:
            conn.rollback()
        raise

    except Exception as e:
        if conn is not None:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()


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

    Frontend flow:
    1. User enters company name or ABN.
    2. User optionally uploads annual/sustainability reports.
    3. Backend resolves the legal entity via ABR.
    4. Backend searches news APIs and scans uploaded reports for evidence.
    """
    saved_report_paths = save_uploaded_reports(reports)
    try:
        resolution = resolve_company_for_analysis(company_or_abn)
        normalized_name = resolution["normalized_name"]

        query_id = None
        database_error = None

        try:
            conn = get_conn()
            cur = conn.cursor()
            try:
                query = create_search_query(
                    cur,
                    input_type="company_name",
                    input_value=company_or_abn.strip(),
                )
                query_id = str(query["query_id"])
                update_search_query(
                    cur,
                    query["query_id"],
                    "resolved" if resolution["abr"].get("success") else "failed",
                )
                conn.commit()
            finally:
                cur.close()
                conn.close()
        except Exception as error:
            database_error = str(error)
            query_id = str(uuid4())

        pipeline_steps = [
            "ABR company lookup" if resolution["input_type"] == "company_name" else "ABR ABN verification",
            "Legal name normalization",
            "Search query generation",
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

        report_paths = saved_report_paths or resolve_report_paths([], reports_dir=str(REPORTS_DIR))
        report_records = test_uploaded_reports(
            normalized_name,
            report_paths,
            max_report_chars=3000,
            max_report_chunks=max(1, min(max_report_chunks, 10)),
            australia_only=False,
        )

        report_payloads = [evidence_record_to_dict(record) for record in report_records]

        return {
            "query_id": query_id,
            "status": "success",
            "database_error": database_error,
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
            "uploaded_reports": [Path(path).name for path in saved_report_paths],
            "analysed_reports": [Path(path).name for path in report_paths],
            "reports_deleted_after_analysis": bool(saved_report_paths),
            "news": {
                "candidate_count": len(news_candidates),
                "candidates": news_candidates,
                "evidence": news_records,
            },
            "reports": {
                "evidence_count": len(report_payloads),
                "evidence": report_payloads,
            },
        }
    finally:
        delete_temporary_reports(saved_report_paths)


# ============================================================
# Standalone Test Endpoints
# ============================================================

@app.get("/api/abn/verify/{abn}")
def verify_abn(abn: str):
    """
    Verify ABN directly.

    Example:
    GET /api/abn/verify/88000014675
    """
    if not is_abn(abn):
        raise HTTPException(status_code=400, detail="ABN must be 11 digits")
    return verify_abn_with_abr(abn)


@app.get("/api/company/search/{company_name}")
def lookup_company_name(company_name: str):
    """
    Search company name directly through ABR.

    Example:
    GET /api/company/search/Coles
    """
    cleaned_name = clean_text(company_name)
    if not cleaned_name or len(cleaned_name) < 2:
        raise HTTPException(status_code=400, detail="Company name must contain at least 2 characters")
    return search_company_name_with_abr(cleaned_name)


@app.get("/api/barcode/{barcode}")
def lookup_barcode(barcode: str):
    """
    Lookup barcode directly using OpenFoodFacts.

    Example:
    GET /api/barcode/5449000000996
    """
    if not is_barcode(barcode):
        raise HTTPException(status_code=400, detail="Invalid barcode")
    return lookup_barcode_openfoodfacts(barcode)


@app.get("/api/trademark/token-test")
def test_ip_australia_token():
    """
    Test IP Australia OAuth token retrieval.

    This endpoint only returns a token preview, not the full token.
    """
    token = get_ip_australia_access_token()
    if not token:
        return {"status": "error", "message": "Unable to obtain token"}
    return {"status": "success", "token_preview": token[:20]}


# ============================================================
# Pipeline Utility Endpoints
# ============================================================

@app.post("/api/pipeline/normalize-company-name")
def normalize_company_name_endpoint(payload: Dict[str, str]):
    """
    Normalize a company legal name to search-friendly format.

    Removes legal suffixes like LIMITED, PTY, etc. and converts to proper case.

    Example:
    POST /api/pipeline/normalize-company-name
    {"company_name": "BHP GROUP LIMITED"}
    
    Response:
    {"original": "BHP GROUP LIMITED", "normalized": "BHP"}
    """
    company_name = payload.get("company_name", "").strip()
    if not company_name:
        raise HTTPException(status_code=400, detail="company_name is required")
    
    normalized = company_search_name(company_name)
    return {
        "original": company_name,
        "normalized": normalized,
    }


@app.post("/api/pipeline/build-search-queries")
def build_search_queries_endpoint(payload: Dict[str, str]):
    """
    Build targeted search queries for a normalized company name.

    Queries are generated based on company type hints (mining, food retail, agribusiness).

    Example:
    POST /api/pipeline/build-search-queries
    {"company_name": "BHP"}
    
    Response:
    {"company_name": "BHP", "queries": ["BHP biodiversity Australia", ...]}
    """
    company_name = payload.get("company_name", "").strip()
    if not company_name:
        raise HTTPException(status_code=400, detail="company_name is required")
    
    queries = build_company_search_queries(company_name)
    return {
        "company_name": company_name,
        "query_count": len(queries),
        "queries": queries,
    }


@app.post("/api/pipeline/normalize-and-query")
def normalize_and_query_endpoint(payload: Dict[str, str]):
    """
    Combined endpoint: normalize company name AND build search queries in one call.

    Useful for the frontend to get both normalized name and search queries.

    Example:
    POST /api/pipeline/normalize-and-query
    {"company_name": "BHP GROUP LIMITED"}
    
    Response:
    {"original": "BHP GROUP LIMITED", "normalized": "BHP", "queries": [...]}
    """
    company_name = payload.get("company_name", "").strip()
    if not company_name:
        raise HTTPException(status_code=400, detail="company_name is required")
    
    normalized = company_search_name(company_name)
    queries = build_company_search_queries(normalized)
    
    return {
        "original": company_name,
        "normalized": normalized,
        "query_count": len(queries),
        "queries": queries,
    }


@app.get("/api/trademark/search/{brand}")
def lookup_trademark(brand: str):
    """
    Test IP Australia Trade Mark Search API directly.

    Example:
    GET /api/trademark/search/Coles
    """
    cleaned_brand = clean_text(brand)
    if not cleaned_brand or len(cleaned_brand) < 2:
        raise HTTPException(status_code=400, detail="Brand must contain at least 2 characters")
    return search_trademark_ip_australia(cleaned_brand)


# ============================================================
# Search History
# ============================================================

@app.get("/api/search/history/{user_id}")
def get_search_history(user_id: str):
    """
    Get search history for a user.

    Kept for compatibility with user_id-based flows. The current consumer flow
    mainly uses query_id returned by /api/search.
    """
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT
                query_id,
                input_type,
                input_value,
                resolution_status,
                resolved_company_id,
                resolved_brand_id,
                resolved_product_id,
                submitted_at
            FROM search_query
            WHERE user_id = %s
            ORDER BY submitted_at DESC;
            """,
            (user_id,),
        )
        rows = cur.fetchall()
        return {"user_id": user_id, "history": [serialize_row(row) for row in rows]}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        cur.close()
        conn.close()


@app.get("/api/search/query/{query_id}")
def get_search_query(query_id: str):
    """
    Retrieve one search_query record by query_id.

    This is useful for debugging and for the report team to confirm that a
    query_id exists before generating a report.
    """
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT
                query_id,
                user_id,
                input_type,
                input_value,
                resolution_status,
                resolved_company_id,
                resolved_brand_id,
                resolved_product_id,
                submitted_at
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
  
