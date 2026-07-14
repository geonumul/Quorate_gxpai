# -*- coding: utf-8 -*-
"""청정등급을 **구역(zone)** 으로 채운다. **신규 (2026-07-14).**

## 내가 크게 오해하고 있었다

나는 "내용고형제 도면에 등급 표기가 0건" 을 **도면 결함, 최대 병목** 이라고 썼다.
발주처 확인요청서에도 "등급 표기가 있는 도면을 달라" 고 적었다. **틀렸다.**

1차 미팅(2026-07-09) 대표님 말씀:

    Q(geonumul) "그럼 이게 방별로 그레이드 등급이 매겨져 있는 거요?"
    A(대표님)   "**방별로는 안 하고** … 아까 그 **구역** 말씀"
    Q          "그럼 그런 건 따로 적혀 있지는 않은 거예요?"
    A          "**그렇죠.** 이제 그건 **나중에**, 이 방을 1, 2, 3, 4로 가든 a, b, c로 하든 쫙 해놓고
                '**a부터 b는 그레이드 B, d부터 f까지는 그레이드 C**' 이렇게 해주면
                [AI]가 알아서 그렇게 가게끔 해야죠.
                근데 **보통 그레이드는 이렇게 붙어 있는 방끼리 가요** - 그래야 동선 안에서
                그레이드가 바뀌잖아요. 그럼 예를 들면 **버퍼존을 준다든지 도어를 줘서 차단**하고
                넘어가고…"

**등급이 도면에 없는 것은 정상이다.** 등급은 사람이 **구역으로 묶어 지정**하는 것이고,
엔진은 그걸 받아서 채워야 한다. 그 기능이 없었다. 이제 만든다.

## 제형이 기본 등급을 정한다 (같은 미팅)

    내용고형제 (알약, 캡슐)          → **D**
    액제(마시는), 연고, 크림          → **C**
    주사제 (인체에 투입되는 것)      → **B 이상**
    일반 사무공간 (블랙존)          → 관리 안 함 (차압, 공조 없음)

## 채우는 순서 (앞의 것이 이긴다)

    1. drawing          도면에 적혀 있으면 그것이 진실이다 (참고도면 Grade 레이어 49건)
    2. zone             프로파일 `grade_zones` 에서 사람이 지정한 것
    3. product_default  제형 기본값. **단, 청정 관리 대상인 방에만.**
                        복도, 기계실, 보관소, 사무실은 등급을 주지 않는다(NC/관리 제외)

**추정이 아니다 - 사람이 준 값이거나 미팅에서 확정된 값이다.**
그래도 `grade_source` 로 출처를 남겨, 리포트에서 무엇이 어디서 왔는지 보이게 한다.
"""
from __future__ import annotations

from ..compliance.checks._regime import NEUTRAL, is_corridor, resolve_regime

# 제형 → 기본 등급 (1차 미팅 2026-07-09 대표님)
PRODUCT_GRADE = {
    "osd": "D", "내용고형제": "D", "정제": "D", "캡슐": "D", "고형제": "D",
    "액제": "C", "연고": "C", "크림": "C", "외용제": "C",
    "주사제": "B", "무균": "B", "sterile": "B", "injectable": "B",
}


def grade_from_product(product_type: str | None) -> str | None:
    if not product_type:
        return None
    p = product_type.replace(" ", "").lower()
    for k, g in PRODUCT_GRADE.items():
        if k in p:
            return g
    return None


def _expand(spec) -> set[str]:
    """구역 지정을 방번호 집합으로 편다.

    받는 꼴:
        ["4401", "4402"]                 방번호 목록
        {"from": "4401", "to": "4409"}   범위 (문자열 비교. 같은 자릿수여야 한다)
        ["4401", {"from":"4501","to":"4508"}]   섞어 써도 된다
    """
    out: set[str] = set()
    items = spec if isinstance(spec, list) else [spec]
    for it in items:
        if isinstance(it, dict) and "from" in it and "to" in it:
            lo, hi = str(it["from"]), str(it["to"])
            # 숫자 방번호면 숫자로, 아니면 문자열로 범위를 편다
            if lo.isdigit() and hi.isdigit() and len(lo) == len(hi):
                out |= {str(n).zfill(len(lo)) for n in range(int(lo), int(hi) + 1)}
            else:
                out.add(lo)
                out.add(hi)
        elif it is not None:
            out.add(str(it))
    return out


def apply_grade_zones(rooms: list[dict], profile: dict) -> dict:
    """도면에 등급이 없는 방을 **구역 지정 → 제형 기본값** 순으로 채운다.

    rooms 를 제자리에서 고치고, 출처별 개수를 돌려준다.
    """
    zones = profile.get("grade_zones") or {}
    default_grade = profile.get("default_grade") or grade_from_product(
        profile.get("product_type"))
    overrides = (profile.get("pressure_regime") or {}).get("overrides") or {}

    # 방번호 → 등급 (사람이 지정한 구역)
    by_no: dict[str, str] = {}
    for grade, spec in zones.items():
        for no in _expand(spec):
            by_no[no] = grade

    counts = {"drawing": 0, "zone": 0, "product_default": 0, "none": 0}
    for r in rooms:
        no = r.get("room_no")
        if r.get("grade"):
            r.setdefault("grade_source", "drawing")
            counts["drawing"] += 1
            continue

        if no and no in by_no:
            r["grade"] = by_no[no]
            r["grade_source"] = "zone"
            counts["zone"] += 1
            continue

        # 제형 기본값은 **청정 관리 대상 방에만** 준다.
        #   복도, 기계실, 보관소, 사무실은 등급을 주지 않는다 - 대표님: "일반 사무 공간,
        #   거기는 차압 관리 안 해요. 공조를 안 해요."
        #   여기서 regime 을 재활용한다(중립 = 관리 대상 아님).
        if default_grade:
            name = r.get("name")
            regime = r.get("regime") or resolve_regime(name, None, overrides, no)[0]
            if regime != NEUTRAL and not is_corridor(name):
                r["grade"] = default_grade
                r["grade_source"] = "product_default"
                counts["product_default"] += 1
                continue

        counts["none"] += 1
    return counts
