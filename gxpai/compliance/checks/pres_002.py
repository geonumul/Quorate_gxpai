# -*- coding: utf-8 -*-
"""PRES-002 - 차압 기준값 이탈 (major). **신규 구현 (2026-07-13).**

★가장 중요한 설계 판단: **절대 수치로 판정하면 안 된다.**

  실사 지적사례(식약처 「의약품GMP 현장감시 주요 지적사례」)의 실제 문구:
      "청정등급이 변경되는 지역 간의 차압을 **자사 기준서에 정해진 기준**에 맞게 유지하지 아니함"
      【관련규정】「의약품 등의 안전에 관한 규칙」[별표1] 2.3 환경관리 나.

  즉 실사관은 *"법정 수치를 지켰나"* 가 아니라 ***"당신 회사가 정한 기준을 지켰나"*** 를 본다.
  법이 요구하는 것은 ①등급·차압을 **설정**할 것 ②설정한 대로 **유지**할 것 ③기록할 것 이지,
  **특정 수치가 아니다.**

  → "10Pa 미만이므로 위반"이라고 판정하면 **법적으로 틀린 판정**이다.
  → 그래서 이 규칙은 **발주처의 사내 기준서 값을 프로파일로 받아** 도면과 대조한다.
  → 기준서가 아예 없으면 → **"차압 기준 미설정"** 자체가 위반이다(설정 의무 위반).

법정 수치는 딱 하나뿐이고 그나마 참고치다
  고시 별표1 제4호 하목: "서로 다른 청정등급의 인접한 작업실은 **최소 10 파스칼(참고치) 이상**"
  → 무균제제에만 적용. `statutory_min_pa` 로 따로 둔다(위반이 아니라 **경고**).
  ⚠ 흔히 쓰는 "10~15Pa"은 **2018년판까지의 문구**다. 2023년 개정에서 상한 15 가 삭제됐다.
     (PE 009-14 "10-15 pascals" → PE 009-17 "a minimum of 10 Pascals" — 원문 대조 확인)
     식약처 게시판에는 아직 구판 별표가 올라와 있어 설계사들이 15Pa 을 쓰는 것으로 보인다.

상세 근거: 법규/조문근거_색인.md A · A-2절
"""
from __future__ import annotations

from ._model import AdjPair, RoomView, load_adjacency, load_rooms
from ._regime import NEUTRAL, resolve_regime


def evaluate(adj: list[AdjPair], rooms: list[RoomView], cfg: dict) -> list[dict]:
    """자사 기준서(프로파일) 범위를 벗어난 인접 실 쌍을 위반으로 반환."""
    # 자사 기준서: 등급이 다를 때 / 같을 때의 허용 차압 범위 [min, max]
    diff_range = cfg.get("diff_grade_pa")     # 예: [10, 15]
    same_range = cfg.get("same_grade_pa")     # 예: [5, 10]
    statutory_min = cfg.get("statutory_min_pa")   # 고시 참고치(무균). 경고용
    overrides = cfg.get("regime_overrides", {}) or {}

    view = {r.room_no: r for r in rooms if r.room_no}

    def regime_of(no: str) -> str:
        r = view[no]
        return r.regime or resolve_regime(r.name, r.grade, overrides, no)[0]

    # 기준서가 없으면 '미설정' 자체가 위반 — 단, 압력 데이터가 있을 때만 말이 된다
    if diff_range is None and same_range is None:
        has_pa = any(r.pressure_pa is not None for r in rooms)
        if has_pa:
            return [{
                "severity": "major",
                "rooms": [],
                "message": ("차압 기준 미설정: 도면에 차압이 표기돼 있으나 "
                            "발주처 사내 기준서(허용 범위)가 프로파일에 없어 판정할 수 없음"),
                "evidence": {"필요": "profile.pres_002.diff_grade_pa / same_grade_pa",
                             "근거": "안전에 관한 규칙 별표1 2.3 환경관리 나 (설정·유지 의무)"},
            }]
        return []

    out: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for pair in adj:
        a, b = pair.a, pair.b
        if a not in view or b not in view:
            continue
        key = tuple(sorted((a, b)))
        if key in seen:
            continue
        ra, rb = view[a], view[b]
        if ra.pressure_pa is None or rb.pressure_pa is None:
            continue
        # 압력 관리 대상이 아닌 공간(보관소·기계실 등)은 제외
        if regime_of(a) == NEUTRAL or regime_of(b) == NEUTRAL:
            continue
        if not ra.grade or not rb.grade:
            continue
        seen.add(key)

        d = abs(ra.pressure_pa - rb.pressure_pa)
        same = ra.grade == rb.grade
        rng = same_range if same else diff_range
        if rng is None:
            continue
        lo, hi = rng
        if lo <= d <= hi:
            continue

        kind = "동일 등급" if same else "등급 상이"
        out.append({
            "severity": "major",
            "rooms": [a, b],
            "message": (f"차압 기준 이탈: {a}({ra.grade},{ra.pressure_pa:g}Pa) ↔ "
                        f"{b}({rb.grade},{rb.pressure_pa:g}Pa) = Δ{d:g}Pa. "
                        f"[{kind}] 사내 기준 {lo}~{hi}Pa 범위 밖"),
            "evidence": {"room_a": a, "grade_a": ra.grade, "pa_a": ra.pressure_pa,
                         "room_b": b, "grade_b": rb.grade, "pa_b": rb.pressure_pa,
                         "delta_pa": d, "기준": f"{lo}~{hi}", "구분": kind,
                         "근거": "발주처 사내 기준서(프로파일). 법정 수치 아님"},
        })

        # 고시 참고치(무균 한정) 별도 경고 — 위반이 아니라 확인 요청
        if (statutory_min is not None and not same and d < statutory_min):
            out.append({
                "severity": "minor",
                "rooms": [a, b],
                "message": (f"고시 참고치 미달(확인 필요): Δ{d:g}Pa < {statutory_min:g}Pa. "
                            f"고시 별표1 제4호 하목은 '최소 10파스칼(참고치) 이상' — "
                            f"오염관리전략(CCS)으로 타당성을 입증하면 달리 정할 수 있음"),
                "evidence": {"room_a": a, "room_b": b, "delta_pa": d,
                             "clause": "식약처고시 제2024-87호 별표1 제4호 하목",
                             "note": "참고치(guidance value). hard fail 아님"},
            })
    return out


def run(cur, run_id, facility_id, rule) -> list[dict]:
    cfg = rule.get("config", {}) or {}
    if not cfg.get("enabled"):
        return []
    return evaluate(load_adjacency(cur, run_id), load_rooms(cur, run_id), cfg)
