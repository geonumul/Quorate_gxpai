# -*- coding: utf-8 -*-
"""부대구역 규칙(ADJ-003 화장실, ADJ-004 휴게실, 식당) 회귀 시험.

## 왜 합성 데이터인가 - "데이터가 없어서 못 한다"는 답을 금지한다

두 도면 다 **화장실이 없다**(기준 시설, 참고도면 모두 0개).
휴게실은 기준 시설에 2개 있으나 **차압도에만 있고 평면도에 없어** 좌표가 없다.

그렇다고 규칙을 안 만들면, 도면이 왔을 때 처음부터 시작해야 한다.
→ **로직은 합성 데이터로 완성해 둔다.** 실데이터가 오면 그날 바로 켜진다.

## 이 조문들이 특별한 이유

GMP 조문 대부분은 "가급적", "적절히", "타당한" 으로 여지를 남긴다. 그래서 우리가 혼자
판정하면 안 되고 대부분 보류로 둔다. **그런데 이 둘은 다르다.**

    별표17 3.6 나목: "화장실은 작업소 또는 보관소와 **직접 연결되지 아니하여야 한다**"  ← 금지
    별표17 3.6 가목: "휴게실과 식당은 다른 구역과 **분리**되어 있어야 한다"              ← 의무

도면만으로 판정할 수 있는 몇 안 되는 조문이다.
(법제처 HWP, 고시 XML, 식약처 PDF 세 출처에서 원문 대조 확인)
"""
from __future__ import annotations

from gxpai.compliance.checks import adj_003, adj_004
from gxpai.compliance.checks._model import AdjPair, RoomView

CFG = {"enabled": True}


# ── ADJ-003: 화장실 직접 연결 금지 ────────────────────────────────
def test_화장실이_작업소와_문으로_이어지면_위반():
    rooms = [RoomView(room_no="T1", name="화장실"),
             RoomView(room_no="P1", name="타정1실", grade="D")]
    v = adj_003.evaluate([AdjPair("T1", "P1", via_door=True)], rooms, CFG)
    assert len(v) == 1
    assert v[0]["evidence"]["target_kind"] == "작업소"
    assert "직접 연결되지 아니하여야" in v[0]["evidence"]["원문"]


def test_화장실이_보관소와_문으로_이어지면_위반():
    rooms = [RoomView(room_no="T1", name="화장실(남)"),
             RoomView(room_no="S1", name="원료 보관실")]
    v = adj_003.evaluate([AdjPair("T1", "S1", via_door=True)], rooms, CFG)
    assert len(v) == 1 and v[0]["evidence"]["target_kind"] == "보관소"


def test_화장실이_복도를_거치면_위반이_아니다():
    """조문은 '**직접** 연결'을 금지한다. 복도를 거치면 직접이 아니다.

    이걸 놓치면 거의 모든 화장실이 위반으로 찍힌다 - 화장실은 원래 복도에 붙어 있다.
    """
    rooms = [RoomView(room_no="T1", name="화장실"),
             RoomView(room_no="C1", name="복도"),
             RoomView(room_no="P1", name="타정1실", grade="D")]
    adj = [AdjPair("T1", "C1", via_door=True),      # 화장실 → 복도
           AdjPair("C1", "P1", via_door=True)]      # 복도 → 작업소
    assert adj_003.evaluate(adj, rooms, CFG) == []


def test_화장실이_갱의실과_붙은_것은_정상():
    """부대구역끼리 붙는 건 오히려 자연스럽다(작업원이 옷 갈아입기 전에 들른다)."""
    rooms = [RoomView(room_no="T1", name="화장실"),
             RoomView(room_no="G1", name="갱의실(남)"),
             RoomView(room_no="S1", name="샤워실(남)")]
    adj = [AdjPair("T1", "G1", via_door=True), AdjPair("T1", "S1", via_door=True)]
    assert adj_003.evaluate(adj, rooms, CFG) == []


def test_벽만_맞댄_화장실은_위반이_아니다():
    """'직접 연결' = **문으로 이어짐**이다. 벽을 맞댄 것은 연결이 아니다.

    벽 맞댐으로 판정하면 '벽 하나 사이의 화장실'을 전부 위반으로 찍는다 - 거짓 위반이다.
    """
    rooms = [RoomView(room_no="T1", name="화장실"),
             RoomView(room_no="P1", name="타정1실", grade="D")]
    assert adj_003.evaluate([AdjPair("T1", "P1", via_door=False)], rooms, CFG) == []


def test_문_정보가_없는_도면에서는_아무것도_판정하지_않는다():
    """via_door 가 전부 NULL = 문 데이터를 못 믿는 도면.

    이때 벽 인접으로 대신 판정하면 거짓 위반이 쏟아진다.
    **모른다고 추측하지 않는다. 아무것도 내지 않는다.**
    """
    rooms = [RoomView(room_no="T1", name="화장실"),
             RoomView(room_no="P1", name="타정1실", grade="D")]
    assert adj_003.evaluate([AdjPair("T1", "P1", via_door=None)], rooms, CFG) == []


def test_분진공정실도_작업소다_등급이_없어도():
    """기준 시설 도면에는 **등급 표기가 0건**이다. 등급만 보면 작업소를 하나도 못 찾는다.

    → 분진, 특수 공정실(regime = contain/hazard)도 작업소로 본다.
    """
    rooms = [RoomView(room_no="T1", name="화장실"),
             RoomView(room_no="P1", name="(N)칭량1실")]     # 등급 없음. 이름으로 contain
    v = adj_003.evaluate([AdjPair("T1", "P1", via_door=True)], rooms, CFG)
    assert len(v) == 1 and v[0]["evidence"]["target_kind"] == "작업소"


def test_대기실은_작업소가_아니다():
    """`칭량 전 원료대기실` 은 머리말이 '대기실' 이라 공정실이 아니다(_regime 참조).

    화장실이 대기실 옆에 있는 건 위반이 아니다.
    """
    rooms = [RoomView(room_no="T1", name="화장실"),
             RoomView(room_no="W1", name="(N)칭량 전 원료대기실")]
    assert adj_003.evaluate([AdjPair("T1", "W1", via_door=True)], rooms, CFG) == []


# ── ADJ-004: 휴게실, 식당 분리 ─────────────────────────────────────
def test_휴게실이_작업소와_문으로_이어지면_위반():
    rooms = [RoomView(room_no="R1", name="휴게실"),
             RoomView(room_no="P1", name="(N)타정1실")]
    v = adj_004.evaluate([AdjPair("R1", "P1", via_door=True)], rooms, CFG)
    assert len(v) == 1
    assert "분리되어 있어야" in v[0]["evidence"]["원문"]
    # '분리' 는 '구획' 보다 강하다 - 별도 공조까지 요구한다. 근거에 남긴다.
    assert "별도 공조" in v[0]["evidence"]["분리의_뜻"]


def test_식당도_같은_규칙():
    rooms = [RoomView(room_no="R1", name="구내식당"),
             RoomView(room_no="S1", name="자재 보관실")]
    v = adj_004.evaluate([AdjPair("R1", "S1", via_door=True)], rooms, CFG)
    assert len(v) == 1 and v[0]["evidence"]["target_kind"] == "보관소"


def test_휴게실과_화장실이_붙은_것은_정상():
    rooms = [RoomView(room_no="R1", name="휴게실"),
             RoomView(room_no="T1", name="화장실"),
             RoomView(room_no="C1", name="복도")]
    adj = [AdjPair("R1", "T1", via_door=True), AdjPair("R1", "C1", via_door=True)]
    assert adj_004.evaluate(adj, rooms, CFG) == []


def test_휴게실_위반_0건은_분리_확인이_아니다():
    """가장 중요한 한계. **'분리 아님'은 증명할 수 있어도 '분리 맞음'은 증명할 수 없다.**

    조문의 '분리'는 **별도 공조**까지 요구한다(2010 안내서 p.25).
    우리는 도면에서 '문으로 이어짐'만 본다. 공조 계통은 모른다.
    → 위반 0건이어도 "분리 확인됨"이라고 쓰면 **거짓말**이다.
    이 시험은 근거에 그 한계가 반드시 적히는지 고정한다.
    """
    rooms = [RoomView(room_no="R1", name="휴게실"),
             RoomView(room_no="P1", name="(N)타정1실")]
    v = adj_004.evaluate([AdjPair("R1", "P1", via_door=True)], rooms, CFG)
    assert "별도 공조인지는 공조 계통도가 있어야" in v[0]["evidence"]["한계"]
    assert v[0]["evidence"]["판단"].startswith("보류")
