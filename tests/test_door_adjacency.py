# -*- coding: utf-8 -*-
"""**동선 인접**(문으로 이어진 방) 회귀 시험.

★ADJ-001 이 엉뚱한 것을 보고 있었다.

  지금까지 '인접' = **벽을 맞댄 방**이었다. 그런데 조문이 말하는 건 그게 아니다.
      고시 별표1 제4호 타목  : "작업원 **동선**은 D→C→B 로 점진적"
      고시 별표17 제3.3호 라목: "청정도에 따른 타당한 순서로 **연결된** 구역에 배치"
  둘 다 **사람·물건이 오가는 길**을 말한다.
  벽만 맞대고 문이 없으면 오갈 수 없다 → 등급이 급변해도 동선 위반이 아니다.

  벽 맞댐으로 판정하면 **지나갈 수도 없는 두 방**을 '등급 급변'이라 우긴다(거짓 위반).
"""
from __future__ import annotations

from gxpai.compliance.checks import adj_001
from gxpai.compliance.checks._model import AdjPair, RoomView

CFG = {"enabled": True, "max_jump": 1,
       "grade_rank": {"A": 5, "B": 4, "C": 3, "D": 2, "CNC": 1, "NC": 0}}
ROOMS = [RoomView(room_no="R1", name="무균 조제실", grade="B"),
         RoomView(room_no="R2", name="자재 창고", grade="NC")]


def test_문이_없으면_등급이_급변해도_위반이_아니다():
    """★핵심. 벽 하나를 사이에 둔 무균실과 창고 — 문이 없으면 사람이 못 지나간다."""
    벽만 = [AdjPair("R1", "R2", via_door=False)]
    assert adj_001.evaluate(벽만, ROOMS, CFG) == []


def test_문으로_이어지면_위반이다():
    문있음 = [AdjPair("R1", "R2", via_door=True)]
    v = adj_001.evaluate(문있음, ROOMS, CFG)
    assert len(v) == 1
    assert v[0]["evidence"]["via_door"] is True
    assert "동선 확인" in v[0]["evidence"]["인접근거"]


def test_문_정보가_없는_도면은_벽_인접으로_폴백하되_보류로_남긴다():
    """★참고도면에는 문 블록이 없다. 판정을 **포기하지도 확정하지도** 않는다.

    벽 인접으로 판정하되 근거에 "문이 없으면 위반이 아닐 수 있다"를 남긴다.
    모든 추정은 보류 — 발주처가 확인한다.
    """
    문모름 = [AdjPair("R1", "R2", via_door=None)]
    v = adj_001.evaluate(문모름, ROOMS, CFG)
    assert len(v) == 1
    assert v[0]["evidence"]["via_door"] is None
    assert "문 정보 없는 도면" in v[0]["evidence"]["인접근거"]
    assert v[0]["evidence"]["판단"].startswith("보류")


def test_한_쌍이라도_문_정보가_있으면_문_기준으로_판정한다():
    """★`via_door=[]` 함정 방지.

    '문이 하나도 안 이어진 도면'과 '문 데이터가 없는 도면'은 **다르다.**
    앞의 것은 전부 걸러야 하고, 뒤의 것은 벽으로 폴백해야 한다.
    (차압 화살표에서 `rels=[]` vs `rels=None` 으로 똑같은 함정을 밟았다.)
    """
    rooms = ROOMS + [RoomView(room_no="R3", name="복도", grade="D")]
    adj = [AdjPair("R1", "R2", via_door=False),    # 벽만 — 걸러야 한다
           AdjPair("R2", "R3", via_door=True)]     # 문 — 판정해야 한다 (NC↔D = 2단계)
    v = adj_001.evaluate(adj, rooms, CFG)
    assert [x["rooms"] for x in v] == [["R2", "R3"]]
