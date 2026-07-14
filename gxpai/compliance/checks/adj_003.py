# -*- coding: utf-8 -*-
"""ADJ-003 — **화장실이 작업소, 보관소와 직접 연결됨** (major). 신규 (2026-07-14).

## 조문 (드물게 명확하다 — "가급적" 도 "적절히" 도 없다)

    고시 별표17 제3.6호 부대구역 나목
      "갱의실, 수세시설 및 화장실은 쉽게 사용할 수 있어야 하고 사용자 수에 적합하여야 한다.
       **화장실은 작업소 또는 보관소와 직접 연결되지 아니하여야 한다.**"

    → 법제처 HWP, 고시 XML, 식약처 PDF **세 출처에서 동일**하게 확인했다.
      (근거가 여럿이면 대조한다 — 그게 우리 규칙이다)

GMP 조문 대부분은 "가급적", "적절히", "타당한" 같은 말로 여지를 남긴다. 그래서 우리가
혼자 판정하면 안 되고 대부분 보류로 둔다. **그런데 이 조문은 다르다** — *"직접 연결되지
아니하여야 한다"* 는 **금지**다. 도면만으로 판정할 수 있는 몇 안 되는 조문이다.

## 왜 지금 구현할 수 있게 됐나

'직접 연결' = **문으로 바로 이어짐**이다. 벽을 맞댄 것은 연결이 아니다.
문 인접(동선 그래프)이 생기기 전에는 이 규칙을 만들 수 없었다.
`화장실 → 복도 → 작업소` 는 **위반이 아니다.** 복도를 거치면 '직접'이 아니다.

## 무엇을 '작업소', '보관소'로 보는가 (정직하게: 이건 우리 해석이다)

조문은 '작업소', '보관소'가 무엇인지 정의하지 않는다. 우리는 이렇게 본다:
  작업소 = **청정등급이 부여된 실** 또는 **분진, 특수 공정실**(regime = contain/hazard)
  보관소 = 이름에 보관, 창고, 저장이 든 실

부대구역(갱의실, 탈의실, 샤워실, 전실, 복도)은 **작업소가 아니다.**
화장실이 갱의실과 붙어 있는 것은 오히려 정상이다(작업원이 옷 갈아입기 전에 들른다).

→ 이 해석은 **보류**다. 발주처, 컨설턴트가 확인해야 한다.
"""
from __future__ import annotations

from ._model import AdjPair, RoomView, load_adjacency, load_rooms
from ._regime import CONTAIN, HAZARD, head_form, resolve_regime

TOILET_WORDS = ("화장실", "변소", "세면장", "W.C", "WC", "TOILET")
STORE_WORDS = ("보관", "창고", "저장")
# 부대구역 — 작업소가 아니다. 화장실과 붙어 있어도 정상이다.
ANNEX_WORDS = ("갱의", "탈의", "샤워", "전실", "에어락", "에어록", "복도", "통로",
               "휴게", "식당", "사무", "화장실", "세면", "계단", "승강기", "엘리베이터")


def _has(name: str | None, words) -> bool:
    n = (name or "").replace(" ", "").upper()
    return any(w.replace(" ", "").upper() in n for w in words)


def is_toilet(name: str | None) -> bool:
    return _has(name, TOILET_WORDS)


def is_annex(name: str | None) -> bool:
    """부대구역(갱의, 샤워, 전실, 복도 등). 작업소가 아니다.

    `캡슐충전실` 이 '전실'을 품고 있다고 **부대구역으로 오인**하면
      **화장실이 작업소와 직결된 명백한 위반(별표17 3.6 나)을 놓친다.**
      `_regime.is_airlock` 과 같은 병이었다 — 머리말로 갈라야 한다.
    """
    from ._regime import NOT_AIRLOCK, head_form

    h = head_form(name)
    if not h:
        return False
    # `충전실`, `변전실` 은 부대구역이 아니다 (머리말로 가른다)
    if any(h.endswith(w.upper()) for w in NOT_AIRLOCK):
        return False
    return any(w.replace(" ", "").upper() in h for w in ANNEX_WORDS)


def classify_target(r: RoomView, overrides: dict | None = None) -> str | None:
    """이 방이 조문이 말하는 '작업소' 인가 '보관소' 인가. 아니면 None."""
    if is_toilet(r.name):
        return None                      # 화장실끼리 붙은 건 문제가 아니다
    if _has(r.name, STORE_WORDS) and not is_annex(r.name):
        return "보관소"
    if is_annex(r.name):
        return None                      # 부대구역은 작업소가 아니다
    regime = r.regime or resolve_regime(r.name, r.grade, overrides, r.room_no)[0]
    if regime in (CONTAIN, HAZARD):
        return "작업소"                   # 분진, 특수 공정실
    if r.grade:
        return "작업소"                   # 청정등급이 부여된 실
    return None


def evaluate(adj: list[AdjPair], rooms: list[RoomView], cfg: dict) -> list[dict]:
    overrides = cfg.get("regime_overrides", {}) or {}
    view = {r.room_no: r for r in rooms if r.room_no}

    # '직접 연결' = **문으로 바로 이어짐**. 벽을 맞댄 것은 연결이 아니다.
    #   문 데이터를 못 믿는 도면(via_door 가 전부 NULL)에서는 **판정하지 않는다.**
    #   벽 인접으로 대신 판정하면 '벽 하나 사이의 화장실'을 전부 위반으로 찍는다 — 거짓 위반이다.
    #   조문이 금지하는 건 '맞닿음'이 아니라 '직접 연결'이다.
    has_door = any(p.via_door is not None for p in adj)
    if not has_door:
        return []

    out: list[dict] = []
    seen: set[frozenset] = set()
    for pair in adj:
        if not pair.via_door:
            continue                     # 문으로 이어지지 않았다 = '직접 연결' 아님
        a, b = pair.a, pair.b
        if a not in view or b not in view:
            continue
        ra, rb = view[a], view[b]

        for t, o in ((ra, rb), (rb, ra)):
            if not is_toilet(t.name):
                continue
            kind = classify_target(o, overrides)
            if not kind:
                continue
            key = frozenset((t.room_no, o.room_no))
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "severity": "major",
                "rooms": sorted((t.room_no, o.room_no)),
                "message": (f"화장실 직접 연결: {t.room_no}({t.name}) 가 "
                            f"{o.room_no}({o.name}) [{kind}] 와 **문으로 직접** 이어져 있음. "
                            f"고시 별표17 3.6 나목은 이를 금지한다"),
                "evidence": {
                    "toilet": t.room_no, "target": o.room_no, "target_kind": kind,
                    "target_grade": o.grade, "target_regime": o.regime,
                    "via_door": True,
                    "clause": "식약처고시 별표17 제3.6호 부대구역 나목",
                    "원문": "화장실은 작업소 또는 보관소와 직접 연결되지 아니하여야 한다",
                    "근거": "문 인접(동선). 복도를 거치면 '직접 연결'이 아니므로 위반 아님",
                    "판단": "보류. '작업소'의 범위는 우리 해석 — 발주처 확인 필요",
                },
            })
    return out


def run(cur, run_id, facility_id, rule) -> list[dict]:
    cfg = rule.get("config", {}) or {}
    if not cfg.get("enabled"):
        return []
    return evaluate(load_adjacency(cur, run_id), load_rooms(cur, run_id), cfg)
