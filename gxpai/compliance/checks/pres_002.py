# -*- coding: utf-8 -*-
"""PRES-002 - 차압 기준값 이탈 (major). **신규 구현 (2026-07-13).**

가장 중요한 설계 판단: **절대 수치로 판정하면 안 된다.**

  실사 지적사례(식약처 「의약품GMP 현장감시 주요 지적사례」)의 실제 문구:
      "청정등급이 변경되는 지역 간의 차압을 **자사 기준서에 정해진 기준**에 맞게 유지하지 아니함"
      【관련규정】「의약품 등의 안전에 관한 규칙」[별표1] 2.3 환경관리 나.

  즉 실사관은 *"법정 수치를 지켰나"* 가 아니라 ***"당신 회사가 정한 기준을 지켰나"*** 를 본다.
  법이 요구하는 것은 ①등급, 차압을 **설정**할 것 ②설정한 대로 **유지**할 것 ③기록할 것 이지,
  **특정 수치가 아니다.**

  → "10Pa 미만이므로 위반"이라고 판정하면 **법적으로 틀린 판정**이다.
  → 그래서 이 규칙은 **발주처의 사내 기준서 값을 프로파일로 받아** 도면과 대조한다.
  → 기준서가 아예 없으면 → **"차압 기준 미설정"** 자체가 위반이다(설정 의무 위반).

법정 수치는 딱 하나뿐이고 그나마 참고치다
  고시 별표1 제4호 하목: "서로 다른 청정등급의 인접한 작업실은 **최소 10 파스칼(참고치) 이상**"
  → 무균제제에만 적용. `statutory_min_pa` 로 따로 둔다(위반이 아니라 **경고**).
  [주의] 흔히 쓰는 "10~15Pa"은 **2018년판까지의 문구**다. 2023년 개정에서 상한 15 가 삭제됐다.
     (PE 009-14 "10-15 pascals" → PE 009-17 "a minimum of 10 Pascals" - 원문 대조 확인)
     식약처 게시판에는 아직 구판 별표가 올라와 있어 설계사들이 15Pa 을 쓰는 것으로 보인다.

상세 근거: 10_법규/조문근거_색인.md A, A-2절
"""
from __future__ import annotations

from ._model import (AdjPair, PressureRel, RoomView, load_adjacency,
                     load_pressure_rels, load_rooms)
from ._regime import NEUTRAL, is_corridor, resolve_regime


def evaluate(adj: list[AdjPair], rooms: list[RoomView], cfg: dict,
             rels: list[PressureRel] | None = None) -> list[dict]:
    """자사 기준서(프로파일) 범위를 벗어난 **차압 설정 구간**을 위반으로 반환.

    적용 범위가 핵심이다 - 처음엔 **인접한 모든 실 쌍**에 기준을 들이댔다가 과잉 검출했다.
      실제 도면에서 `Δ0Pa`(같은 등급, 같은 압력) 쌍을 무더기로 위반으로 찍었다.
      그런데 **도면 범례 3번**이 명시한다: *"기류흐름 및 차압계 설치가 요구되지 않는 위치"*.
      **차압이 설정되지 않은 구간에는 차압 기준이 애초에 적용되지 않는다.**

      → `rels`(차압 화살표)가 주어지면 **화살표가 있는 실 쌍만** 검사한다.
        rels 가 없으면(=화살표 데이터가 없는 시설) 예전처럼 인접 전체를 본다.
    """
    # 자사 기준서: 등급이 다를 때 / 같을 때의 허용 차압 범위 [min, max]
    diff_range = cfg.get("diff_grade_pa")     # 예: [10, 15]
    same_range = cfg.get("same_grade_pa")     # 예: [5, 10]
    statutory_min = cfg.get("statutory_min_pa")   # 고시 참고치(무균). 경고용
    overrides = cfg.get("regime_overrides", {}) or {}
    # 도면 설정값과 실제 차압의 허용오차(Pa). 설계 도면의 반올림, 표기 관행을 흡수한다.
    tol = cfg.get("setpoint_tolerance_pa", 5)

    view = {r.room_no: r for r in rooms if r.room_no}

    def regime_of(no: str) -> str:
        r = view[no]
        return r.regime or resolve_regime(r.name, r.grade, overrides, no)[0]

    # 도면 화살표 레이어가 구간별 설정값을 갖고 있으면(`Air Flow 15Pa`) **그것이 기준**이다.
    #   그런데 이 조기 반환이 그 확인보다 **먼저** 와서, 설정값이 다 있는 도면에도
    #   "차압 기준 미설정" 위반을 냈다. 같은 파일이 스스로 "도면 설정값이 있으면 그것이
    #   기준이다(설계사가 정한 값 = 사실상의 자사 기준)"라고 적어 놓고 어겼다.
    has_setpoint = bool(rels) and any(
        r.setpoint_pa is not None and not r.approx for r in (rels or []))

    # 기준서가 없으면 '미설정' 자체가 위반 - 단, 압력 데이터가 있고 **도면 설정값도 없을 때만**
    if diff_range is None and same_range is None and not has_setpoint:
        has_pa = any(r.pressure_pa is not None for r in rooms)
        if has_pa:
            return [{
                "severity": "major",
                "rooms": [],
                "message": ("차압 기준 미설정: 도면에 차압이 표기돼 있으나 "
                            "발주처 사내 기준서(허용 범위)가 프로파일에 없어 판정할 수 없음"),
                "evidence": {"필요": "profile.pres_002.diff_grade_pa / same_grade_pa",
                             "근거": "안전에 관한 규칙 별표1 2.3 환경관리 나 (설정, 유지 의무)"},
            }]
        return []

    # ── 어느 구간을 검사할 것인가 ──────────────────────────────
    # 차압이 **설정된** 구간(화살표가 있는 실 쌍)만 검사한다.
    # `rels=[]`(화살표가 하나도 없다)와 `rels=None`(화살표 데이터 자체가 없다)은 **다르다.**
    #   `if rels:` 로 쓰면 빈 리스트가 falsy 라 '정보 없음'으로 취급돼 인접 전체를 검사한다.
    #   시험이 이 실수를 잡았다.
    #
    # 그리고 **도면이 구간마다 목표 차압을 직접 말해준다** - 화살표 레이어 이름이
    #   'Air Flow 10Pa' / 'Air Flow 15Pa' / 'Air Flow no차압' 이다.
    #   처음엔 이걸 통째로 버리고 프로파일의 등급별 범위만 썼다. 도면에 답이 적혀 있는데
    #   짐작으로 판정한 셈이다. 이제 **도면 설정값이 있으면 그것을 기준으로 삼는다**
    #   (설계사가 정한 값 = 사실상의 자사 기준). 없을 때만 프로파일 범위로 폴백한다.
    metered: set[tuple[str, str]] | None = None
    setpoint: dict[tuple[str, str], float] = {}   # 구간 → 도면이 적어둔 목표 차압
    nospec: set[tuple[str, str]] = set()          # 'no차압' = 차압 기준이 없는 구간
    if rels is not None:
        metered = set()
        for r in rels:
            if r.approx or not r.room_high_no or not r.room_low_no:
                continue
            k = tuple(sorted((r.room_high_no, r.room_low_no)))
            metered.add(k)
            if r.setpoint_pa is not None:
                # 같은 구간에 화살표가 둘이면 큰 쪽(엄격한 쪽)을 남긴다
                setpoint[k] = max(setpoint.get(k, 0.0), r.setpoint_pa)
            elif r.layer and "NO차압" in r.layer.replace(" ", "").upper():
                nospec.add(k)

    out: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for pair in adj:
        a, b = pair.a, pair.b
        if a not in view or b not in view:
            continue
        key = tuple(sorted((a, b)))
        if key in seen:
            continue
        if metered is not None and key not in metered:
            continue          # 차압 설정 구간이 아니다 (도면 범례 3번)
        if key in nospec:
            continue          # 'no차압' = 차압계 설치가 요구되지 않는 위치. 기준 자체가 없다
        ra, rb = view[a], view[b]
        if ra.pressure_pa is None or rb.pressure_pa is None:
            continue
        # **복도를 빼면 안 된다.** 여기서 봉쇄형 시설의 **핵심 구간을 통째로 버리고 있었다.**
        #
        #   `regime_of(복도) == NEUTRAL` 이라 `continue` 했다. 그런데 _regime.py 가 스스로
        #   적어 뒀다 - *"※ 복도는 '중립'이 아니라 **기준면**이다."*
        #
        #   봉쇄형 시설(내용고형제)에서 차압이 설정되는 구간은 **대부분 복도 ↔ 작업실**이다.
        #   그걸 다 빼면 PRES-002 는 **0건을 내고 "깨끗하다"고 말한다.**
        #   (타정실 15Pa ↔ 복도 30Pa, 도면 설정 15Pa → 0건이 나왔다. 검증으로 잡았다)
        #
        #   RASE exception 도 "보관소, 기계실 **등**"만 빼라고 적혀 있다. 복도가 아니다.
        #   → 중립이되 **복도가 아닌 것**(보관소, 기계실)만 뺀다.
        if ((regime_of(a) == NEUTRAL and not is_corridor(view[a].name))
                or (regime_of(b) == NEUTRAL and not is_corridor(view[b].name))):
            continue
        seen.add(key)

        d = abs(ra.pressure_pa - rb.pressure_pa)

        # ── ① 도면이 목표 차압을 적어뒀다면 그것이 기준이다 ──────────
        sp = setpoint.get(key)
        if sp is not None:
            if abs(d - sp) <= tol:
                continue
            out.append({
                "severity": "major",
                "rooms": [a, b],
                "message": (f"차압 설정값 불일치: {a}({ra.pressure_pa:g}Pa) ↔ "
                            f"{b}({rb.pressure_pa:g}Pa) = Δ{d:g}Pa 인데, "
                            f"도면이 이 구간에 지정한 차압은 {sp:g}Pa 다"),
                "evidence": {"room_a": a, "pa_a": ra.pressure_pa,
                             "room_b": b, "pa_b": rb.pressure_pa,
                             "delta_pa": d, "setpoint_pa": sp, "허용오차": tol,
                             "근거": "도면 화살표 레이어가 지정한 차압 설정값 vs 방별 절대압력",
                             "판단": "보류. 도면 오기인지 설계 의도인지 발주처 확인 필요"},
            })
            continue

        # ── ② 설정값이 없으면 프로파일(사내 기준서) 범위로 폴백 ──────
        if not ra.grade or not rb.grade:
            continue
        same = ra.grade == rb.grade
        rng = same_range if same else diff_range
        if rng is None:
            continue
        lo, hi = rng
        if lo <= d <= hi:
            # 범위 안이어도 **고시 참고치는 따로 봐야 한다.**
            #   예전엔 여기서 `continue` 해버려 참고치 경고가 **범위 위반이 난 쌍에만**
            #   따라붙었다 → 사내 기준 [5,10] 에 Δ7Pa 이면 참고치(10Pa) 미달 경고가
            #   **영원히 안 났다.** 그리고 Δ3Pa 이면 major + minor **2건**이 한 원인으로 떴다.
            out.extend(_statutory_note(a, b, d, same, statutory_min))
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

        out.extend(_statutory_note(a, b, d, same, statutory_min))
    return out


def _statutory_note(a, b, d, same, statutory_min) -> list[dict]:
    """고시 참고치(무균 한정) 경고 - **위반이 아니라 확인 요청**.

    사내 기준 범위 **안**이어도 참고치 미달이면 알려야 한다. 예전엔 범위 위반이 난 쌍에만
    따라붙어, 사내 기준을 지켰지만 고시 참고치엔 못 미치는 구간을 **영원히 놓쳤다.**
    """
    if statutory_min is None or same or d >= statutory_min:
        return []
    return [{
        "severity": "minor",
        "rooms": [a, b],
        "message": (f"고시 참고치 미달(확인 필요): Δ{d:g}Pa < {statutory_min:g}Pa. "
                    f"고시 별표1 제4호 하목은 '최소 10파스칼(참고치) 이상' - "
                    f"오염관리전략(CCS)으로 타당성을 입증하면 달리 정할 수 있음"),
        "evidence": {"room_a": a, "room_b": b, "delta_pa": d,
                     "clause": "식약처고시 제2024-87호 별표1 제4호 하목",
                     "note": "참고치(guidance value). hard fail 아님"},
    }]


def run(cur, run_id, facility_id, rule) -> list[dict]:
    cfg = rule.get("config", {}) or {}
    if not cfg.get("enabled"):
        return []
    return evaluate(load_adjacency(cur, run_id), load_rooms(cur, run_id), cfg,
                    load_pressure_rels(cur, run_id))
