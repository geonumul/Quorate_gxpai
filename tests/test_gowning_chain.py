# -*- coding: utf-8 -*-
"""ADJ-002 — **갱의실 우회 경로** 회귀 시험.

## 조문 (예전엔 "검수대기"로 비워 뒀다)

    고시 별표1 제4호 가목
      "이 청정실은 작업원의 경우 **에어락 역할을 하는 갱의실을 통해 이동해야 하며**
       장비와 원자재는 에어락을 통해 이동해야 한다."

예전 규칙 파일에는 clause 가 `"별표17 / PIC-S Annex 1 - 검수대기"` 라고만 적혀 있었다.
**조문 번호도 원문도 없이 규칙을 만들어 뒀던 것**이다. 법규 코퍼스에서 찾아 채웠다.

## 판정 방법이 핵심

"갱의실이 있느냐"가 아니라 **"우회로가 없느냐"** 를 본다.
갱의실을 아무리 잘 갖춰 놔도 **옆에 뒷문이 하나 있으면 소용이 없다.** 그 뒷문을 찾는다.

→ 동선 그래프에서 **갱의실·에어락 노드를 제거**한다.
  그래도 청정실이 비청정 구역과 이어지면 우회로가 있는 것이다.
"""
from __future__ import annotations

from gxpai.compliance.checks import adj_002
from gxpai.compliance.checks._model import AdjPair, RoomView

CFG = {"enabled": True, "clean_min_rank": 2,
       "grade_rank": {"A": 5, "B": 4, "C": 3, "D": 2, "CNC": 1, "NC": 0}}


def test_갱의실을_거치면_위반이_아니다():
    """정상 설계: 일반복도 → 갱의실 → 청정실. 갱의실이 유일한 관문이다."""
    rooms = [RoomView(room_no="G1", name="일반복도", grade="NC"),
             RoomView(room_no="GW", name="갱의실(남)"),
             RoomView(room_no="C1", name="무균 조제실", grade="B")]
    adj = [AdjPair("G1", "GW", via_door=True), AdjPair("GW", "C1", via_door=True)]
    assert adj_002.evaluate(adj, rooms, CFG) == []


def test_뒷문_하나가_갱의실을_무력화한다():
    """★핵심. 갱의실을 제대로 갖춰 놨어도 **뒷문이 하나 있으면** 소용없다."""
    rooms = [RoomView(room_no="G1", name="일반복도", grade="NC"),
             RoomView(room_no="GW", name="갱의실(남)"),
             RoomView(room_no="C1", name="무균 조제실", grade="B")]
    adj = [AdjPair("G1", "GW", via_door=True),
           AdjPair("GW", "C1", via_door=True),
           AdjPair("G1", "C1", via_door=True)]        # ← 뒷문
    v = adj_002.evaluate(adj, rooms, CFG)
    assert len(v) == 1
    assert sorted(v[0]["evidence"]["breach_door"]) == ["C1", "G1"]


def test_뚫린_문_하나를_한_건으로_보고한다():
    """★실제 도면에서 잡은 과잉 검출.

    참고도면에서 처음엔 **10건**이 나왔다. 파 보니 실제 원인은 **문 2개**뿐이었다 —
    나머지 8건은 그 두 문을 통해 갈 수 있는 방들을 **중복해서 센 것**이었다.

    설계자가 고쳐야 하는 것은 **그 문**이다. 문 하나를 막으면 여러 건이 한꺼번에 사라진다.
    → (청정실, 비청정실) 쌍이 아니라 **뚫린 문**을 단위로 보고한다.
    """
    rooms = [RoomView(room_no="D1", name="일반복도", grade="NC"),
             RoomView(room_no="W1", name="세척실", grade="D"),      # 뚫린 방
             RoomView(room_no="C1", name="청정 복도", grade="D"),
             RoomView(room_no="C2", name="조제실", grade="C"),
             RoomView(room_no="C3", name="충진실", grade="B")]
    adj = [AdjPair("D1", "W1", via_door=True),        # ← 뚫린 문 (여기 하나)
           AdjPair("W1", "C1", via_door=True),
           AdjPair("C1", "C2", via_door=True),
           AdjPair("C1", "C3", via_door=True)]
    v = adj_002.evaluate(adj, rooms, CFG)
    assert len(v) == 1, "청정실 4개가 노출돼도 **문은 하나**다"
    e = v[0]["evidence"]
    assert sorted(e["breach_door"]) == ["D1", "W1"]
    # 그 문 때문에 노출되는 청정실을 함께 알려준다(피해 범위)
    assert set(e["노출된_청정실"]) == {"W1", "C1", "C2", "C3"}


def test_벽만_맞댄_것은_우회로가_아니다():
    """★벽은 지나갈 수 없다. 문 인접(동선)으로만 판정한다."""
    rooms = [RoomView(room_no="G1", name="일반복도", grade="NC"),
             RoomView(room_no="C1", name="무균 조제실", grade="B")]
    assert adj_002.evaluate([AdjPair("G1", "C1", via_door=False)], rooms, CFG) == []


def test_문_데이터가_없으면_판정하지_않는다():
    rooms = [RoomView(room_no="G1", name="일반복도", grade="NC"),
             RoomView(room_no="C1", name="무균 조제실", grade="B")]
    assert adj_002.evaluate([AdjPair("G1", "C1", via_door=None)], rooms, CFG) == []


def test_등급이_없으면_판정하지_않는다():
    """★기준 시설(내용고형제) 도면에는 **등급 표기가 0건**이다.

    어디가 청정실이고 어디가 비청정인지 모르면 판정할 수 없다.
    추측해서 내지 않는다.
    """
    rooms = [RoomView(room_no="G1", name="일반복도"),
             RoomView(room_no="C1", name="무균 조제실")]
    assert adj_002.evaluate([AdjPair("G1", "C1", via_door=True)], rooms, CFG) == []


def test_등급_미상_방은_판정에서_뺀다():
    """등급이 없는 방은 청정인지 비청정인지 모른다. **경유는 시키되 판정 대상에서 뺀다.**"""
    rooms = [RoomView(room_no="G1", name="일반복도", grade="NC"),
             RoomView(room_no="X1", name="미상실"),                 # 등급 없음
             RoomView(room_no="C1", name="무균 조제실", grade="B")]
    # 일반복도 → 미상실 → 무균 조제실 : 갱의실이 없다 → 우회로다
    adj = [AdjPair("G1", "X1", via_door=True), AdjPair("X1", "C1", via_door=True)]
    v = adj_002.evaluate(adj, rooms, CFG)
    assert len(v) == 1
    # 뚫린 문은 미상실 → 일반복도 구간이다
    assert sorted(v[0]["evidence"]["breach_door"]) == ["G1", "X1"]


def test_전실도_관문이다():
    """전실(前室)·에어락도 갱의실과 같은 관문 역할을 한다."""
    rooms = [RoomView(room_no="G1", name="일반복도", grade="NC"),
             RoomView(room_no="A1", name="무균 전실"),
             RoomView(room_no="C1", name="무균 조제실", grade="B")]
    adj = [AdjPair("G1", "A1", via_door=True), AdjPair("A1", "C1", via_door=True)]
    assert adj_002.evaluate(adj, rooms, CFG) == []
