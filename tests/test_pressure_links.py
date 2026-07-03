# -*- coding: utf-8 -*-
"""화살표 ↔ 방 귀속 순수 로직 시험 (DB 없이).

관찰된 기하만 검증한다: 화살촉이 향하는 방(head)과 꼬리 쪽 방(tail)을 옳게 찾는지.
'어느 쪽이 고압인지'라는 해석은 이 모듈이 하지 않으므로 시험도 하지 않는다.
"""
from __future__ import annotations

from gxpai.geometry.pressure_links import associate_one, head_vector


def test_head_vector_down_at_zero():
    # rotation=0 → 화살촉 -y(아래). 세계각도 270°.
    hx, hy = head_vector(0.0)
    assert abs(hx) < 1e-9 and abs(hy + 1.0) < 1e-9


def test_associate_arrow_between_two_rooms():
    # 화살표는 (0,0), rotation=0 → 화살촉이 아래(-y)를 향함.
    # 아래쪽 방 = head, 위쪽 방 = tail.
    rooms = [("A_up", 0.0, 2000.0), ("B_down", 0.0, -2000.0)]
    tail, head = associate_one(0.0, 0.0, 0.0, rooms)
    assert tail == "A_up" and head == "B_down"


def test_rotation_flips_head_tail():
    # rotation=180 → 화살촉이 위(+y)를 향함. head/tail 이 뒤집힌다.
    rooms = [("A_up", 0.0, 2000.0), ("B_down", 0.0, -2000.0)]
    tail, head = associate_one(0.0, 0.0, 180.0, rooms)
    assert tail == "B_down" and head == "A_up"


def test_no_room_in_range_returns_none():
    rooms = [("far", 0.0, 99999.0)]
    assert associate_one(0.0, 0.0, 0.0, rooms) == (None, None)


def test_lateral_rooms_excluded():
    # 화살표 축(수직)에서 옆으로 크게 벗어난 방은 제외(측면거리 초과).
    rooms = [("side", 5000.0, -500.0)]
    assert associate_one(0.0, 0.0, 0.0, rooms) == (None, None)


def test_only_one_side_returns_none():
    # 머리쪽 방만 있고 꼬리쪽이 없으면 귀속 실패(둘 다 있어야 함).
    rooms = [("B_down", 0.0, -2000.0)]
    assert associate_one(0.0, 0.0, 0.0, rooms) == (None, None)
