-- 014: 방번호 충돌 - **같은 방번호가 서로 다른 두 방에 붙어 있다**
--
-- 이 표는 **우리 버그가 아니라 도면의 결함**을 담는다.
--
-- 방번호 충돌 감지기를 만들자마자 기준 시설에서 **2건**이 나왔다:
--
--     3203  '샤워실(남)A'      ↔  '샤워실(남)A'        (8.9m 떨어진 서로 다른 방)
--     4504  '(N)타정4실'       ↔  '(N)타정2실 전실'    (6.0m 떨어진 서로 다른 방)
--
-- 그리고 45xx 번호대에서 **4507 이 통째로 빠져 있다**:
--     4501 4502 4503 [4504 4504] 4505 4506 ____ 4508 4509 4510
--
-- → 설계사가 번호를 잘못 매긴 것으로 **보인다**. 그러나 이건 **추정이다.**
--   (특별한 표기 관례일 수도 있다) **발주처 확인 필요.**
--
-- 예전에는 `_merge` 가 한쪽을 **조용히 덮어썼다.** 예외도 로그도 없었다 -
-- 방이 하나 사라지는데 아무도 몰랐다. 이제 남긴다.
--
-- 병합 동작 자체는 그대로 둔다(한쪽이 이긴다). 방번호는 우리 데이터의 **키**라
-- 중복을 허용하면 화살표 귀속, 차압 관계가 어느 방을 가리키는지 알 수 없게 된다.
-- → **버리되, 버렸다는 사실을 기록한다.**

CREATE TABLE IF NOT EXISTS room_no_conflict (
    id          BIGSERIAL PRIMARY KEY,
    run_id      TEXT NOT NULL REFERENCES run(id) ON DELETE CASCADE,
    facility_id TEXT NOT NULL,
    room_no     TEXT NOT NULL,

    -- 살아남은 쪽 (DB 의 room 에 들어간 것)
    kept_name   TEXT,
    kept_floor  TEXT,
    kept_x      DOUBLE PRECISION,
    kept_y      DOUBLE PRECISION,

    -- 덮어써져 **사라진** 쪽
    lost_name   TEXT,
    lost_floor  TEXT,
    lost_x      DOUBLE PRECISION,
    lost_y      DOUBLE PRECISION,

    -- 두 라벨 사이 거리(mm). 크면 **서로 다른 방**, 작으면 같은 방에 라벨이 두 번.
    dist_mm     DOUBLE PRECISION,

    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_room_no_conflict_run ON room_no_conflict(run_id);
