# -*- coding: utf-8 -*-
"""ADJ-005 - **A, B 등급으로 연결되는 에어락에 인터락이 없다** 회귀 시험.

## 이 규칙이 이 파일의 존재 이유다: **구판을 인용했으면 규칙 자체를 못 만들었다**

    구판 (식약처 게시판, **인용금지**)
      "… 인터락 시스템(interlocking system) **또는** 시각적 및 청각적 …
       경보장치가 가동되어야 한다."          ← '또는' 이라 인터락이 필수가 아니다

    현행 (법제처) 고시 별표1 제4호 파목
      "**A등급과 B등급 구역으로 연결되는 에어락의 경우 인터락 시스템을 사용해야 한다.**
       C등급과 D등급 청정실로 연결되는 에어락의 경우, 최소한 시각경고시스템 …"
                                            ← 등급별로 갈라놨다. A/B 는 인터락 **필수**

구판을 인용했으면 **A/B 의 인터락 의무를 놓쳤을 것이다.**
**근거가 둘이면 반드시 대조한다.** (식약처 게시판에는 아직 구판이 올라와 있다)

## 왜 인터락인가
에어락의 두 문이 **동시에 열리면 에어락이 아니다** - 청정실이 비청정 구역에 그대로 뚫린다.
경고등은 사람이 무시할 수 있지만 인터락은 물리적으로 막는다.
"""
from __future__ import annotations

from gxpai.compliance.checks import adj_005
from gxpai.compliance.checks._model import AdjPair, RoomView

CFG = {"enabled": True, "interlock_min_rank": 4,
       "grade_rank": {"A": 5, "B": 4, "C": 3, "D": 2, "CNC": 1, "NC": 0}}


def test_B등급으로_이어지는_에어락에_인터락이_없으면_위반():
    """실제 도면에서 잡은 2건. `무균 전실` → `무균 복도(B)` 인데 인터락이 없다."""
    rooms = [RoomView(room_no="A1", name="무균 전실", grade="B", interlock_count=0),
             RoomView(room_no="C1", name="무균 복도", grade="B", interlock_count=0)]
    v = adj_005.evaluate([AdjPair("A1", "C1", via_door=True)], rooms, CFG)
    assert len(v) == 1
    assert v[0]["evidence"]["airlock"] == "A1"
    assert "인터락 시스템을 사용해야 한다" in v[0]["evidence"]["원문"]


def test_인터락이_있으면_위반_아님():
    rooms = [RoomView(room_no="A1", name="무균 전실", grade="B", interlock_count=1),
             RoomView(room_no="C1", name="무균 복도", grade="B", interlock_count=0)]
    assert adj_005.evaluate([AdjPair("A1", "C1", via_door=True)], rooms, CFG) == []


def test_C_D_등급으로만_이어지면_인터락_의무가_아니다():
    """조문이 등급별로 갈라놨다. C, D 는 **최소한 시각경고시스템**이면 된다.

    이걸 안 갈랐으면(구판대로 뭉뚱그렸으면) 모든 전실이 위반으로 찍혔을 것이다.
    """
    rooms = [RoomView(room_no="A1", name="타정1실 전실", grade="D", interlock_count=0),
             RoomView(room_no="P1", name="(N)타정1실", grade="D", interlock_count=0),
             RoomView(room_no="C1", name="복도", grade="CNC", interlock_count=0)]
    adj = [AdjPair("A1", "P1", via_door=True), AdjPair("A1", "C1", via_door=True)]
    assert adj_005.evaluate(adj, rooms, CFG) == []


def test_A등급으로_이어져도_위반():
    rooms = [RoomView(room_no="A1", name="무균 전실", grade="B", interlock_count=0),
             RoomView(room_no="F1", name="무균 충전실", grade="A", interlock_count=0)]
    assert len(adj_005.evaluate([AdjPair("A1", "F1", via_door=True)], rooms, CFG)) == 1


def test_에어락이_아닌_방은_대상이_아니다():
    """조문은 '에어락, 이송해치'에 대해 말한다. 그냥 붙어 있는 방은 대상이 아니다."""
    rooms = [RoomView(room_no="R1", name="조제실", grade="C", interlock_count=0),
             RoomView(room_no="C1", name="무균 복도", grade="B", interlock_count=0)]
    assert adj_005.evaluate([AdjPair("R1", "C1", via_door=True)], rooms, CFG) == []


def test_인터락_도면이_없는_시설은_판정하지_않는다():
    """`interlock_count=None` = "인터락 정보가 없다" 이지 **"인터락이 없다"가 아니다.**

    혼동하면 **전 에어락이 거짓 위반**이 된다.
    (rels=[], door_pairs=[], has_gauge=false, interlock_count=0
     - **네 번째** 만나는 같은 함정이다. 매번 시험으로 막는다)
    """
    rooms = [RoomView(room_no="A1", name="무균 전실", grade="B"),          # None
             RoomView(room_no="C1", name="무균 복도", grade="B")]
    assert adj_005.evaluate([AdjPair("A1", "C1", via_door=True)], rooms, CFG) == []


def test_벽만_맞댄_것은_연결이_아니다():
    rooms = [RoomView(room_no="A1", name="무균 전실", grade="B", interlock_count=0),
             RoomView(room_no="C1", name="무균 복도", grade="B", interlock_count=0)]
    assert adj_005.evaluate([AdjPair("A1", "C1", via_door=False)], rooms, CFG) == []


def test_패스박스와_이송해치도_에어락이다():
    """조문은 "**이송해치 및 에어락**(물품 및 작업원용)"이라고 한다. 물자용도 포함이다."""
    for nm in ("패스박스", "이송 해치", "pass box"):
        rooms = [RoomView(room_no="A1", name=nm, grade="B", interlock_count=0),
                 RoomView(room_no="C1", name="무균 복도", grade="B", interlock_count=0)]
        assert len(adj_005.evaluate([AdjPair("A1", "C1", via_door=True)], rooms, CFG)) == 1, nm
