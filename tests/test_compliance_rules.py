# -*- coding: utf-8 -*-
"""T2.3.3 - 합성 위반 회귀 시험.

목적: 검사 규칙이 (1)일부러 심은 위반은 빠짐없이 잡고, (2)깨끗한 데이터에서는
오탐 0 임을 DB 없이 빠르게 고정한다. 규칙 로직을 순수 함수(evaluate)로 분리했기에
가능하다. 실제 도면 검사 결과(변경 후에도 바뀌면 안 되는 기준값 LBL-001=3/LBL-002=17)와는 독립이다.

여기서 PRES-001/ADJ-001 은 아직 게이트(실제 파이프라인 미작동)지만, 순수 로직은
합성 정답으로 완전히 검증해 둔다. 발주처 확인, 검수 후 enabled 만 켜면 되도록.
"""
from __future__ import annotations

from gxpai.compliance.checks import adj_001, lbl_001, lbl_002, pres_001
from gxpai.compliance.checks._model import AdjPair, PressureRel, RoomView


# ---------------------------------------------------------------- LBL-001
def test_lbl001_catches_name_mismatch():
    rooms = [
        # 위반: 정규화 후에도 이름이 다름
        RoomView(room_no="3101", name="충전실", pressure_name="포장실", plan_x=0.0),
        # 비위반: 공백/괄호/N 표기 차이만 있음 → 정규화하면 같음
        RoomView(room_no="3102", name="제 조 실(N)", pressure_name="제조실", plan_x=1.0),
        # 비위반: 한쪽 도면에만 있어 비교 불가(이건 LBL-002 소관)
        RoomView(room_no="3103", name="복도", pressure_name=None, plan_x=2.0),
    ]
    found = lbl_001.evaluate(rooms)
    assert [v["rooms"] for v in found] == [["3101"]]
    assert found[0]["severity"] == "minor"


def test_lbl001_clean_has_no_violation():
    rooms = [RoomView(room_no="3101", name="충전실", pressure_name="충전실", plan_x=0.0)]
    assert lbl_001.evaluate(rooms) == []


def test_lbl001_new_room_marker_normalized():
    # 의도된 동작: "(N)"(신설 표기) 차이만 있으면 위반 아님.
    rooms = [RoomView(room_no="3105", name="(N)충전실", pressure_name="충전실", plan_x=0.0)]
    assert lbl_001.evaluate(rooms) == []


def test_lbl001_맨_N은_이름의_일부다():
    """**이 시험은 예전에 '알려진 한계'였다. 이제 해결됐다.** (2026-07-14)

    옛 정규화는 `[\\s()N\\-]` 였다 — **문자열 어디에 있든 대문자 N 을 지웠다.**
    그래서 두 방향으로 다 틀렸다:

        `N동`  vs `동`            → 둘 다 `동` → 같다고 판정 → **위반을 놓친다**
        `GRANULATION` vs `Granulation`
                                 → `GRAULATIO` vs `Granulation` → **거짓 위반**
                                   (소문자 n 은 안 지웠고 대소문자 폴딩도 안 했다)

    옛 시험이 스스로 개선안을 적어 뒀다 —
      *"'(N)' 접두만 제거하도록 정규식을 좁히면 오탐누락 감소(단 기준값 재확인 필요)"*
    그대로 고쳤고, **기준값(LBL-001 3건 / LBL-002 17건)도 실도면에서 재확인**했다.

    이제 **괄호로 감싼 N 만** 지운다. 맨 N 은 이름의 일부다.
    """
    # `N동` 과 `동` 은 **다른 이름**이다 → 위반으로 잡아야 한다
    rooms = [RoomView(room_no="3106", name="N동", pressure_name="동", plan_x=0.0)]
    assert len(lbl_001.evaluate(rooms)) == 1, \
        "맨 N 을 지워버리면 서로 다른 이름을 같다고 판정한다(위반 놓침)"


def test_lbl001_대소문자만_다르면_같은_이름이다():
    """옛 정규화는 대소문자 폴딩을 안 해서 `GRANULATION` vs `Granulation` 을
    **거짓 위반**으로 찍었다(게다가 N 을 지워 `GRAULATIO` 가 됐다).
    참고도면은 방 이름이 영문 대문자, 차압도는 첫 글자만 대문자인 곳이 있다."""
    rooms = [RoomView(room_no="3107", name="GRANULATION",
                      pressure_name="Granulation", plan_x=0.0)]
    assert lbl_001.evaluate(rooms) == []


def test_lbl001_신설표시는_앞뒤_어디든_지운다():
    """`(N)` 은 신설 표시다. 도면마다 `(N)제조실` 도 있고 `제 조 실(N)` 도 있다.
    전각 괄호(`（N）`)를 쓰는 도면도 있다."""
    for a, b in [("(N)제조실", "제조실"), ("제 조 실(N)", "제조실"),
                 ("（N）제조실", "제조실"), ("(n)제조실", "제조실")]:
        rooms = [RoomView(room_no="3108", name=a, pressure_name=b, plan_x=0.0)]
        assert lbl_001.evaluate(rooms) == [], f"{a} vs {b} 는 같은 이름이다"


# ---------------------------------------------------------------- LBL-002
def test_lbl002_catches_single_drawing_rooms():
    rooms = [
        # 양쪽 도면 모두 존재 → 비위반
        RoomView(room_no="3101", name="충전실", pressure_name="충전실", plan_x=0.0),
        # 평면도에만 존재
        RoomView(room_no="3102", name="포장실", pressure_name=None, plan_x=1.0),
        # 차압도에만 존재(plan_x None)
        RoomView(room_no="3103", name=None, pressure_name="세척실", plan_x=None),
    ]
    found = lbl_002.evaluate(rooms)
    by_room = {v["rooms"][0]: v["evidence"]["in"] for v in found}
    assert by_room == {"3102": "floorplan_only", "3103": "pressure_only"}


def test_lbl002_clean_has_no_violation():
    rooms = [RoomView(room_no="3101", name="충전실", pressure_name="충전실", plan_x=0.0)]
    assert lbl_002.evaluate(rooms) == []


# ---------------------------------------------------------------- PRES-001
_PRES_CFG = {"cleaner_should_be": "higher",
             "grade_rank": {"A": 4, "B": 3, "C": 2, "D": 1, "CNC": 0}}


def test_pres001_catches_cascade_inversion():
    rooms = [
        RoomView(room_no="R1", grade="D"),  # 덜 깨끗
        RoomView(room_no="R2", grade="A"),  # 더 깨끗
        RoomView(room_no="R3", grade="A"),
        RoomView(room_no="R4", grade="D"),
    ]
    rels = [
        # 위반: 고압=R1(D), 저압=R2(A) → 더 깨끗한 R2 가 저압 쪽
        PressureRel(room_high_no="R1", room_low_no="R2", approx=False),
        # 정상: 고압=R3(A), 저압=R4(D) → 깨끗한 방이 고압
        PressureRel(room_high_no="R3", room_low_no="R4", approx=False),
    ]
    found = pres_001.evaluate(rels, rooms, _PRES_CFG)
    assert len(found) == 1
    assert set(found[0]["rooms"]) == {"R1", "R2"}
    assert found[0]["severity"] == "critical"


def test_pres001_skips_approx_and_ungraded():
    rooms = [RoomView(room_no="R1", grade="D"), RoomView(room_no="R2", grade="A"),
             RoomView(room_no="R5", grade=None), RoomView(room_no="R6", grade="A")]
    rels = [
        # approx=True(원시 화살표, 방 귀속 미확정) → 판정 불가
        PressureRel(room_high_no="R1", room_low_no="R2", approx=True),
        # 등급 미상 방 포함 → 건너뜀
        PressureRel(room_high_no="R5", room_low_no="R6", approx=False),
    ]
    assert pres_001.evaluate(rels, rooms, _PRES_CFG) == []


def test_pres001_gate_blocks_run(monkeypatch):
    # config.enabled 가 없으면 데이터가 있어도 run() 은 0건 (게이트)
    calls = {"n": 0}
    monkeypatch.setattr(pres_001, "load_pressure_rels", lambda *a: calls.__setitem__("n", 1) or [])
    monkeypatch.setattr(pres_001, "load_rooms", lambda *a: [])
    out = pres_001.run(cur=None, run_id="x", facility_id="f", rule={"id": "PRES-001"})
    assert out == [] and calls["n"] == 0  # 로딩조차 하지 않음


# ---------------------------------------------------------------- ADJ-001
_ADJ_CFG = {"forbidden_pairs": [["A", "D"], ["A", "CNC"]]}


def test_adj001_catches_forbidden_adjacency():
    rooms = [RoomView(room_no="R1", grade="A"), RoomView(room_no="R2", grade="D"),
             RoomView(room_no="R3", grade="B")]
    adjacency = [
        AdjPair("R1", "R2"),  # 위반: A-D 직접 인접
        AdjPair("R2", "R1"),  # 같은 쌍 역방향 → 중복 집계 금지
        AdjPair("R1", "R3"),  # 정상: A-B 는 금지쌍 아님
    ]
    found = adj_001.evaluate(adjacency, rooms, _ADJ_CFG)
    assert len(found) == 1
    assert found[0]["rooms"] == ["R1", "R2"]


def test_adj001_clean_and_ungraded():
    rooms = [RoomView(room_no="R1", grade="A"), RoomView(room_no="R2", grade="B"),
             RoomView(room_no="R7", grade=None)]
    adjacency = [AdjPair("R1", "R2"), AdjPair("R1", "R7")]
    assert adj_001.evaluate(adjacency, rooms, _ADJ_CFG) == []


def test_adj001_gate_blocks_run(monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(adj_001, "load_adjacency", lambda *a: calls.__setitem__("n", 1) or [])
    out = adj_001.run(cur=None, run_id="x", facility_id="f", rule={"id": "ADJ-001"})
    assert out == [] and calls["n"] == 0
