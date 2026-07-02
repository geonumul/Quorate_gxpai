# -*- coding: utf-8 -*-
"""LBL-002 - 방번호가 도면 간 불일치 (한 도면에만 존재).

같은 번호방이 평면도·차압도 중 한쪽에만 있으면 도면 정합성 경고.
(v0.1: 평면도 96 ∩ 차압도 112 = 94 매칭, 나머지는 한쪽에만 존재)
판정: plan_x 유무 = 평면도 존재, pressure_name 유무 = 차압도 존재.
"""
from __future__ import annotations


def run(cur, run_id, facility_id, rule) -> list[dict]:
    cur.execute(
        """SELECT room_no, name, plan_x, pressure_name FROM room
           WHERE run_id=%s AND room_no IS NOT NULL""",
        (run_id,),
    )
    out = []
    for room_no, name, plan_x, pname in cur.fetchall():
        in_floor = plan_x is not None
        in_pres = pname is not None
        if in_floor and not in_pres:
            out.append({
                "severity": "minor", "rooms": [room_no],
                "message": f"방번호 {room_no}('{name}'): 평면도에만 있고 차압도에 없음",
                "evidence": {"in": "floorplan_only", "name": name},
            })
        elif in_pres and not in_floor:
            out.append({
                "severity": "minor", "rooms": [room_no],
                "message": f"방번호 {room_no}('{pname}'): 차압도에만 있고 평면도에 없음",
                "evidence": {"in": "pressure_only", "name": pname},
            })
    return out
