# -*- coding: utf-8 -*-
"""ADJ-001 - Grade 인접 금지쌍 위반 (critical).

특정 청정등급 조합은 직접 맞닿으면 안 된다(예: 최고청정 A 구역이 일반 D 구역과
문 하나로 바로 인접). 인접 그래프(room_adjacency)와 방별 청정등급(grade)을 맞대어
금지쌍이 직접 인접하면 위반.

게이트(중요): 실제 파이프라인 작동은 두 가지 확정 전 금지.
  1) 방별 청정등급 = Grade 도면 수령,
  2) forbidden_pairs(금지 등급쌍) = GMP 컨설턴트 검수.
run() 은 rule.config.enabled 가 true 일 때만 판정(기본 false). 순수 로직 evaluate() 는
합성 데이터로 검증한다. 인접 판정은 현재 최근접-k 근사이므로, 방 경계 폴리곤 승격 후
정밀 인접으로 재검증이 필요하다(그 전에는 오탐/누락 가능 - 주석으로 남김).
"""
from __future__ import annotations

from ._model import AdjPair, RoomView, load_adjacency, load_rooms


def evaluate(adjacency: list[AdjPair], rooms: list[RoomView], cfg: dict) -> list[dict]:
    """금지 등급쌍이 직접 인접한 경우를 위반으로 반환."""
    forbidden = {frozenset(p) for p in cfg.get("forbidden_pairs", []) if len(p) == 2}
    grade_by = {r.room_no: r.grade for r in rooms if r.room_no}

    out = []
    seen = set()
    for pair in adjacency:
        ga, gb = grade_by.get(pair.a), grade_by.get(pair.b)
        if ga is None or gb is None:
            continue
        key = frozenset((pair.a, pair.b))
        if key in seen:
            continue  # 인접은 양방향 저장될 수 있어 쌍 단위로 1건만
        if frozenset((ga, gb)) in forbidden:
            seen.add(key)
            out.append({
                "severity": "critical",
                "rooms": sorted((pair.a, pair.b)),
                "message": f"등급 인접 금지 위반: {pair.a}(등급 {ga}) - {pair.b}(등급 {gb}) 직접 인접",
                "evidence": {"pair": sorted((pair.a, pair.b)), "grades": sorted((ga, gb))},
            })
    return out


def run(cur, run_id, facility_id, rule) -> list[dict]:
    cfg = rule.get("config", {}) or {}
    if not cfg.get("enabled"):
        return []  # 게이트: Grade 도면·검수 확정 후 rules YAML 에서 enabled:true
    return evaluate(load_adjacency(cur, run_id), load_rooms(cur, run_id), cfg)
