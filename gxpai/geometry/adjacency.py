# -*- coding: utf-8 -*-
"""인접행렬 - 두 가지 방법.

  polygon (정밀)  : 벽 flood-fill 로 얻은 방 영역이 서로 닿는가 (geometry/boundaries.py)
                    → **이게 정답이다.** ADJ-001·PRES-002/003 이 이 정확도를 요구한다.
  nearest (근사)  : 방 경계를 못 구했을 때의 폴백. 같은 층 최근접 k개.
                    오탐/누락이 있어 규칙을 켜기엔 부족하다.

무방향 간선, room_a < room_b 로 저장(R-G8).
"""
from __future__ import annotations

import math

from ..core.db import connect


def load_pairs(run_id: str, pairs: list[tuple[str, str]], method: str = "polygon",
               door_pairs: list[tuple[str, str]] | None = None) -> int:
    """방번호 쌍 목록을 room_adjacency 에 적재한다(정밀 인접).

    boundaries.build() 가 돌려준 (room_no, room_no) 쌍을 방 id 로 바꿔 넣는다.
    기존 근사 간선은 지운다 — 두 방법이 섞이면 어느 것을 믿을지 알 수 없다.

    door_pairs: **문으로 이어진** 쌍(동선). via_door 로 표시한다.
      None 이면 문 데이터가 없는 도면 → via_door 를 NULL 로 둔다(판정 불가).
      조문은 "작업원 **동선**"·"**연결된** 구역"을 말한다. 벽만 맞대고 문이 없으면
      사람이 오갈 수 없으니 등급이 급변해도 동선 위반이 아니다.
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT room_no, id FROM room WHERE run_id=%s AND room_no IS NOT NULL",
            (run_id,),
        )
        id_by = dict(cur.fetchall())

        edges: set[tuple[int, int]] = set()
        for a, b in pairs:
            ia, ib = id_by.get(a), id_by.get(b)
            if ia is None or ib is None:
                continue                       # 경계는 잡혔는데 방이 없다 = 있을 수 없음
            edges.add((ia, ib) if ia < ib else (ib, ia))

        door_edges: set[tuple[int, int]] | None = None
        if door_pairs is not None:
            door_edges = set()
            for a, b in door_pairs:
                ia, ib = id_by.get(a), id_by.get(b)
                if ia is None or ib is None:
                    continue
                door_edges.add((ia, ib) if ia < ib else (ib, ia))

        cur.execute("DELETE FROM room_adjacency WHERE run_id=%s", (run_id,))
        for a, b in edges:
            via = None if door_edges is None else ((a, b) in door_edges)
            cur.execute(
                """INSERT INTO room_adjacency (run_id, room_a, room_b, method, via_door)
                   VALUES (%s,%s,%s,%s,%s)""",
                (run_id, a, b, method, via),
            )
        conn.commit()
        return len(edges)


def build(run_id: str, k: int = 3, same_floor: bool = True) -> int:
    """최근접 k 인접을 계산해 room_adjacency 에 적재. 적재 간선 수 반환."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT id, floor, plan_x, plan_y FROM room
               WHERE run_id=%s AND plan_x IS NOT NULL AND plan_y IS NOT NULL""",
            (run_id,),
        )
        rooms = cur.fetchall()  # (id, floor, x, y)

        edges: set[tuple[int, int]] = set()
        for i, (rid, floor, x, y) in enumerate(rooms):
            cand = []
            for rid2, floor2, x2, y2 in rooms:
                if rid2 == rid:
                    continue
                if same_floor and floor != floor2:
                    continue
                cand.append((math.hypot(x2 - x, y2 - y), rid2))
            cand.sort()
            for _d, rid2 in cand[:k]:
                a, b = (rid, rid2) if rid < rid2 else (rid2, rid)
                edges.add((a, b))

        cur.execute("DELETE FROM room_adjacency WHERE run_id=%s", (run_id,))
        for a, b in edges:
            cur.execute(
                "INSERT INTO room_adjacency (run_id, room_a, room_b, method) VALUES (%s,%s,%s,'nearest')",
                (run_id, a, b),
            )
        conn.commit()
        return len(edges)
