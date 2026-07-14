# -*- coding: utf-8 -*-
"""ADJ-004 — **휴게실, 식당이 다른 구역과 분리되지 않음** (major). 신규 (2026-07-14).

## 조문

    고시 별표17 제3.6호 부대구역 **가목**
      "**휴게실과 식당은 다른 구역과 분리되어 있어야 한다.**"

    → 법제처 HWP, 고시 XML, 식약처 PDF 세 출처에서 동일 확인.

## '분리'는 세 단계 중 **가장 강한 것**이다 (2010 시설기준 안내서 p.25)

    분리(分離)  별개 건물 권장 + **전용 출입구** + **별도 공조**   ← 이 조문이 요구하는 것
    구획(區劃)  벽, 칸막이로 나눔. **공조는 공유 가능**
    구분(區分)  선, 간격으로 나눔

즉 휴게실, 식당은 단순히 벽으로 막힌 정도가 아니라 **작업 구역과 떨어져 있어야** 한다.

## 우리가 도면에서 확인할 수 있는 것 / 없는 것 (정직하게)

  확인 가능: 휴게실, 식당이 **작업소, 보관소와 문으로 바로 이어지는가**
             → 이어져 있으면 '분리'가 아니다. 명백한 위반이다.
  확인 불가: **별도 공조**인가 (공조 계통도가 필요하다)
             → 이건 판정하지 않는다. 리포트에 "확인 필요"로 남긴다.

**우리는 '분리 아님'을 증명할 수는 있어도 '분리 맞음'을 증명할 수는 없다.**
그래서 위반이 0건이라도 *"분리 확인됨"* 이라고 쓰지 않는다. *"직접 연결은 없음"* 이라고 쓴다.

## 현재 데이터 상태 (2026-07-14)

기준 시설에 휴게실이 2개(4111, 4112) 있으나 **차압도에만 있고 평면도에 없다**
(좌표가 없어 경계, 인접을 못 구한다. LBL-002 로 이미 보고되고 있다).
→ 지금은 **판정 불가**. 평면도에 휴게실이 그려진 도면이 오면 이 규칙이 켜진다.
   로직은 합성 데이터로 완성해 두었다(tests/test_annex_rules.py).
"""
from __future__ import annotations

from ._model import AdjPair, RoomView, load_adjacency, load_rooms
from .adj_003 import classify_target, is_toilet

# 별표17 3.6 가목이 지목하는 방
REST_WORDS = ("휴게", "식당", "구내식당", "카페테리아", "다과")


def is_rest_area(name: str | None) -> bool:
    n = (name or "").replace(" ", "")
    return any(w in n for w in REST_WORDS)


def evaluate(adj: list[AdjPair], rooms: list[RoomView], cfg: dict) -> list[dict]:
    """휴게실, 식당이 작업소, 보관소와 **문으로 직접** 이어지면 위반."""
    overrides = cfg.get("regime_overrides", {}) or {}
    view = {r.room_no: r for r in rooms if r.room_no}

    # 문 데이터를 못 믿는 도면에서는 판정하지 않는다.
    # 벽 인접으로 대신하면 '벽 하나 사이의 휴게실'을 전부 위반으로 찍는다 — 거짓 위반이다.
    if not any(p.via_door is not None for p in adj):
        return []

    out: list[dict] = []
    seen: set[frozenset] = set()
    for pair in adj:
        if not pair.via_door:
            continue
        a, b = pair.a, pair.b
        if a not in view or b not in view:
            continue
        for rest, other in ((view[a], view[b]), (view[b], view[a])):
            if not is_rest_area(rest.name):
                continue
            if is_rest_area(other.name) or is_toilet(other.name):
                continue                  # 휴게실↔식당, 휴게실↔화장실은 문제가 아니다
            kind = classify_target(other, overrides)
            if not kind:
                continue
            key = frozenset((rest.room_no, other.room_no))
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "severity": "major",
                "rooms": sorted((rest.room_no, other.room_no)),
                "message": (f"휴게실, 식당 분리 위반: {rest.room_no}({rest.name}) 가 "
                            f"{other.room_no}({other.name}) [{kind}] 와 **문으로 직접** 이어져 있음. "
                            f"고시 별표17 3.6 가목은 '다른 구역과 분리'를 요구한다"),
                "evidence": {
                    "rest_area": rest.room_no, "target": other.room_no, "target_kind": kind,
                    "via_door": True,
                    "clause": "식약처고시 별표17 제3.6호 부대구역 가목",
                    "원문": "휴게실과 식당은 다른 구역과 분리되어 있어야 한다",
                    "분리의_뜻": ("2010 시설기준 안내서 p.25 — 분리 = 별개 건물 권장 + 전용 출입구 "
                               "+ **별도 공조**. 구획(벽, 칸막이)보다 강한 요구다"),
                    "한계": ("우리는 '문으로 이어짐'만 본다. **별도 공조인지는 공조 계통도가 있어야 "
                           "알 수 있다** → 위반 0건이어도 '분리 확인됨'이 아니라 '직접 연결 없음'이다"),
                    "판단": "보류. 발주처 확인 필요",
                },
            })
    return out


def run(cur, run_id, facility_id, rule) -> list[dict]:
    cfg = rule.get("config", {}) or {}
    if not cfg.get("enabled"):
        return []
    return evaluate(load_adjacency(cur, run_id), load_rooms(cur, run_id), cfg)
