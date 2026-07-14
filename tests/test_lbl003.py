# -*- coding: utf-8 -*-
"""LBL-003 - 같은 방번호가 서로 다른 두 방에 붙어 있다. 신규 (2026-07-14).

방번호 충돌을 세는 코드를 넣자마자 기준 시설에서 2건이 나왔다.
그 전까지 `_merge` 가 한쪽을 조용히 덮어썼다. 예외도 로그도 0건도 아니었다.

    3203  '샤워실(남)A'  vs '샤워실(남)A'       8,896mm 떨어짐
    4504  '(N)타정4실'   vs '(N)타정2실 전실'   6,025mm 떨어짐

두 사건의 성격이 다르다는 게 핵심이다.

    4504 - 차압도가 정답을 갖고 있다. '(N)타정4실' 을 4507 이라 부르고,
           4507 은 평면도에 아예 없다. 평면도가 4504 를 잘못 적은 것이다.
    3203 - 32xx 에 빈 번호가 없고 차압도도 다른 번호를 말하지 않는다.
           어느 쪽이 잘못됐는지 알 수 없다. 그렇게 보고한다.

근거가 있으면 근거를 대고, 없으면 없다고 말한다. 지어내지 않는다.
"""
from __future__ import annotations

from gxpai.compliance.checks import lbl_003
from gxpai.compliance.checks._model import RoomView

CFG = {"enabled": True, "different_room_min_dist_mm": 3000}


def _conflict(no, lost, kept, dist):
    return {"room_no": no, "lost_name": lost, "kept_name": kept,
            "lost_floor": "4F", "kept_floor": "4F",
            "lost_x": 0.0, "lost_y": 0.0, "kept_x": dist, "kept_y": 0.0,
            "dist_mm": dist}


# 기준 시설 45xx 를 그대로 옮긴 것. 4507 은 차압도에만 있다(plan_x=None).
ROOMS_45 = [
    RoomView(room_no="4503", name="(N)타정2실", pressure_name="(N)타정2실", plan_x=1.0),
    RoomView(room_no="4504", name="(N)타정2실 전실",
             pressure_name="(N)타정2실 전실", plan_x=2.0),
    RoomView(room_no="4505", name="(N)타정3실", pressure_name="(N)타정3실", plan_x=3.0),
    RoomView(room_no="4506", name="(N)타정3실 전실",
             pressure_name="(N)타정3실 전실", plan_x=4.0),
    # 평면도에 없다. 차압도만 안다. 평면도가 이 방에 4504 를 붙여 버렸기 때문이다.
    RoomView(room_no="4507", name="(N)타정4실", pressure_name="(N)타정4실", plan_x=None),
    RoomView(room_no="4508", name="(N)타정4실 전실",
             pressure_name="(N)타정4실 전실", plan_x=5.0),
]


def test_차압도가_원래_번호를_알려주면_그걸_짚어준다():
    """기준 시설의 실제 4504 사건.

    평면도는 '(N)타정4실' 에 4504 를 붙였고, 차압도는 같은 방을 4507 이라 부른다.
    4507 은 평면도에 없다. 두 도면을 대조하면 어느 쪽이 틀렸는지 나온다.
    """
    v = lbl_003.evaluate(
        [_conflict("4504", "(N)타정4실", "(N)타정2실 전실", 6025.0)], ROOMS_45, CFG)

    assert len(v) == 1
    msg = v[0]["message"]
    assert "4507" in msg, "차압도가 알려주는 번호를 메시지에 안 썼다"
    assert "잘못 적은 것으로 보인다" in msg
    ev = v[0]["evidence"]
    assert ev["차압도가_말하는_번호"] == {"방이름": "(N)타정4실", "차압도_번호": "4507"}
    assert "발주처" in ev["판단"], "확정은 우리가 하지 않는다"


def test_사라지는_방은_검사조차_못_받는다는_걸_말한다():
    """이 규칙의 요점. 덮어써진 방은 DB 에 없으니 아무 검사도 못 받는데
    리포트에는 '위반 없음'으로 보인다."""
    v = lbl_003.evaluate(
        [_conflict("4504", "(N)타정4실", "(N)타정2실 전실", 6025.0)], ROOMS_45, CFG)
    assert "검사를 아예 받지 못한다" in v[0]["message"]


def test_근거가_없으면_없다고_말한다():
    """기준 시설의 실제 3203 사건.

    32xx 는 3201~3206 이 빈틈없이 차 있고, 차압도도 3203 을 하나만 안다.
    어느 쪽이 잘못됐는지 도면만으로는 알 수 없다. 지어내지 않는다.
    """
    rooms = [RoomView(room_no=f"320{i}", name=f"방{i}",
                      pressure_name=f"방{i}", plan_x=float(i)) for i in range(1, 7)]
    v = lbl_003.evaluate(
        [_conflict("3203", "샤워실(남)A", "샤워실(남)A", 8896.0)], rooms, CFG)

    assert len(v) == 1
    assert "알 수 없다" in v[0]["message"]
    assert v[0]["evidence"]["번호대_빈자리"] == []
    assert v[0]["evidence"]["차압도가_말하는_번호"] is None


def test_차압도가_없어도_번호대_빈자리는_근거가_된다():
    """차압도를 못 받은 시설이면 교차검증은 못 한다.
    그래도 번호대에 빈자리가 있으면 그건 말해 줄 수 있다."""
    rooms = [
        RoomView(room_no="4503", name="가", plan_x=1.0),
        RoomView(room_no="4504", name="나", plan_x=2.0),
        RoomView(room_no="4506", name="다", plan_x=3.0),   # 4505 가 비었다
    ]
    v = lbl_003.evaluate([_conflict("4504", "가방", "나방", 6000.0)], rooms, CFG)
    assert v[0]["evidence"]["번호대_빈자리"] == ["4505"]
    assert "4505" in v[0]["message"]


def test_같은_방에_라벨이_두번이면_결함이_아니다():
    """도면에 번호를 두 번 쓴 것뿐이다. 거짓 위반을 내면 안 된다."""
    assert lbl_003.evaluate(
        [_conflict("3101", "타정실", "타정실", 500.0)], ROOMS_45, CFG) == []


def test_거리를_모르면_판정하지_않는다():
    """dist_mm=None 은 '거리가 0'이 아니라 '모른다'이다.
    모르는 걸 결함으로 바꾸지 않는다."""
    c = _conflict("3101", "타정실", "포장실", 6000.0)
    c["dist_mm"] = None
    assert lbl_003.evaluate([c], ROOMS_45, CFG) == []


def test_충돌이_없으면_위반이_없다():
    assert lbl_003.evaluate([], ROOMS_45, CFG) == []


def test_게이트가_꺼져_있으면_돌지_않는다():
    assert lbl_003.run(None, "run1", "f1", {"config": {"enabled": False}}) == []
