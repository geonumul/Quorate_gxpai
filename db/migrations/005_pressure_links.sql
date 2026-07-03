-- 005_pressure_links.sql - 차압도 방 위치 보존 + 화살표↔방 귀속(관찰된 기하만)
--
-- 배경: 차압도와 평면도는 좌표계가 다르다(docs/기존데이터_분석.md). 그래서 화살표(차압도 좌표)를
-- 평면도 방에 직접 못 붙인다. 우회로: 차압도 화살표와 차압도 방 라벨은 같은 좌표계이므로,
-- 차압도 안에서 화살표를 방에 붙여 방번호 쌍을 얻는다. 이를 위해 차압도 방 위치(pres_x/pres_y)를
-- 보존한다(그동안 _merge 에서 버려지던 값).
--
-- 원칙(리스크 S-1, 발주처 확인 전 해석 금지): 저장하는 것은 '관찰된 기하'뿐이다.
--   room_head = 화살촉이 향하는 방, room_tail = 꼬리쪽 방 (도면에서 그대로 읽은 사실).
-- '어느 쪽이 고압/저압인지'는 화살표 의미가 확정돼야 정해지는 '해석'이므로 room_high/room_low 는
-- 계속 NULL 로 둔다. 발주처가 "화살촉=저압"을 확인하면 그때 room_high=room_tail, room_low=room_head
-- 로 채운다(우리 잠정 추정은 head=저압이나, 확정 아님).

ALTER TABLE room ADD COLUMN IF NOT EXISTS pres_x DOUBLE PRECISION;  -- 차압도 방 라벨 x
ALTER TABLE room ADD COLUMN IF NOT EXISTS pres_y DOUBLE PRECISION;  -- 차압도 방 라벨 y

-- pressure_relation 은 001 에서 기본키가 없어 행을 지목해 갱신할 수 없다. id 부여(행별 귀속 갱신용).
ALTER TABLE pressure_relation ADD COLUMN IF NOT EXISTS id BIGSERIAL PRIMARY KEY;
ALTER TABLE pressure_relation ADD COLUMN IF NOT EXISTS room_head BIGINT REFERENCES room(id);
ALTER TABLE pressure_relation ADD COLUMN IF NOT EXISTS room_tail BIGINT REFERENCES room(id);
