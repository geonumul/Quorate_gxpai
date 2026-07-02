-- 003_overview.sql - 설계개요 표에서 뽑은 시설 메타 (T1.2.2)
-- 키-값 항목(공사명/연면적/구조 등)을 run 단위로 저장. 같은 run 안 key 중복 차단.
CREATE TABLE IF NOT EXISTS facility_meta (
    id                BIGSERIAL PRIMARY KEY,
    facility_id       TEXT NOT NULL REFERENCES facility(id),
    run_id            TEXT NOT NULL REFERENCES run(id),
    key               TEXT NOT NULL,
    value             TEXT,
    source_drawing_id TEXT REFERENCES drawing(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_facility_meta_run_key
    ON facility_meta (facility_id, run_id, key);
