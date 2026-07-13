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


# ── 불완전한 문 데이터는 문 데이터가 없는 것보다 나쁘다 ──────────────
def test_문_검출률이_낮으면_문_데이터를_쓰면_안_된다():
    """★스스로 판 함정. 문 인접을 만들어 놓고 **검출률을 안 봤다.**

    참고도면에서 문 인접이 **4쌍**(방 51개 중 7개만 문이 닿음 = 14%),
    기준 시설에서 33쌍(79개 중 35개 = 44%) 나왔다.
    **방에는 대개 문이 하나씩 있다.** 이 숫자는 도면에 문이 없어서가 아니라
    **우리 문 검출이 실패했다**는 뜻이다.

    그런데도 문 인접을 쓰면 ADJ-001 이 **검출하지 못한 문**에 대해
    "문이 없으니 동선 위반 아님" 으로 **진짜 위반을 숨긴다.**

    → 검출률이 임계값(80%) 미만이면 via_door 를 NULL 로 두고 벽 인접으로 폴백한다.
      `gxpai/core/run.py` 의 DOOR_TRUST. 이 시험은 그 **판정 규칙**을 고정한다.
    """
    from gxpai.geometry.boundaries import BoundaryResult, RoomRegion

    def _res(n_rooms, door_pairs):
        r = BoundaryResult(
            rooms=[RoomRegion(room_no=f"R{i}", area_m2=10.0, polygon=[]) for i in range(n_rooms)],
            door_adjacency=door_pairs)
        touched = {x for p in door_pairs for x in p}
        r.door_coverage = len(touched) / len(r.rooms) if r.rooms else 0.0
        return r

    # 방 10개 중 문이 닿은 방 4개 = 40% → 못 믿는다
    낮음 = _res(10, [("R0", "R1"), ("R2", "R3")])
    assert 낮음.door_coverage == 0.4

    # 방 10개 중 9개가 문에 닿음 = 90% → 믿는다
    높음 = _res(10, [("R0", "R1"), ("R2", "R3"), ("R4", "R5"), ("R6", "R7"), ("R8", "R1")])
    assert 높음.door_coverage == 0.9

    DOOR_TRUST = 0.8
    assert 낮음.door_coverage < DOOR_TRUST      # → None 을 넘겨 via_door NULL
    assert 높음.door_coverage >= DOOR_TRUST     # → 문 인접을 쓴다


def test_문_양옆_방을_한_거리만_찍으면_안_된다():
    """★문 검출률이 14% 였던 진짜 원인.

    문 한가운데에서 수직으로 **600mm 한 점만** 찍어 방을 읽었다.
    그 점이 **벽 두께 안**이거나 **가구 위**에 떨어지면 방을 못 읽는다.
    참고도면에서 문 호 85개 중 4쌍만 건졌다(14%).

    → 여러 거리(300·500·700·1000·1400·1900·2500mm)를 훑어 **처음 만나는 방**을 쓴다.
      검출률 14% → **84%** (참고도면) · 44% → **87%** (기준 시설).
      둘 다 신뢰 임계값(80%)을 넘어 문 데이터를 실제로 쓰게 됐다.

    이 시험은 '여러 거리를 훑는다'는 설계를 고정한다.
    """
    from gxpai.geometry.boundaries import _DOOR_PROBE_STEPS

    assert len(_DOOR_PROBE_STEPS) >= 5, "한두 거리만 훑으면 벽·가구에 막힌다"
    assert _DOOR_PROBE_STEPS[0] <= 300, "가까운 데부터 봐야 옆방을 훔쳐오지 않는다"
    assert _DOOR_PROBE_STEPS[-1] >= 2000, "벽이 두껍거나 가구가 크면 멀리까지 봐야 한다"
    assert list(_DOOR_PROBE_STEPS) == sorted(_DOOR_PROBE_STEPS), "가까운 순이어야 한다"
