# -*- coding: utf-8 -*-
"""ADJ-002 — **갱의실을 우회해 청정실로 들어갈 수 있다** (critical). 구현 (2026-07-14).

## 조문 (예전엔 "검수대기"로 비워 뒀다. 찾았다.)

    고시 별표1 제4호 가목 (무균의약품 제조)
      "무균의약품 제조는 적절한 청정실에서 수행되어야 하며, 이 청정실은
       **작업원의 경우 에어락 역할을 하는 갱의실을 통해 이동해야 하며**
       장비와 원자재는 에어락을 통해 이동해야 한다."

    → 법제처 HWP · 고시 XML 대조 확인.

예전 규칙 파일에는 clause 가 `"별표17 / PIC-S Annex 1 - 검수대기"` 라고만 적혀 있었다.
**조문 번호도 원문도 없이 규칙을 만들어 두었던 것이다.** 근거를 찾아 채웠다.

## 어떻게 판정하나 — 그래프에서 갱의실을 **빼 본다**

조문이 요구하는 것: *비청정 구역에서 청정실로 가려면 **반드시** 갱의실(에어락)을 지나야 한다.*

    → 동선 그래프(문으로 이어진 방)에서 **갱의실·에어락·전실 노드를 전부 제거**한다.
      그래도 청정실이 비청정 구역과 이어져 있으면, **갱의실을 우회하는 길이 있다.**

이 방법이 좋은 이유: "갱의실이 있느냐"가 아니라 **"우회로가 없느냐"** 를 본다.
갱의실을 아무리 잘 갖춰 놔도 옆에 뒷문이 하나 있으면 소용이 없다. 그 뒷문을 찾는다.

## 전제 (없으면 판정하지 않는다)

  ① **문 인접(동선)** — 벽 맞댐으로 하면 안 된다. 벽은 지나갈 수 없다.
  ② **청정등급** — 어디가 청정실이고 어디가 비청정인지 알아야 한다.

기준 시설(내용고형제) 도면에는 **등급 표기가 0건**이라 지금은 판정 불가다.
참고도면(무균)에는 등급이 49개 있어 실제로 돌아간다.
"""
from __future__ import annotations

from collections import deque

from ._model import AdjPair, RoomView, load_adjacency, load_rooms

# 갱의실·에어락 — 조문이 말하는 '통과해야 하는 관문'
GOWN_WORDS = ("갱의", "탈의", "에어락", "에어록", "air lock", "airlock", "전실",
              "샤워", "손세정", "손씻", "세면")
# 청정등급 순위 (클수록 깨끗)
DEFAULT_RANK = {"A": 5, "B": 4, "C": 3, "D": 2, "CNC": 1, "NC": 0}


def is_gowning(name: str | None, words=GOWN_WORDS) -> bool:
    """★`무균 **충전실**` 은 '전실'을 품고 있지만 관문이 아니다.

    관문으로 오인하면 그래프에서 그 노드를 **끊어 버려** 우회로를 못 찾는다 —
    **진짜 위반을 숨긴다.** 시험이 잡았다.
    """
    from ._regime import NOT_AIRLOCK
    n = (name or "").replace(" ", "").lower()
    if any(w in n for w in NOT_AIRLOCK):
        return False
    return any(w.replace(" ", "").lower() in n for w in words)


def evaluate(adj: list[AdjPair], rooms: list[RoomView], cfg: dict) -> list[dict]:
    rank = cfg.get("grade_rank") or DEFAULT_RANK
    # 이 등급 이상이면 '청정실'로 본다 (기본 D — 청정등급이 부여된 작업실)
    clean_min = int(cfg.get("clean_min_rank", rank.get("D", 2)))
    words = cfg.get("gowning_words") or GOWN_WORDS

    view = {r.room_no: r for r in rooms if r.room_no}

    # ★전제 ①: 문 인접(동선)이 있어야 한다. 벽은 지나갈 수 없다.
    doors = [p for p in adj if p.via_door]
    if not doors:
        return []
    # ★전제 ②: 등급이 있어야 어디가 청정실인지 안다.
    if not any(r.grade for r in rooms):
        return []

    def rk(r: RoomView) -> int | None:
        return rank.get(r.grade) if r.grade else None

    clean, dirty = set(), set()
    for no, r in view.items():
        if is_gowning(r.name, words):
            continue                      # 갱의실은 관문이지 목적지도 출발지도 아니다
        k = rk(r)
        if k is None:
            continue                      # 등급 미상 → 어느 쪽인지 모른다. 판정에서 뺀다
        (clean if k >= clean_min else dirty).add(no)

    if not clean or not dirty:
        return []

    # ★갱의실·에어락을 **그래프에서 빼고** 이웃 관계를 만든다.
    #   그래도 청정실 ↔ 비청정 구역이 이어지면 = 갱의실을 우회하는 길이 있다.
    nbr: dict[str, set[str]] = {}
    for p in doors:
        a, b = p.a, p.b
        if a not in view or b not in view:
            continue
        if is_gowning(view[a].name, words) or is_gowning(view[b].name, words):
            continue                      # 관문을 지나는 간선은 끊는다
        nbr.setdefault(a, set()).add(b)
        nbr.setdefault(b, set()).add(a)

    # ★**뚫린 문**을 보고한다. (청정실, 비청정실) 쌍을 전부 보고하면 안 된다.
    #
    #   참고도면에서 처음엔 10건이 나왔다. 그런데 파 보니 실제 원인은 **문 2개**뿐이었다:
    #       F2I06(바이알 세척 및 멸균실, D) ↔ F2G01(일반복도, NC)
    #       F2I12(세척및무균준비실, D)      ↔ F2I13(Auto clave 기계실, NC)
    #   나머지 8건은 그 두 문을 통해 갈 수 있는 방들을 **중복해서 센 것**이었다.
    #
    #   설계자가 고쳐야 하는 것은 **그 문**이다. 문 하나를 막으면 여러 건이 한꺼번에 사라진다.
    #   그러니 문(뚫린 간선)을 단위로 보고하고, 그 문 때문에 노출되는 청정실을 함께 적는다.
    breach: dict[tuple[str, str], dict] = {}
    for start in sorted(clean):
        seen = {start}
        q = deque([(start, [start])])
        while q:
            cur, path = q.popleft()
            for nx in sorted(nbr.get(cur, ())):
                if nx in seen:
                    continue
                seen.add(nx)
                p2 = path + [nx]
                if nx in dirty:
                    edge = (cur, nx)                # ★비청정으로 넘어가는 **그 문**
                    b = breach.setdefault(edge, {"exposed": set(), "route": p2})
                    b["exposed"].add(start)
                    if len(p2) < len(b["route"]):   # 가장 짧은 경로를 보여준다
                        b["route"] = p2
                    continue                        # 더 깊이 안 간다
                q.append((nx, p2))

    out: list[dict] = []
    for (inner, outer), b in sorted(breach.items()):
        ri, ro = view[inner], view[outer]
        exposed = sorted(b["exposed"])
        route = " → ".join(f"{n}({view[n].name})" for n in b["route"])
        others = [e for e in exposed if e != inner]
        also = (f" 이 문 하나 때문에 {len(others)}개 청정실이 더 노출된다: "
                f"{', '.join(f'{e}({view[e].name})' for e in others[:4])}"
                f"{' 외' if len(others) > 4 else ''}") if others else ""
        out.append({
            "severity": "critical",
            "rooms": [inner, outer],
            "message": (
                f"갱의실 우회 문: {ri.room_no}({ri.name}, 등급 {ri.grade}) ↔ "
                f"{ro.room_no}({ro.name}, 등급 {ro.grade}) 가 **갱의실·에어락 없이 문으로 직접** "
                f"이어져 있음.{also}"),
            "evidence": {
                "breach_door": [inner, outer],
                "inner_grade": ri.grade, "outer_grade": ro.grade,
                "노출된_청정실": exposed,
                "경로_예": route,
                "clause": "식약처고시 별표1 제4호 가목",
                "원문": ("이 청정실은 작업원의 경우 에어락 역할을 하는 갱의실을 통해 "
                       "이동해야 하며 장비와 원자재는 에어락을 통해 이동해야 한다"),
                "판정방법": ("동선 그래프에서 갱의실·에어락 노드를 **제거**해도 청정실이 "
                         "비청정 구역과 이어지면 = 우회로가 있다. "
                         "'갱의실이 있느냐'가 아니라 **'우회로가 없느냐'** 를 본다"),
                "판단": ("보류. 발주처 확인 필요 — 물자 전용 문·패스박스·비상구는 "
                       "**작업원 동선이 아닐 수 있다**"),
            },
        })
    return out


def run(cur, run_id, facility_id, rule) -> list[dict]:
    cfg = rule.get("config", {}) or {}
    if not cfg.get("enabled"):
        return []
    return evaluate(load_adjacency(cur, run_id), load_rooms(cur, run_id), cfg)
