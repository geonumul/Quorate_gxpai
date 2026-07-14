-- 006_run_audit.sql - run 감사추적 정직성 (코드리뷰 M6/M7)
-- 문제: run.status 가 한 트랜잭션 안에서 running→done 이라 실패 시 run 행 자체가 롤백돼 'failed'
--       이력이 남지 않았다(GMP 감사에 치명적). run 을 별도 트랜잭션으로 먼저 커밋하고, 완료/실패를
--       나중에 기록하도록 코드를 바꾼다. 그 종료 시각, 오류를 남길 컬럼을 추가한다.
-- 이력은 append-only(불변): 매 ingest = 새 run. 이게 감사추적의 올바른 모델이다(과거 run 삭제 안 함).
ALTER TABLE run ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ;
ALTER TABLE run ADD COLUMN IF NOT EXISTS error TEXT;

CREATE INDEX IF NOT EXISTS idx_run_facility_started ON run (facility_id, started_at DESC);
