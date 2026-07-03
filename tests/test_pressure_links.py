# -*- coding: utf-8 -*-
"""화살표 ↔ 방 귀속 순수 로직 시험 (DB 없이).

관찰된 기하만 검증한다: 화살촉이 향하는 방(head)과 꼬리 쪽 방(tail)을 옳게 찾는지.
'어느 쪽이 고압인지'라는 해석은 이 모듈이 하지 않으므로 시험도 하지 않는다.
"""
from __future__ import annotations

from gxpai.geometry.pressure_links import associate_one, head_vector


def _close(v, target):
    return abs(v - target) < 1e-9


def test_head_vector_all_quadrants():
    # 세계각도 = 270° + rotation. 블록이 회전하면 화살촉도 같이 돈다.
    hx, hy = head_vector(0.0)     # 270° → -y(아래)
    assert _close(hx, 0.0) and _close(hy, -1.0)
    hx, hy = head_vector(90.0)    # 360°=0° → +x(오른쪽)
    assert _close(hx, 1.0) and _close(hy, 0.0)
    hx, hy = head_vector(180.0)   # 450°=90° → +y(위)
    assert _close(hx, 0.0) and _close(hy, 1.0)
    hx, hy = head_vector(270.0)   # 540°=180° → -x(왼쪽)
    assert _close(hx, -1.0) and _close(hy, 0.0)


def test_associate_rotation_90_points_right():
    # rotation=90 → 화살촉 +x. 오른쪽 방=head, 왼쪽 방=tail.
    rooms = [("L", -2000.0, 0.0), ("R", 2000.0, 0.0)]
    tail, head = associate_one(0.0, 0.0, 90.0, rooms)
    assert tail == "L" and head == "R"


def test_associate_rotation_270_points_left():
    rooms = [("L", -2000.0, 0.0), ("R", 2000.0, 0.0)]
    tail, head = associate_one(0.0, 0.0, 270.0, rooms)
    assert tail == "R" and head == "L"


def test_associate_arbitrary_rotation_45():
    # rotation=45 → 세계각도 315° → 화살촉 (+x,-y) 대각. 그 방향 방이 head.
    rooms = [("NW", -1500.0, 1500.0), ("SE", 1500.0, -1500.0)]
    tail, head = associate_one(0.0, 0.0, 45.0, rooms)
    assert tail == "NW" and head == "SE"


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


def test_picks_nearest_room_not_farthest_each_side():
    # 화살촉 방향(-y)에 방이 둘: 가까운 것(near)과 먼 것(far, 원뿔 안). 가까운 방이 head 여야.
    rooms = [("up", 0.0, 1500.0),          # tail 쪽(가까움)
             ("near", 500.0, -1500.0),     # head 쪽 가까움(측면 500)
             ("far", 0.0, -5500.0)]        # head 쪽 멀리(반경 6000 이내)
    tail, head = associate_one(0.0, 0.0, 0.0, rooms)
    assert head == "near" and tail == "up"


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
