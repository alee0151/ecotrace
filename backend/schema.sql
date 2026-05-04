-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS pgcrypto;


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
