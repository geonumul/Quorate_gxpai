# -*- coding: utf-8 -*-
"""LBL-001 - 방번호-이름 라벨 불일치 (평면도 vs 차압도).

같은 방번호인데 평면도 이름과 차압도 이름이 다르면 위반. 정규화(공백/괄호/N/하이픈 제거)
후 비교하여 표기 차이만 있는 경우는 제외 (v0.1 로직 승계).
"""
from __future__ import annotations

import re

_NORM = re.compile(r"[\s()N\-]")


def _norm(s: str) -> str:
    return _NORM.sub("", s or "")


def run(cur, run_id, facility_id, rule) -> list[dict]:
    cur.execute(
        """SELECT room_no, name, pressure_name FROM room
           WHERE run_id=%s AND room_no IS NOT NULL
                 AND name IS NOT NULL AND pressure_name IS NOT NULL""",
        (run_id,),
    )
    out = []
    for room_no, name, pname in cur.fetchall():
        if _norm(name) != _norm(pname):
            out.append({
                "severity": "minor",
                "rooms": [room_no],
                "message": f"방번호 {room_no}: 평면도 '{name}' vs 차압도 '{pname}' 이름 불일치",
                "evidence": {"floorplan": name, "pressure_plan": pname},
            })
    return out
