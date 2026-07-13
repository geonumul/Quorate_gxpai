# -*- coding: utf-8 -*-
"""ADJ-001 - 청정등급 급변 인접 (critical). **2026-07-13 재설계.**

★무엇이 바뀌었나
  예전: "금지 등급쌍(A-D 등)이 맞닿으면 위반" — **조문에 그런 목록이 없다.**
        법제처 유권해석 1,830건 전수 검색에도 없었다. 우리가 지어낸 것이었다.
  지금: 조문에 **실제로 있는 것은 '점진성'** 이다.

    고시 별표1 제4호 타목 — "작업원 동선은 **D→C→B 로 점진적**"
    고시 별표1 제4호 타목 — "**에어락 최종단계는 비작업시 인접 청정실과 동일 등급**"
    고시 별표17 제3.3호 라목 — "시설·설비는 **가급적** 청정도에 따른 타당한 순서로 연결된 구역에 배치"

  → 규칙을 '금지쌍 목록'이 아니라 **'등급 점프 폭'** 으로 정의한다.
     인접한 두 실의 등급 차가 max_jump(기본 1)를 넘으면 위반.
     단, **전실·에어락·패스박스를 경유하면 직접 인접이 아니다** → 예외.

  전실의 등급 규칙(예외 처리의 근거)
    새GMP규정 Q&A 문16 — "청정도가 낮은 지역과 높은 지역 사이에 위치한 **전실 및 패스박스는
    청정도가 높은 지역의 청정도로 관리**하는 것이 바람직"

상세 근거: 법규/조문근거_색인.md B·B-2절

한계(정직)
  - 인접 판정이 지금 최근접-k 근사면 오탐/누락이 난다. **방 경계 폴리곤 승격 후 재검증 필요.**
  - forbidden_pairs 는 비워 둔다. 컨설턴트가 특정 조합을 금지하면 그때 채운다.
"""
from __future__ import annotations

from ._model import AdjPair, RoomView, load_adjacency, load_rooms

DEFAULT_AIRLOCK = ("전실", "에어락", "air lock", "airlock", "패스박스", "pass box")


def _is_airlock(name: str | None, words) -> bool:
    if not name:
        return False
    n = name.replace(" ", "").lower()
    return any(w.replace(" ", "").lower() in n for w in words)


def evaluate(adjacency: list[AdjPair], rooms: list[RoomView], cfg: dict) -> list[dict]:
    rank = cfg.get("grade_rank", {})
    max_jump = int(cfg.get("max_jump", 1))
    words = cfg.get("airlock_words") or DEFAULT_AIRLOCK
    forbidden = {frozenset(p) for p in (cfg.get("forbidden_pairs") or []) if len(p) == 2}

    view = {r.room_no: r for r in rooms if r.room_no}

    out: list[dict] = []
    seen: set[frozenset] = set()

    # ★**문으로 이어진 쌍만** 판정한다 (via_door). 조문이 말하는 건 벽이 아니라 **동선**이다.
    #
    #   고시 별표1 제4호 타목  : "작업원 **동선**은 D→C→B 로 점진적"
    #   고시 별표17 제3.3호 라목: "청정도에 따른 타당한 순서로 **연결된** 구역에 배치"
    #
    #   벽만 맞대고 문이 없으면 사람이 오갈 수 없다 → 등급이 급변해도 동선 위반이 아니다.
    #   벽 맞댐으로 판정하면 **지나갈 수도 없는 두 방**을 '등급 급변'이라 우긴다.
    #   참고도면에서 근사 인접(101쌍)을 진짜 벽 인접(42쌍)으로 바꾸자 9건 → 4건이 됐다.
    #   문 인접으로 한 번 더 좁히면 여기서 또 줄어든다.
    #
    #   ⚠ via_door 가 **None** 이면 문 데이터가 없는 도면이다(참고도면).
    #     이때는 벽 인접으로 폴백하되, 근거에 "문 정보 없음"을 남긴다.
    #     **판정을 포기하지도, 확정하지도 않는다.**
    has_door_data = any(p.via_door is not None for p in adjacency)

    for pair in adjacency:
        a, b = pair.a, pair.b
        if a not in view or b not in view:
            continue
        if has_door_data and pair.via_door is False:
            continue                      # 벽만 맞댔다 — 오갈 수 없으니 동선 위반이 아니다
        key = frozenset((a, b))
        if key in seen:
            continue                      # 인접은 양방향 저장될 수 있다
        ra, rb = view[a], view[b]
        ga, gb = ra.grade, rb.grade
        if not ga or not gb:
            continue                      # 등급 미상 → 판정 불가

        # 예외: 전실·에어락·패스박스는 등급 완충 장치다. 이를 경유하면 '직접 인접'이 아니다.
        if _is_airlock(ra.name, words) or _is_airlock(rb.name, words):
            continue

        seen.add(key)

        # (1) 컨설턴트가 지정한 금지쌍 (기본 비어 있음)
        if frozenset((ga, gb)) in forbidden:
            out.append({
                "severity": "critical",
                "rooms": sorted((a, b)),
                "message": f"등급 인접 금지 위반: {a}(등급 {ga}) - {b}(등급 {gb}) 직접 인접",
                "evidence": {"pair": sorted((a, b)), "grades": sorted((ga, gb)),
                             "근거": "컨설턴트 지정 금지쌍"},
            })
            continue

        # (2) 등급 점프 폭 (조문에 실제로 있는 것)
        if ga not in rank or gb not in rank:
            continue
        jump = abs(rank[ga] - rank[gb])
        if jump > max_jump:
            via = ("문으로 이어짐(동선 확인)" if pair.via_door
                   else "문 정보 없는 도면 — 벽 맞댐으로 판정. **문이 없으면 위반이 아닐 수 있다**")
            out.append({
                "severity": "critical",
                "rooms": sorted((a, b)),
                "message": (f"청정등급 급변: {a}(등급 {ga}) ↔ {b}(등급 {gb}) 가 "
                            f"에어락/전실 없이 직접 인접 (등급 {jump}단계 차, 허용 {max_jump})"),
                "evidence": {"pair": sorted((a, b)), "grades": [ga, gb], "jump": jump,
                             "max_jump": max_jump, "via_door": pair.via_door, "인접근거": via,
                             "근거": "고시 별표1 제4호 타목 — 동선은 D→C→B 로 점진적",
                             "판단": "보류. 발주처 확인 필요"},
            })
    return out


def run(cur, run_id, facility_id, rule) -> list[dict]:
    cfg = rule.get("config", {}) or {}
    if not cfg.get("enabled"):
        return []      # 게이트: Grade 적재 + 폴리곤 인접 + 컨설턴트 검수 후 enabled:true
    return evaluate(load_adjacency(cur, run_id), load_rooms(cur, run_id), cfg)
