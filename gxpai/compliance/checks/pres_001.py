# -*- coding: utf-8 -*-
"""PRES-001 - 압력 캐스케이드 역전 (critical).

원칙(OSD 통상): 청정도가 높은(더 깨끗한) 방이 인접 낮은 방보다 '고압'이어야
오염 유입을 막는다. 차압 화살표(pressure_relation)가 알려주는 고/저압 방향과
방의 청정등급(grade)을 맞대어, 더 깨끗한 방이 오히려 저압 쪽에 있으면 역전 위반.

게이트(중요): 이 규칙은 두 가지 확정 전에는 실제 파이프라인에서 '작동 금지'다.
  1) 화살표 화살촉이 '고압→저압'을 뜻하는지 발주처 확인(S-1),
  2) 방별 청정등급 = Grade 도면 수령,
  3) grade_rank/방향 = GMP 컨설턴트 검수.
따라서 run() 은 rule.config.enabled 가 true 일 때만 판정한다(기본 false). 그 전에는
설령 데이터가 있어도 0건을 반환한다. 순수 로직 evaluate() 자체는 합성 데이터로 검증한다.
"""
from __future__ import annotations

from ._model import PressureRel, RoomView, load_pressure_rels, load_rooms


def evaluate(rels: list[PressureRel], rooms: list[RoomView], cfg: dict) -> list[dict]:
    """차압 방향과 청정등급이 모순되는(깨끗한 방이 저압) 관계를 위반으로 반환."""
    rank = cfg.get("grade_rank", {})          # 등급명 → 정수(클수록 깨끗)
    cleaner_higher = cfg.get("cleaner_should_be", "higher") == "higher"
    grade_by = {r.room_no: r.grade for r in rooms if r.room_no}

    out = []
    for rel in rels:
        if rel.approx or not rel.room_high_no or not rel.room_low_no:
            continue  # 방 귀속 미확정(원시 화살표)은 판정 불가
        gh, gl = grade_by.get(rel.room_high_no), grade_by.get(rel.room_low_no)
        if gh not in rank or gl not in rank:
            continue  # 등급 미상인 방은 건너뜀
        # cleaner_higher 규칙에서, 저압(low) 쪽이 고압(high) 쪽보다 더 깨끗하면 역전.
        inverted = rank[gl] > rank[gh] if cleaner_higher else rank[gh] > rank[gl]
        if inverted:
            hi, lo = rel.room_high_no, rel.room_low_no
            out.append({
                "severity": "critical",
                "rooms": [hi, lo],
                "message": (f"압력 캐스케이드 역전: {lo}(등급 {gl})가 "
                            f"{hi}(등급 {gh})보다 깨끗한데 저압 쪽에 있음"),
                "evidence": {"high_room": hi, "high_grade": gh,
                             "low_room": lo, "low_grade": gl},
            })
    return out


def run(cur, run_id, facility_id, rule) -> list[dict]:
    cfg = rule.get("config", {}) or {}
    if not cfg.get("enabled"):
        return []  # 게이트: 화살표 의미·Grade·검수 확정 후 rules YAML 에서 enabled:true
    return evaluate(load_pressure_rels(cur, run_id), load_rooms(cur, run_id), cfg)
