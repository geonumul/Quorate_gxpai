# -*- coding: utf-8 -*-
"""ingest 파이프라인의 순수 함수 시험 - 등급, 압력, 압력유형 적용.

가장 중요한 회귀: **등급을 '세기만 하고 버리던' 버그**.
  예전 ingest 는 GradeExtractor 결과를 counts["grade_zone"] 로 세기만 하고
  방에 붙이지 않았다. 그래서 room.grade 가 영원히 NULL 이었고,
  grade 에 의존하는 규칙(PRES-001, ADJ-001)이 **데이터가 있어도 0건**을 냈다.
"""
from __future__ import annotations

from gxpai.core.run import apply_grades, apply_pressures, apply_regimes


def test_등급이_방에_실제로_붙는다():
    """'세기만 하고 버리던' 버그의 회귀."""
    merged = [{"room_no": "F2I01", "name": "탈의실(남)"},
              {"room_no": "F2I03", "name": "갱의실(남)"}]
    grades = [{"room_no": "F2I01", "grade": "CNC"},
              {"room_no": "F2I03", "grade": "D"}]
    n = apply_grades(merged, grades)
    assert n == 2
    assert merged[0]["grade"] == "CNC"
    assert merged[1]["grade"] == "D"


def test_등급표기_없으면_grade_는_None():
    """기준 시설(내용고형제)처럼 도면에 등급 표기가 없는 경우. 0건이 정상이다."""
    merged = [{"room_no": "3117", "name": "타정실"}]
    assert apply_grades(merged, []) == 0
    assert merged[0].get("grade") is None


def test_등급_없는_방은_건드리지_않는다():
    merged = [{"room_no": "A", "name": "조제실"}, {"room_no": "B", "name": "복도"}]
    apply_grades(merged, [{"room_no": "A", "grade": "C"}])
    assert merged[0]["grade"] == "C"
    assert "grade" not in merged[1]


def test_절대압력이_방에_붙는다():
    merged = [{"room_no": "F2I01"}, {"room_no": "F2I03"}]
    n = apply_pressures(merged, [{"room_no": "F2I01", "pressure_pa": 5.0},
                                 {"room_no": "F2I03", "pressure_pa": 15.0}])
    assert n == 2
    assert merged[0]["pressure_pa"] == 5.0
    assert merged[1]["pressure_pa"] == 15.0


def test_압력_0Pa_도_적용된다():
    """0Pa 은 '값 없음'이 아니다. 일반복도가 0Pa 이다. falsy 로 걸러지면 안 된다."""
    merged = [{"room_no": "F2G01", "name": "일반복도"}]
    assert apply_pressures(merged, [{"room_no": "F2G01", "pressure_pa": 0.0}]) == 1
    assert merged[0]["pressure_pa"] == 0.0


def test_압력유형이_이름으로_추정된다():
    merged = [{"room_no": "A", "name": "타정실"},
              {"room_no": "B", "name": "복도"},
              {"room_no": "C", "name": "무균 조제실"},
              {"room_no": "D", "name": "페니실린 충전실"}]
    counts = apply_regimes(merged, {})
    assert merged[0]["regime"] == "contain"     # 분진 발생
    assert merged[1]["regime"] == "neutral"     # 복도
    assert merged[2]["regime"] == "protect"     # 무균
    assert merged[3]["regime"] == "hazard"      # 특수제제
    assert counts == {"contain": 1, "neutral": 1, "protect": 1, "hazard": 1}
    assert all(r["regime_source"] == "inferred" for r in merged)


def test_프로파일_override_가_추론을_이긴다():
    """'캡슐 충전실'은 분말이라 분진이 나지만, 이름만으로는 못 가른다.

    (무균 '바이알 충진'은 액체라 분진이 없다 - 같은 단어가 시설마다 정반대다.)
    그래서 프로파일로 지정할 수 있어야 하고, 그게 추론을 이겨야 한다.
    """
    merged = [{"room_no": "3117", "name": "캡슐 충전실"}]
    profile = {"pressure_regime": {"overrides": {"3117": "contain"}}}
    apply_regimes(merged, profile)
    assert merged[0]["regime"] == "contain"
    assert merged[0]["regime_source"] == "profile"    # 감사 추적: 어디서 온 값인지
