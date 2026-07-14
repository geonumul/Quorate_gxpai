# -*- coding: utf-8 -*-
"""PRES-003 - 봉쇄 실패 (critical). **신규 (2026-07-13).**

무엇을 보나
  **분진이 나는 작업실(칭량, 혼합, 과립, 정립, 타정, 코팅)은 인접 복도보다 저압**이어야 한다.
  분진이 복도로 빠져나가면 교차오염이다. 특수제제(페니실린, 세포독성)는 더 강하게 음압이어야 한다.

  이것이 우리 기준 시설(내용고형제)에 **실제로 적용되는** 압력 규칙이다.
    PRES-001("깨끗한 방이 고압")은 무균제제용이고, 여기엔 맞지 않는다.

근거
  - 2010 「의약품제조소 시설기준(구조, 설비) 안내서」 p.24 그림6
      "분진이 많이 생겨 교차오염 가능성이 높은 작업실" → **통로 30Pa > 작업실 15Pa**
  - 같은 안내서 p.60 (시설기준령 시행규칙 제5조 해설)
      특수제제: "공기의 차압을 이용하여 **내부의 분진이 확산되지(외부로 빠져나가지) 않도록** 한다"
  - 같은 안내서 p.33
      "분진이 발생하는 작업실에는 국소집진시설을 설치할 것"
  - 1차 미팅(2026-07-09) 대표님: "복도가 높고 여기가 낮다… 복도 공기가 룸 안으로 들어가야 돼"
  - 상세: 10_법규/조문근거_색인.md A-4, A-5절

판정 방법 (두 가지 증거를 모두 쓴다)
  1) **화살표**(pressure_relation): 봉쇄실이 화살표의 *고압(tail)* 쪽에 있고
     상대가 복도면 → 공기가 봉쇄실 → 복도로 나간다 = **봉쇄 실패**.
  2) **절대압력**(pressure_pa): 봉쇄실 Pa 가 인접 복도 Pa 보다 **높으면** 봉쇄 실패.
  둘 중 하나라도 걸리면 보고한다. 둘 다 없으면(데이터 부재) 조용히 건너뛴다.

한계(정직)
  - 봉쇄 여부는 **방 이름으로 추정**한다(_regime.py). 이름은 회사마다 다르다.
    → 프로파일로 덮어쓸 수 있고, evidence 에 regime_source 를 남긴다.
  - "인접 복도"는 인접 그래프에 의존한다. 지금 인접이 최근접-k 근사면 오탐 가능.
    → 방 경계 폴리곤 승격 후 정확해진다.
"""
from __future__ import annotations

from ._model import (AdjPair, PressureRel, RoomView, load_adjacency,
                     load_pressure_rels, load_rooms)
from ._regime import CONTAIN, HAZARD, is_corridor, resolve_regime


def _contradicts(hi: RoomView, lo: RoomView) -> bool:
    """화살표와 절대압력이 **서로 어긋나는가.**

    근거가 둘인데 **어긋나면 판정하지 않는다.** 그게 우리 철칙이다.
      PRES-004 의 이력이 증언한다 - *"화살표 vs 압력 모순 9건이 **전부 우리 버그**였다."*
      그런 구간에서 PRES-003 이 critical 을 내면 **우리 버그를 위반으로 보고**하는 것이다.
      → 모순은 PRES-004 가 "확인 필요"로 보고한다. PRES-003 은 **손을 뗀다.**
    """
    if hi.pressure_pa is None or lo.pressure_pa is None:
        return False
    return hi.pressure_pa < lo.pressure_pa    # 꼬리(고압)가 화살촉(저압)보다 낮다 = 모순


def evaluate(rels: list[PressureRel], adj: list[AdjPair], rooms: list[RoomView],
             cfg: dict) -> list[dict]:
    overrides = cfg.get("regime_overrides", {}) or {}

    view: dict[str, RoomView] = {r.room_no: r for r in rooms if r.room_no}
    regime: dict[str, tuple[str, str]] = {}
    for no, r in view.items():
        if r.regime:
            regime[no] = (r.regime, r.regime_source or "drawing")
        else:
            regime[no] = resolve_regime(r.name, r.grade, overrides, no)

    def corridor(no: str) -> bool:
        r = view.get(no)
        return bool(r) and is_corridor(r.name)

    out: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def report(room: str, other: str, why: str, ev: dict) -> None:
        key = (room, other)
        if key in seen:
            return
        seen.add(key)
        reg, src = regime[room]
        kind = "특수제제(음압)" if reg == HAZARD else "분진 발생실"
        oname = view[other].name or ""
        out.append({
            "severity": "critical",
            "rooms": [room, other],
            "message": (f"봉쇄 실패: {kind} {room}({view[room].name or ''})이(가) "
                        f"{other}({oname})보다 고압 - {why}. "
                        f"분진이 밖으로 확산될 수 있음"),
            "evidence": {"room": room, "neighbor": other,
                         "neighbor_regime": regime[other][0] if other in regime else None,
                         "regime": reg, "regime_source": src, **ev},
        })

    # 1) 화살표 근거: 봉쇄실이 **고압쪽**이고, 저압쪽이 봉쇄실이 아니면 분진이 나간다
    #
    #   처음엔 저압쪽이 '복도'일 때만 봤다. 실제 도면에서 3건을 놓쳤다:
    #       contain → neutral (보관실, 기계실) 2건
    #       contain → protect (청정실) 1건  ← 이게 제일 나쁘다
    #     분진이 나가는 곳이 복도든 보관실이든 청정실이든 **봉쇄 실패**다.
    #     (contain → contain 은 둘 다 분진 구역이라 문제 아님 - 실제 14건 있었다)
    for rel in rels:
        if rel.approx or not rel.room_high_no or not rel.room_low_no:
            continue
        hi, lo = rel.room_high_no, rel.room_low_no
        if hi not in regime or lo not in regime:
            continue
        if regime[hi][0] not in (CONTAIN, HAZARD):
            continue
        if regime[lo][0] in (CONTAIN, HAZARD):
            continue                       # 분진 구역끼리는 문제 아님
        where = "복도" if corridor(lo) else f"{regime[lo][0]} 구역"
        report(hi, lo, f"화살표가 작업실 → {where} 방향", {"근거": "arrow"})

    # 2) 절대압력 근거: 봉쇄실 Pa > 인접(비봉쇄) 실 Pa
    for pair in adj:
        for a, b in ((pair.a, pair.b), (pair.b, pair.a)):
            if a not in regime or b not in regime:
                continue
            if regime[a][0] not in (CONTAIN, HAZARD):
                continue
            if regime[b][0] in (CONTAIN, HAZARD):
                continue                   # 분진 구역끼리는 문제 아님
            pa, pb = view[a].pressure_pa, view[b].pressure_pa
            if pa is None or pb is None:
                continue
            if pa > pb:
                where = "복도" if corridor(b) else f"{regime[b][0]} 구역"
                report(a, b, f"{pa:g}Pa > {where} {pb:g}Pa",
                       {"근거": "pressure_pa", "room_pa": pa, "neighbor_pa": pb})
    return out


def run(cur, run_id, facility_id, rule) -> list[dict]:
    cfg = rule.get("config", {}) or {}
    if not cfg.get("enabled"):
        return []
    return evaluate(load_pressure_rels(cur, run_id), load_adjacency(cur, run_id),
                    load_rooms(cur, run_id), cfg)
