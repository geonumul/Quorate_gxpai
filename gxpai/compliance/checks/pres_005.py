# -*- coding: utf-8 -*-
"""PRES-005 — **청정실 경계에 차압계가 없다** (major). 신규 (2026-07-14).

## 조문 (도면만으로 판정할 수 있다)

    고시 별표1 제4호 너목
      "**청정실 및 필요한 경우 아이솔레이터와 주변구역 사이에 차압계가 설치되어야 한다.**
       오염관리전략에서 차압에 대한 설정값 및 중요도를 고려하여야 한다.
       중요하다고 확인된 차압은 **연속적으로 모니터하고 기록**하여야 한다."

    (법제처 HWP · 고시 XML · 식약처 PDF 대조 확인)

차압을 설정만 하고 **재지 않으면 유지·기록할 방법이 없다.** 그래서 차압계가 의무다.

## 도면이 이미 답을 갖고 있다

    `Air Flow 10Pa` / `Air Flow 15Pa`   차압이 **설정된** 구간
    `Air Flow no차압`                   차압계 설치가 **요구되지 않는** 위치 (도면 범례 3번)
    `차압계-아날로그`(21) · `차압계-디지털`(7)   **실제로 설치된 차압계**

★우리는 이걸 통째로 못 보고 있었다 — 참고도면은 같은 평면도에 겹을 얹은 **시트가 6장**인데
  우리는 **시트 2(차압흐름도)만** 잘라 쓰고 있었다. 차압계는 시트 3에 있다.

## 범위를 좁히지 않으면 **거짓 위반 6건**이 난다 (실제로 그럴 뻔했다)

차압이 설정됐는데 차압계가 없는 구간이 6개 있었다. 그런데 파 보니 **전부 CNC↔NC** 였다 —
탈의실·갱의실·전실, 즉 갱의 체인 입구다.

    조문은 "**청정실** 및 … 주변구역 사이"라고 한다.
    CNC(관리되나 등급 미분류)·NC(미분류)는 **청정실이 아니다.**

→ **한쪽 이상이 청정실(등급 D 이상)인 구간만** 판정한다.
   그러고 나니 위반 0건 — **설계가 맞았다.**
   범위를 느슨하게 잡았으면 멀쩡한 설계에 거짓 위반 6건을 냈을 것이다.
"""
from __future__ import annotations

from ._model import PressureRel, RoomView, load_pressure_rels, load_rooms

DEFAULT_RANK = {"A": 5, "B": 4, "C": 3, "D": 2, "CNC": 1, "NC": 0}


def evaluate(rels: list[PressureRel], rooms: list[RoomView], cfg: dict) -> list[dict]:
    rank = cfg.get("grade_rank") or DEFAULT_RANK
    # 이 등급 이상이면 조문이 말하는 '청정실'이다 (기본 D)
    clean_min = int(cfg.get("clean_min_rank", rank.get("D", 2)))

    view = {r.room_no: r for r in rooms if r.room_no}

    # ★차압계 도면이 없는 시설이면 **판정하지 않는다.**
    #   has_gauge 가 전부 NULL = "차압계 정보가 없다"이지 "차압계가 없다"가 아니다.
    #   혼동하면 전 구간이 거짓 위반이 된다. (rels=[] vs None 함정과 같은 종류다)
    if not any(r.has_gauge is not None for r in rels):
        return []

    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for r in rels:
        if r.approx or not r.room_high_no or not r.room_low_no:
            continue
        if r.has_gauge:
            continue                       # 차압계가 있다
        # 도면이 "여긴 차압계 필요 없다"고 명시한 구간 (범례 3번)
        if r.setpoint_pa is None:
            continue
        hi, lo = view.get(r.room_high_no), view.get(r.room_low_no)
        if not hi or not lo:
            continue

        # ★조문의 범위: **청정실**과 주변구역 사이. CNC·NC 끼리는 대상이 아니다.
        ranks = [rank.get(x.grade) for x in (hi, lo) if x.grade]
        if not ranks or max(ranks) < clean_min:
            continue

        key = tuple(sorted((hi.room_no, lo.room_no)))
        if key in seen:
            continue
        seen.add(key)

        out.append({
            "severity": "major",
            "rooms": list(key),
            "message": (
                f"차압계 없음: {hi.room_no}({hi.name}, 등급 {hi.grade}) ↔ "
                f"{lo.room_no}({lo.name}, 등급 {lo.grade}) 구간은 차압 {r.setpoint_pa:g}Pa 로 "
                f"**설정**돼 있으나 **차압계가 없다**. 설정만 하고 재지 않으면 유지·기록할 수 없다"),
            "evidence": {
                "room_high": hi.room_no, "room_low": lo.room_no,
                "grades": [hi.grade, lo.grade],
                "setpoint_pa": r.setpoint_pa,
                "arrow_layer": r.layer,
                "clause": "식약처고시 별표1 제4호 너목",
                "원문": ("청정실 및 필요한 경우 아이솔레이터와 주변구역 사이에 차압계가 "
                       "설치되어야 한다. … 중요하다고 확인된 차압은 연속적으로 모니터하고 "
                       "기록하여야 한다"),
                "적용범위": ("**한쪽 이상이 청정실(등급 D 이상)** 인 구간만. "
                         "CNC·NC 끼리(탈의실·갱의실 등)는 조문이 말하는 '청정실'이 아니다"),
                "판단": "보류. 발주처 확인 필요 (차압계 도면에 안 그려졌을 뿐일 수도 있다)",
            },
        })
    return out


def run(cur, run_id, facility_id, rule) -> list[dict]:
    cfg = rule.get("config", {}) or {}
    if not cfg.get("enabled"):
        return []
    return evaluate(load_pressure_rels(cur, run_id), load_rooms(cur, run_id), cfg)
