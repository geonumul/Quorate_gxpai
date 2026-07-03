# -*- coding: utf-8 -*-
"""차압 화살표 ↔ 방 귀속 (관찰된 기하만; 압력 해석은 하지 않음).

로드맵: T2.1 후속. docs/기존데이터_분석.md 가설 2·3의 우회로를 파이프라인에 반영.

각 화살표에 대해 차압도 방 라벨(같은 좌표계) 중 화살촉이 향하는 쪽(head)과 꼬리 쪽(tail)을
찾아 pressure_relation.room_head / room_tail 에 저장한다. 이것은 도면에서 읽은 사실이다.

'어느 방이 고압인가'는 화살표 의미(S-1)가 확정돼야 정해지는 해석이므로 여기서 하지 않는다.
room_high/room_low 는 계속 NULL 로 둔다(발주처 확인 후 채움). 우리 잠정 추정은 head=저압이지만
확정이 아니며, 이 모듈은 그 추정을 데이터에 반영하지 않는다.

구조: associate() 는 순수 함수(DB 무관, 합성 시험 대상), build() 는 DB 어댑터.
화살표 기하(S-1 확정): rotation=0 에서 화살촉 -y, 세계각도 = 270° + rotation.
"""
from __future__ import annotations

import math

from ..core.db import connect

MAX_DIST = 6000.0   # 방 라벨 탐색 반경(mm)
MAX_LAT = 3500.0    # 화살표 축에서 벗어난 측면거리 허용(mm)


def head_vector(rotation_deg: float) -> tuple[float, float]:
    th = math.radians(270.0 + rotation_deg)
    return math.cos(th), math.sin(th)


def associate_one(ax: float, ay: float, rotation_deg: float,
                  rooms: list[tuple], max_dist: float = MAX_DIST,
                  max_lat: float = MAX_LAT):
    """화살표 하나에 대해 (tail_key, head_key) 반환. 못 붙이면 (None, None).

    rooms: (key, x, y) 목록. key 는 room_no(테스트) 또는 room id(DB) 무엇이든 됨.
    head = 화살촉이 향하는 쪽(투영 +), tail = 꼬리 쪽(투영 -).
    """
    hx, hy = head_vector(rotation_deg)
    head_key = tail_key = None
    head_s = tail_s = None
    for key, rx, ry in rooms:
        if rx is None or ry is None:
            continue
        dx, dy = rx - ax, ry - ay
        if math.hypot(dx, dy) > max_dist:
            continue
        if abs(dx * -hy + dy * hx) > max_lat:   # 측면거리(축 수직 성분)
            continue
        proj = dx * hx + dy * hy
        if proj > 0 and (head_s is None or proj > head_s):
            head_key, head_s = key, proj
        elif proj < 0 and (tail_s is None or -proj > tail_s):
            tail_key, tail_s = key, -proj
    if head_key is not None and tail_key is not None and head_key != tail_key:
        return tail_key, head_key
    return None, None


def build(run_id: str) -> int:
    """pressure_relation 각 화살표에 room_head/room_tail 을 채운다. 귀속 성공 수 반환."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT id, pres_x, pres_y FROM room
               WHERE run_id=%s AND room_no IS NOT NULL
                     AND pres_x IS NOT NULL AND pres_y IS NOT NULL""",
            (run_id,),
        )
        rooms = [(r[0], r[1], r[2]) for r in cur.fetchall()]

        cur.execute(
            "SELECT id, evidence_x, evidence_y, rotation FROM pressure_relation WHERE run_id=%s",
            (run_id,),
        )
        arrows = cur.fetchall()  # (id, ex, ey, rot)

        n = 0
        for pr_id, ex, ey, rot in arrows:
            tail_id, head_id = associate_one(ex, ey, rot or 0.0, rooms)
            # room_high/room_low 는 건드리지 않는다(해석 - 발주처 확인 전 금지).
            cur.execute(
                "UPDATE pressure_relation SET room_head=%s, room_tail=%s WHERE id=%s",
                (head_id, tail_id, pr_id),
            )
            if head_id is not None and tail_id is not None:
                n += 1
        conn.commit()
        return n
