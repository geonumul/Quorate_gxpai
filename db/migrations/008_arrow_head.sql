-- 008: 차압 화살표의 화살촉 세계각 + 레이어(=차압 설정값)
--
-- 왜 필요한가
--   ① head_deg: 예전엔 INSERT 의 rotation 만 저장하고 "화살촉은 rotation=0 에서 -y" 라고
--      **가정**했다. 실제 도면은 블록마다 화살촉 방향이 다르고(±x 정반대), 일부는
--      xscale 음수로 **거울반사**돼 있었다 → 28개 중 9개를 거꾸로 읽었다.
--      이제 블록 기하에서 재서 세계 각도를 그대로 넣는다. NULL = 못 읽음(추측 금지).
--   ② layer / setpoint_pa: 레이어 이름이 곧 차압 설정값이다
--      ('Air Flow 10Pa' / 'Air Flow 15Pa' / 'Air Flow no차압').
--      setpoint_pa IS NULL AND layer LIKE '%no차압%' = **차압 기준이 없는 구간**
--      (도면 범례 3번). 여기에 기준을 들이대면 거짓 위반이다.
ALTER TABLE pressure_relation
    ADD COLUMN IF NOT EXISTS head_deg    double precision,
    ADD COLUMN IF NOT EXISTS layer       text,
    ADD COLUMN IF NOT EXISTS setpoint_pa double precision;
