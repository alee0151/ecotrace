#!/usr/bin/env python3
"""
Seeco — Spatial Data Cleaning & PostGIS Loader
Datasets: CAPAD, KBA, IBRA v7
Pipeline:
  1. Load shapefile/GeoJSON
  2. Validate + clean geometry and attributes
  3. Reproject to WGS84 (EPSG:4326)
  4. Standardise column names to Seeco schema
  5. Push to PostGIS with spatial index
"""

import geopandas as gpd
import pandas as pd
import numpy as np
from shapely.validation import make_valid
from sqlalchemy import create_engine, text
import logging
import sys
import os
from datetime import datetime

# ── CONFIG ─────────────────────────────────────────────────────────────────────
DB_URL = "postgresql://seeco:password@localhost:5432/seeco_db"
# Example: "postgresql://user:password@host:port/dbname"

# File paths — update to your downloaded shapefile locations
CAPAD_PATH = "~/Downloads/datasets/CAPAD/Collaborative_Australian_Protected_Areas_Database_(CAPAD)_2024_-_Terrestrial__.shp"   # or .geojson
KBA_PATH   = "~/Downloads/datasets/KBA_Data/KBAsGlobal_2026_March_01_POL.shp"
IBRA_PATH  = "~/Downloads/datasets/IBRARegion_Aust70/IBRARegion_Aust70.shp"

TARGET_CRS = "EPSG:4326"   # WGS84 — required for PostGIS lat/lon queries
CHUNK_SIZE = 500            # rows per DB write batch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)

# ── GEOMETRY CLEANING ──────────────────────────────────────────────────────────
def clean_geometries(gdf: gpd.GeoDataFrame, dataset_name: str) -> gpd.GeoDataFrame:
    """
    Validates, repairs, and filters geometries.
    Removes null, empty, and unrecoverable invalid geometries.
    """
    original_count = len(gdf)

    # 1. Drop null geometries
    gdf = gdf[gdf.geometry.notna()].copy()
    null_dropped = original_count - len(gdf)

    # 2. Drop empty geometries
    gdf = gdf[~gdf.geometry.is_empty].copy()
    empty_dropped = original_count - null_dropped - len(gdf)

    # 3. Repair invalid geometries using make_valid (buffer(0) alternative)
    invalid_mask = ~gdf.geometry.is_valid
    invalid_count = invalid_mask.sum()
    if invalid_count > 0:
        gdf.loc[invalid_mask, "geometry"] = gdf.loc[invalid_mask, "geometry"].apply(make_valid)
        log.info(f"  [{dataset_name}] Repaired {invalid_count} invalid geometries")

    # 4. Drop still-invalid after repair
    gdf = gdf[gdf.geometry.is_valid].copy()

    # 5. Explode MultiPolygons to single parts for consistent spatial indexing
    gdf = gdf.explode(index_parts=False).reset_index(drop=True)

    # 6. Remove slivers (area < 1m² after projection)
    if gdf.crs and gdf.crs.is_geographic:
        # Reproject temporarily to GDA2020 (EPSG:7844) for area check
        gdf_proj = gdf.to_crs("EPSG:3577")
        area_mask = gdf_proj.geometry.area >= 1.0
        gdf = gdf[area_mask].copy()
        sliver_dropped = (~area_mask).sum()
        if sliver_dropped > 0:
            log.info(f"  [{dataset_name}] Removed {sliver_dropped} sliver polygons (<1m²)")

    log.info(f"  [{dataset_name}] Geometry cleaning: {original_count} → {len(gdf)} "
             f"(dropped: {null_dropped} null, {empty_dropped} empty)")
    return gdf

# ── STRING CLEANING ────────────────────────────────────────────────────────────
def clean_string_cols(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    for col in gdf.select_dtypes(include="object").columns:
        if col == "geometry":
            continue
        gdf[col] = (
            gdf[col]
            .astype(str)
            .str.strip()
            .str.replace(r"\s+", " ", regex=True)   # collapse whitespace
            .replace({"nan": None, "None": None, "": None, "N/A": None,
                      "NA": None, "NULL": None, "null": None})
        )
    return gdf

# ── DATE PARSING ───────────────────────────────────────────────────────────────
def safe_parse_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", dayfirst=True)

# ═══════════════════════════════════════════════════════════════════════════════
# DATASET 1: CAPAD
# Source: digital.atlas.gov.au/datasets/capad
# Key fields: PA_ID, NAME, TYPE, TYPE_ABBR, IUCN, GAZ_AREA, GIS_AREA,
#             GAZ_DATE, LATEST_GAZ, NRS_PA, STATE, AUTHORITY, GOVERNANCE
# ═══════════════════════════════════════════════════════════════════════════════
def process_capad(path: str) -> gpd.GeoDataFrame:
    log.info("\n── CAPAD: Loading and cleaning ──")
    gdf = gpd.read_file(path)
    log.info(f"  Loaded: {len(gdf):,} rows | CRS: {gdf.crs}")
    log.info(f"  Columns: {list(gdf.columns)}")

    # ── Geometry cleaning
    gdf = clean_geometries(gdf, "CAPAD")

    # ── Reproject to WGS84
    if gdf.crs != TARGET_CRS:
        gdf = gdf.to_crs(TARGET_CRS)

    # ── Standardise column names to Seeco schema
    col_map = {
        "PA_ID":       "pa_id",
        "NAME":        "name",
        "TYPE":        "pa_type",
        "TYPE_ABBR":   "type_abbr",
        "IUCN":        "iucn_category",
        "GAZ_AREA":    "gaz_area_ha",
        "GIS_AREA":    "gis_area_ha",
        "GAZ_DATE":    "gaz_date",
        "LATEST_GAZ":  "latest_gaz_date",
        "NRS_PA":      "nrs_pa",
        "STATE":       "state",
        "AUTHORITY":   "authority",
        "GOVERNANCE":  "governance",
        "ENVIRON":     "environment",
        "MGT_PLAN":    "mgt_plan_status",
    }
    # Only rename columns that exist
    rename = {k: v for k, v in col_map.items() if k in gdf.columns}
    gdf = gdf.rename(columns=rename)

    # ── Keep only Seeco-relevant columns
    keep_cols = list(rename.values()) + ["geometry"]
    gdf = gdf[[c for c in keep_cols if c in gdf.columns]]

    # ── String cleaning
    gdf = clean_string_cols(gdf)

    # ── Date parsing
    for date_col in ["gaz_date", "latest_gaz_date"]:
        if date_col in gdf.columns:
            gdf[date_col] = safe_parse_date(gdf[date_col])

    # ── Numeric cleaning
    for num_col in ["gaz_area_ha", "gis_area_ha"]:
        if num_col in gdf.columns:
            gdf[num_col] = pd.to_numeric(gdf[num_col], errors="coerce")
            # Flag implausible areas (< 0 or > 500M ha — Australia total ~768M ha)
            invalid_area = gdf[num_col] < 0
            if invalid_area.sum() > 0:
                log.warning(f"  CAPAD: {invalid_area.sum()} rows with negative {num_col} set to NaN")
                gdf.loc[invalid_area, num_col] = np.nan

    # ── Classify Indigenous Protected Areas for Seeco flag
    if "type_abbr" in gdf.columns:
        gdf["is_indigenous_pa"] = gdf["type_abbr"].str.upper().str.strip() == "IPA"

    # ── Add metadata
    gdf["source_dataset"] = "CAPAD_2022"
    gdf["loaded_at"]      = datetime.utcnow()

    log.info(f"  CAPAD cleaned: {len(gdf):,} rows | Columns: {[c for c in gdf.columns if c != 'geometry']}")
    return gdf

# ═══════════════════════════════════════════════════════════════════════════════
# DATASET 2: KBA — Key Biodiversity Areas
# Source: keybiodiversityareas.org / discover.data.vic.gov.au
# Key fields: SitRecID, NatName, IntName, Country, IsoCode, SitArea,
#             TrigGroup, DesigDate, SiteDesc
# ═══════════════════════════════════════════════════════════════════════════════
def process_kba(path: str) -> gpd.GeoDataFrame:
    log.info("\n── KBA: Loading and cleaning ──")
    gdf = gpd.read_file(path)
    log.info(f"  Loaded: {len(gdf):,} rows | CRS: {gdf.crs}")
    log.info(f"  Columns: {list(gdf.columns)}")

    # ── Filter to Australia only (in case global dataset used)
    for country_col in ["Country", "COUNTRY", "country", "IsoCode", "ISO3"]:
        if country_col in gdf.columns:
            gdf = gdf[
                gdf[country_col].str.upper().str.strip().isin(["AUSTRALIA", "AUS", "AU"])
            ].copy()
            log.info(f"  KBA: Filtered to Australia via '{country_col}': {len(gdf):,} rows")
            break

    # ── Geometry cleaning
    gdf = clean_geometries(gdf, "KBA")

    # ── Reproject
    if gdf.crs != TARGET_CRS:
        gdf = gdf.to_crs(TARGET_CRS)

    # ── Standardise columns
    col_map = {
        "SitRecID":    "kba_id",
        "NatName":     "national_name",
        "IntName":     "international_name",
        "SitArea":     "site_area_km2",
        "TrigGroup":   "trigger_group",
        "DesigDate":   "designation_date",
        "SiteDesc":    "site_description",
        "IsoCode":     "iso_code",
        # VIC portal field variants
        "SITRECID":    "kba_id",
        "NATNAME":     "national_name",
        "INTNAME":     "international_name",
        "SITAREA":     "site_area_km2",
        "TRIGGROUP":   "trigger_group",
        "DESIGDATE":   "designation_date",
    }
    rename = {k: v for k, v in col_map.items() if k in gdf.columns}
    gdf = gdf.rename(columns=rename)

    keep_cols = list(dict.fromkeys(rename.values())) + ["geometry"]
    gdf = gdf[[c for c in keep_cols if c in gdf.columns]]

    # ── String cleaning
    gdf = clean_string_cols(gdf)

    # ── Date parsing
    if "designation_date" in gdf.columns:
        gdf["designation_date"] = safe_parse_date(gdf["designation_date"])

    # ── Numeric
    if "site_area_km2" in gdf.columns:
        gdf["site_area_km2"] = pd.to_numeric(gdf["site_area_km2"], errors="coerce")

    # ── Deduplicate by kba_id if present
    if "kba_id" in gdf.columns:
        dupes = gdf.duplicated(subset=["kba_id"], keep="first").sum()
        if dupes > 0:
            log.warning(f"  KBA: {dupes} duplicate kba_id values — keeping first")
            gdf = gdf.drop_duplicates(subset=["kba_id"], keep="first")

    # ── Add metadata
    gdf["source_dataset"] = "KBA_Australia"
    gdf["loaded_at"]      = datetime.utcnow()

    log.info(f"  KBA cleaned: {len(gdf):,} rows | Columns: {[c for c in gdf.columns if c != 'geometry']}")
    return gdf

# ═══════════════════════════════════════════════════════════════════════════════
# DATASET 3: IBRA v7
# Source: fed.dcceew.gov.au / data.nsw.gov.au
# Key fields: REG_CODE_7, REG_NAME_7, SUB_CODE_7, SUB_NAME_7, STA_CODE,
#             HECTARES, SQ_KM
# ═══════════════════════════════════════════════════════════════════════════════
def process_ibra(path: str) -> gpd.GeoDataFrame:
    log.info("\n── IBRA v7: Loading and cleaning ──")
    gdf = gpd.read_file(path)
    log.info(f"  Loaded: {len(gdf):,} rows | CRS: {gdf.crs}")
    log.info(f"  Columns: {list(gdf.columns)}")

    # ── Geometry cleaning
    gdf = clean_geometries(gdf, "IBRA")

    # ── Reproject
    if gdf.crs != TARGET_CRS:
        gdf = gdf.to_crs(TARGET_CRS)

    # ── Standardise columns (handle both regions and subregions files)
    col_map = {
        "REG_CODE_7":  "region_code",
        "REG_NAME_7":  "region_name",
        "SUB_CODE_7":  "subregion_code",
        "SUB_NAME_7":  "subregion_name",
        "STA_CODE":    "state_code",
        "HECTARES":    "area_ha",
        "SQ_KM":       "area_km2",
        # Alternate field names in some releases
        "REC_ID":      "record_id",
        "REG_CODE_6":  "region_code_v6",
        "REG_NAME_6":  "region_name_v6",
    }
    rename = {k: v for k, v in col_map.items() if k in gdf.columns}
    gdf = gdf.rename(columns=rename)

    keep_cols = list(dict.fromkeys(rename.values())) + ["geometry"]
    gdf = gdf[[c for c in keep_cols if c in gdf.columns]]

    # ── String cleaning
    gdf = clean_string_cols(gdf)

    # ── Numeric
    for num_col in ["area_ha", "area_km2"]:
        if num_col in gdf.columns:
            gdf[num_col] = pd.to_numeric(gdf[num_col], errors="coerce")

    # ── Derive area_km2 from area_ha if missing
    if "area_km2" not in gdf.columns and "area_ha" in gdf.columns:
        gdf["area_km2"] = gdf["area_ha"] / 100

    # ── Validate region codes are non-null (critical join key)
    if "region_code" in gdf.columns:
        null_codes = gdf["region_code"].isna().sum()
        if null_codes > 0:
            log.warning(f"  IBRA: {null_codes} rows with null region_code — flagged")
            gdf["region_code_missing"] = gdf["region_code"].isna()

    # ── Add metadata
    gdf["ibra_version"]  = "7.0"
    gdf["source_dataset"] = "IBRA_v7"
    gdf["loaded_at"]      = datetime.utcnow()

    log.info(f"  IBRA cleaned: {len(gdf):,} rows | Columns: {[c for c in gdf.columns if c != 'geometry']}")
    return gdf

# ── POSTGIS LOADER ─────────────────────────────────────────────────────────────
def push_to_postgis(
    gdf: gpd.GeoDataFrame,
    table_name: str,
    engine,
    schema: str = "biodiversity",
    if_exists: str = "replace"
):
    """
    Writes GeoDataFrame to PostGIS in chunks with spatial index.
    if_exists: 'replace' (drop+recreate) or 'append'
    """
    log.info(f"\n  [DB] Writing {len(gdf):,} rows → {schema}.{table_name}...")

    # Convert datetime columns for PG compatibility
    for col in gdf.select_dtypes(include=["datetime64[ns]"]).columns:
        gdf[col] = gdf[col].astype("object").where(gdf[col].notna(), other=None)

    # Write in chunks
    total = len(gdf)
    chunks = range(0, total, CHUNK_SIZE)

    for i, start in enumerate(chunks):
        chunk = gdf.iloc[start:start + CHUNK_SIZE]
        mode  = if_exists if i == 0 else "append"
        chunk.to_postgis(
            name      = table_name,
            con       = engine,
            schema    = schema,
            if_exists = mode,
            index     = False,
            dtype     = None
        )
        log.info(f"  [DB] Chunk {i+1}/{len(chunks)}: rows {start}–{min(start+CHUNK_SIZE, total)}")

    # Create spatial index
    with engine.connect() as conn:
        idx_name = f"idx_{table_name}_geom"
        conn.execute(text(
            f"CREATE INDEX IF NOT EXISTS {idx_name} "
            f"ON {schema}.{table_name} USING GIST (geometry);"
        ))
        conn.commit()
        log.info(f"  [DB] Spatial index created: {idx_name}")

    log.info(f"  [DB] ✅ {table_name} loaded successfully ({total:,} rows)")

# ── SETUP DB SCHEMA ────────────────────────────────────────────────────────────
def setup_schema(engine, schema: str = "biodiversity"):
    with engine.connect() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema};"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        conn.commit()
    log.info(f"  [DB] Schema '{schema}' and PostGIS extension confirmed")

# ── VALIDATION REPORT ──────────────────────────────────────────────────────────
def print_validation_report(gdf: gpd.GeoDataFrame, name: str):
    print(f"\n  {'─'*55}")
    print(f"  Validation Report: {name}")
    print(f"  {'─'*55}")
    print(f"  Rows              : {len(gdf):,}")
    print(f"  CRS               : {gdf.crs}")
    print(f"  Geometry types    : {gdf.geom_type.value_counts().to_dict()}")
    print(f"  Valid geometries  : {gdf.geometry.is_valid.sum():,} / {len(gdf):,}")
    print(f"  Null values per column:")
    for col in gdf.columns:
        if col == "geometry":
            continue
        nulls = gdf[col].isna().sum()
        if nulls > 0:
            pct = nulls / len(gdf) * 100
            print(f"    {col:<30} : {nulls:,} ({pct:.1f}%)")
    bbox = gdf.total_bounds
    print(f"  Bounding box (WGS84): "
          f"W={bbox[0]:.3f} S={bbox[1]:.3f} E={bbox[2]:.3f} N={bbox[3]:.3f}")
    print(f"  {'─'*55}")

# ── MAIN ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("="*65)
    print("  Seeco — Spatial Data Cleaning & PostGIS Loader")
    print(f"  Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*65)

    # ── Connect to DB
    try:
        engine = create_engine(DB_URL)
        setup_schema(engine)
    except Exception as e:
        log.error(f"DB connection failed: {e}")
        log.error("Update DB_URL in CONFIG and ensure PostgreSQL+PostGIS is running.")
        sys.exit(1)

    results = {}

    # ── Process CAPAD
    if os.path.exists(CAPAD_PATH):
        capad = process_capad(CAPAD_PATH)
        print_validation_report(capad, "CAPAD")
        push_to_postgis(capad, "capad", engine)
        results["CAPAD"] = len(capad)
    else:
        log.warning(f"CAPAD file not found: {CAPAD_PATH}")
        log.warning("Download from: https://digital.atlas.gov.au/datasets/capad")

    # ── Process KBA
    if os.path.exists(KBA_PATH):
        kba = process_kba(KBA_PATH)
        print_validation_report(kba, "KBA")
        push_to_postgis(kba, "kba", engine)
        results["KBA"] = len(kba)
    else:
        log.warning(f"KBA file not found: {KBA_PATH}")
        log.warning("Download from: https://www.keybiodiversityareas.org/request-gis-data")

    # ── Process IBRA
    if os.path.exists(IBRA_PATH):
        ibra = process_ibra(IBRA_PATH)
        print_validation_report(ibra, "IBRA")
        push_to_postgis(ibra, "ibra", engine)
        results["IBRA"] = len(ibra)
    else:
        log.warning(f"IBRA file not found: {IBRA_PATH}")
        log.warning("Download from: https://fed.dcceew.gov.au/datasets/fa066cfb26ff4ccdb8172a38734905cc")

    # ── Summary
    print(f"\n{'='*65}")
    print("  LOAD SUMMARY")
    print(f"  {'─'*55}")
    for ds, count in results.items():
        print(f"  ✅ {ds:<10} : {count:,} rows loaded to PostGIS")
    if not results:
        print("  ⚠️  No files processed — update file paths in CONFIG")
    print(f"  DB Schema  : biodiversity.*")
    print(f"  Tables     : capad | kba | ibra")
    print("="*65)
