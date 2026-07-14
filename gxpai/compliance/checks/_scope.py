# -*- coding: utf-8 -*-
"""규칙의 **적용 범위(제형)** — 무균 조문으로 완제 시설을 판정하면 안 된다. 신규 (2026-07-14).

## 가장 심각한 구조적 결함이었다

전수 감사에서 나왔다. 법규 코퍼스를 검색해 **직접 확인했다**:

    별표17 (완제의약품)에서
        '청정등급' → **0건**
        '차압계'   → **0건**
        '인터락'   → **0건**

    그런데 우리 규칙 5종이 **별표1(무균)** 조문을 근거로 **완제 시설(내용고형제)** 을
    판정하고 있었다.

특히 ADJ-002 의 조문은 **문장 첫머리에 적용범위가 박혀 있다**:

    별표1 제4호 가목
      "**무균의약품 제조는** 적절한 청정실에서 수행되어야 하며, 이 청정실은 …"

그리고 ADJ-005 의 조문은 **"A등급과 B등급 구역으로 연결되는 에어락"** 이라고 한정한다.
내용고형제의 기본 등급은 **D** 다(1차 미팅 대표님). **A, B 구역이 아예 없다.**
그런데 `interlock_min_rank` 를 낮추는 순간 **조문에 없는 의무를 만들어내는 판정**이 된다.

## 왜 이게 우리가 가장 경계하는 실수인가

우리는 "근거 없는 관행을 법인 것처럼 판정하지 않는다"를 철칙으로 삼았고,
환기 횟수(구 KGMP 해설서)와 4대 동선(조문 없음)을 그 이유로 안 만들었다.

**그런데 정작 만든 규칙들이 제형이 다른 조문을 갖다 쓰고 있었다.** 같은 종류의 잘못이다.
게이트가 잠겨 있어 사고가 안 났을 뿐이다.

## 어떻게 고치나

규칙마다 `applies_to` 를 둔다. 시설의 `product_type` 과 안 맞으면 **판정하지 않는다**
(0건이 아니라 **"적용 대상 아님"**).

    별표1  → 무균의약품 (주사제, 점안제 등)
    별표17 → 완제의약품 (내용고형제, 액제, 연고 …) 우리 기준 시설
    별표15 → 원료의약품
    안전에 관한 규칙 별표1 → **제형 무관** (모든 의약품 제조소)
"""
from __future__ import annotations

# 제형 코드
STERILE = "sterile"      # 무균 (별표1)
FINISHED = "finished"    # 완제 (별표17)  내용고형제, 액제, 연고
API = "api"              # 원료 (별표15)
ANY = "any"              # 제형 무관 (안전에 관한 규칙 별표1, 자사 기준)

# 시설의 product_type 문자열 → 제형 코드
_PRODUCT = {
    "무균": STERILE, "주사": STERILE, "점안": STERILE, "수액": STERILE,
    "sterile": STERILE, "injectable": STERILE,
    "내용고형제": FINISHED, "고형제": FINISHED, "정제": FINISHED, "캡슐": FINISHED,
    "액제": FINISHED, "연고": FINISHED, "크림": FINISHED, "외용": FINISHED,
    "완제": FINISHED, "osd": FINISHED, "finished": FINISHED,
    "원료": API, "api": API,
}


def product_scope(product_type: str | None) -> str | None:
    """시설의 제형 → 제형 코드. 모르면 None(= 판정하지 않는다)."""
    if not product_type:
        return None
    p = product_type.replace(" ", "").lower()
    for k, v in _PRODUCT.items():
        if k in p:
            return v
    return None


def applies(rule_cfg: dict, facility_scope: str | None) -> bool:
    """이 규칙을 이 시설에 적용해도 되는가.

    **모르면 적용하지 않는다.** 시설 제형을 모르는데 무균 조문을 들이대면 안 된다.
      다만 `applies_to` 가 아예 없는 규칙(내부 정합성 LBL 등)은 제형과 무관하다.
    """
    scopes = rule_cfg.get("applies_to")
    if not scopes:
        return True                       # 제형과 무관한 규칙 (LBL, PRES-004 …)
    if ANY in scopes:
        return True
    if facility_scope is None:
        return False                      # 시설 제형을 모른다 → 판정하지 않는다
    return facility_scope in scopes


def why_not(rule_cfg: dict, facility_scope: str | None,
            product_type: str | None) -> str:
    """왜 적용하지 않는지 사람이 읽을 문장. 리포트가 '0건'과 구분해서 보여준다."""
    scopes = rule_cfg.get("applies_to") or []
    ko = {STERILE: "무균(별표1)", FINISHED: "완제(별표17)",
          API: "원료(별표15)", ANY: "제형 무관"}
    want = ", ".join(ko.get(s, s) for s in scopes)
    if facility_scope is None:
        return (f"시설의 제형(product_type)을 모른다 → 판정하지 않는다. "
                f"이 규칙은 **{want}** 조문이다")
    return (f"이 규칙은 **{want}** 조문인데, 이 시설은 "
            f"**{ko.get(facility_scope, facility_scope)}**({product_type})다 → 적용 대상 아님")
