-- 002_ingest.sql — 적재 멱등성 보강 (리스크 R-E3)
-- 같은 run 안에서 방번호 중복 적재를 DB 레벨에서 차단.
-- 무번호 방(room_no IS NULL)은 부분 인덱스로 제외한다.
CREATE UNIQUE INDEX IF NOT EXISTS uq_room_run_no
    ON room (facility_id, run_id, room_no)
    WHERE room_no IS NOT NULL;
