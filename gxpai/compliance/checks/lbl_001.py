# -*- coding: utf-8 -*-
"""LBL-001 - 방번호-이름 라벨 불일치 (평면도 vs 차압도).

같은 방번호인데 평면도 이름과 차압도 이름이 다르면 위반. 정규화(공백/괄호/N/하이픈 제거)
후 비교하여 표기 차이만 있는 경우는 제외 (v0.1 로직 승계).

구조: evaluate() 는 순수 함수(DB 무관, 합성 시험 대상), run() 은 얇은 DB 어댑터.
"""
from __future__ import annotations

import re

from ._model import RoomView, load_rooms

_NORM = re.compile(r"[\s()N\-]")


def _norm(s: str) -> str:
    return _NORM.sub("", s or "")


def evaluate(rooms: list[RoomView]) -> list[dict]:
    """평면도 이름과 차압도 이름이 정규화 후에도 다른 방을 위반으로 반환."""
    out = []
    for r in rooms:
        if not r.room_no or r.name is None or r.pressure_name is None:
            continue
        if _norm(r.name) != _norm(r.pressure_name):
            out.append({
                "severity": "minor",
                "rooms": [r.room_no],
                "message": f"방번호 {r.room_no}: 평면도 '{r.name}' vs 차압도 '{r.pressure_name}' 이름 불일치",
                "evidence": {"floorplan": r.name, "pressure_plan": r.pressure_name},
            })
    return out


def run(cur, run_id, facility_id, rule) -> list[dict]:
    return evaluate(load_rooms(cur, run_id))
