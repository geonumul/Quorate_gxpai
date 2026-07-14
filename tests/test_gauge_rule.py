# -*- coding: utf-8 -*-
"""PRES-005 — **청정실 경계에 차압계가 없다** 회귀 시험.

## 조문

    고시 별표1 제4호 너목
      "**청정실 및 필요한 경우 아이솔레이터와 주변구역 사이에 차압계가 설치되어야 한다.**
       … 중요하다고 확인된 차압은 **연속적으로 모니터하고 기록**하여야 한다."

차압을 설정만 하고 **재지 않으면 유지, 기록할 방법이 없다.** 그래서 차압계가 의무다.

## 이 파일이 지키는 가장 중요한 것: **범위를 좁히지 않으면 거짓 위반 6건이 난다**

실제 도면에서 차압이 설정됐는데 차압계가 없는 구간이 **6개** 나왔다.
그런데 파 보니 **전부 CNC↔NC** 였다 — 탈의실, 갱의실, 전실(갱의 체인 입구)이다.

    조문은 "**청정실** 및 … 주변구역 사이"라고 한다.
    CNC(관리되나 등급 미분류), NC(미분류)는 **청정실이 아니다.**

→ 한쪽 이상이 청정실(D 이상)인 구간만 판정한다. 그러고 나니 **위반 0건 — 설계가 맞았다.**
  범위를 느슨하게 잡았으면 **멀쩡한 설계에 거짓 위반 6건**을 냈을 것이다.
"""
from __future__ import annotations

from gxpai.compliance.checks import pres_005
from gxpai.compliance.checks._model import PressureRel, RoomView

CFG = {"enabled": True, "clean_min_rank": 2,
       "grade_rank": {"A": 5, "B": 4, "C": 3, "D": 2, "CNC": 1, "NC": 0}}


def test_청정실_경계에_차압계가_없으면_위반():
    rooms = [RoomView(room_no="C1", name="무균 조제실", grade="B"),
             RoomView(room_no="G1", name="청정 복도", grade="C")]
    rels = [PressureRel(room_high_no="C1", room_low_no="G1",
                        setpoint_pa=15.0, has_gauge=False, layer="Air Flow 15Pa")]
    v = pres_005.evaluate(rels, rooms, CFG)
    assert len(v) == 1
    assert "차압계가 설치되어야 한다" in v[0]["evidence"]["원문"]


def test_차압계가_있으면_위반_아님():
    rooms = [RoomView(room_no="C1", name="무균 조제실", grade="B"),
             RoomView(room_no="G1", name="청정 복도", grade="C")]
    rels = [PressureRel(room_high_no="C1", room_low_no="G1",
                        setpoint_pa=15.0, has_gauge=True, gauge_kind="디지털")]
    assert pres_005.evaluate(rels, rooms, CFG) == []


def test_CNC와_NC_사이는_조문_대상이_아니다():
    """핵심. 이걸 안 걸렀으면 멀쩡한 설계에 **거짓 위반 6건**이 났다.

    실제 도면의 6건이 전부 이 모양이었다 — 탈의실, 갱의실, 전실(갱의 체인 입구).
    조문은 '**청정실** 및 … 주변구역 사이'라고 한다. CNC, NC 는 청정실이 아니다.
    """
    rooms = [RoomView(room_no="G1", name="갱의실 (남) 2", grade="CNC"),
             RoomView(room_no="T1", name="탈의실 (남) 2", grade="NC")]
    rels = [PressureRel(room_high_no="G1", room_low_no="T1",
                        setpoint_pa=10.0, has_gauge=False, layer="Air Flow 10Pa")]
    assert pres_005.evaluate(rels, rooms, CFG) == []

    # 한쪽만 청정실(D)이 되면 대상이 된다
    rooms2 = [RoomView(room_no="G1", name="갱의실 (남) 2", grade="D"),
              RoomView(room_no="T1", name="탈의실 (남) 2", grade="NC")]
    assert len(pres_005.evaluate(rels, rooms2, CFG)) == 1


def test_도면이_차압계_불필요라_한_구간은_대상이_아니다():
    """`Air Flow no차압` = "기류흐름 및 차압계 설치가 요구되지 않는 위치" (도면 범례 3번).

    설정값이 없으면 지킬 기준도 없다. 위반으로 찍으면 안 된다.
    """
    rooms = [RoomView(room_no="C1", name="무균 조제실", grade="B"),
             RoomView(room_no="G1", name="청정 복도", grade="C")]
    rels = [PressureRel(room_high_no="C1", room_low_no="G1",
                        setpoint_pa=None, has_gauge=False, layer="Air Flow no차압")]
    assert pres_005.evaluate(rels, rooms, CFG) == []


def test_차압계_도면이_없는_시설은_판정하지_않는다():
    """`has_gauge=None` = "차압계 정보가 없다" 이지 **"차압계가 없다"가 아니다.**

    혼동하면 **전 구간이 거짓 위반**이 된다.
    (`rels=[]` vs `rels=None`, `door_pairs=[]` vs `None` — 같은 함정을 세 번째 만난다)
    """
    rooms = [RoomView(room_no="C1", name="무균 조제실", grade="B"),
             RoomView(room_no="G1", name="청정 복도", grade="C")]
    rels = [PressureRel(room_high_no="C1", room_low_no="G1",
                        setpoint_pa=15.0, has_gauge=None)]
    assert pres_005.evaluate(rels, rooms, CFG) == []


def test_방_귀속_안된_화살표는_건너뛴다():
    rooms = [RoomView(room_no="C1", name="무균 조제실", grade="B")]
    rels = [PressureRel(room_high_no=None, room_low_no=None, approx=True,
                        setpoint_pa=15.0, has_gauge=False)]
    assert pres_005.evaluate(rels, rooms, CFG) == []
