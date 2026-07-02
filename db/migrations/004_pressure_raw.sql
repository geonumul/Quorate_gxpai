-- 004_pressure_raw.sql - 추출했으나 저장 안 되던 원시 데이터 보존 (Stage 1 완결성)
-- 감사에서 확인: 차압 화살표 98개·TA 98개가 추출 후 버려짐.
-- 화살표 방향 의미 확정(S-1)은 Stage 2 이므로, 지금은 room 미귀속 + approx=true 로 원시 보관.
-- 차압도 방이름은 room.pressure_name 에 보존 → Stage 2 LBL-001(이름 불일치) 검출용.
ALTER TABLE room ADD COLUMN IF NOT EXISTS pressure_name TEXT;

CREATE TABLE IF NOT EXISTS ta_value (
    id          BIGSERIAL PRIMARY KEY,
    run_id      TEXT NOT NULL REFERENCES run(id),
    facility_id TEXT NOT NULL REFERENCES facility(id),
    x           DOUBLE PRECISION,
    y           DOUBLE PRECISION,
    value_raw   DOUBLE PRECISION,
    unit        TEXT                       -- UNKNOWN (CMH vs Pa 미확정, question 등록됨)
);

CREATE INDEX IF NOT EXISTS idx_ta_value_run ON ta_value(run_id);
CREATE INDEX IF NOT EXISTS idx_pressure_relation_run ON pressure_relation(run_id);
