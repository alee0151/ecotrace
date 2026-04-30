"""
brand_pipeline.py
=================

Purpose
-------
Handles the complete brand name input phase of the EcoTrace search pipeline.

Brand pipeline flow
-------------------
  User input (brand name string)
      │
      ├─── 1. Validate       minimum length, strip whitespace
      │
      ├─── 2. OAuth token    POST to TEST token endpoint (body params)
      │                     Credentials: IP_AUSTRALIA_CLIENT_ID / IP_AUSTRALIA_CLIENT_SECRET
      │                     URL (fixed): test.api.ipaustralia.gov.au
      │
      ├─── 3. Quick search   POST to PRODUCTION trademark API
      │                     URL (fixed): production.api.ipaustralia.gov.au
      │                     Auth: Bearer <token from step 2>
      │                     Body: {query, filters: {quickSearchType:[WORD], status:[REGISTERED]}}
      │
      ├─── 4. TM Detail      GET from PRODUCTION trademark API
      │                     Walks IDs until one resolves
      │
      ├─── 5. Owner pick     record["owner"][0]["name"] / ["abn"]
      │
      └─── 6. ABR verify     ABR name search using extracted legal owner

Environment variables  (backend/.env)
--------------------------------------
  IP_AUSTRALIA_CLIENT_ID      client id from Sandbox subscription  (required)
  IP_AUSTRALIA_CLIENT_SECRET  client secret from Sandbox subscription  (required)

  IP_AUSTRALIA_TOKEN_URL      override token URL     (optional, leave blank)
  IP_AUSTRALIA_TRADEMARK_URL  override trademark URL (optional, leave blank)

Default URLs
------------
  Token     : https://test.api.ipaustralia.gov.au/public/external-token-api/v1/access_token
  TM API    : https://production.api.ipaustralia.gov.au/public/australian-trade-mark-search-api/v1

Token request format (confirmed working)
-----------------------------------------
  POST <token_url>
  Content-Type: application/x-www-form-urlencoded
  Body: grant_type=client_credentials&client_id=...&client_secret=...

Diagnostic endpoint
-------------------
  GET /api/debug/trademark-auth
"""

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


# ============================================================
# Section 1 — URL helpers
# ============================================================

_DEFAULT_TOKEN_URL     = "https://test.api.ipaustralia.gov.au/public/external-token-api/v1/access_token"
_DEFAULT_TRADEMARK_URL = "https://test.api.ipaustralia.gov.au/public/australian-trade-mark-search-api/v1"


def _token_url() -> str:
    override = (os.getenv("IP_AUSTRALIA_TOKEN_URL") or "").strip()
    return override if override else _DEFAULT_TOKEN_URL


def _base_url() -> str:
    override = (os.getenv("IP_AUSTRALIA_TRADEMARK_URL") or "").strip()
    return override.rstrip("/") if override else _DEFAULT_TRADEMARK_URL


def _get_credentials():
    """Read IP_AUSTRALIA_CLIENT_ID and IP_AUSTRALIA_CLIENT_SECRET from environment."""
    client_id     = (os.getenv("IP_AUSTRALIA_CLIENT_ID")     or "").strip()
    client_secret = (os.getenv("IP_AUSTRALIA_CLIENT_SECRET") or "").strip()
    return client_id, client_secret


# ============================================================
# Section 2 — OAuth Token  (body params — confirmed working)
# ============================================================

_TOKEN_CACHE: Dict[str, Any] = {
    "access_token": None,
    "expires_at":   0,
}


def get_ip_australia_access_token() -> Optional[str]:
    """
    Obtain (or return cached) an IP Australia OAuth token.

    Token endpoint: TEST environment (fixed)
    Method: body params first (confirmed working), Basic Auth as fallback
    Cache: in-process, refreshed 60 s before expiry
    """
    now = int(time.time())
    if _TOKEN_CACHE["access_token"] and now < int(_TOKEN_CACHE["expires_at"]) - 60:
        return _TOKEN_CACHE["access_token"]

    client_id, client_secret = _get_credentials()

    if not client_id or not client_secret:
        print(
            "[brand_pipeline] ERROR: IP_AUSTRALIA_CLIENT_ID or IP_AUSTRALIA_CLIENT_SECRET "
            "is missing from .env.\n"
            "  Copy backend/.env.example -> backend/.env and fill in your credentials."
        )
        return None

    url = _token_url()
    print(f"[brand_pipeline] Fetching token from: {url}")

    # ---- Method A: body params (confirmed working) ----
    try:
        resp = requests.post(
            url,
            data={
                "grant_type":    "client_credentials",
                "client_id":     client_id,
                "client_secret": client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        print(f"[brand_pipeline] Token (body params): HTTP {resp.status_code}")
        if resp.ok:
            token = resp.json().get("access_token")
            if token:
                expires_in = int(resp.json().get("expires_in", 3600))
                _TOKEN_CACHE["access_token"] = token
                _TOKEN_CACHE["expires_at"]   = now + expires_in
                print(f"[brand_pipeline] Token obtained, expires in {expires_in}s.")
                return token
        print(f"[brand_pipeline] Body params rejected ({resp.status_code}), trying Basic Auth...")
    except requests.exceptions.Timeout:
        print("[brand_pipeline] Token request (body params) timed out")
    except requests.exceptions.RequestException as e:
        print(f"[brand_pipeline] Token request (body params) error: {e}")

    # ---- Method B: Basic Auth header (fallback) ----
    import base64
    basic_creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    try:
        resp = requests.post(
            url,
            data={"grant_type": "client_credentials"},
            headers={
                "Content-Type":  "application/x-www-form-urlencoded",
                "Authorization": f"Basic {basic_creds}",
            },
            timeout=30,
        )
        print(f"[brand_pipeline] Token (Basic Auth): HTTP {resp.status_code}")
        if resp.ok:
            token = resp.json().get("access_token")
            if token:
                expires_in = int(resp.json().get("expires_in", 3600))
                _TOKEN_CACHE["access_token"] = token
                _TOKEN_CACHE["expires_at"]   = now + expires_in
                print(f"[brand_pipeline] Token obtained (Basic Auth), expires in {expires_in}s.")
                return token
        print(
            f"[brand_pipeline] Both token methods failed. Last HTTP {resp.status_code}.\n"
            f"  URL : {url}\n"
            f"  Body: {resp.text[:300]}"
        )
    except requests.exceptions.Timeout:
        print("[brand_pipeline] Token request (Basic Auth) timed out")
    except requests.exceptions.RequestException as e:
        print(f"[brand_pipeline] Token request (Basic Auth) error: {e}")

    return None


def _get_auth_headers() -> Optional[Dict[str, str]]:
    """Build Bearer auth headers for PRODUCTION trademark API calls."""
    token = get_ip_australia_access_token()
    if not token:
        return None
    return {
        "Authorization": f"Bearer {token}",
        "Accept":        "application/json",
        "Content-Type":  "application/json",
    }


# ============================================================
# Section 3 — Quick Search  (PRODUCTION API)
# ============================================================

def _quick_search(brand_name: str) -> Dict[str, Any]:
    """
    POST {PRODUCTION_TRADEMARK_URL}/search/quick

    Body structure (from confirmed working script):
      {
        "query": "<brand_name>",
        "filters": {
          "quickSearchType": ["WORD"],
          "status": ["REGISTERED"]
        }
      }
    Returns: {"trademarkIds": [...], "count": N}
    """
    headers = _get_auth_headers()
    if not headers:
        return {
            "success": False,
            "message": (
                "Unable to obtain IP Australia OAuth token. "
                "Check IP_AUSTRALIA_CLIENT_ID and IP_AUSTRALIA_CLIENT_SECRET "
                f"in backend/.env.  Token URL: {_token_url()}"
            ),
        }

    url  = f"{_base_url()}/search/quick"
    body = {
        "query": brand_name,
        "filters": {
            "quickSearchType": ["WORD"],
            "status":          ["REGISTERED"],
        },
    }
    print(f"[brand_pipeline] Quick search POST (PRODUCTION): {url}  query={brand_name!r}")

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=30)

        # Token expired mid-flight — refresh once and retry
        if resp.status_code == 401:
            _TOKEN_CACHE["access_token"] = None
            _TOKEN_CACHE["expires_at"]   = 0
            headers = _get_auth_headers()
            if headers:
                resp = requests.post(url, headers=headers, json=body, timeout=30)

        if not resp.ok:
            return {"success": False, "status_code": resp.status_code, "message": resp.text[:500]}

        return {"success": True, "data": resp.json()}

    except requests.exceptions.Timeout:
        return {"success": False, "message": "IP Australia quick search timed out"}
    except requests.exceptions.RequestException as e:
        return {"success": False, "message": f"IP Australia network error: {e}"}


# ============================================================
# Section 4 — Trademark Detail  (PRODUCTION API)
# ============================================================

_TM_DETAIL_MAX_TRIES = 10


def _fetch_trademark_detail(trademark_id: str) -> Dict[str, Any]:
    """
    GET {PRODUCTION_TRADEMARK_URL}/trade-mark/{trademark_id}

    Returns the full ApiTrademark record including:
      record["owner"][0]["name"]  — legal owner name
      record["owner"][0]["abn"]   — owner ABN (may be None)
    """
    headers = _get_auth_headers()
    if not headers:
        return {"success": False, "message": "No auth token for trademark detail lookup"}

    url = f"{_base_url()}/trade-mark/{trademark_id}"
    print(f"[brand_pipeline] Trademark detail GET (PRODUCTION): {url}")

    try:
        resp = requests.get(url, headers=headers, timeout=30)

        if resp.status_code == 401:
            _TOKEN_CACHE["access_token"] = None
            _TOKEN_CACHE["expires_at"]   = 0
            headers = _get_auth_headers()
            if headers:
                resp = requests.get(url, headers=headers, timeout=30)

        if resp.status_code == 404:
            return {"success": False, "not_found": True,
                    "message": f"Trademark {trademark_id} not found (404)"}

        if not resp.ok:
            return {"success": False, "status_code": resp.status_code,
                    "message": resp.text[:300]}

        return {"success": True, "data": resp.json()}

    except requests.exceptions.Timeout:
        return {"success": False, "message": "Trademark detail request timed out"}
    except requests.exceptions.RequestException as e:
        return {"success": False, "message": f"Trademark detail network error: {e}"}


def _fetch_first_available_trademark(
    ids: List[str],
    max_tries: int = _TM_DETAIL_MAX_TRIES,
) -> Dict[str, Any]:
    """Walk IDs in order; return the first that resolves (HTTP 200). Skip 404s."""
    skipped: List[str] = []
    for tm_id in [str(i) for i in ids[:max_tries]]:
        resp = _fetch_trademark_detail(tm_id)
        if resp.get("success"):
            if skipped:
                print(f"[brand_pipeline] skipped 404 IDs {skipped}; resolved on {tm_id}")
            return {"success": True, "data": resp["data"],
                    "tried": len(skipped) + 1, "id": tm_id}
        if resp.get("not_found"):
            skipped.append(tm_id)
            continue
        return {"success": False,
                "message": resp.get("message", "Trademark detail lookup failed"),
                "tried": len(skipped) + 1}
    return {
        "success": False,
        "message": (
            f"None of the first {max_tries} trademark IDs returned a valid record. "
            f"IDs tried: {skipped}"
        ),
        "tried": len(skipped),
    }


# ============================================================
# Section 5 — Owner Extraction
# ============================================================

def _extract_owner_from_record(record: Dict[str, Any]) -> Optional[str]:
    """
    Extract legal owner name from ApiTrademark record.

    Primary  : record["owner"][0]["name"]          (ApiPartyType[])
    Fallback : record["addressForService"][0]["name"]
    """
    for key in ("owner", "addressForService"):
        lst = record.get(key)
        if isinstance(lst, list) and lst:
            first = lst[0]
            name  = first.get("name") if isinstance(first, dict) else first
            if isinstance(name, str) and name.strip():
                return name.strip()
    return None


def _extract_abn_from_record(record: Dict[str, Any]) -> Optional[str]:
    """
    Extract ABN directly from record["owner"][0]["abn"] if present.
    Saves an ABR lookup when IP Australia already provides it.
    """
    owner_list = record.get("owner")
    if isinstance(owner_list, list) and owner_list:
        first = owner_list[0]
        if isinstance(first, dict):
            abn = first.get("abn")
            if abn and str(abn).strip():
                return str(abn).strip()
    return None


def _build_trademark_summary(record: Dict[str, Any], legal_owner: Optional[str]) -> Dict:
    words     = record.get("words") or []
    word_mark = " ".join(words).strip() if isinstance(words, list) else None
    return {
        "number":            record.get("number"),
        "word_mark":         word_mark or None,
        "status":            record.get("statusCode") or record.get("statusGroup"),
        "filing_date":       record.get("filingDate") or record.get("lodgementDate"),
        "registration_date": record.get("enteredOnRegisterDate"),
        "goods_services":    record.get("goodsAndServices"),
        "legal_owner":       legal_owner,
        "owner_abn":         _extract_abn_from_record(record),
    }


# ============================================================
# Section 6 — Diagnostic  (GET /api/debug/trademark-auth)
# ============================================================

def diagnose_token() -> Dict[str, Any]:
    """
    Test OAuth token fetch in isolation.
    Tries body params first (confirmed working), then Basic Auth.
    """
    import base64
    client_id, client_secret = _get_credentials()
    token_url_val            = _token_url()
    tm_url_val               = _base_url()

    report: Dict[str, Any] = {
        "token_environment":     "test  (fixed)",
        "trademark_environment": "production  (fixed)",
        "token_url":             token_url_val,
        "trademark_url":         tm_url_val,
        "credential_vars": {
            "id":     "IP_AUSTRALIA_CLIENT_ID",
            "secret": "IP_AUSTRALIA_CLIENT_SECRET",
        },
        "client_id_set":     bool(client_id),
        "client_secret_set": bool(client_secret),
        "token_obtained":    False,
        "method_used":       None,
        "http_status":       None,
        "error":             None,
    }

    if not client_id or not client_secret:
        report["error"] = (
            "IP_AUSTRALIA_CLIENT_ID or IP_AUSTRALIA_CLIENT_SECRET "
            "is missing from backend/.env."
        )
        return report

    # Method A: body params
    try:
        resp = requests.post(
            token_url_val,
            data={
                "grant_type":    "client_credentials",
                "client_id":     client_id,
                "client_secret": client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        report["http_status"] = resp.status_code
        if resp.ok and resp.json().get("access_token"):
            report["token_obtained"] = True
            report["method_used"]    = "Body params (confirmed working)"
            return report
        report["error"] = f"Body params: HTTP {resp.status_code} — {resp.text[:200]}"
    except Exception as e:
        report["error"] = f"Body params exception: {e}"

    # Method B: Basic Auth
    basic_creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    try:
        resp = requests.post(
            token_url_val,
            data={"grant_type": "client_credentials"},
            headers={
                "Content-Type":  "application/x-www-form-urlencoded",
                "Authorization": f"Basic {basic_creds}",
            },
            timeout=30,
        )
        report["http_status"] = resp.status_code
        if resp.ok and resp.json().get("access_token"):
            report["token_obtained"] = True
            report["method_used"]    = "Basic Auth header (fallback)"
            report["error"]          = None
            return report
        report["error"] = (
            (report.get("error") or "") +
            f" | Basic Auth: HTTP {resp.status_code} — {resp.text[:200]}"
        )
    except Exception as e:
        report["error"] = (report.get("error") or "") + f" | Basic Auth exception: {e}"

    return report


# ============================================================
# Section 7 — Orchestrated Brand Resolution
# ============================================================

def resolve_brand(
    brand_name:    str,
    abr_lookup_fn: Any = None,
) -> Dict[str, Any]:
    """
    Full brand resolution pipeline.
    1. Validate brand_name.
    2. Quick search  →  list of trademark IDs.
    3. Detail fetch  →  first resolved ApiTrademark record.
    4. Extract owner name + ABN from record["owner"][0].
    5. ABR lookup on owner name (if ABN not already present in record).
    """
    pipeline: List[str] = []
    errors:   List[str] = []

    brand_name = (brand_name or "").strip()

    pipeline.append("Brand name validation")
    if len(brand_name) < 2:
        return {
            "success":    False,
            "brand_name": brand_name,
            "error":      "Brand name must be at least 2 characters.",
            "pipeline":   pipeline,
            "errors":     errors,
            "confidence": 0,
        }

    pipeline.append(f"OAuth token  ←  {_token_url()}")
    pipeline.append(f"TM Search    →  {_base_url()}")
    pipeline.append(f"Query: '{brand_name}'")

    search_resp = _quick_search(brand_name)

    if not search_resp.get("success"):
        msg = search_resp.get("message", "IP Australia search failed")
        return {
            "success": False, "brand_name": brand_name, "error": msg,
            "trademark": None, "legal_owner": None, "abr": None,
            "pipeline": pipeline, "errors": [msg], "confidence": 0,
        }

    search_data = search_resp["data"]
    total_ids   = search_data.get("count", 0)
    ids         = search_data.get("trademarkIds") or []

    pipeline.append(f"Found {total_ids} trademark ID(s)")

    if not ids:
        return {
            "success": False, "brand_name": brand_name,
            "error":   f"No registered word-mark trademarks found for '{brand_name}'",
            "trademark": None, "legal_owner": None, "abr": None,
            "pipeline": pipeline, "errors": errors, "confidence": 0,
        }

    pipeline.append(f"Fetching detail (up to {_TM_DETAIL_MAX_TRIES} tries)")
    detail_resp = _fetch_first_available_trademark(ids)

    if not detail_resp.get("success"):
        msg = detail_resp.get("message", "Could not fetch any trademark detail record")
        errors.append(msg)
        return {
            "success": False, "brand_name": brand_name, "error": msg,
            "trademark": None, "legal_owner": None, "abr": None,
            "tm_total": total_ids, "pipeline": pipeline, "errors": errors, "confidence": 10,
        }

    resolved_id = detail_resp["id"]
    pipeline.append(f"Resolved trademark ID: {resolved_id} (after {detail_resp['tried']} attempt(s))")

    record      = detail_resp["data"]
    legal_owner = _extract_owner_from_record(record)
    owner_abn   = _extract_abn_from_record(record)   # may already be in record
    trademark   = _build_trademark_summary(record, legal_owner)

    abr_result: Optional[Dict[str, Any]] = None
    if abr_lookup_fn and legal_owner:
        pipeline.append(f"ABR name lookup: '{legal_owner}'")
        abr_result = abr_lookup_fn(legal_owner)
        if not abr_result.get("success"):
            short_name = _strip_legal_suffix(legal_owner)
            if short_name and short_name != legal_owner:
                pipeline.append(f"ABR retry with short name: '{short_name}'")
                abr_result = abr_lookup_fn(short_name)

    confidence = 0
    if resolved_id:                                                 confidence += 20
    if str(trademark.get("status") or "").lower() == "registered": confidence += 30
    elif trademark.get("status"):                                   confidence += 10
    if legal_owner:                                                 confidence += 20
    if owner_abn or (abr_result and abr_result.get("success")):    confidence += 30

    return {
        "success":     True,
        "brand_name":  brand_name,
        "trademark":   trademark,
        "legal_owner": legal_owner,
        "owner_abn":   owner_abn,
        "abr":         abr_result,
        "tm_total":    total_ids,
        "confidence":  min(confidence, 100),
        "pipeline":    pipeline,
        "errors":      errors,
    }


def _strip_legal_suffix(name: str) -> str:
    import re
    for p in [r"\bPty\.?\s*Ltd\.?", r"\bPty\.?", r"\bLtd\.?", r"\bLimited\b",
              r"\bInc\.?", r"\bCorp\.?", r"\bLLC\.?", r"\bCo\.?", r"\bHoldings\b"]:
        name = re.sub(p, "", name, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", name).strip()


# ============================================================
# Section 8 — Convenience wrapper for main.py
# ============================================================

def run_brand_phase(
    brand_name:    str,
    abr_lookup_fn: Any = None,
) -> Dict[str, Any]:
    """Thin wrapper used by /api/search brand branch in main.py."""
    resolved = resolve_brand(brand_name, abr_lookup_fn=abr_lookup_fn)
    resolved["status"] = "external_resolved" if resolved["success"] else "not_found"
    return resolved
