# -*- coding: utf-8 -*-
"""LBL-001 - 방번호-이름 라벨 불일치 (평면도 vs 차압도).

같은 방번호인데 평면도 이름과 차압도 이름이 다르면 위반. 정규화(공백/괄호/N/하이픈 제거)
후 비교하여 표기 차이만 있는 경우는 제외 (v0.1 로직 승계).

구조: evaluate() 는 순수 함수(DB 무관, 합성 시험 대상), run() 은 얇은 DB 어댑터.
"""
from __future__ import annotations

import re

from ._model import RoomView, load_rooms

# `[\s()N\-]` 이었다 - **문자열 어디의 대문자 N 이든 지웠다.**
#   `(N)` 접두어(신설 표시)를 지우려던 것인데:
#     평면도 `GRANULATION` vs 차압도 `Granulation`
#       → `GRAULATIO` vs `Granulation` → **이름 불일치 거짓 위반**
#     `N실` vs `실` → 같다고 판정 → **놓침**
#   소문자 `n` 은 안 지우고, 대소문자 폴딩도 안 했다.
#   → `(N)`, `（N）` **접두어만** 지우고, 나머지는 공백, 괄호, 하이픈만 정리한 뒤 대문자로 통일.
# `(N)` = 신설 표시. **앞이든 뒤든** 붙는다(`(N)제조실`, `제 조 실(N)`).
# **괄호로 감싼 N 만** 지운다 - 맨 N(`N동`)은 이름의 일부다.
_MARKER = re.compile(r"[（(]\s*[NnＮ]\s*[）)]")
_NORM = re.compile(r"[\s()（）\-_]")


def _norm(s: str | None) -> str:
    """이름 비교용 정규형. `(N)` 접두어 제거 + 공백, 괄호, 하이픈 제거 + 대문자."""
    if not s:
        return ""
    t = _MARKER.sub("", s.strip())
    return _NORM.sub("", t).upper()



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
