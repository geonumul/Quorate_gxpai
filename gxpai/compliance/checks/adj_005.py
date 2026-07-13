# -*- coding: utf-8 -*-
"""ADJ-005 — **A·B 등급으로 연결되는 에어락에 인터락이 없다** (critical). 신규 (2026-07-14).

## 조문 — **현행판과 구판이 다르다.** 구판을 인용했으면 이 규칙을 못 만들었다.

    현행 (법제처) 고시 별표1 제4호 파목
      "이송해치 및 에어락(물품 및 작업원용)의 경우 입구용과 출구용 문이
       **동시에 열려서는 안 된다.**
       **A등급과 B등급 구역으로 연결되는 에어락의 경우 인터락 시스템을 사용해야 한다.**
       C등급과 D등급 청정실로 연결되는 에어락의 경우, 최소한 시각경고시스템 및
       필요한 경우 음성경고시스템 …"

    구판 (식약처 게시판 · **인용금지**)
      "… 인터락 시스템(interlocking system) **또는** 시각적 및 청각적 …
       경보장치가 가동되어야 한다."

★구판은 "인터락 **또는** 경보장치"로 뭉뚱그렸다. **현행은 등급별로 갈라놨다** —
  A/B 는 인터락 **필수**, C/D 는 시각경고면 된다.
  구판을 인용했으면 **A/B 의 인터락 의무를 놓쳤을 것이다.**
  근거가 둘이면 반드시 대조한다.

## 왜 인터락인가

에어락의 두 문이 **동시에 열리면 에어락이 아니다** — 청정실이 비청정 구역에 그대로 뚫린다.
경고등은 사람이 무시할 수 있지만, 인터락은 물리적으로 막는다.
그래서 가장 깨끗한 A/B 구역에는 경고가 아니라 **인터락**을 요구한다.

## 도면에서 (참고도면 2층)

레이어 `u-interlock` 의 **2점 선** 24개 = 에어락의 두 문을 잇는 연결선.
17개 방에 붙어 있는데, **갱의 체인(y=48,083)에는 하나도 없다**:

    F2I19 갱의 전실 (C)  → F2I20 무균 갱의실 (**B**)                    ← 인터락 없음
    F2I21 무균 전실 (B)  → F2I23 무균 복도 (**B**) · F2I22 충진실 (**B**)  ← 인터락 없음

⚠ **보류 · 발주처 확인 필요**: 도면에 안 그려졌을 뿐 실제로는 설치될 수도 있다.
"""
from __future__ import annotations

from ._model import AdjPair, RoomView, load_adjacency, load_rooms
from ._regime import AIRLOCK_WORDS as _AW
from ._regime import is_airlock as _is_airlock

AIRLOCK_WORDS = _AW
DEFAULT_RANK = {"A": 5, "B": 4, "C": 3, "D": 2, "CNC": 1, "NC": 0}


def is_airlock(name: str | None, words=AIRLOCK_WORDS) -> bool:
    """★`무균 **충전실**` 은 '전실'을 품고 있지만 에어락이 아니다. _regime 이 걸러 준다."""
    return _is_airlock(name, words)


def evaluate(adj: list[AdjPair], rooms: list[RoomView], cfg: dict) -> list[dict]:
    rank = cfg.get("grade_rank") or DEFAULT_RANK
    # 인터락이 **의무**가 되는 최저 등급 (기본 B — 조문은 "A등급과 B등급 구역")
    lock_min = int(cfg.get("interlock_min_rank", rank.get("B", 4)))
    words = cfg.get("airlock_words") or AIRLOCK_WORDS

    view = {r.room_no: r for r in rooms if r.room_no}

    # ★인터락 도면이 없는 시설이면 판정하지 않는다.
    #   interlock_count 가 전부 NULL = "인터락 정보가 없다"이지 "인터락이 없다"가 아니다.
    #   혼동하면 **전 에어락이 거짓 위반**이 된다.
    if not any(r.interlock_count is not None for r in rooms):
        return []
    # 문 인접(동선)이 없으면 '연결'을 알 수 없다.
    doors = [p for p in adj if p.via_door]
    if not doors:
        return []

    out: list[dict] = []
    for no, r in sorted(view.items()):
        if not is_airlock(r.name, words):
            continue
        if (r.interlock_count or 0) > 0:
            continue                       # 인터락이 있다
        # 이 에어락이 문으로 이어진 방들 중 A·B 등급이 있나
        high = []
        for p in doors:
            o = p.b if p.a == no else (p.a if p.b == no else None)
            if not o or o not in view:
                continue
            g = view[o].grade
            if g and rank.get(g, -1) >= lock_min:
                high.append(o)
        if not high:
            continue                       # C/D 이하만 연결 → 시각경고면 된다(조문상)

        names = ", ".join(f"{h}({view[h].name}, {view[h].grade})" for h in sorted(high))
        out.append({
            "severity": "critical",
            "rooms": [no] + sorted(high),
            "message": (
                f"인터락 없음: {no}({r.name}) 은 **{names}** 로 이어지는 에어락인데 "
                f"인터락 표시가 없다. 조문은 **A·B 등급으로 연결되는 에어락에 인터락 시스템**을 "
                f"요구한다(경고등만으로는 부족하다)"),
            "evidence": {
                "airlock": no, "airlock_grade": r.grade,
                "connected_high": sorted(high),
                "interlock_count": r.interlock_count,
                "clause": "식약처고시 별표1 제4호 파목",
                "원문": ("이송해치 및 에어락(물품 및 작업원용)의 경우 입구용과 출구용 문이 "
                       "동시에 열려서는 안 된다. **A등급과 B등급 구역으로 연결되는 에어락의 "
                       "경우 인터락 시스템을 사용해야 한다.** C등급과 D등급 청정실로 연결되는 "
                       "에어락의 경우, 최소한 시각경고시스템 …"),
                "구판과_다름": ("구판(식약처 게시판·인용금지)은 '인터락 **또는** 경보장치'로 "
                            "뭉뚱그렸다. 현행은 등급별로 갈라놨다 — A/B 는 인터락 **필수**. "
                            "구판을 인용했으면 이 의무를 놓쳤을 것이다"),
                "판단": "보류. 발주처 확인 필요 — 도면에 안 그려졌을 뿐 실제로는 설치될 수도 있다",
            },
        })
    return out


def run(cur, run_id, facility_id, rule) -> list[dict]:
    cfg = rule.get("config", {}) or {}
    if not cfg.get("enabled"):
        return []
    return evaluate(load_adjacency(cur, run_id), load_rooms(cur, run_id), cfg)
