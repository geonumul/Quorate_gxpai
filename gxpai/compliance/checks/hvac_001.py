# -*- coding: utf-8 -*-
"""HVAC-001 - **환기 횟수가 자사 기준에 못 미친다** (major). 신규 (2026-07-14).

## 대표님이 "제일 중요하다"고 하신 것 (1차 미팅 2026-07-09)

> "**제일 중요한 게 환기 횟수**라는 개념이 있어요. 이 방 안에 공기는
>  **1시간에 몇 번 순환**을 해야 된다는 **조건이 꼭 있거든요.**
>  그 조건을 맞추려면 이 방 안에 전체 **풍량이 필요해요. 풍량을 무조건 줘야 돼요.**
>  근데 차압도 중요하다고 그랬잖아요. 그럼 **풍량을 환기횟수에 맞게 주고**,
>  이 두 개 **차압을 맞추기 위해서 여기서 빼 나가는 거예요.**"

## [주의]그런데 **법정 수치로 판정하지 않는다**

흔히 인용되는 수치(Class 100(A) **600회/hr**, Class 10,000(B) **20회/hr**)는
「GMP 조사평가 매뉴얼」이 인용한 **구 KGMP 해설서**에만 있다.
**현행 고시(별표1, 2023 개정, PIC/S Annex 1 기반)에는 환기 횟수 수치가 없다.**
(별표1의 '환기' 언급 6건을 전수 확인했다 - 전부 EO 멸균 환기 등 다른 맥락)
현행은 **오염관리전략(CCS)** 으로 타당성을 입증하게 한다.

→ **차압(PRES-002)과 똑같이 간다.** 실사관은 *"법정 수치를 지켰나"* 가 아니라
  ***"당신 회사가 정한 기준을 지켰나"*** 를 본다.
  **자사 기준서(프로파일)** 의 값과 대조한다. 법정 수치를 박아 넣지 않는다.

## 계산

    환기 횟수(회/hr) = 급기 풍량(CMH) ÷ (바닥 면적(㎡) × 천장고(m))

**천장고가 없으면 판정하지 않는다.** 추측해서 채우지 않는다.
(발주처 확인요청서 G항 - 천장고 + 자사 환기 기준)

## 이 값이 믿을 만한가 - **근거 셋이 일치한다**

  ① 도면이 단위를 명시했다 (천정기구배치도 `B-ZONE` 의 `풍량(CMH)`)
  ② 물리적으로 말이 된다 (천장고 2.7m 가정 시 B 60, C 32, D 19 회/hr)
  ③ **등급이 높을수록 환기가 많다** - 단조 감소한다 (B 60 > C 32 > D 19 > NC 8.5)

  ③은 급기 귀속을 **반경 최근접**에서 **방 경계 안**으로 바꾸고 나서야 나왔다.
    그전엔 `NC 3㎡ 방에 1,697 CMH(187회/hr)` 같은 값이 있었다.
"""
from __future__ import annotations

from ._model import RoomView, load_rooms


def evaluate(rooms: list[RoomView], cfg: dict) -> list[dict]:
    # 자사 기준서. 없으면 판정하지 않는다 - 법정 수치를 대신 쓰지 않는다.
    spec = cfg.get("ach_by_grade") or {}
    height = cfg.get("ceiling_height_m")
    if not spec or not height:
        return []

    out: list[dict] = []
    for r in rooms:
        if not r.grade or r.airflow_cmh is None or not r.area_m2:
            continue
        need = spec.get(r.grade)
        if need is None:
            continue
        volume = r.area_m2 * float(height)
        if volume <= 0:
            continue
        ach = r.airflow_cmh / volume
        if ach >= float(need):
            continue
        out.append({
            "severity": "major",
            "rooms": [r.room_no],
            "message": (
                f"환기 횟수 미달: {r.room_no}({r.name}, 등급 {r.grade}) 은 "
                f"{ach:.1f}회/hr 인데 자사 기준은 {need}회/hr 이다 "
                f"(급기 {r.airflow_cmh:,.0f} CMH ÷ {r.area_m2:.1f}㎡ × {height}m)"),
            "evidence": {
                "room": r.room_no, "grade": r.grade,
                "ach": round(ach, 1), "required": need,
                "airflow_cmh": r.airflow_cmh, "area_m2": r.area_m2,
                "ceiling_height_m": height,
                "근거": ("**발주처 자사 기준서**(프로파일). 법정 수치가 아니다 - "
                       "현행 고시에는 환기 횟수 수치가 없다"),
                "판단": "보류. 천장고와 자사 기준이 발주처가 준 값인지 확인 필요",
            },
        })
    return out


def run(cur, run_id, facility_id, rule) -> list[dict]:
    cfg = rule.get("config", {}) or {}
    if not cfg.get("enabled"):
        return []
    return evaluate(load_rooms(cur, run_id), cfg)
