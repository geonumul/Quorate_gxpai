# -*- coding: utf-8 -*-
"""DB(PostgreSQL) → Neo4j 멱등 적재.

로드맵: T2.2.2
멱등(R-E3): 재실행 시 해당 run 노드/엣지를 삭제 후 재생성. 모든 노드에 run_id + facility_id.
PRESSURE_OVER 는 화살표 방향 의미 확정(S-1) 전이므로 이번엔 만들지 않는다(정직성).
"""
from __future__ import annotations

from ..core.db import connect, neo4j_driver


def build(facility_id: str, run_id: str | None = None) -> dict:
    with connect() as conn, conn.cursor() as cur:
        if run_id is None:
            cur.execute("SELECT id FROM run WHERE facility_id=%s ORDER BY started_at DESC, id DESC LIMIT 1",
                        (facility_id,))
            row = cur.fetchone()
            run_id = row[0] if row else None
        if not run_id:
            raise ValueError("실행(run) 없음. 먼저 ingest 하세요.")
        cur.execute("SELECT name FROM facility WHERE id=%s", (facility_id,))
        frow = cur.fetchone()
        fac_name = frow[0] if frow else facility_id

        cur.execute("""SELECT id, room_no, name, floor FROM room
                       WHERE run_id=%s AND room_no IS NOT NULL""", (run_id,))
        rooms = [{"id": a, "room_no": b, "name": c, "floor": d} for a, b, c, d in cur.fetchall()]
        cur.execute("SELECT room_a, room_b, method FROM room_adjacency WHERE run_id=%s", (run_id,))
        adj = cur.fetchall()
        cur.execute("SELECT ahu_id, floor FROM ahu WHERE run_id=%s", (run_id,))
        ahus = cur.fetchall()

    driver = neo4j_driver()
    try:
        with driver.session() as s:
            # 멱등: 이 run 의 기존 노드 제거
            s.run("MATCH (n {run_id:$r}) DETACH DELETE n", r=run_id)
            # Facility 도 run_id 로 키를 잡는다(모든 노드에 run_id 불변식). 예전엔 facility_id 로만
            # MERGE 해 노드를 run 간 공유했고, 다른 run 을 재빌드할 때 DETACH DELETE 가 이 공유
            # 노드를 지워 앞 run 의 HAS 엣지를 끊는 교차오염이 있었다(수정됨).
            s.run("MERGE (f:Facility {facility_id:$fid, run_id:$r}) SET f.name=$name",
                  fid=facility_id, name=fac_name, r=run_id)

            floors = sorted({r["floor"] for r in rooms if r["floor"]})
            for fl in floors:
                s.run("""MATCH (f:Facility {facility_id:$fid, run_id:$r})
                         MERGE (fl:Floor {facility_id:$fid, run_id:$r, name:$fl})
                         MERGE (f)-[:HAS]->(fl)""", fid=facility_id, r=run_id, fl=fl)

            for rm in rooms:
                s.run("""MATCH (fl:Floor {facility_id:$fid, run_id:$r, name:$fl})
                         MERGE (rm:Room {facility_id:$fid, run_id:$r, db_id:$id})
                           SET rm.room_no=$no, rm.name=$nm, rm.floor=$fl
                         MERGE (fl)-[:HAS]->(rm)""",
                      fid=facility_id, r=run_id, fl=rm["floor"], id=rm["id"],
                      no=rm["room_no"], nm=rm["name"])

            for a, b, method in adj:
                s.run("""MATCH (x:Room {facility_id:$fid, run_id:$r, db_id:$a})
                         MATCH (y:Room {facility_id:$fid, run_id:$r, db_id:$b})
                         MERGE (x)-[e:ADJACENT_TO]->(y) SET e.method=$m""",
                      fid=facility_id, r=run_id, a=a, b=b, m=method)

            for ahu_id, floor in ahus:
                s.run("""MERGE (a:Ahu {facility_id:$fid, run_id:$r, ahu_id:$aid})
                           SET a.floor=$fl""",
                      fid=facility_id, r=run_id, aid=ahu_id, fl=floor)

            counts = s.run(
                """MATCH (n {run_id:$r}) RETURN labels(n)[0] AS label, count(*) AS n
                   ORDER BY label""", r=run_id).data()
            rels = s.run(
                "MATCH ({run_id:$r})-[e]->() RETURN count(e) AS n", r=run_id).single()["n"]
    finally:
        driver.close()

    return {"run_id": run_id, "nodes": {c["label"]: c["n"] for c in counts},
            "relationships": rels}
