#!/usr/bin/env python3
"""
Seeco — Layer A: Species & Threat Data
Datasets:
  1. ALA Biocache API  → species occurrences near location
  2. IUCN Red List v4  → threat category enrichment per species
"""

import requests
import time
import json
import os
import threading
import math
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


def safe_print(message: object = "") -> None:
    """
    Keep Layer A logging from crashing under Windows code pages when species
    names or decorative characters are not representable in the active console.
    """
    text = str(message)
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))

# ── CONFIG ─────────────────────────────────────────────────────────────────────
IUCN_TOKEN   = "istMdZT8xqeky1Hc1o8ZgxHrf62HvsByF5Em"
ALA_BASE     = "https://biocache-ws.ala.org.au/ws"
ALA_OCCURRENCES_URL = "https://biocache-ws.ala.org.au/ws/occurrences/search"
IUCN_BASE    = "https://api.iucnredlist.org/api/v4"
TIMEOUT      = int(os.getenv("ALA_TIMEOUT_SECONDS", "30"))
ALA_RETRIES  = int(os.getenv("ALA_RETRIES", "2"))
IUCN_DELAY   = 0.5   # seconds between IUCN calls to respect rate limits
DEFAULT_IUCN_CACHE_FILE = Path(__file__).resolve().parents[1] / "cache" / "iucn_au_cache.json"

# Threat category weights for biodiversity score contribution
THREAT_WEIGHTS = {
    "CR": 1.00,   # Critically Endangered
    "EN": 0.75,   # Endangered
    "VU": 0.50,   # Vulnerable
    "NT": 0.20,   # Near Threatened
    "LC": 0.05,   # Least Concern
    "DD": 0.10,   # Data Deficient (precautionary)
    "EX": 0.00,   # Extinct
    "EW": 0.00,   # Extinct in the Wild
}

# ── DATA CLASSES ───────────────────────────────────────────────────────────────
@dataclass
class SpeciesRecord:
    scientific_name: str
    common_name: Optional[str]
    taxon_rank: Optional[str]
    record_count: int
    iucn_category: Optional[str] = None
    iucn_category_name: Optional[str] = None
    threat_weight: float = 0.0
    iucn_url: Optional[str] = None

@dataclass
class LayerAResult:
    lat: float
    lon: float
    radius_km: float
    total_ala_records: int
    unique_species: list[SpeciesRecord] = field(default_factory=list)
    threatened_species: list[SpeciesRecord] = field(default_factory=list)
    species_threat_score: float = 0.0
    score_breakdown: dict = field(default_factory=dict)


def calculate_species_threat_score(species: list[SpeciesRecord]) -> float:
    """
    Calculate a 0-100 Layer A species threat score.

    The score is intentionally proportional to IUCN-assessed species, not raw
    ALA occurrence volume. A site with a small number of threatened species
    should not become "Critical" just because occurrence records are numerous.
    """
    assessed = [s for s in species if s.iucn_category]
    assessed_count = len(assessed)
    if assessed_count == 0:
        return 0.0

    threatened = [s for s in assessed if s.iucn_category in ("CR", "EN", "VU")]
    if not threatened:
        return 0.0

    threatened_count = len(threatened)
    threatened_ratio = threatened_count / assessed_count
    weighted_threat = sum(THREAT_WEIGHTS.get(s.iucn_category or "", 0.0) for s in threatened)
    weighted_threat_ratio = weighted_threat / assessed_count

    # Presence captures how much of the assessed local community is threatened.
    presence_component = math.sqrt(threatened_ratio) * 45

    # Severity rewards CR/EN/VU composition without letting a few species max out.
    severity_component = weighted_threat_ratio * 70

    # Small extra signal for genuinely severe categories.
    critical_endangered_bonus = min(
        15.0,
        sum(6.0 for s in threatened if s.iucn_category == "CR")
        + sum(3.0 for s in threatened if s.iucn_category == "EN"),
    )

    # Occurrence volume is only confidence/context and is capped tightly.
    occurrence_context = min(
        5.0,
        (
            sum(math.log1p(max(0, s.record_count)) for s in threatened)
            / max(1, threatened_count)
            / math.log(101)
        ) * 5,
    )

    score = (
        presence_component
        + severity_component
        + critical_endangered_bonus
        + occurrence_context
    )
    return round(min(100.0, score), 2)

# ── IUCN CATEGORY LOOKUP ───────────────────────────────────────────────────────
IUCN_CATEGORY_NAMES = {
    "CR": "Critically Endangered",
    "EN": "Endangered",
    "VU": "Vulnerable",
    "NT": "Near Threatened",
    "LC": "Least Concern",
    "DD": "Data Deficient",
    "EX": "Extinct",
    "EW": "Extinct in the Wild",
}

# Pre-built IUCN Australia cache — avoids repeated API calls per species
# Populated once on first run via build_iucn_cache()
_iucn_au_cache: dict[str, dict] = {}
_iucn_cache_lock = threading.RLock()
_iucn_cache_status = {
    "state": "empty",
    "count": 0,
    "started_at": None,
    "finished_at": None,
    "error": None,
    "source": None,
    "cache_file": str(DEFAULT_IUCN_CACHE_FILE),
}

def get_iucn_cache_status() -> dict:
    return {
        **_iucn_cache_status,
        "count": len(_iucn_au_cache),
        "cache_file": str(get_iucn_cache_file()),
    }


def get_iucn_cache_file() -> Path:
    configured = (os.getenv("IUCN_CACHE_FILE") or "").strip()
    return Path(configured) if configured else DEFAULT_IUCN_CACHE_FILE


def get_iucn_cache_max_age_hours() -> int:
    try:
        return int(os.getenv("IUCN_CACHE_MAX_AGE_HOURS", "168"))
    except ValueError:
        return 168

def ensure_iucn_cache_loaded() -> int:
    """
    Build the in-memory IUCN Australia cache once per backend process.
    Returns the number of cached species records.
    """
    global _iucn_au_cache

    if _iucn_au_cache:
        return len(_iucn_au_cache)

    with _iucn_cache_lock:
        if not _iucn_au_cache:
            _iucn_cache_status.update({
                "state": "loading",
                "count": 0,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "finished_at": None,
                "error": None,
                "source": None,
            })
            try:
                disk_cache = load_iucn_cache_from_disk()
                if disk_cache is not None:
                    _iucn_au_cache = disk_cache
                    source = "disk"
                else:
                    _iucn_au_cache = build_iucn_cache()
                    save_iucn_cache_to_disk(_iucn_au_cache)
                    source = "api"
                _iucn_cache_status.update({
                    "state": "ready",
                    "count": len(_iucn_au_cache),
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "error": None,
                    "source": source,
                })
            except Exception as error:
                _iucn_cache_status.update({
                    "state": "failed",
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "error": str(error),
                })
                raise
        return len(_iucn_au_cache)


def load_iucn_cache_from_disk() -> Optional[dict]:
    cache_file = get_iucn_cache_file()
    max_age_hours = get_iucn_cache_max_age_hours()
    if max_age_hours <= 0 or not cache_file.exists():
        return None

    try:
        with cache_file.open("r", encoding="utf-8") as cache_handle:
            payload = json.load(cache_handle)
    except Exception as error:
        print(f"  [IUCN] Disk cache ignored: {error}")
        return None

    generated_raw = payload.get("generated_at")
    records = payload.get("records")
    if not isinstance(records, dict) or not generated_raw:
        print("  [IUCN] Disk cache ignored: invalid format")
        return None

    try:
        generated_at = datetime.fromisoformat(str(generated_raw).replace("Z", "+00:00"))
    except ValueError:
        print("  [IUCN] Disk cache ignored: invalid timestamp")
        return None

    max_age = timedelta(hours=max_age_hours)
    if datetime.now(timezone.utc) - generated_at > max_age:
        print(f"  [IUCN] Disk cache expired: {cache_file}")
        return None

    print(f"  [IUCN] Loaded disk cache: {len(records):,} Australian species from {cache_file}")
    return records


def save_iucn_cache_to_disk(cache: dict) -> None:
    if not cache:
        return

    try:
        cache_file = get_iucn_cache_file()
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "IUCN Red List v4 countries/AU",
            "count": len(cache),
            "records": cache,
        }
        tmp_path = cache_file.with_suffix(f"{cache_file.suffix}.tmp")
        with tmp_path.open("w", encoding="utf-8") as cache_handle:
            json.dump(payload, cache_handle, ensure_ascii=True, separators=(",", ":"))
        tmp_path.replace(cache_file)
        print(f"  [IUCN] Saved disk cache: {cache_file}")
    except Exception as error:
        print(f"  [IUCN] Disk cache save skipped: {error}")


def build_iucn_cache() -> dict:
    """
    Fetches all IUCN-assessed Australian species (paginated) and builds
    a scientific_name → {category, url} lookup dict.
    Called once at startup; results cached in memory.
    """
    print("  [IUCN] Building Australia species cache (paginated)...")
    headers = {"Authorization": f"Bearer {IUCN_TOKEN}"}
    cache = {}
    page = 1

    while True:
        url = f"{IUCN_BASE}/countries/AU"
        params = {"latest": "true", "scope_code": 1, "page": page}
        try:
            r = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
            if r.status_code != 200:
                print(f"  [IUCN] Warning: HTTP {r.status_code} on page {page}")
                break

            data = r.json()
            assessments = data.get("assessments", [])
            if not assessments:
                break

            for a in assessments:
                name = a.get("taxon_scientific_name", "").strip().lower()
                cat  = a.get("red_list_category_code", "")
                url_ = a.get("url", "")
                if name:
                    cache[name] = {"category": cat, "url": url_}

            print(f"  [IUCN] Page {page}: {len(assessments)} records | Cache size: {len(cache)}")

            # IUCN paginates at 100 per page — stop when last page returns < 100
            if len(assessments) < 100:
                break

            page += 1
            time.sleep(IUCN_DELAY)

        except Exception as e:
            print(f"  [IUCN] Error on page {page}: {e}")
            break

    print(f"  [IUCN] Cache built: {len(cache):,} Australian species indexed\n")
    return cache

def lookup_iucn(scientific_name: str) -> tuple[Optional[str], Optional[str]]:
    """
    Looks up a species in the pre-built IUCN cache.
    Returns (category_code, iucn_url) or (None, None) if not found.
    """
    key = scientific_name.strip().lower()
    match = _iucn_au_cache.get(key)
    if match:
        return match["category"], match["url"]

    # Try genus-level fallback (first word only)
    genus = key.split()[0] if " " in key else key
    for cached_name, data in _iucn_au_cache.items():
        if cached_name.startswith(genus + " "):
            return data["category"], data["url"]

    return None, None

# ── ALA SPECIES QUERY ──────────────────────────────────────────────────────────
def query_ala_species(lat: float, lon: float, radius_km: float,
                      page_size: int = 50) -> tuple[int, list[dict]]:
    """
    Queries ALA Biocache for unique species observed within radius of location.

    Args:
        lat        : Latitude of location (WGS84)
        lon        : Longitude of location (WGS84)
        radius_km  : Search radius in kilometres
        page_size  : Max unique species to return (default 50, ALA hard cap 1000)

    Returns:
        (total_records, species_list)
        total_records : int  — total ALA occurrence records in radius
        species_list  : list[dict] with keys:
                          scientific_name, common_name, taxon_rank, record_count
    """
    # ── Step 1: Faceted species query ──────────────────────────────────────────
    params = {
        "q":              "*:*",
        "lat":            lat,
        "lon":            lon,
        "radius":         radius_km,
        "pageSize":       0,
        "qualityProfile": "ALA",
        "fq":             "taxonRank:species",
        "facets":         "taxon_name",
        "flimit":         min(page_size, 1000),  # ALA hard cap is 1000
    }
    last_error = None
    for attempt in range(1, max(1, ALA_RETRIES) + 1):
        try:
            r = requests.get(f"{ALA_BASE}/occurrences/search", params=params, timeout=TIMEOUT)
            break
        except requests.exceptions.Timeout as error:
            last_error = error
            if attempt >= max(1, ALA_RETRIES):
                raise
            print(f"  [ALA] Timeout on attempt {attempt}; retrying...")
            time.sleep(1.5 * attempt)
    else:
        raise last_error or RuntimeError("ALA request failed")
    r.raise_for_status()

    data          = r.json()
    total_records = data.get("totalRecords", 0)
    facet_results = data.get("facetResults", [])
    raw_species   = facet_results[0].get("fieldResult", []) if facet_results else []

    # ── Step 2: Normalise to Seeco schema ──────────────────────────────────────
    species_list = []
    for s in raw_species:
        label = s.get("label", "").strip()
        if not label or label.lower() in ("null", "unknown", "incertae sedis"):
            continue
        species_list.append({
            "scientific_name": label,
            "common_name":     "",
            "taxon_rank":      "species",
            "record_count":    s.get("count", 1)   # ✅ occurrence count per species
        })

    # ── Step 3: Common name enrichment via ALA name-matching API ───────────────
    # Capped at 20 enrichments to prevent timeout on large species lists
    NAME_SEARCH = "https://namematching-ws.ala.org.au/api/searchByClassification"
    for i in range(min(len(species_list), 20)):
        try:
            nr = requests.get(NAME_SEARCH, params={
                "scientificName": species_list[i]["scientific_name"]
            }, timeout=5)
            if nr.status_code == 200:
                result = nr.json()
                common = (result.get("commonName") or
                          result.get("vernacularName") or "")
                species_list[i]["common_name"] = common.strip()
        except Exception:
            pass  # best-effort only; scoring works without common names

    return total_records, species_list

# ── LAYER A MAIN FUNCTION ──────────────────────────────────────────────────────
def run_layer_a(lat: float, lon: float, radius_km: float = 10.0,
                max_species: int = 50) -> LayerAResult:
    """
    Full Layer A pipeline:
      1. Query ALA for species occurrences near location
      2. Enrich each species with IUCN threat category
      3. Calculate species threat score component
    """
    global _iucn_au_cache

    safe_print(f"\n{'='*65}")
    safe_print("  Seeco - Layer A: Species & Threat Data")
    safe_print(f"  Location : {lat}, {lon}  |  Radius: {radius_km}km")
    safe_print(f"{'='*65}\n")

    # ── Step 1: Build IUCN cache if empty ─────────────────────────────────────
    ensure_iucn_cache_loaded()

    # ── Step 2: Query ALA ──────────────────────────────────────────────────────
    safe_print(f"  [ALA] Querying species occurrences within {radius_km}km...")
    total_records, raw_species = query_ala_species(lat, lon, radius_km, max_species)
    safe_print(f"  [ALA] Total records: {total_records:,} | Unique species found: {len(raw_species)}\n")

    # ── Step 3: IUCN enrichment ────────────────────────────────────────────────
    safe_print(f"  [IUCN] Enriching {len(raw_species)} species with threat categories...")
    enriched: list[SpeciesRecord] = []

    for sp in raw_species:
        cat, iucn_url = lookup_iucn(sp["scientific_name"])
        cat_name = IUCN_CATEGORY_NAMES.get(cat, "Not assessed") if cat else "Not assessed"
        weight   = THREAT_WEIGHTS.get(cat, 0.0) if cat else 0.0

        enriched.append(SpeciesRecord(
            scientific_name  = sp["scientific_name"],
            common_name      = sp.get("common_name", ""),
            taxon_rank       = sp.get("taxon_rank", ""),
            record_count     = sp.get("record_count", 1),
            iucn_category    = cat,
            iucn_category_name = cat_name,
            threat_weight    = weight,
            iucn_url         = iucn_url
        ))

    # ── Step 4: Identify threatened species (CR/EN/VU) ────────────────────────
    threatened = [s for s in enriched if s.iucn_category in ("CR", "EN", "VU")]
    threatened.sort(key=lambda x: x.threat_weight, reverse=True)

    # ── Step 5: Calculate species threat score (0–100) ────────────────────────
    normalised = calculate_species_threat_score(enriched)

    # Breakdown by category
    breakdown = {}
    for cat in THREAT_WEIGHTS:
        count = sum(1 for s in enriched if s.iucn_category == cat)
        if count > 0:
            breakdown[f"{cat} ({IUCN_CATEGORY_NAMES[cat]})"] = count

    result = LayerAResult(
        lat                  = lat,
        lon                  = lon,
        radius_km            = radius_km,
        total_ala_records    = total_records,
        unique_species       = enriched,
        threatened_species   = threatened,
        species_threat_score = normalised,
        score_breakdown      = breakdown,
    )

    # ── Step 6: Print summary ──────────────────────────────────────────────────
    safe_print(f"\n  {'-'*60}")
    safe_print("  LAYER A RESULTS")
    safe_print(f"  {'-'*60}")
    safe_print(f"  Total ALA records (radius {radius_km}km)  : {total_records:,}")
    safe_print(f"  Unique species queried                : {len(enriched)}")
    safe_print(f"  IUCN-assessed species                 : {sum(1 for s in enriched if s.iucn_category)}")
    safe_print(f"  Threatened species (CR/EN/VU)         : {len(threatened)}")
    safe_print(f"  Species Threat Score (0-100)          : {normalised}")
    safe_print()

    if breakdown:
        safe_print("  Threat Category Breakdown:")
        for cat_label, count in breakdown.items():
            safe_print(f"    {cat_label:<35} : {count} species")

    if threatened:
        safe_print("\n  Top Threatened Species:")
        for sp in threatened[:10]:
            flag = "CR" if sp.iucn_category == "CR" else "EN" if sp.iucn_category == "EN" else "VU"
            safe_print(f"    {flag} [{sp.iucn_category}] {sp.scientific_name}"
                       + (f" ({sp.common_name})" if sp.common_name else ""))

    safe_print(f"  {'-'*60}\n")
    return result

# ── ENTRY POINT ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Test: Port of Melbourne industrial precinct
    result = run_layer_a(
        lat       = -37.8224,
        lon       = 144.9340,
        radius_km = 10.0,
        max_species = 50
    )

    # Export full species list to JSON
    output = {
        "location": {"lat": result.lat, "lon": result.lon, "radius_km": result.radius_km},
        "total_ala_records": result.total_ala_records,
        "species_threat_score": result.species_threat_score,
        "score_breakdown": result.score_breakdown,
        "threatened_species": [
            {
                "scientific_name": s.scientific_name,
                "common_name": s.common_name,
                "iucn_category": s.iucn_category,
                "iucn_category_name": s.iucn_category_name,
                "threat_weight": s.threat_weight,
                "iucn_url": s.iucn_url
            }
            for s in result.threatened_species
        ],
        "all_species": [
            {
                "scientific_name": s.scientific_name,
                "common_name": s.common_name,
                "iucn_category": s.iucn_category or "Not assessed",
                "threat_weight": s.threat_weight
            }
            for s in result.unique_species
        ]
    }

    with open("layer_a_result.json", "w") as f:
        json.dump(output, f, indent=2)

    print("  Output saved → layer_a_result.json")
