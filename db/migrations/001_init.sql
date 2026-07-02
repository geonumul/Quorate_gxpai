-- 001_init.sql - GXPAI 초기 스키마 (가이드라인 B.4)
-- 원칙: 스키마 변경은 반드시 마이그레이션 파일로. 손 ALTER 금지.
-- 모든 정형 데이터는 facility 단위로 격리된다.

CREATE EXTENSION IF NOT EXISTS vector;   -- pgvector (Stage 4 임베딩)

CREATE TABLE facility (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    product_type TEXT,
    profile_id   TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE drawing (
    id           TEXT PRIMARY KEY,
    facility_id  TEXT NOT NULL REFERENCES facility(id),
    kind         TEXT,                 -- floorplan | pressure | hvac | overview | ...
    filename     TEXT NOT NULL,
    sha256       TEXT NOT NULL,        -- 원본 불변성 매니페스트
    dxf_version  TEXT,
    ingested_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE run (
    id               TEXT PRIMARY KEY,
    facility_id      TEXT NOT NULL REFERENCES facility(id),
    pipeline_version TEXT NOT NULL,    -- 재현성 스탬프
    profile_version  TEXT NOT NULL,
    started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    status           TEXT NOT NULL DEFAULT 'running'  -- running | done | failed
);

CREATE TABLE room (
    id              BIGSERIAL PRIMARY KEY,
    facility_id     TEXT NOT NULL REFERENCES facility(id),
    run_id          TEXT NOT NULL REFERENCES run(id),
    room_no         TEXT,
    name            TEXT,
    floor           TEXT,
    sheet           TEXT,
    plan_x          DOUBLE PRECISION,
    plan_y          DOUBLE PRECISION,
    boundary        JSONB,            -- 폴리곤 좌표 (GEOMETRY 승격은 PostGIS 도입 시)
    boundary_method TEXT,             -- polyline | xref | floodfill | label_only (신뢰도 추적)
    area_m2         DOUBLE PRECISION,
    grade           TEXT,
    source_drawing_id TEXT REFERENCES drawing(id),
    confidence      REAL,             -- Stage 4 학습 루프 대비
    review_status   TEXT DEFAULT 'unreviewed'  -- unreviewed | approved | corrected
);

CREATE TABLE room_adjacency (
    run_id  TEXT NOT NULL REFERENCES run(id),
    room_a  BIGINT NOT NULL REFERENCES room(id),
    room_b  BIGINT NOT NULL REFERENCES room(id),
    method  TEXT NOT NULL            -- polygon | nearest
);

CREATE TABLE pressure_relation (
    run_id      TEXT NOT NULL REFERENCES run(id),
    room_high   BIGINT REFERENCES room(id),
    room_low    BIGINT REFERENCES room(id),
    evidence_x  DOUBLE PRECISION,
    evidence_y  DOUBLE PRECISION,
    rotation    DOUBLE PRECISION,
    approx      BOOLEAN DEFAULT false
);

CREATE TABLE equipment (
    id           BIGSERIAL PRIMARY KEY,
    run_id       TEXT NOT NULL REFERENCES run(id),
    facility_id  TEXT NOT NULL REFERENCES facility(id),
    name         TEXT,
    room_id      BIGINT REFERENCES room(id),
    x            DOUBLE PRECISION,
    y            DOUBLE PRECISION,
    method       TEXT                 -- nearest | contains
);

CREATE TABLE ahu (
    id           BIGSERIAL PRIMARY KEY,
    run_id       TEXT NOT NULL REFERENCES run(id),
    facility_id  TEXT NOT NULL REFERENCES facility(id),
    ahu_id       TEXT,
    x            DOUBLE PRECISION,
    y            DOUBLE PRECISION,
    floor        TEXT
);

CREATE TABLE violation (
    id        BIGSERIAL PRIMARY KEY,
    run_id    TEXT NOT NULL REFERENCES run(id),
    rule_id   TEXT NOT NULL,
    severity  TEXT NOT NULL,          -- critical | major | minor
    rooms     JSONB,
    message   TEXT,
    evidence  JSONB,
    status    TEXT DEFAULT 'open'     -- open | accepted | false_positive (Stage 4 학습 원료)
);

CREATE TABLE question (
    id           BIGSERIAL PRIMARY KEY,
    facility_id  TEXT REFERENCES facility(id),
    topic        TEXT,
    body         TEXT,
    status       TEXT DEFAULT 'open', -- open | answered
    answer       TEXT
);

-- 다중 시설 쿼리 인덱스
CREATE INDEX idx_room_facility  ON room(facility_id);
CREATE INDEX idx_room_run       ON room(run_id);
CREATE INDEX idx_drawing_facility ON drawing(facility_id);
CREATE INDEX idx_violation_run  ON violation(run_id);
