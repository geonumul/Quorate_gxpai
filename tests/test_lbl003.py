# -*- coding: utf-8 -*-
"""LBL-003 — 같은 방번호가 서로 다른 두 방에 붙어 있다. 신규 (2026-07-14).

## 이 규칙은 **감지기를 만들다가 발견됐다**

방번호 충돌을 세는 코드를 넣자마자 **기준 시설에서 2건**이 나왔다.
그 전까지 `_merge` 가 한쪽을 **조용히 덮어썼다** — 예외도 로그도 0건도 아니었다.

    3203  '샤워실(남)A'  ↔ '샤워실(남)A'       8,896mm 떨어짐
    4504  '(N)타정4실'   ↔ '(N)타정2실 전실'   6,025mm 떨어짐

두 라벨 모두 각자의 방 이름에서 250mm 거리 — **둘 다 정상적인 방 라벨이다.**
같은 방에 번호를 두 번 쓴 게 아니라, **서로 다른 두 방이 같은 번호를 달고 있다.**

45xx 번호대에서 **4507 이 통째로 비어 있다** → 설계사 번호 오기로 **보인다**.
그러나 **단정하지 않는다.** 우리는 사실만 보고하고 발주처에 묻는다.
"""
from __future__ import annotations

from gxpai.compliance.checks import lbl_003

CFG = {"enabled": True, "different_room_min_dist_mm": 3000}


def test_서로_다른_두_방이_같은_번호면_위반이다():
    """★기준 시설의 실제 4504 케이스."""
    v = lbl_003.evaluate([{
        "room_no": "4504",
        "lost_name": "(N)타정4실", "lost_floor": "4F", "lost_x": 560842, "lost_y": 37279,
        "kept_name": "(N)타정2실 전실", "kept_floor": "4F", "kept_x": 557495, "kept_y": 42290,
        "dist_mm": 6025.0,
    }], CFG)
    assert len(v) == 1
    assert v[0]["rooms"] == ["4504"]
    assert "타정4실" in v[0]["message"]
    # ★사라진 방은 **검사조차 안 된다** — 이게 이 규칙의 요점이다
    assert "검사" in v[0]["message"]
    assert "발주처" in v[0]["evidence"]["판단"]


def test_같은_방에_라벨이_두번이면_결함이_아니다():
    """도면에 번호를 두 번 쓴 것뿐이다. 거짓 위반을 내면 안 된다."""
    assert lbl_003.evaluate([{
        "room_no": "3101", "lost_name": "타정실", "kept_name": "타정실",
        "lost_x": 0, "lost_y": 0, "kept_x": 500, "kept_y": 0,
        "dist_mm": 500.0,                    # 50cm — 같은 방이다
    }], CFG) == []


def test_거리를_모르면_판정하지_않는다():
    """★`dist_mm=None` 은 **'거리가 0' 이 아니라 '모른다'** 이다.

    모르는 걸 결함으로 바꾸면 안 된다. (`[]` vs `None` 함정과 같은 종류 —
    이 프로젝트에서 다섯 번 넘게 밟았다)"""
    assert lbl_003.evaluate([{
        "room_no": "3101", "lost_name": "타정실", "kept_name": "포장실",
        "lost_x": None, "lost_y": None, "kept_x": None, "kept_y": None,
        "dist_mm": None,
    }], CFG) == []


def test_이름이_같아도_다른_방이면_위반이다():
    """★기준 시설의 실제 3203 케이스 — 두 방 다 '샤워실(남)A' 다.
    이름이 같다고 넘기면 안 된다. **8.9m 떨어진 서로 다른 방**이다."""
    v = lbl_003.evaluate([{
        "room_no": "3203", "lost_name": "샤워실(남)A", "kept_name": "샤워실(남)A",
        "lost_x": 464914, "lost_y": 44518, "kept_x": 469642, "kept_y": 36983,
        "dist_mm": 8896.0,
    }], CFG)
    assert len(v) == 1
    assert v[0]["evidence"]["이름도_같은가"] is True


def test_충돌이_없으면_위반이_없다():
    assert lbl_003.evaluate([], CFG) == []


def test_게이트가_꺼져_있으면_돌지_않는다():
    """`enabled: false` 면 아무것도 안 한다(동결 게이트)."""
    assert lbl_003.run(None, "run1", "f1", {"config": {"enabled": False}}) == []
