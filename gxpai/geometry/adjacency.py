# -*- coding: utf-8 -*-
"""인접행렬 - 방 경계가 없을 때의 최근접 k 근사.

로드맵: T2.1.2
현 데이터는 방 경계 폴리곤이 없다(XREF 벽체 미수령). 그래서 boundary 교차 대신
같은 층 내 최근접 k개로 인접을 근사한다(method='nearest'). 경계 확보 시
buffer 교차(method='polygon')로 승격 예정. 무방향 간선, room_a < room_b 로 저장(R-G8).
"""
from __future__ import annotations

import math

from ..core.db import connect


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
