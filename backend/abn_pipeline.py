"""
abn_pipeline.py
===============

Purpose
-------
Handles both ABN number lookup and company name search for the EcoTrace pipeline.

This module owns all ABR (Australian Business Register) Web Services calls
so they are not scattered across main.py, barcode_pipeline.py, and brand_pipeline.py.

ABN pipeline flow
-----------------
  User input (11-digit ABN)
      │
      ├─── 1. Format check     ── digits only, length == 11
      ├─── 2. Checksum         ── ATO weighted-sum algorithm (mod 89)
      └─── 3. ABR lookup       ── SearchByABNv202001 (REST GET)
                                   returns: legal name, entity type, ABN status,
                                            ACN, GST registration, state, postcode,
                                            main business activity

Company name pipeline flow
--------------------------
  User input (company / trading name string)
      │
      ├─── 1. Name validation  ── minimum 2 characters
      └─── 2. ABR name search  ── ABRSearchByName (SOAP POST)
                                   returns first Active result (highest ABR score)

External APIs
-------------
ABR SearchByABN (REST GET):
  GET https://abr.business.gov.au/abrxmlsearch/AbrXmlSearch.asmx/SearchByABNv202001

ABR SearchByName (SOAP POST):
  POST https://abr.business.gov.au/ABRXMLSearch/AbrXmlSearch.asmx
  SOAPAction: http://abr.business.gov.au/ABRXMLSearch/ABRSearchByName
  Response element: <searchResultsRecord> (NOT businessEntity202001)

  NOTE: ABRSearchByNameAdvancedSimpleProtocol2017 (REST GET) returns HTTP 500
        and has been removed.  All name searches now use the SOAP endpoint.

Required .env variable: ABR_GUID
Obtain a free GUID from https://abr.business.gov.au/Tools/WebServices

Public exports
--------------
    run_abn_phase(abn)               -> full ABN lookup with checksum validation
    run_company_phase(company_name)  -> full company name search
    run_company_abn_phase(value)     -> auto-detects ABN vs name; used by main.py

    verify_abn_with_abr(abn)               -> raw ABR ABN lookup
    search_company_name_with_abr(name)      -> raw ABR name search (abr_lookup_fn)

    clean_abn(value)            -> strip whitespace from ABN string
    is_abn(value)               -> True if value is 11 digits after cleaning
    validate_abn_checksum(abn)  -> True if ATO checksum passes
"""

import os
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

import requests


# ============================================================
# ABN Helpers
# ============================================================

def clean_abn(value: str) -> str:
    """Remove all whitespace from an ABN string.

    '12 345 678 901'  ->  '12345678901'
    """
    return re.sub(r"\s+", "", value or "")


def is_abn(value: str) -> bool:
    """Return True if the value is exactly 11 digits after whitespace removal."""
    cleaned = clean_abn(value)
    return cleaned.isdigit() and len(cleaned) == 11


def validate_abn_checksum(abn: str) -> bool:
    """
    Validate an ABN using the ATO weighted-sum checksum algorithm.

    Algorithm (https://abr.business.gov.au/Help/AbnFormat):
    1. Subtract 1 from the first digit.
    2. Multiply each digit by weights [10,1,3,5,7,9,11,13,15,17,19].
    3. Sum all products.  Valid if divisible by 89.
    """
    abn = clean_abn(abn)
    if not abn.isdigit() or len(abn) != 11:
        return False
    weights = [10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19]
    digits  = [int(d) for d in abn]
    digits[0] -= 1
    return sum(d * w for d, w in zip(digits, weights)) % 89 == 0


# ============================================================
# ABR XML Namespace helpers
# ============================================================

_ABR_NS = {"abr": "http://abr.business.gov.au/ABRXMLSearch/"}


def _text(node, path: str) -> Optional[str]:
    """Find child by XPath and return its .text, or None."""
    found = node.find(path, _ABR_NS)
    return found.text if found is not None else None


def _check_abr_exception(root) -> Optional[str]:
    """Return the ABR exception description if present, else None."""
    ex = root.find(".//abr:exception", _ABR_NS)
    if ex is not None:
        desc = ex.find(".//abr:exceptionDescription", _ABR_NS)
        return desc.text if desc is not None else "ABR returned an unspecified exception"
    return None


# ============================================================
# ABR ABN Lookup  (REST GET — SearchByABNv202001)
# ============================================================

def verify_abn_with_abr(abn: str) -> Dict[str, Any]:
    """
    Verify a single ABN via ABR SearchByABNv202001 (REST GET).

    Returns the entity's legal name, entity type, ABN status, ACN,
    GST registration, state, postcode and main business activity.
    """
    guid = os.getenv("ABR_GUID", "").strip()
    if not guid:
        return {"success": False, "source": "ABR", "message": "ABR_GUID missing in .env"}

    abn = clean_abn(abn)
    if not is_abn(abn):
        return {"success": False, "source": "ABR", "message": "ABN must be 11 digits"}

    url    = "https://abr.business.gov.au/abrxmlsearch/AbrXmlSearch.asmx/SearchByABNv202001"
    params = {
        "searchString":             abn,
        "includeHistoricalDetails": "N",
        "authenticationGuid":       guid,
    }

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
    except requests.exceptions.Timeout:
        return {"success": False, "source": "ABR", "message": "ABR request timed out"}
    except requests.exceptions.RequestException as e:
        return {"success": False, "source": "ABR", "message": f"Network error: {e}"}
    except ET.ParseError as e:
        return {"success": False, "source": "ABR", "message": f"Invalid XML from ABR: {e}"}

    err = _check_abr_exception(root)
    if err:
        return {"success": False, "source": "ABR", "message": err}

    abn_node = root.find(".//abr:identifierValue", _ABR_NS)
    if abn_node is None:
        return {"success": False, "source": "ABR", "message": "ABN not found in ABR register"}

    org_name    = _text(root, ".//abr:organisationName")
    given_name  = _text(root, ".//abr:givenName")
    family_name = _text(root, ".//abr:familyName")
    legal_name  = org_name or " ".join(filter(None, [given_name, family_name])) or None

    entity_type_code = _text(root, ".//abr:entityTypeCode")
    entity_type_desc = _text(root, ".//abr:entityTypeDescription") or entity_type_code

    acn = None
    for id_node in root.findall(".//abr:identifier", _ABR_NS):
        id_type  = _text(id_node, ".//abr:identifierType")
        id_value = _text(id_node, ".//abr:identifierValue")
        if id_type and "acn" in id_type.lower() and id_value:
            acn = id_value
            break

    gst_node       = root.find(".//abr:goodsAndServicesTax", _ABR_NS)
    gst_registered = gst_node is not None
    gst_from_date  = _text(root, ".//abr:goodsAndServicesTax/abr:effectiveFrom") if gst_registered else None

    state    = _text(root, ".//abr:mainBusinessPhysicalAddress/abr:stateCode") \
             or _text(root, ".//abr:stateCode")
    postcode = _text(root, ".//abr:mainBusinessPhysicalAddress/abr:postcode") \
             or _text(root, ".//abr:postcode")

    anzsic_code = _text(root, ".//abr:mainBusinessActivity/abr:code")
    anzsic_desc = _text(root, ".//abr:mainBusinessActivity/abr:description") or anzsic_code

    abn_status = (
        _text(root, ".//abr:entityStatus/abr:entityStatusCode")
        or _text(root, ".//abr:entityStatusCode")
    )

    return {
        "success":          True,
        "source":           "ABR",
        "abn":              abn_node.text,
        "legal_name":       legal_name,
        "entity_type":      entity_type_desc,
        "entity_type_code": entity_type_code,
        "acn":              acn,
        "state":            state,
        "postcode":         postcode,
        "abn_status":       abn_status,
        "gst_registered":   gst_registered,
        "gst_from_date":    gst_from_date,
        "main_activity":    anzsic_desc,
        "verified":         True,
    }


# ============================================================
# ABR Company Name Search  (SOAP POST — ABRSearchByName)
# ============================================================

_ABR_SOAP_URL    = "https://abr.business.gov.au/ABRXMLSearch/AbrXmlSearch.asmx"
_ABR_SOAP_ACTION = "http://abr.business.gov.au/ABRXMLSearch/ABRSearchByName"


def _build_name_search_soap_body(name: str, guid: str) -> str:
    """
    Build the SOAP 1.1 envelope for ABRSearchByName.

    Structure matches the confirmed working reference (abn_trial.py):
    - ABRSearchByName uses default xmlns= (no abr: prefix inside body)
    - authenticationGUID (uppercase) inside externalNameSearch
    - nameType nested INSIDE <filters>
    - Second <authenticationGuid> directly under <ABRSearchByName>
    """
    safe_name = (
        name
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xmlns:xsd="http://www.w3.org/2001/XMLSchema"
               xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <ABRSearchByName xmlns="http://abr.business.gov.au/ABRXMLSearch/">
      <externalNameSearch>
        <authenticationGUID>{guid}</authenticationGUID>
        <name>{safe_name}</name>
        <filters>
          <nameType>
            <tradingName>Y</tradingName>
            <legalName>Y</legalName>
          </nameType>
        </filters>
      </externalNameSearch>
      <authenticationGuid>{guid}</authenticationGuid>
    </ABRSearchByName>
  </soap:Body>
</soap:Envelope>"""


def _parse_soap_name_response(
    xml_text:     str,
    company_name: str,
) -> Dict[str, Any]:
    """
    Parse the SOAP response from ABRSearchByName.

    ABR returns <searchResultsRecord> elements (confirmed from live response).
    Only the first Active result (highest ABR relevance score) is returned.

    Each <searchResultsRecord> contains:
      ABN/identifierValue, ABN/identifierStatus,
      mainName/organisationName  (legal name, with <score>),
      mainTradingName/organisationName,
      mainBusinessPhysicalAddress/stateCode + postcode
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        return {"success": False, "message": f"SOAP XML parse error: {e}", "result": None}

    err = _check_abr_exception(root)
    if err:
        return {"success": False, "message": err, "result": None}

    # ABR name search response uses <searchResultsRecord> elements.
    # Try with namespace prefix first, then unqualified as fallback.
    records = root.findall(".//abr:searchResultsRecord", _ABR_NS)
    if not records:
        records = root.findall(".//searchResultsRecord")

    if not records:
        return {"success": False, "message": f"No results for '{company_name}'", "result": None}

    # ABR returns records sorted by relevance score descending.
    # Walk records and return the first one with Active status.
    # Fall back to the very first record if none are Active.
    def _parse_record(record) -> Dict:
        abn_val = (
            _text(record, "abr:ABN/abr:identifierValue")
            or _text(record, ".//abr:identifierValue")
        )
        abn_status = (
            _text(record, "abr:ABN/abr:identifierStatus")
            or _text(record, ".//abr:identifierStatus")
        )
        # mainName holds the legal/registered name
        legal_name = (
            _text(record, "abr:mainName/abr:organisationName")
            or _text(record, ".//abr:organisationName")
        )
        if not legal_name:
            given  = _text(record, ".//abr:givenName")
            family = _text(record, ".//abr:familyName")
            legal_name = " ".join(filter(None, [given, family])) or company_name

        trading_name = _text(record, "abr:mainTradingName/abr:organisationName")
        state        = (
            _text(record, "abr:mainBusinessPhysicalAddress/abr:stateCode")
            or _text(record, ".//abr:stateCode")
        )
        postcode = (
            _text(record, "abr:mainBusinessPhysicalAddress/abr:postcode")
            or _text(record, ".//abr:postcode")
        )
        return {
            "abn":          abn_val,
            "legal_name":   legal_name,
            "trading_name": trading_name,
            "entity_type":  None,   # not present in name search results; populated by ABN lookup
            "state":        state,
            "postcode":     postcode,
            "abn_status":   abn_status,
            "verified":     abn_val is not None,
        }

    # First pass: first Active record
    for record in records:
        status = (
            _text(record, "abr:ABN/abr:identifierStatus")
            or _text(record, ".//abr:identifierStatus")
            or ""
        )
        if status.lower() == "active":
            return {"success": True, "result": _parse_record(record)}

    # Fallback: highest-scored record regardless of status
    return {"success": True, "result": _parse_record(records[0])}


def search_company_name_with_abr(company_name: str) -> Dict[str, Any]:
    """
    Search ABR by company or business name using the SOAP POST endpoint.

    Returns the single best Active result (highest ABR relevance score).
    """
    guid = os.getenv("ABR_GUID", "").strip()
    if not guid:
        return {"success": False, "source": "ABR", "message": "ABR_GUID missing in .env"}

    company_name = (company_name or "").strip()
    if len(company_name) < 2:
        return {
            "success": False, "source": "ABR",
            "message": "Company name must be at least 2 characters",
        }

    soap_body = _build_name_search_soap_body(company_name, guid)
    headers   = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction":   _ABR_SOAP_ACTION,
        "User-Agent":   "EcoTrace-App/1.0 (student project)",
    }

    try:
        resp = requests.post(
            _ABR_SOAP_URL,
            data=soap_body.encode("utf-8"),
            headers=headers,
            timeout=20,
        )
        resp.raise_for_status()
    except requests.exceptions.Timeout:
        return {"success": False, "source": "ABR", "message": "ABR SOAP request timed out"}
    except requests.exceptions.RequestException as e:
        return {"success": False, "source": "ABR", "message": f"ABR SOAP network error: {e}"}

    parsed = _parse_soap_name_response(resp.text, company_name)

    if not parsed["success"] or not parsed.get("result"):
        return {
            "success": False,
            "source":  "ABR",
            "message": parsed.get("message", "ABR name search returned no results"),
        }

    match = parsed["result"]
    return {
        "success":    True,
        "source":     "ABR",
        "best_match": match,
        **match,
    }


# ============================================================
# Pipeline Runners
# ============================================================

def run_abn_phase(abn: str) -> Dict[str, Any]:
    """Full ABN input pipeline: format check -> checksum -> ABR lookup."""
    pipeline: List[str] = []
    errors:   List[str] = []

    abn_raw = abn
    abn     = clean_abn(abn)

    pipeline.append("ABN format check")
    valid_format = is_abn(abn)
    if not valid_format:
        return {
            "success":        False,
            "abn":            abn,
            "valid_format":   False,
            "valid_checksum": False,
            "error":          f"'{abn_raw}' is not a valid ABN format (must be 11 digits).",
            "pipeline":       pipeline,
            "errors":         errors,
            "confidence":     0,
        }

    pipeline.append("ABN checksum validation (ATO mod-89)")
    valid_checksum = validate_abn_checksum(abn)
    if not valid_checksum:
        errors.append(
            f"ABN {abn} fails the ATO checksum — mathematically invalid. "
            "Search will still proceed."
        )

    pipeline.append(f"ABR ABN lookup: {abn}")
    abr = verify_abn_with_abr(abn)

    if not abr.get("success"):
        return {
            "success":        False,
            "abn":            abn,
            "valid_format":   valid_format,
            "valid_checksum": valid_checksum,
            "error":          abr.get("message", "ABR lookup failed"),
            "source":         "ABR",
            "pipeline":       pipeline,
            "errors":         errors,
            "confidence":     10 if valid_checksum else 0,
        }

    confidence = 0
    if valid_format:                          confidence += 10
    if valid_checksum:                        confidence += 20
    if abr.get("abn_status") == "Active":     confidence += 50
    elif abr.get("abn_status"):               confidence += 20
    if abr.get("gst_registered"):             confidence += 10
    if abr.get("legal_name"):                 confidence += 10

    return {
        "success":          True,
        "abn":              abn,
        "valid_format":     valid_format,
        "valid_checksum":   valid_checksum,
        "legal_name":       abr.get("legal_name"),
        "entity_type":      abr.get("entity_type"),
        "entity_type_code": abr.get("entity_type_code"),
        "acn":              abr.get("acn"),
        "state":            abr.get("state"),
        "postcode":         abr.get("postcode"),
        "abn_status":       abr.get("abn_status"),
        "gst_registered":   abr.get("gst_registered"),
        "gst_from_date":    abr.get("gst_from_date"),
        "main_activity":    abr.get("main_activity"),
        "source":           "ABR",
        "status":           "external_resolved" if abr.get("abn_status") == "Active" else "external_found",
        "confidence":       min(confidence, 100),
        "pipeline":         pipeline,
        "errors":           errors,
    }


def run_company_phase(company_name: str) -> Dict[str, Any]:
    """Full company name pipeline: validation -> ABR name search (SOAP POST)."""
    pipeline: List[str] = []
    errors:   List[str] = []

    company_name = (company_name or "").strip()

    pipeline.append("Company name validation")
    if len(company_name) < 2:
        return {
            "success":      False,
            "company_name": company_name,
            "error":        "Company name must be at least 2 characters.",
            "pipeline":     pipeline,
            "errors":       errors,
            "confidence":   0,
        }

    pipeline.append(f"ABR company name search: '{company_name}'")
    abr = search_company_name_with_abr(company_name)

    if not abr.get("success"):
        return {
            "success":      False,
            "company_name": company_name,
            "company":      None,
            "source":       "ABR",
            "error":        abr.get("message", "ABR search failed"),
            "status":       "not_found",
            "pipeline":     pipeline,
            "errors":       errors,
            "confidence":   0,
        }

    best = abr.get("best_match", {})

    confidence = 0
    if best.get("abn"):                                    confidence += 30
    if best.get("abn_status", "").lower() == "active":     confidence += 40
    elif best.get("abn_status"):                           confidence += 15
    if best.get("legal_name"):                             confidence += 20

    return {
        "success":      True,
        "company_name": company_name,
        "company": {
            "legal_name":  best.get("legal_name"),
            "abn":         best.get("abn"),
            "entity_type": best.get("entity_type"),
            "state":       best.get("state"),
            "postcode":    best.get("postcode"),
            "abn_status":  best.get("abn_status"),
        },
        "source":     "ABR",
        "status":     "external_resolved" if best.get("abn_status", "").lower() == "active" else "external_found",
        "confidence": min(confidence, 100),
        "pipeline":   pipeline,
        "errors":     errors,
    }


def run_company_abn_phase(value: str) -> Dict[str, Any]:
    """
    Auto-detect ABN vs company name and dispatch.

    - 11 digits (after whitespace removal) -> run_abn_phase()
    - Anything else                        -> run_company_phase()
    """
    cleaned = clean_abn(value)
    if cleaned.isdigit() and len(cleaned) == 11:
        return run_abn_phase(cleaned)
    return run_company_phase(value)
