-- 007_pressure_regime.sql
-- 압력 규칙 재설계에 필요한 컬럼 추가 (2026-07-13)
--
-- 왜 필요한가 (근거: 법규/조문근거_색인.md A-5절, 2010 시설기준 안내서 p.24/p.60)
--   압력 방향에는 **3가지 유형**이 있고, 하나의 규칙으로 묶으면 안 된다.
--     ① 보호(protect)   : 실이 고압. 외부 오염이 못 들어오게 (무균제제, 일반 청정실)
--     ② 봉쇄(contain)   : 실이 저압, **복도가 고압**. 분진이 복도로 못 나가게
--                          (칭량, 혼합, 과립, 정립, 타정 = 우리 기준 시설 내용고형제!)
--     ③ 특수봉쇄(hazard): 실이 음압 + 전용 전실 + 별도 공조 (페니실린, 세포독성, 성호르몬)
--   "청정할수록 고압"만 검사하면 ②③에서 **전부 거짓 위반**이 난다.
--
--   pressure_pa   : 도면에 표기된 실의 절대 정압(Pa). 새 참고도면 DXF 레이어 `차압` 의 TEXT.
--   regime        : 위 3유형. 공정(방 이름)에서 추론하고, 프로파일로 덮어쓸 수 있다.
--   regime_source : 값이 어디서 왔는지(감사 추적). inferred | profile | drawing | manual

ALTER TABLE room ADD COLUMN IF NOT EXISTS pressure_pa    DOUBLE PRECISION;
ALTER TABLE room ADD COLUMN IF NOT EXISTS regime         TEXT;
ALTER TABLE room ADD COLUMN IF NOT EXISTS regime_source  TEXT;

COMMENT ON COLUMN room.pressure_pa   IS '도면 표기 절대 정압(Pa). 없으면 NULL → 수치 규칙은 건너뜀';
COMMENT ON COLUMN room.regime        IS 'protect | contain | hazard | neutral (압력 방향 유형)';
COMMENT ON COLUMN room.regime_source IS 'inferred | profile | drawing | manual (감사 추적)';
