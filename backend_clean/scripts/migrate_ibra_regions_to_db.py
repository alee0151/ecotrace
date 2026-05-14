#!/usr/bin/env python3
"""
Replace the Postgres IBRA regions table from the local IBRA shapefile.

Usage:
    python backend_clean/scripts/migrate_ibra_regions_to_db.py
    python backend_clean/scripts/migrate_ibra_regions_to_db.py --dry-run
    python backend_clean/scripts/migrate_ibra_regions_to_db.py --path datasets/IBRARegion_Aust70/IBRARegion_Aust70.shp

Defaults:
    Source: datasets/IBRARegion_Aust70/IBRARegion_Aust70.shp
    Table : ibra_regions

Environment:
    DB_HOST
    DB_PORT
    DB_NAME
    DB_USER
    DB_PASSWORD
    DB_SSLMODE            optional; use "disable" for local Postgres
    IBRA_SHAPEFILE_PATH   optional override for the source shapefile
    IBRA_SOURCE_CRS       optional fallback when source CRS is missing; default EPSG:3107
    IBRA_CHUNK_SIZE       optional insert batch size; default 200
"""

from __future__ import annotations

import os
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
from psycopg2.extras import Json, execute_values

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


TABLE_NAME = "ibra_regions"
TARGET_CRS = "EPSG:4326"
DEFAULT_SOURCE_RELATIVE_PATH = Path("datasets/IBRARegion_Aust70/IBRARegion_Aust70.shp")


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


def default_ibra_path() -> Path:
    override = os.getenv("IBRA_SHAPEFILE_PATH")
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
            ibra_region_id  BIGSERIAL PRIMARY KEY,
            object_id       INTEGER,
            region_code     VARCHAR(20) NOT NULL,
            region_name     TEXT        NOT NULL,
            region_number   INTEGER,
            state_code      VARCHAR(10),
            shape_area      DOUBLE PRECISION,
            shape_length    DOUBLE PRECISION,
            area_km2        DOUBLE PRECISION,
            source_dataset  VARCHAR(120) NOT NULL DEFAULT 'IBRARegion_Aust70',
            source_path     TEXT,
            raw_json        JSONB       NOT NULL DEFAULT '{{}}'::jsonb,
            geometry        geometry(MultiPolygon, 4326) NOT NULL,
            imported_at     TIMESTAMP   NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMP   NOT NULL DEFAULT NOW()
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
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_region_code ON {TABLE_NAME}(region_code);")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_state_code ON {TABLE_NAME}(state_code);")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_geometry ON {TABLE_NAME} USING GIST (geometry);")


def first_value(row: Any, *columns: str) -> Any:
    for column in columns:
        if column in row.index:
            value = row[column]
            if not is_missing(value):
                return value
    return None


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        if value != value:
            return True
    except Exception:
        pass
    return str(value).strip() == ""


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


def load_ibra_rows(path: Path) -> List[Tuple[Any, ...]]:
    if not path.exists():
        raise RuntimeError(f"IBRA shapefile not found: {path}")

    print(f"[IBRA] Reading {path}")
    gdf = gpd.read_file(path)
    if gdf.empty:
        raise RuntimeError(f"IBRA shapefile has no rows: {path}")

    if gdf.crs is None:
        fallback_crs = os.getenv("IBRA_SOURCE_CRS", "EPSG:3107")
        print(f"[IBRA] Source CRS missing; assuming {fallback_crs}")
        gdf = gdf.set_crs(fallback_crs)
    if str(gdf.crs) != TARGET_CRS:
        print(f"[IBRA] Reprojecting {gdf.crs} -> {TARGET_CRS}")
        gdf = gdf.to_crs(TARGET_CRS)

    imported_at = datetime.now(timezone.utc)
    source_path = str(path)
    source_dataset = path.parent.name or "IBRARegion_Aust70"
    rows: List[Tuple[Any, ...]] = []
    skipped = 0

    for _, row in gdf.iterrows():
        geometry = as_multipolygon(row.geometry)
        if geometry is None:
            skipped += 1
            continue

        region_code = clean_str(first_value(row, "IBRA_REG_C", "REG_CODE_7", "region_code"))
        region_name = clean_str(first_value(row, "IBRA_REG_N", "REG_NAME_7", "region_name"))
        if not region_code or not region_name:
            skipped += 1
            continue

        object_id = int_or_none(first_value(row, "OBJECTID", "REC_ID", "object_id"))
        shape_area = float_or_none(first_value(row, "SHAPE_AREA", "shape_area"))
        shape_length = float_or_none(first_value(row, "SHAPE_LEN", "shape_length"))
        raw: Dict[str, Any] = {}
        for column in row.index:
            if column == "geometry":
                continue
            value = row[column]
            raw[column] = None if is_missing(value) else str(value)

        rows.append(
            (
                object_id,
                region_code,
                region_name,
                int_or_none(first_value(row, "IBRA_REG_1", "region_number")),
                clean_str(first_value(row, "STATE", "STA_CODE", "state_code")),
                shape_area,
                shape_length,
                (shape_area / 1_000_000) if shape_area is not None else float_or_none(first_value(row, "SQ_KM", "area_km2")),
                source_dataset,
                source_path,
                Json(raw),
                psycopg2.Binary(geometry.wkb),
                imported_at,
                imported_at,
            )
        )

    print(f"[IBRA] Prepared {len(rows)} rows; skipped {skipped} invalid/incomplete rows")
    if not rows:
        raise RuntimeError("No valid IBRA rows prepared; refusing to clear table")
    return rows


def replace_ibra_table(rows: List[Tuple[Any, ...]]) -> int:
    chunk_size = max(1, int_env("IBRA_CHUNK_SIZE", 200))
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
                        region_code,
                        region_name,
                        region_number,
                        state_code,
                        shape_area,
                        shape_length,
                        area_km2,
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
                    "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
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
    parser = argparse.ArgumentParser(description="Migrate local IBRA v7 regions into PostGIS.")
    parser.add_argument("--dry-run", action="store_true", help="Parse and validate rows without clearing/inserting DB data.")
    parser.add_argument("--path", type=Path, help="Override IBRA shapefile path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = get_repo_root()
    load_dotenv(repo_root / "backend_clean" / ".env")
    load_dotenv(repo_root / "backend_clean" / "env.example")

    path = args.path.expanduser().resolve() if args.path else default_ibra_path()
    rows = load_ibra_rows(path)
    if args.dry_run:
        print(f"[DRY RUN] Parsed {len(rows)} IBRA rows; database was not changed")
        return 0

    inserted = replace_ibra_table(rows)
    print(f"[DB] Migration complete: replaced {TABLE_NAME} with {inserted} IBRA regions")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        raise SystemExit(1)
