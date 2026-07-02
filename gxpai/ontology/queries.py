# -*- coding: utf-8 -*-
"""표준 질의 함수 - 엔진은 이 모듈만 통해 그래프에 접근한다.

로드맵: T2.2.4
현재 구현(그래프에 있는 것): 방 이웃, 층별 방수, 인접 통계, 고립 방(X-14: 인접 0 = 경계실패 신호).
PRESSURE_OVER/Grade 의존 질의(압력경로, 갱의체인, Grade 경계쌍)는 방향확정·Grade수령 후 추가.
"""
from __future__ import annotations

from ..core.db import neo4j_driver


def _run(cypher, **params):
    driver = neo4j_driver()
    try:
        with driver.session() as s:
            return s.run(cypher, **params).data()
    finally:
        driver.close()


def neighbors(facility_id: str, run_id: str, room_no: str) -> list[dict]:
    """방번호의 인접 방 목록 (무방향)."""
    return _run(
        """MATCH (r:Room {facility_id:$fid, run_id:$r, room_no:$no})-[:ADJACENT_TO]-(n:Room)
           RETURN n.room_no AS room_no, n.name AS name ORDER BY room_no""",
        fid=facility_id, r=run_id, no=room_no)


def floor_room_counts(facility_id: str, run_id: str) -> list[dict]:
    return _run(
        """MATCH (fl:Floor {facility_id:$fid, run_id:$r})-[:HAS]->(rm:Room)
           RETURN fl.name AS floor, count(rm) AS rooms ORDER BY floor""",
        fid=facility_id, r=run_id)


def isolated_rooms(facility_id: str, run_id: str) -> list[dict]:
    """인접 간선이 하나도 없는 방 (X-14: 경계/추출 실패 신호)."""
    return _run(
        """MATCH (rm:Room {facility_id:$fid, run_id:$r})
           WHERE NOT (rm)-[:ADJACENT_TO]-()
           RETURN rm.room_no AS room_no, rm.name AS name, rm.floor AS floor
           ORDER BY room_no""",
        fid=facility_id, r=run_id)


def adjacency_summary(facility_id: str, run_id: str) -> dict:
    rows = _run(
        """MATCH (rm:Room {facility_id:$fid, run_id:$r})
           OPTIONAL MATCH (rm)-[a:ADJACENT_TO]-()
           WITH rm, count(a) AS deg
           RETURN count(rm) AS rooms, sum(deg)/2 AS edges,
                  avg(deg) AS avg_degree, min(deg) AS min_degree, max(deg) AS max_degree""",
        fid=facility_id, r=run_id)
    return rows[0] if rows else {}
