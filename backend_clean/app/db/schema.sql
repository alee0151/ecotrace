-- Enable UUID generation and spatial geometry support
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS postgis;


-- ============================================================
-- Seeco Database Schema
-- Epic 1
-- Entities: USER, SEARCH_QUERY, COMPANY, ABN_RECORD,
--           BRAND, TRADEMARK, PRODUCT, GRAPH_NODE
-- ============================================================

-- ------------------------------------------------------------
-- ENUMS
-- ------------------------------------------------------------
CREATE TYPE user_type_enum       AS ENUM ('consumer', 'investor', 'esg_platform');
CREATE TYPE input_type_enum      AS ENUM ('company_name', 'brand_name', 'barcode');
CREATE TYPE resolution_status_enum AS ENUM ('pending', 'resolved', 'failed');
CREATE TYPE entity_type_enum     AS ENUM ('PTY LTD', 'LTD', 'TRUST', 'PARTNERSHIP', 'SOLE TRADER', 'OTHER');
CREATE TYPE company_status_enum  AS ENUM ('registered', 'deregistered', 'suspended');
CREATE TYPE trademark_status_enum AS ENUM ('registered', 'pending', 'lapsed', 'removed');
CREATE TYPE data_source_enum     AS ENUM ('open_food_facts', 'gs1');
CREATE TYPE node_type_enum       AS ENUM ('company', 'facility', 'location', 'species');
CREATE TYPE sentiment_enum          AS ENUM ('positive', 'neutral', 'negative');

-- ------------------------------------------------------------
-- 1. USER
-- ------------------------------------------------------------
CREATE TABLE "user" (
    user_id     UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_type   user_type_enum  NOT NULL,
    email       VARCHAR(255)    NOT NULL UNIQUE,
    created_at  TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE TABLE email_verification (
    verification_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES "user"(user_id) ON DELETE CASCADE,
    email           VARCHAR(255) NOT NULL,
    token_hash      CHAR(64) NOT NULL UNIQUE,
    return_to       TEXT NOT NULL DEFAULT '/app/search',
    requested_at    TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMP NOT NULL,
    verified_at     TIMESTAMP,
    delivery_method VARCHAR(50)
);

CREATE INDEX idx_email_verification_email
    ON email_verification(email, requested_at DESC);

-- ------------------------------------------------------------
-- 2. ABN_RECORD  (no FK deps — must exist before COMPANY)
-- ------------------------------------------------------------
CREATE TABLE abn_record (
    abn             CHAR(11)            PRIMARY KEY,
    legal_name      VARCHAR(255)        NOT NULL,
    entity_type     entity_type_enum    NOT NULL,
    gst_registered  BOOLEAN             NOT NULL DEFAULT FALSE,
    state           CHAR(3),
    postcode        CHAR(4),
    last_updated    TIMESTAMP           NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- 3. COMPANY
-- ------------------------------------------------------------
CREATE TABLE company (
    company_id      UUID                PRIMARY KEY DEFAULT gen_random_uuid(),
    abn             CHAR(11)            NOT NULL UNIQUE REFERENCES abn_record(abn),
    acn             CHAR(9)             UNIQUE,
    legal_name      VARCHAR(255)        NOT NULL,
    entity_type     entity_type_enum    NOT NULL,
    company_status  company_status_enum NOT NULL DEFAULT 'registered',
    anzsic_code     VARCHAR(10)
);

CREATE INDEX idx_company_abn         ON company(abn);
CREATE INDEX idx_company_legal_name  ON company(legal_name);

-- ------------------------------------------------------------
-- 4. TRADEMARK
-- ------------------------------------------------------------
CREATE TABLE trademark (
    trademark_id        UUID                    PRIMARY KEY DEFAULT gen_random_uuid(),
    trademark_number    VARCHAR(50)             NOT NULL UNIQUE,
    trademark_name      VARCHAR(255)            NOT NULL,
    owner_legal_name    VARCHAR(255)            NOT NULL,
    class_code          VARCHAR(10),            -- Nice Classification code
    status              trademark_status_enum   NOT NULL DEFAULT 'registered',
    registration_date   DATE
);

-- ------------------------------------------------------------
-- 5. BRAND
-- ------------------------------------------------------------
CREATE TABLE brand (
    brand_id        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_name      VARCHAR(255) NOT NULL,
    company_id      UUID        NOT NULL REFERENCES company(company_id) ON DELETE CASCADE,
    trademark_id    UUID        REFERENCES trademark(trademark_id) ON DELETE SET NULL
);

CREATE INDEX idx_brand_company_id    ON brand(company_id);
CREATE INDEX idx_brand_trademark_id  ON brand(trademark_id);

-- ------------------------------------------------------------
-- 6. PRODUCT
-- ------------------------------------------------------------
CREATE TABLE product (
    product_id          UUID                PRIMARY KEY DEFAULT gen_random_uuid(),
    barcode             VARCHAR(20)         NOT NULL UNIQUE,   -- EAN-13 / GTIN
    product_name        VARCHAR(255)        NOT NULL,
    brand_id            UUID                NOT NULL REFERENCES brand(brand_id) ON DELETE RESTRICT,
    manufacturer_name   VARCHAR(255),
    data_source         data_source_enum    NOT NULL
);

CREATE INDEX idx_product_brand_id ON product(brand_id);
CREATE INDEX idx_product_barcode  ON product(barcode);

-- ------------------------------------------------------------
-- 7. SEARCH_QUERY
-- ------------------------------------------------------------
CREATE TABLE search_query (
    query_id            UUID                    PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID                    REFERENCES "user"(user_id) ON DELETE CASCADE,
    input_type          input_type_enum         NOT NULL,
    input_value         VARCHAR(500)            NOT NULL,
    resolution_status   resolution_status_enum  NOT NULL DEFAULT 'pending',
    -- Optional FKs — populated after resolution
    resolved_company_id UUID                    REFERENCES company(company_id) ON DELETE SET NULL,
    resolved_brand_id   UUID                    REFERENCES brand(brand_id)     ON DELETE SET NULL,
    resolved_product_id UUID                    REFERENCES product(product_id) ON DELETE SET NULL,
    submitted_at        TIMESTAMP               NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_search_query_user_id  ON search_query(user_id);
CREATE INDEX idx_search_query_input    ON search_query(input_type, input_value);

-- ------------------------------------------------------------
-- 8. GRAPH_NODE
-- ------------------------------------------------------------
CREATE TABLE graph_node (
    node_id     UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  UUID            NOT NULL REFERENCES company(company_id) ON DELETE CASCADE,
    node_type   node_type_enum  NOT NULL,
    label       VARCHAR(255)    NOT NULL,
    latitude    DOUBLE PRECISION,
    longitude   DOUBLE PRECISION,
    valid_from  TIMESTAMP       NOT NULL DEFAULT NOW(),
    valid_to    TIMESTAMP       -- NULL means currently active
);

CREATE INDEX idx_graph_node_company_id ON graph_node(company_id);
CREATE INDEX idx_graph_node_valid      ON graph_node(valid_from, valid_to);
-- Optional: PostGIS spatial index if using geography type
-- CREATE INDEX idx_graph_node_geom ON graph_node USING GIST(ST_MakePoint(longitude, latitude));



-- 9. NEWS_ARTICLE
-- ------------------------------------------------------------
CREATE TABLE news_article (
    article_id      UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      UUID            NOT NULL REFERENCES company(company_id) ON DELETE CASCADE,
    headline        VARCHAR(500)    NOT NULL,
    source_url      VARCHAR(1000)   NOT NULL UNIQUE,
    publisher       VARCHAR(255),
    sentiment       sentiment_enum  NOT NULL DEFAULT 'neutral',
    published_at    TIMESTAMP,
    ingested_at     TIMESTAMP       NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_news_company_id   ON news_article(company_id);
CREATE INDEX idx_news_published_at ON news_article(published_at);
CREATE INDEX idx_news_sentiment    ON news_article(sentiment);
-- ------------------------------------------------------------
-- 10. RISK_EVENT
-- ------------------------------------------------------------
CREATE TABLE risk_event (
    event_id            UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id             UUID            NOT NULL REFERENCES graph_node(node_id) ON DELETE CASCADE,
    source_type         VARCHAR(20)     NOT NULL DEFAULT 'news'
                                        CHECK (source_type = 'news'),
    source_id           UUID            NOT NULL REFERENCES news_article(article_id) ON DELETE CASCADE,
    risk_type           VARCHAR(100)    NOT NULL,
    description         TEXT,
    confidence_score    FLOAT           CHECK (confidence_score BETWEEN 0 AND 1),
    llm_model_version   VARCHAR(50),
    prov_agent          VARCHAR(255),
    extracted_at        TIMESTAMP       NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_risk_event_node_id   ON risk_event(node_id);
CREATE INDEX idx_risk_event_source_id ON risk_event(source_id);


-- ------------------------------------------------------------
-- 11. INFERRED_LOCATION
-- Holds locations inferred from ABN records, news articles,
-- or attached reports (e.g. sustainability/annual reports).
-- ------------------------------------------------------------

CREATE TYPE location_source_enum AS ENUM ('abn', 'news', 'report');
CREATE TYPE location_confidence_enum AS ENUM ('high', 'medium', 'low');

CREATE TABLE inferred_location (
    location_id         UUID                        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Owning company (always required)
    company_id          UUID                        NOT NULL REFERENCES company(company_id) ON DELETE CASCADE,

    -- Source discriminator
    source_type         location_source_enum        NOT NULL,

    -- Optional FK to the originating source record
    -- Only one of these will be populated depending on source_type
    abn_ref             CHAR(11)                    REFERENCES abn_record(abn) ON DELETE SET NULL,
    article_id          UUID                        REFERENCES news_article(article_id) ON DELETE SET NULL,
    report_id           UUID,                       -- FK placeholder for a future REPORT table

    -- Location detail
    label               VARCHAR(255),               -- Human-readable e.g. "Port of Melbourne"
    address_raw         TEXT,                       -- Raw extracted address string
    suburb              VARCHAR(100),
    state               CHAR(3),
    postcode            CHAR(4),
    country             CHAR(2)     NOT NULL DEFAULT 'AU',  -- ISO 3166-1 alpha-2
    latitude            DOUBLE PRECISION,
    longitude           DOUBLE PRECISION,

    -- Provenance & confidence
    confidence          location_confidence_enum    NOT NULL DEFAULT 'medium',
    llm_model_version   VARCHAR(50),                -- Set if extracted via LLM
    prov_agent          VARCHAR(255),               -- Service/agent that inferred the location
    extracted_at        TIMESTAMP                   NOT NULL DEFAULT NOW(),

    -- Temporal validity
    valid_from          TIMESTAMP                   NOT NULL DEFAULT NOW(),
    valid_to            TIMESTAMP,                  -- NULL = currently active

    -- Prevent duplicate inferences from the same source
    CONSTRAINT uq_inferred_location_source
        UNIQUE NULLS NOT DISTINCT (company_id, source_type, abn_ref, article_id, latitude, longitude)
);

-- Indexes
CREATE INDEX idx_inferred_loc_company_id    ON inferred_location(company_id);
CREATE INDEX idx_inferred_loc_source_type   ON inferred_location(source_type);
CREATE INDEX idx_inferred_loc_state_postcode ON inferred_location(state, postcode);
CREATE INDEX idx_inferred_loc_valid         ON inferred_location(valid_from, valid_to);
-- Optional PostGIS spatial index:
-- CREATE INDEX idx_inferred_loc_geom ON inferred_location USING GIST(ST_MakePoint(longitude, latitude));


-- ------------------------------------------------------------
-- 12. REPORT
-- Persisted printable reports generated from search_query.
-- ------------------------------------------------------------
CREATE TABLE report (
    report_id        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    query_id         UUID        NOT NULL REFERENCES search_query(query_id) ON DELETE CASCADE,
    recipient_email  VARCHAR(255),
    title            VARCHAR(500) NOT NULL,
    format           VARCHAR(20)  NOT NULL DEFAULT 'html',
    status           VARCHAR(30)  NOT NULL DEFAULT 'generated',
    html_content     TEXT         NOT NULL,
    metadata_json    JSONB        NOT NULL DEFAULT '{}'::jsonb,
    generated_at     TIMESTAMP    NOT NULL DEFAULT NOW(),
    sent_at          TIMESTAMP,
    delivery_method  VARCHAR(30)
);

CREATE INDEX idx_report_query_id     ON report(query_id);
CREATE INDEX idx_report_generated_at ON report(generated_at);
CREATE INDEX idx_report_status       ON report(status);


-- ------------------------------------------------------------
-- 13. COMPANY_WATCHLIST
-- User-scoped company monitoring list for Epic 5.
-- Each user can watch a company once; the company may be linked to
-- an internal company row when available, or stored from an analysis
-- payload before persistence succeeds.
-- ------------------------------------------------------------
CREATE TABLE company_watchlist (
    watchlist_id        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID        NOT NULL REFERENCES "user"(user_id) ON DELETE CASCADE,
    company_id          UUID        REFERENCES company(company_id) ON DELETE SET NULL,
    query_id            UUID        REFERENCES search_query(query_id) ON DELETE SET NULL,
    company_name        VARCHAR(255) NOT NULL,
    abn                 CHAR(11),
    industry            VARCHAR(255),
    region              VARCHAR(255),
    risk_score          INTEGER,
    risk_level          VARCHAR(30),
    alerts_enabled      BOOLEAN     NOT NULL DEFAULT TRUE,
    notes               TEXT,
    metadata_json       JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMP   NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP   NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_company_watchlist_user_company
        UNIQUE NULLS NOT DISTINCT (user_id, company_id, abn, company_name)
);

CREATE INDEX idx_company_watchlist_user_id ON company_watchlist(user_id, created_at DESC);
CREATE INDEX idx_company_watchlist_company_id ON company_watchlist(company_id);


-- ------------------------------------------------------------
-- 14. NEWS_ANALYSIS_CACHE
-- Database-backed cache for expensive company news analysis.
-- Reuses previously collected article candidates and extracted evidence
-- for the same normalized company/search settings until the TTL expires.
-- ------------------------------------------------------------
CREATE TABLE news_analysis_cache (
    cache_key           CHAR(64)    PRIMARY KEY,
    company_id          UUID        REFERENCES company(company_id) ON DELETE SET NULL,
    normalized_name     VARCHAR(255) NOT NULL,
    params_json         JSONB       NOT NULL DEFAULT '{}'::jsonb,
    candidates_json     JSONB       NOT NULL DEFAULT '[]'::jsonb,
    evidence_json       JSONB       NOT NULL DEFAULT '[]'::jsonb,
    model_fingerprint   JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMP   NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP   NOT NULL DEFAULT NOW(),
    expires_at          TIMESTAMP   NOT NULL
);

CREATE INDEX idx_news_analysis_cache_company_id ON news_analysis_cache(company_id);
CREATE INDEX idx_news_analysis_cache_expires_at ON news_analysis_cache(expires_at);


-- ------------------------------------------------------------
-- 15. IUCN_REDLIST_CACHE
-- Database-backed cache for IUCN Red List Australia species data.
-- This replaces the process-local/disk JSON cache as the durable source
-- for Layer A species threat enrichment.
-- ------------------------------------------------------------
CREATE TABLE iucn_redlist_cache (
    scientific_name    TEXT        PRIMARY KEY,
    category_code      VARCHAR(10),
    category_name      VARCHAR(80),
    iucn_url           TEXT,
    source             VARCHAR(120) NOT NULL DEFAULT 'IUCN Red List v4 countries/AU',
    raw_json           JSONB       NOT NULL DEFAULT '{}'::jsonb,
    imported_at        TIMESTAMP   NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_iucn_redlist_cache_category
    ON iucn_redlist_cache(category_code);

CREATE INDEX idx_iucn_redlist_cache_imported_at
    ON iucn_redlist_cache(imported_at DESC);


-- ------------------------------------------------------------
-- 16. IBRA_REGIONS
-- Interim Biogeographic Regionalisation for Australia v7 regions.
-- Loaded from datasets/IBRARegion_Aust70 and stored as WGS84 PostGIS
-- multipolygons for spatial intersection/containment queries.
-- ------------------------------------------------------------
CREATE TABLE ibra_regions (
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
    raw_json        JSONB       NOT NULL DEFAULT '{}'::jsonb,
    geometry        geometry(MultiPolygon, 4326) NOT NULL,
    imported_at     TIMESTAMP   NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_ibra_regions_source_object
    ON ibra_regions(source_dataset, object_id)
    WHERE object_id IS NOT NULL;

CREATE INDEX idx_ibra_regions_region_code
    ON ibra_regions(region_code);

CREATE INDEX idx_ibra_regions_state_code
    ON ibra_regions(state_code);

CREATE INDEX idx_ibra_regions_geometry
    ON ibra_regions USING GIST (geometry);


-- ------------------------------------------------------------
-- 17. KBA_SITES
-- Key Biodiversity Areas polygon dataset.
-- Loaded from datasets/KBA_Data/KBAsGlobal_2026_March_01_POL.shp
-- and stored as WGS84 PostGIS multipolygons.
-- ------------------------------------------------------------
CREATE TABLE kba_sites (
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
    raw_json           JSONB       NOT NULL DEFAULT '{}'::jsonb,
    geometry           geometry(MultiPolygon, 4326) NOT NULL,
    imported_at        TIMESTAMP   NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_kba_sites_source_sitrec
    ON kba_sites(source_dataset, sitrec_id)
    WHERE sitrec_id IS NOT NULL;

CREATE INDEX idx_kba_sites_iso3
    ON kba_sites(iso3);

CREATE INDEX idx_kba_sites_country
    ON kba_sites(country);

CREATE INDEX idx_kba_sites_kba_status
    ON kba_sites(kba_status);

CREATE INDEX idx_kba_sites_geometry
    ON kba_sites USING GIST (geometry);


-- ------------------------------------------------------------
-- 18. CAPAD_PROTECTED_AREAS
-- Collaborative Australian Protected Areas Database (CAPAD) 2024
-- terrestrial polygons stored as WGS84 PostGIS multipolygons.
-- ------------------------------------------------------------
CREATE TABLE capad_protected_areas (
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
    raw_json          JSONB       NOT NULL DEFAULT '{}'::jsonb,
    geometry          geometry(MultiPolygon, 4326) NOT NULL,
    imported_at       TIMESTAMP   NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_capad_protected_areas_source_object
    ON capad_protected_areas(source_dataset, object_id)
    WHERE object_id IS NOT NULL;

CREATE INDEX idx_capad_protected_areas_pa_id
    ON capad_protected_areas(pa_id);

CREATE INDEX idx_capad_protected_areas_state_code
    ON capad_protected_areas(state_code);

CREATE INDEX idx_capad_protected_areas_iucn
    ON capad_protected_areas(iucn_category);

CREATE INDEX idx_capad_protected_areas_type_abbr
    ON capad_protected_areas(type_abbr);

CREATE INDEX idx_capad_protected_areas_geometry
    ON capad_protected_areas USING GIST (geometry);
