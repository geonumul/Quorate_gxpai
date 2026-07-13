# -*- coding: utf-8 -*-
"""LBL-002 - 방번호가 도면 간 불일치 (한 도면에만 존재).

같은 번호방이 평면도·차압도 중 한쪽에만 있으면 도면 정합성 경고.
(v0.1: 평면도 96 ∩ 차압도 112 = 94 매칭, 나머지는 한쪽에만 존재)
판정: plan_x 유무 = 평면도 존재, pressure_name 유무 = 차압도 존재.

구조: evaluate() 는 순수 함수(DB 무관, 합성 시험 대상), run() 은 얇은 DB 어댑터.
"""
from __future__ import annotations

from ._model import RoomView, load_rooms


def evaluate(rooms: list[RoomView]) -> list[dict]:
    """평면도·차압도 한쪽에만 존재하는 번호방을 위반으로 반환."""
    out = []
    for r in rooms:
        if not r.room_no:
            continue
        # ★**'차압도에 있는가'는 좌표로 판단한다.** 예전엔 `pressure_name` 유무로 봤다.
        #   차압도에 방번호만 있고 **이름이 없는** 도면(참고도면 2층)에서
        #   51개 방을 전부 '차압도에 없음'으로 찍었다 — **거짓 위반 51건**.
        #   (게다가 LBL 은 review: internal 이라 게이트가 열려 있어 **DB에 실제로 적재됐다**)
        #
        #   이름이 없는 것과 방이 없는 것은 **다르다.** 이름 불일치는 LBL-001 이 따로 본다.
        #   pres_x 가 없는 옛 데이터는 pressure_name 으로 폴백한다(하위호환).
        in_floor = r.plan_x is not None
        in_pres = (r.pres_x is not None) if r.pres_x is not None             else (r.pressure_name is not None)
        if in_floor and not in_pres:
            out.append({
                "severity": "minor", "rooms": [r.room_no],
                "message": f"방번호 {r.room_no}('{r.name}'): 평면도에만 있고 차압도에 없음",
                "evidence": {"in": "floorplan_only", "name": r.name},
            })
        elif in_pres and not in_floor:
            out.append({
                "severity": "minor", "rooms": [r.room_no],
                "message": f"방번호 {r.room_no}('{r.pressure_name}'): 차압도에만 있고 평면도에 없음",
                "evidence": {"in": "pressure_only", "name": r.pressure_name},
            })
    return out


def run(cur, run_id, facility_id, rule) -> list[dict]:
    return evaluate(load_rooms(cur, run_id))
