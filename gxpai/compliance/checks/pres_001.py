# -*- coding: utf-8 -*-
"""PRES-001 - 압력 캐스케이드 역전 (critical). **2026-07-13 전면 재설계.**

무엇이 바뀌었나 - 엔진을 통째로 잘못 만들 뻔했다
  예전 규칙: "청정도가 높은 방이 인접 낮은 방보다 고압이어야 한다" - **한 유형에만 맞는 말이다.**
  실제로는 압력 방향이 세 가지고, **우리 기준 시설(내용고형제)은 '봉쇄형'이라 정반대다.**

    ① protect(보호)  실이 고압    ← 무균제제, 일반 청정실. 이 규칙이 적용된다.
    ② contain(봉쇄)  실이 **저압**, 복도가 고압  ← 분진 발생(칭량, 혼합, 과립, 정립, 타정).
                     여기에 ①을 들이대면 **전부 거짓 위반**이 난다. → PRES-003 이 따로 검사.
    ③ hazard(특수)   실이 음압    ← 페니실린, 세포독성. 역시 ①이 아니다.

  근거: 2010 시설기준 안내서 p.24 그림6(통로 30Pa > 작업실 15Pa), p.60(제5조 해설)
        1차 미팅 대표님 "복도가 높고 여기가 낮다"
        상세: 10_법규/조문근거_색인.md A-4, A-5절

화살표 의미 (S-1) - **확정됨(2026-07-13)**
  화살촉 = 저압 쪽 = 공기가 흘러가는 방향. 4중 확인:
    ① 1차 미팅 "바람은 높은 데서 낮은 데로"
    ② 새 참고도면 범례(화살표별 차압 설정값 명시)
    ③ 도면의 절대압력(Pa)과 대조 일치
    ④ DXF 원본에 회전각(0/90/180/270)으로 존재 - 추측 불필요
  → 게이트 해제. 다만 grade_rank, regime 은 여전히 **컨설턴트 검수 대기**(review: unreviewed).

적용 범위(중요)
  **양쪽 방이 모두 protect 일 때만** 판정한다. 한쪽이라도 contain/hazard/neutral 이면 건너뛴다.
  (그 조합은 PRES-003 이 본다.) 이렇게 좁히는 게 거짓 위반을 막는 유일한 길이다.
"""
from __future__ import annotations

from ._model import PressureRel, RoomView, load_pressure_rels, load_rooms
from ._regime import PROTECT, resolve_regime


def evaluate(rels: list[PressureRel], rooms: list[RoomView], cfg: dict) -> list[dict]:
    """보호(protect)형 실 사이에서 '깨끗한 방이 저압'이면 위반."""
    rank = cfg.get("grade_rank", {})                       # 등급명 → 정수(클수록 깨끗)
    cleaner_higher = cfg.get("cleaner_should_be", "higher") == "higher"
    overrides = cfg.get("regime_overrides", {}) or {}

    info: dict[str, tuple[str | None, str]] = {}           # room_no → (grade, regime)
    for r in rooms:
        if not r.room_no:
            continue
        reg = r.regime or resolve_regime(r.name, r.grade, overrides, r.room_no)[0]
        info[r.room_no] = (r.grade, reg)

    out = []
    for rel in rels:
        if rel.approx or not rel.room_high_no or not rel.room_low_no:
            continue                                       # 방 귀속 미확정(원시 화살표)
        hi, lo = rel.room_high_no, rel.room_low_no
        if hi not in info or lo not in info:
            continue
        gh, rh = info[hi]
        gl, rl = info[lo]

        # 핵심: 양쪽 모두 '보호형'일 때만 이 규칙이 성립한다.
        if rh != PROTECT or rl != PROTECT:
            continue
        if gh not in rank or gl not in rank:
            continue                                       # 등급 미상 → 판정 불가

        inverted = rank[gl] > rank[gh] if cleaner_higher else rank[gh] > rank[gl]
        if inverted:
            out.append({
                "severity": "critical",
                "rooms": [hi, lo],
                "message": (f"압력 캐스케이드 역전: {lo}(등급 {gl})가 "
                            f"{hi}(등급 {gh})보다 깨끗한데 저압 쪽에 있음"),
                "evidence": {"high_room": hi, "high_grade": gh, "high_regime": rh,
                             "low_room": lo, "low_grade": gl, "low_regime": rl},
            })
    return out


def run(cur, run_id, facility_id, rule) -> list[dict]:
    cfg = rule.get("config", {}) or {}
    if not cfg.get("enabled"):
        return []      # 게이트: grade_rank, regime 컨설턴트 검수 후 enabled:true
    return evaluate(load_pressure_rels(cur, run_id), load_rooms(cur, run_id), cfg)
