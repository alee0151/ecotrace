#!/usr/bin/env python3
"""
Replace the PostGIS CAPAD protected areas table from the local CAPAD shapefile.

Usage:
    python backend_clean/scripts/migrate_capad_to_postgis.py
    python backend_clean/scripts/migrate_capad_to_postgis.py --dry-run
    python backend_clean/scripts/migrate_capad_to_postgis.py --path datasets/CAPAD/Collaborative_Australian_Protected_Areas_Database_(CAPAD)_2024_-_Terrestrial__.shp

Defaults:
    Source: datasets/CAPAD/Collaborative_Australian_Protected_Areas_Database_(CAPAD)_2024_-_Terrestrial__.shp
    Table : capad_protected_areas

Environment:
    DB_HOST
    DB_PORT
    DB_NAME
    DB_USER
    DB_PASSWORD
    DB_SSLMODE             optional; use "disable" for local Postgres
    CAPAD_SHAPEFILE_PATH   optional override for the source shapefile
    CAPAD_CHUNK_SIZE       optional insert batch size; default 250

Requires PostGIS in the target database. On Azure PostgreSQL this means the
postgis extension must be allow-listed/enabled for the database user.
"""

from __future__ import annotations

import argparse
import os
import sys
import warnings
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
from psycopg2.extras import Json, execute_values

# Avoid noisy NumPy 2.x warnings from old optional Bottleneck wheels in some
# Anaconda installs. Pandas treats Bottleneck as optional and works without it.
sys.modules.setdefault("bottleneck", None)
warnings.filterwarnings("ignore", message="organizePolygons.*", category=RuntimeWarning)
warnings.filterwarnings("ignore", message="Geometry of polygon.*", category=RuntimeWarning)

try:
    import geopandas as gpd
    from shapely.geometry import GeometryCollection, MultiPolygon, Polygon
    from shapely.validation import make_valid
except ImportError as error:  # pragma: no cover - user-facing dependency guard
    raise SystemExit(
        "Missing spatial Python dependencies. Install them with:\n"
        "  pip install geopandas shapely pyogrio pyproj\n"
        f"Original import error: {error}"
    )


TABLE_NAME = "capad_protected_areas"
TARGET_CRS = "EPSG:4326"
DEFAULT_SOURCE_RELATIVE_PATH = Path(
    "datasets/CAPAD/Collaborative_Australian_Protected_Areas_Database_(CAPAD)_2024_-_Terrestrial__.shp"
)


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def env(name: str, default: Optional[str] = None) -> str:
    value = os.getenv(name, default)
    if value is None or value == "":
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def get_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_capad_path() -> Path:
    override = os.getenv("CAPAD_SHAPEFILE_PATH")
    if override:
        return Path(override).expanduser().resolve()
    return (get_repo_root() / DEFAULT_SOURCE_RELATIVE_PATH).resolve()


def get_conn():
    return psycopg2.connect(
        host=env("DB_HOST", "localhost"),
        port=env("DB_PORT", "5432"),
        dbname=env("DB_NAME", "seeco"),
        user=env("DB_USER", "postgres"),
        password=env("DB_PASSWORD"),
        sslmode=env("DB_SSLMODE", "require"),
    )


def ensure_table(cur) -> None:
    cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            capad_area_id     BIGSERIAL PRIMARY KEY,
            object_id         INTEGER,
            pa_id             VARCHAR(80),
            pa_pid            VARCHAR(80),
            name              TEXT,
            pa_type           TEXT,
            type_abbr         VARCHAR(40),
            iucn_category     VARCHAR(20),
            nrs_pa            VARCHAR(20),
            nrs_mpa           VARCHAR(20),
            gaz_area_ha       DOUBLE PRECISION,
            gis_area_ha       DOUBLE PRECISION,
            gaz_date          DATE,
            latest_gaz_date   DATE,
            state_code        VARCHAR(20),
            authority         TEXT,
            datasource        TEXT,
            governance        TEXT,
            comments          TEXT,
            environment       VARCHAR(40),
            overlap           VARCHAR(40),
            mgt_plan_status   VARCHAR(80),
            res_number        TEXT,
            zone_type         TEXT,
            epbc              VARCHAR(80),
            longitude         DOUBLE PRECISION,
            latitude          DOUBLE PRECISION,
            pa_system         VARCHAR(80),
            shape_area        DOUBLE PRECISION,
            shape_length      DOUBLE PRECISION,
            is_indigenous_pa  BOOLEAN     NOT NULL DEFAULT FALSE,
            source_dataset    VARCHAR(120) NOT NULL DEFAULT 'CAPAD_2024_Terrestrial',
            source_path       TEXT,
            raw_json          JSONB       NOT NULL DEFAULT '{{}}'::jsonb,
            geometry          geometry(MultiPolygon, 4326) NOT NULL,
            imported_at       TIMESTAMP   NOT NULL DEFAULT NOW(),
            updated_at        TIMESTAMP   NOT NULL DEFAULT NOW()
        );
        """
    )
    cur.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_{TABLE_NAME}_source_object
        ON {TABLE_NAME}(source_dataset, object_id)
        WHERE object_id IS NOT NULL;
        """
    )
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_pa_id ON {TABLE_NAME}(pa_id);")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_state_code ON {TABLE_NAME}(state_code);")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_iucn ON {TABLE_NAME}(iucn_category);")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_type_abbr ON {TABLE_NAME}(type_abbr);")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_geometry ON {TABLE_NAME} USING GIST (geometry);")


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        if value != value:
            return True
    except Exception:
        pass
    return str(value).strip() == ""


def first_value(row: Any, *columns: str) -> Any:
    for column in columns:
        if column in row.index:
            value = row[column]
            if not is_missing(value):
                return value
    return None


def clean_str(value: Any) -> Optional[str]:
    if is_missing(value):
        return None
    text = str(value).strip()
    return text or None


def int_or_none(value: Any) -> Optional[int]:
    try:
        if is_missing(value):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def float_or_none(value: Any) -> Optional[float]:
    try:
        if is_missing(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def date_or_none(value: Any) -> Optional[date]:
    if is_missing(value):
        return None
    text = str(value).strip()
    if "T" in text:
        text = text.split("T", 1)[0]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def as_multipolygon(geometry: Any) -> Optional[MultiPolygon]:
    if geometry is None or geometry.is_empty:
        return None

    fixed = make_valid(geometry)
    if fixed.is_empty:
        return None
    if isinstance(fixed, Polygon):
        return MultiPolygon([fixed])
    if isinstance(fixed, MultiPolygon):
        return fixed
    if isinstance(fixed, GeometryCollection):
        polygons: List[Polygon] = []
        for part in fixed.geoms:
            if isinstance(part, Polygon):
                polygons.append(part)
            elif isinstance(part, MultiPolygon):
                polygons.extend(list(part.geoms))
        return MultiPolygon(polygons) if polygons else None
    return None


def load_capad_rows(path: Path) -> List[Tuple[Any, ...]]:
    if not path.exists():
        raise RuntimeError(f"CAPAD shapefile not found: {path}")

    print(f"[CAPAD] Reading {path}")
    gdf = gpd.read_file(path)
    if gdf.empty:
        raise RuntimeError(f"CAPAD shapefile has no rows: {path}")

    if gdf.crs is None:
        print(f"[CAPAD] Source CRS missing; assuming EPSG:4283")
        gdf = gdf.set_crs("EPSG:4283")
    if str(gdf.crs) != TARGET_CRS:
        print(f"[CAPAD] Reprojecting {gdf.crs} -> {TARGET_CRS}")
        gdf = gdf.to_crs(TARGET_CRS)

    imported_at = datetime.now(timezone.utc)
    source_path = str(path)
    source_dataset = "CAPAD_2024_Terrestrial"
    rows: List[Tuple[Any, ...]] = []
    skipped = 0
    seen_objects: set[int] = set()

    for _, row in gdf.iterrows():
        geometry = as_multipolygon(row.geometry)
        if geometry is None:
            skipped += 1
            continue

        object_id = int_or_none(first_value(row, "OBJECTID", "object_id"))
        if object_id is not None:
            if object_id in seen_objects:
                skipped += 1
                continue
            seen_objects.add(object_id)

        type_abbr = clean_str(first_value(row, "TYPE_ABBR", "type_abbr"))
        raw: Dict[str, Any] = {}
        for column in row.index:
            if column == "geometry":
                continue
            value = row[column]
            raw[column] = None if is_missing(value) else str(value)

        rows.append(
            (
                object_id,
                clean_str(first_value(row, "PA_ID", "pa_id")),
                clean_str(first_value(row, "PA_PID", "pa_pid")),
                clean_str(first_value(row, "NAME", "name")),
                clean_str(first_value(row, "TYPE", "pa_type")),
                type_abbr,
                clean_str(first_value(row, "IUCN", "iucn_category")),
                clean_str(first_value(row, "NRS_PA", "nrs_pa")),
                clean_str(first_value(row, "NRS_MPA", "nrs_mpa")),
                float_or_none(first_value(row, "GAZ_AREA", "gaz_area_ha")),
                float_or_none(first_value(row, "GIS_AREA", "gis_area_ha")),
                date_or_none(first_value(row, "GAZ_DATE", "gaz_date")),
                date_or_none(first_value(row, "LATEST_GAZ", "latest_gaz_date")),
                clean_str(first_value(row, "STATE", "state_code")),
                clean_str(first_value(row, "AUTHORITY", "authority")),
                clean_str(first_value(row, "DATASOURCE", "datasource")),
                clean_str(first_value(row, "GOVERNANCE", "governance")),
                clean_str(first_value(row, "COMMENTS", "comments")),
                clean_str(first_value(row, "ENVIRON", "environment")),
                clean_str(first_value(row, "OVERLAP", "overlap")),
                clean_str(first_value(row, "MGT_PLAN", "mgt_plan_status")),
                clean_str(first_value(row, "RES_NUMBER", "res_number")),
                clean_str(first_value(row, "ZONE_TYPE", "zone_type")),
                clean_str(first_value(row, "EPBC", "epbc")),
                float_or_none(first_value(row, "LONGITUDE", "longitude")),
                float_or_none(first_value(row, "LATITUDE", "latitude")),
                clean_str(first_value(row, "PA_SYSTEM", "pa_system")),
                float_or_none(first_value(row, "Shape__Are", "SHAPE_AREA", "shape_area")),
                float_or_none(first_value(row, "Shape__Len", "SHAPE_LEN", "shape_length")),
                bool(type_abbr and type_abbr.upper() == "IPA"),
                source_dataset,
                source_path,
                Json(raw),
                psycopg2.Binary(geometry.wkb),
                imported_at,
                imported_at,
            )
        )

    print(f"[CAPAD] Prepared {len(rows)} rows; skipped {skipped} invalid/duplicate rows")
    if not rows:
        raise RuntimeError("No valid CAPAD rows prepared; refusing to clear table")
    return rows


def replace_capad_table(rows: List[Tuple[Any, ...]]) -> int:
    chunk_size = max(1, int_env("CAPAD_CHUNK_SIZE", 250))
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                ensure_table(cur)
                print(f"[DB] Clearing {TABLE_NAME}...")
                cur.execute(f"TRUNCATE TABLE {TABLE_NAME} RESTART IDENTITY;")

                insert_sql = f"""
                    INSERT INTO {TABLE_NAME} (
                        object_id,
                        pa_id,
                        pa_pid,
                        name,
                        pa_type,
                        type_abbr,
                        iucn_category,
                        nrs_pa,
                        nrs_mpa,
                        gaz_area_ha,
                        gis_area_ha,
                        gaz_date,
                        latest_gaz_date,
                        state_code,
                        authority,
                        datasource,
                        governance,
                        comments,
                        environment,
                        overlap,
                        mgt_plan_status,
                        res_number,
                        zone_type,
                        epbc,
                        longitude,
                        latitude,
                        pa_system,
                        shape_area,
                        shape_length,
                        is_indigenous_pa,
                        source_dataset,
                        source_path,
                        raw_json,
                        geometry,
                        imported_at,
                        updated_at
                    )
                    VALUES %s;
                """
                template = (
                    "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                    "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                    "%s, %s, %s, %s, %s, %s, %s, %s, %s, "
                    "ST_Multi(ST_SetSRID(ST_GeomFromWKB(%s), 4326)), %s, %s)"
                )

                inserted = 0
                for start in range(0, len(rows), chunk_size):
                    chunk = rows[start:start + chunk_size]
                    execute_values(cur, insert_sql, chunk, template=template, page_size=chunk_size)
                    inserted += len(chunk)
                    print(f"[DB] Inserted {inserted}/{len(rows)} rows")
        return len(rows)
    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate local CAPAD terrestrial polygons into PostGIS.")
    parser.add_argument("--dry-run", action="store_true", help="Parse and validate rows without clearing/inserting DB data.")
    parser.add_argument("--path", type=Path, help="Override CAPAD shapefile path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = get_repo_root()
    load_dotenv(repo_root / "backend_clean" / ".env")
    load_dotenv(repo_root / "backend_clean" / "env.example")

    path = args.path.expanduser().resolve() if args.path else default_capad_path()
    rows = load_capad_rows(path)
    if args.dry_run:
        print(f"[DRY RUN] Parsed {len(rows)} CAPAD rows; database was not changed")
        return 0

    inserted = replace_capad_table(rows)
    print(f"[DB] Migration complete: replaced {TABLE_NAME} with {inserted} CAPAD protected areas")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        raise SystemExit(1)
