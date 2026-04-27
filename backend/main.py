"""
EcoTrace Backend API

Frontend user inputs:
1. Barcode
2. Brand
3. Company / ABN

Main endpoint:
POST /api/search

Resolution flow:
- If barcode is provided:
    1. Search local product database
    2. If not found, call OpenFoodFacts barcode API
- If brand is provided:
    1. Search local brand database
- If company_or_abn is provided:
    1. If input is 11 digits, verify ABN using ABR API
    2. Otherwise search local company database
- Save every search into search_query table
"""

import os
import re
from wsgiref import headers
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Any
from uuid import UUID

import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


# ============================================================
# Load environment variables
# ============================================================

load_dotenv()


# ============================================================
# FastAPI App
# ============================================================

app = FastAPI(
    title="EcoTrace Backend API",
    version="2.0.0",
    description="""
EcoTrace backend for resolving consumer product input.

Frontend can submit:
- barcode
- brand
- company_or_abn

The backend will combine:
- local database lookup
- OpenFoodFacts barcode API
- ABR ABN verification API
"""
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace with frontend URL after deployment
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Database
# ============================================================

def get_conn():
    """
    Create PostgreSQL database connection.

    Required .env variables:
    DB_HOST
    DB_PORT
    DB_NAME
    DB_USER
    DB_PASSWORD
    """
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "ecotrace"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD"),
        cursor_factory=RealDictCursor
    )


def serialize_row(row):
    """
    Convert database row into JSON-safe dict.
    UUID values must be converted into strings.
    """
    if row is None:
        return None

    result = {}

    for key, value in row.items():
        if isinstance(value, UUID):
            result[key] = str(value)
        else:
            result[key] = value

    return result


# ============================================================
# Request Models
# ============================================================

class SearchRequest(BaseModel):
    """
    Main frontend request body.

    Frontend can send any one or multiple fields.

    Example:
    {
        "user_id": "optional-test-user-id",
        "barcode": "9300605151255",
        "brand": "Coles",
        "company_or_abn": "Coles"
    }
    """
    user_id: Optional[str] = None
    barcode: Optional[str] = None
    brand: Optional[str] = None
    company_or_abn: Optional[str] = None


class CreateUserRequest(BaseModel):
    """
    Create a test user for local development.
    """
    email: str
    user_type: str = "consumer"


# ============================================================
# Utility Functions
# ============================================================

def clean_text(value: Optional[str]) -> Optional[str]:
    """
    Clean frontend input.
    """
    if value is None:
        return None

    value = value.strip()

    if value == "":
        return None

    return value


def clean_abn(value: str) -> str:
    """
    Remove spaces from ABN.
    """
    return re.sub(r"\s+", "", value)


def is_abn(value: str) -> bool:
    """
    Check whether input looks like an ABN.
    ABN must be 11 digits.
    """
    value = clean_abn(value)
    return value.isdigit() and len(value) == 11


def is_barcode(value: str) -> bool:
    """
    Basic barcode validation.
    Most retail barcodes are numeric and between 8 and 14 digits.
    """
    value = value.strip()
    return value.isdigit() and 8 <= len(value) <= 14


# ============================================================
# External API: ABR ABN Verification
# ============================================================

def verify_abn_with_abr(abn: str) -> Dict[str, Any]:
    """
    Verify an ABN using ABR Web Services.

    Required .env:
    ABR_GUID

    Returns a structured ABN result.
    """

    guid = os.getenv("ABR_GUID")

    if not guid:
        return {
            "success": False,
            "source": "ABR",
            "message": "ABR_GUID is missing in .env"
        }

    abn = clean_abn(abn)

    if not is_abn(abn):
        return {
            "success": False,
            "source": "ABR",
            "message": "Invalid ABN format. ABN must be 11 digits."
        }

    url = "https://abr.business.gov.au/abrxmlsearch/AbrXmlSearch.asmx/SearchByABNv202001"

    params = {
        "searchString": abn,
        "includeHistoricalDetails": "N",
        "authenticationGuid": guid
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()

        root = ET.fromstring(response.text)

        ns = {
            "abr": "http://abr.business.gov.au/ABRXMLSearch/"
        }

        abn_node = root.find(".//abr:identifierValue", ns)
        name_node = root.find(".//abr:organisationName", ns)
        state_node = root.find(".//abr:stateCode", ns)
        postcode_node = root.find(".//abr:postcode", ns)
        status_node = root.find(".//abr:entityStatusCode", ns)
        gst_node = root.find(".//abr:goodsAndServicesTax", ns)

        if abn_node is None:
            return {
                "success": False,
                "source": "ABR",
                "message": "ABN not found"
            }

        return {
            "success": True,
            "source": "ABR",
            "abn": abn_node.text,
            "legal_name": name_node.text if name_node is not None else None,
            "state": state_node.text if state_node is not None else None,
            "postcode": postcode_node.text if postcode_node is not None else None,
            "abn_status": status_node.text if status_node is not None else None,
            "gst_registered": gst_node is not None,
            "verified": True
        }

    except Exception as e:
        return {
            "success": False,
            "source": "ABR",
            "message": str(e)
        }


# ============================================================
# External API: OpenFoodFacts Barcode Lookup
# ============================================================

def lookup_barcode_openfoodfacts(barcode: str) -> Dict[str, Any]:
    """
    Look up product information from OpenFoodFacts.

    This is useful when local product database is empty.

    No API key is required.
    """

    if not is_barcode(barcode):
        return {
            "success": False,
            "source": "OpenFoodFacts",
            "message": "Invalid barcode format"
        }

    url = f"https://world.openfoodfacts.org/api/v2/product/{barcode}.json"

    try:
        headers = {
    "User-Agent": "EcoTrace-App/1.0 (student project)"
}

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        data = response.json()

        if data.get("status") != 1:
            return {
                "success": False,
                "source": "OpenFoodFacts",
                "message": "Product not found"
            }

        product = data.get("product", {})

        return {
            "success": True,
            "source": "OpenFoodFacts",
            "barcode": barcode,
            "product_name": product.get("product_name"),
            "brand": product.get("brands"),
            "manufacturer": product.get("manufacturing_places"),
            "categories": product.get("categories"),
            "image_url": product.get("image_url")
        }

    except Exception as e:
        return {
            "success": False,
            "source": "OpenFoodFacts",
            "message": str(e)
        }


# ============================================================
# Local Database Lookup
# ============================================================

def search_local_product(cur, barcode: str):
    """
    Search product by barcode from local database.
    """
    cur.execute("""
        SELECT
            p.product_id,
            p.barcode,
            p.product_name,
            p.manufacturer_name,
            p.data_source,
            b.brand_id,
            b.brand_name,
            c.company_id,
            c.legal_name,
            c.abn,
            c.company_status,
            c.anzsic_code
        FROM product p
        LEFT JOIN brand b ON p.brand_id = b.brand_id
        LEFT JOIN company c ON b.company_id = c.company_id
        WHERE p.barcode = %s
        LIMIT 1;
    """, (barcode,))

    return cur.fetchone()


def search_local_brand(cur, brand: str):
    """
    Search brand from local database.
    """
    cur.execute("""
        SELECT
            b.brand_id,
            b.brand_name,
            c.company_id,
            c.legal_name,
            c.abn,
            c.company_status,
            c.anzsic_code
        FROM brand b
        LEFT JOIN company c ON b.company_id = c.company_id
        WHERE b.brand_name ILIKE %s
        LIMIT 1;
    """, (f"%{brand}%",))

    return cur.fetchone()


def search_local_company(cur, company_name: str):
    """
    Search company by legal name from local database.
    """
    cur.execute("""
        SELECT
            company_id,
            abn,
            acn,
            legal_name,
            entity_type,
            company_status,
            anzsic_code
        FROM company
        WHERE legal_name ILIKE %s
        LIMIT 1;
    """, (f"%{company_name}%",))

    return cur.fetchone()


def search_local_company_by_abn(cur, abn: str):
    """
    Search company by ABN from local database.
    """
    cur.execute("""
        SELECT
            company_id,
            abn,
            acn,
            legal_name,
            entity_type,
            company_status,
            anzsic_code
        FROM company
        WHERE abn = %s
        LIMIT 1;
    """, (abn,))

    return cur.fetchone()


# ============================================================
# Search Logging
# ============================================================

def log_search(
    cur,
    user_id: Optional[str],
    input_type: str,
    input_value: str,
    resolution_status: str,
    resolved_company_id: Optional[str] = None,
    resolved_brand_id: Optional[str] = None,
    resolved_product_id: Optional[str] = None
):
    """
    Save search query into search_query table.

    If user_id is None, search is still processed but not logged.
    """

    if not user_id:
        return None

    cur.execute("""
        INSERT INTO search_query (
            user_id,
            input_type,
            input_value,
            resolution_status,
            resolved_company_id,
            resolved_brand_id,
            resolved_product_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING query_id, submitted_at;
    """, (
        user_id,
        input_type,
        input_value,
        resolution_status,
        resolved_company_id,
        resolved_brand_id,
        resolved_product_id
    ))

    return cur.fetchone()


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
        "main_endpoint": "POST /api/search"
    }


@app.get("/health")
def health():
    """
    Health check endpoint.
    """
    return {
        "status": "ok"
    }


# ============================================================
# Test User Endpoint
# ============================================================

@app.post("/api/users/test")
def create_test_user(payload: CreateUserRequest):
    """
    Create or reuse a test user.

    Useful for frontend local testing because search history needs user_id.
    """

    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO "user" (user_type, email)
            VALUES (%s, %s)
            ON CONFLICT (email)
            DO UPDATE SET email = EXCLUDED.email
            RETURNING user_id, user_type, email, created_at;
        """, (
            payload.user_type,
            payload.email
        ))

        user = cur.fetchone()
        conn.commit()

        return {
            "message": "User ready",
            "user": serialize_row(user)
        }

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
    Main endpoint for frontend.

    Frontend input fields:
    - barcode
    - brand
    - company_or_abn

    The backend returns a unified result object so frontend can display it easily.
    """

    barcode = clean_text(payload.barcode)
    brand = clean_text(payload.brand)
    company_or_abn = clean_text(payload.company_or_abn)

    if not barcode and not brand and not company_or_abn:
        raise HTTPException(
            status_code=400,
            detail="Please provide barcode, brand, or company_or_abn"
        )

    conn = get_conn()
    cur = conn.cursor()

    results = []

    try:
        # ----------------------------------------------------
        # 1. Barcode flow
        # ----------------------------------------------------
        if barcode:
            local_product = search_local_product(cur, barcode)

            if local_product:
                product = serialize_row(local_product)

                result = {
                    "input_type": "barcode",
                    "input_value": barcode,
                    "status": "resolved",
                    "source": "local_database",
                    "product": {
                        "product_id": product.get("product_id"),
                        "barcode": product.get("barcode"),
                        "product_name": product.get("product_name"),
                        "manufacturer_name": product.get("manufacturer_name"),
                        "data_source": product.get("data_source")
                    },
                    "brand": {
                        "brand_id": product.get("brand_id"),
                        "brand_name": product.get("brand_name")
                    },
                    "company": {
                        "company_id": product.get("company_id"),
                        "legal_name": product.get("legal_name"),
                        "abn": product.get("abn"),
                        "company_status": product.get("company_status"),
                        "industry": product.get("anzsic_code")
                    },
                    "confidence": 90
                }

                log_search(
                    cur,
                    payload.user_id,
                    "barcode",
                    barcode,
                    "resolved",
                    product.get("company_id"),
                    product.get("brand_id"),
                    product.get("product_id")
                )

            else:
                external_product = lookup_barcode_openfoodfacts(barcode)

                result = {
                    "input_type": "barcode",
                    "input_value": barcode,
                    "status": "external_resolved" if external_product.get("success") else "not_found",
                    "source": external_product.get("source"),
                    "product": {
                        "barcode": barcode,
                        "product_name": external_product.get("product_name"),
                        "image_url": external_product.get("image_url"),
                        "categories": external_product.get("categories")
                    },
                    "brand": {
                        "brand_name": external_product.get("brand")
                    },
                    "company": {
                        "manufacturer": external_product.get("manufacturer")
                    },
                    "message": external_product.get("message"),
                    "confidence": 65 if external_product.get("success") else 0
                }

                log_search(
                    cur,
                    payload.user_id,
                    "barcode",
                    barcode,
                    result["status"]
                )

            results.append(result)

        # ----------------------------------------------------
        # 2. Brand flow
        # ----------------------------------------------------
        if brand:
            local_brand = search_local_brand(cur, brand)

            if local_brand:
                brand_row = serialize_row(local_brand)

                abn_verification = None
                if brand_row.get("abn"):
                    abn_verification = verify_abn_with_abr(brand_row.get("abn"))

                result = {
                    "input_type": "brand",
                    "input_value": brand,
                    "status": "resolved",
                    "source": "local_database",
                    "brand": {
                        "brand_id": brand_row.get("brand_id"),
                        "brand_name": brand_row.get("brand_name")
                    },
                    "company": {
                        "company_id": brand_row.get("company_id"),
                        "legal_name": brand_row.get("legal_name"),
                        "abn": brand_row.get("abn"),
                        "company_status": brand_row.get("company_status"),
                        "industry": brand_row.get("anzsic_code")
                    },
                    "abn_verification": abn_verification,
                    "confidence": 85
                }

                log_search(
                    cur,
                    payload.user_id,
                    "brand_name",
                    brand,
                    "resolved",
                    brand_row.get("company_id"),
                    brand_row.get("brand_id")
                )

            else:
                result = {
                    "input_type": "brand",
                    "input_value": brand,
                    "status": "not_found",
                    "source": "local_database",
                    "message": "Brand not found in local database. Add brand-company mapping data or search by ABN.",
                    "confidence": 0
                }

                log_search(
                    cur,
                    payload.user_id,
                    "brand_name",
                    brand,
                    "not_found"
                )

            results.append(result)

        # ----------------------------------------------------
        # 3. Company / ABN flow
        # ----------------------------------------------------
        if company_or_abn:
            if is_abn(company_or_abn):
                abn = clean_abn(company_or_abn)

                local_company = search_local_company_by_abn(cur, abn)
                abn_verification = verify_abn_with_abr(abn)

                if local_company:
                    company = serialize_row(local_company)

                    result = {
                        "input_type": "abn",
                        "input_value": abn,
                        "status": "resolved",
                        "source": "local_database_and_ABR",
                        "company": {
                            "company_id": company.get("company_id"),
                            "legal_name": company.get("legal_name"),
                            "abn": company.get("abn"),
                            "acn": company.get("acn"),
                            "entity_type": company.get("entity_type"),
                            "company_status": company.get("company_status"),
                            "industry": company.get("anzsic_code")
                        },
                        "abn_verification": abn_verification,
                        "confidence": 95
                    }

                    log_search(
                        cur,
                        payload.user_id,
                        "abn",
                        abn,
                        "resolved",
                        company.get("company_id")
                    )

                else:
                    result = {
                        "input_type": "abn",
                        "input_value": abn,
                        "status": "external_resolved" if abn_verification.get("success") else "not_found",
                        "source": "ABR",
                        "company": {
                            "legal_name": abn_verification.get("legal_name"),
                            "abn": abn_verification.get("abn"),
                            "state": abn_verification.get("state"),
                            "postcode": abn_verification.get("postcode"),
                            "abn_status": abn_verification.get("abn_status"),
                            "gst_registered": abn_verification.get("gst_registered")
                        },
                        "abn_verification": abn_verification,
                        "message": abn_verification.get("message"),
                        "confidence": 90 if abn_verification.get("success") else 0
                    }

                    log_search(
                        cur,
                        payload.user_id,
                        "abn",
                        abn,
                        result["status"]
                    )

            else:
                local_company = search_local_company(cur, company_or_abn)

                if local_company:
                    company = serialize_row(local_company)

                    abn_verification = None
                    if company.get("abn"):
                        abn_verification = verify_abn_with_abr(company.get("abn"))

                    result = {
                        "input_type": "company_name",
                        "input_value": company_or_abn,
                        "status": "resolved",
                        "source": "local_database",
                        "company": {
                            "company_id": company.get("company_id"),
                            "legal_name": company.get("legal_name"),
                            "abn": company.get("abn"),
                            "acn": company.get("acn"),
                            "entity_type": company.get("entity_type"),
                            "company_status": company.get("company_status"),
                            "industry": company.get("anzsic_code")
                        },
                        "abn_verification": abn_verification,
                        "confidence": 85
                    }

                    log_search(
                        cur,
                        payload.user_id,
                        "company_name",
                        company_or_abn,
                        "resolved",
                        company.get("company_id")
                    )

                else:
                    result = {
                        "input_type": "company_name",
                        "input_value": company_or_abn,
                        "status": "not_found",
                        "source": "local_database",
                        "message": "Company name not found in local database. For stronger verification, ask user to enter ABN.",
                        "confidence": 0
                    }

                    log_search(
                        cur,
                        payload.user_id,
                        "company_name",
                        company_or_abn,
                        "not_found"
                    )

            results.append(result)

        conn.commit()

        return {
            "status": "success",
            "total_results": len(results),
            "results": results
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        cur.close()
        conn.close()


# ============================================================
# Standalone ABN Endpoint
# ============================================================

@app.get("/api/abn/verify/{abn}")
def verify_abn(abn: str):
    """
    Verify ABN directly.

    Example:
    GET /api/abn/verify/12345678901
    """
    if not is_abn(abn):
        raise HTTPException(status_code=400, detail="ABN must be 11 digits")

    return verify_abn_with_abr(abn)


# ============================================================
# Standalone Barcode Endpoint
# ============================================================

@app.get("/api/barcode/{barcode}")
def lookup_barcode(barcode: str):
    """
    Lookup barcode directly using OpenFoodFacts.

    Example:
    GET /api/barcode/9300605151255
    """
    if not is_barcode(barcode):
        raise HTTPException(status_code=400, detail="Invalid barcode")

    return lookup_barcode_openfoodfacts(barcode)


# ============================================================
# Search History
# ============================================================

@app.get("/api/search/history/{user_id}")
def get_search_history(user_id: str):
    """
    Get search history for a user.
    """

    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
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
        """, (user_id,))

        rows = cur.fetchall()

        return {
            "user_id": user_id,
            "history": [serialize_row(row) for row in rows]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        cur.close()
        conn.close()