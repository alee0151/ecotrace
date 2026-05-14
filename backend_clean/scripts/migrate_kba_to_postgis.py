#!/usr/bin/env python3
"""
Replace the PostGIS KBA sites table from the local KBA polygon shapefile.

Usage:
    python backend_clean/scripts/migrate_kba_to_postgis.py
    python backend_clean/scripts/migrate_kba_to_postgis.py --dry-run
    python backend_clean/scripts/migrate_kba_to_postgis.py --all-countries
    python backend_clean/scripts/migrate_kba_to_postgis.py --path datasets/KBA_Data/KBAsGlobal_2026_March_01_POL.shp

Defaults:
    Source: datasets/KBA_Data/KBAsGlobal_2026_March_01_POL.shp
    Table : kba_sites
    Scope : Australia only (ISO3=AUS / Country=Australia)

Environment:
    DB_HOST
    DB_PORT
    DB_NAME
    DB_USER
    DB_PASSWORD
    DB_SSLMODE            optional; use "disable" for local Postgres
    KBA_SHAPEFILE_PATH    optional override for the source shapefile
    KBA_COUNTRY_FILTER    optional CSV; default "AUS,AUSTRALIA,AU"
    KBA_CHUNK_SIZE        optional insert batch size; default 200

Requires PostGIS in the target database. On Azure PostgreSQL this means the
postgis extension must be allow-listed/enabled for the database user.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
from psycopg2.extras import Json, execute_values

# Avoid noisy NumPy 2.x warnings from old optional Bottleneck wheels in some
# Anaconda installs. Pandas treats Bottleneck as optional and works without it.
sys.modules.setdefault("bottleneck", None)

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


TABLE_NAME = "kba_sites"
TARGET_CRS = "EPSG:4326"
DEFAULT_SOURCE_RELATIVE_PATH = Path("datasets/KBA_Data/KBAsGlobal_2026_March_01_POL.shp")


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


def default_kba_path() -> Path:
    override = os.getenv("KBA_SHAPEFILE_PATH")
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
            kba_site_id        BIGSERIAL PRIMARY KEY,
            sitrec_id          INTEGER,
            region             TEXT,
            country            TEXT,
            iso3               CHAR(3),
            national_name      TEXT,
            international_name TEXT,
            site_lat           DOUBLE PRECISION,
            site_lon           DOUBLE PRECISION,
            site_area_km2      DOUBLE PRECISION,
            kba_status         VARCHAR(80),
            kba_class          VARCHAR(120),
            iba_status         VARCHAR(80),
            legacy_kba         VARCHAR(80),
            aze_status         VARCHAR(80),
            last_update        VARCHAR(80),
            source             TEXT,
            shape_length       DOUBLE PRECISION,
            shape_area         DOUBLE PRECISION,
            source_dataset     VARCHAR(120) NOT NULL DEFAULT 'KBAsGlobal_2026_March_01_POL',
            source_path        TEXT,
            raw_json           JSONB       NOT NULL DEFAULT '{{}}'::jsonb,
            geometry           geometry(MultiPolygon, 4326) NOT NULL,
            imported_at        TIMESTAMP   NOT NULL DEFAULT NOW(),
            updated_at         TIMESTAMP   NOT NULL DEFAULT NOW()
        );
        """
    )
    cur.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_{TABLE_NAME}_source_sitrec
        ON {TABLE_NAME}(source_dataset, sitrec_id)
        WHERE sitrec_id IS NOT NULL;
        """
    )
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_iso3 ON {TABLE_NAME}(iso3);")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_country ON {TABLE_NAME}(country);")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_kba_status ON {TABLE_NAME}(kba_status);")
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


def normalized_filter_values() -> set[str]:
    raw = os.getenv("KBA_COUNTRY_FILTER", "AUS,AUSTRALIA,AU")
    return {item.strip().upper() for item in raw.split(",") if item.strip()}


def filter_country(gdf: Any, all_countries: bool) -> Any:
    if all_countries:
        print(f"[KBA] Keeping all countries: {len(gdf):,} rows")
        return gdf

    wanted = normalized_filter_values()
    mask = None
    for column in ("ISO3", "IsoCode", "Country", "COUNTRY", "country"):
        if column not in gdf.columns:
            continue
        values = gdf[column].astype(str).str.upper().str.strip()
        column_mask = values.isin(wanted)
        mask = column_mask if mask is None else (mask | column_mask)

    if mask is None:
        raise RuntimeError("KBA country filter failed: no ISO3/Country column found")

    filtered = gdf[mask].copy()
    print(f"[KBA] Filtered to {sorted(wanted)}: {len(filtered):,}/{len(gdf):,} rows")
    if filtered.empty:
        raise RuntimeError("KBA country filter returned no rows; use --all-countries to migrate everything")
    return filtered


def load_kba_rows(path: Path, all_countries: bool = False) -> List[Tuple[Any, ...]]:
    if not path.exists():
        raise RuntimeError(f"KBA shapefile not found: {path}")

    print(f"[KBA] Reading {path}")
    gdf = gpd.read_file(path)
    if gdf.empty:
        raise RuntimeError(f"KBA shapefile has no rows: {path}")

    gdf = filter_country(gdf, all_countries)
    if gdf.crs is None:
        print(f"[KBA] Source CRS missing; assuming {TARGET_CRS}")
        gdf = gdf.set_crs(TARGET_CRS)
    if str(gdf.crs) != TARGET_CRS:
        print(f"[KBA] Reprojecting {gdf.crs} -> {TARGET_CRS}")
        gdf = gdf.to_crs(TARGET_CRS)

    imported_at = datetime.now(timezone.utc)
    source_path = str(path)
    source_dataset = path.stem
    rows: List[Tuple[Any, ...]] = []
    skipped = 0
    seen_ids: set[int] = set()

    for _, row in gdf.iterrows():
        geometry = as_multipolygon(row.geometry)
        if geometry is None:
            skipped += 1
            continue

        sitrec_id = int_or_none(first_value(row, "SitRecID", "SITRECID", "kba_id"))
        if sitrec_id is not None:
            if sitrec_id in seen_ids:
                skipped += 1
                continue
            seen_ids.add(sitrec_id)

        raw: Dict[str, Any] = {}
        for column in row.index:
            if column == "geometry":
                continue
            value = row[column]
            raw[column] = None if is_missing(value) else str(value)

        rows.append(
            (
                sitrec_id,
                clean_str(first_value(row, "Region")),
                clean_str(first_value(row, "Country", "COUNTRY", "country")),
                clean_str(first_value(row, "ISO3", "IsoCode", "iso_code")),
                clean_str(first_value(row, "NatName", "NATNAME", "national_name")),
                clean_str(first_value(row, "IntName", "INTNAME", "international_name")),
                float_or_none(first_value(row, "SitLat", "site_lat")),
                float_or_none(first_value(row, "SitLong", "site_lon")),
                float_or_none(first_value(row, "SitAreaKM2", "SitArea", "SITAREA", "site_area_km2")),
                clean_str(first_value(row, "KbaStatus", "kba_status")),
                clean_str(first_value(row, "KbaClass", "kba_class")),
                clean_str(first_value(row, "IbaStatus", "iba_status")),
                clean_str(first_value(row, "LegacyKba", "legacy_kba")),
                clean_str(first_value(row, "AzeStatus", "aze_status")),
                clean_str(first_value(row, "LastUpdate", "DesigDate", "designation_date")),
                clean_str(first_value(row, "Source", "source")),
                float_or_none(first_value(row, "Shape_Leng", "shape_length")),
                float_or_none(first_value(row, "Shape_Area", "shape_area")),
                source_dataset,
                source_path,
                Json(raw),
                psycopg2.Binary(geometry.wkb),
                imported_at,
                imported_at,
            )
        )

    print(f"[KBA] Prepared {len(rows)} rows; skipped {skipped} invalid/duplicate rows")
    if not rows:
        raise RuntimeError("No valid KBA rows prepared; refusing to clear table")
    return rows


def replace_kba_table(rows: List[Tuple[Any, ...]]) -> int:
    chunk_size = max(1, int_env("KBA_CHUNK_SIZE", 200))
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                ensure_table(cur)
                print(f"[DB] Clearing {TABLE_NAME}...")
                cur.execute(f"TRUNCATE TABLE {TABLE_NAME} RESTART IDENTITY;")

                insert_sql = f"""
                    INSERT INTO {TABLE_NAME} (
                        sitrec_id,
                        region,
                        country,
                        iso3,
                        national_name,
                        international_name,
                        site_lat,
                        site_lon,
                        site_area_km2,
                        kba_status,
                        kba_class,
                        iba_status,
                        legacy_kba,
                        aze_status,
                        last_update,
                        source,
                        shape_length,
                        shape_area,
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
    parser = argparse.ArgumentParser(description="Migrate local KBA polygons into PostGIS.")
    parser.add_argument("--dry-run", action="store_true", help="Parse and validate rows without clearing/inserting DB data.")
    parser.add_argument("--path", type=Path, help="Override KBA polygon shapefile path.")
    parser.add_argument("--all-countries", action="store_true", help="Migrate the full global KBA polygon dataset.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = get_repo_root()
    load_dotenv(repo_root / "backend_clean" / ".env")
    load_dotenv(repo_root / "backend_clean" / "env.example")

    path = args.path.expanduser().resolve() if args.path else default_kba_path()
    rows = load_kba_rows(path, all_countries=args.all_countries)
    if args.dry_run:
        print(f"[DRY RUN] Parsed {len(rows)} KBA rows; database was not changed")
        return 0

    inserted = replace_kba_table(rows)
    print(f"[DB] Migration complete: replaced {TABLE_NAME} with {inserted} KBA sites")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        raise SystemExit(1)
