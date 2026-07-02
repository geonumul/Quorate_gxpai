# -*- coding: utf-8 -*-
"""온톨로지 스키마 v1 - 노드/엣지 타입 (버전 관리).

로드맵: T2.2.1
모든 노드에 facility_id 속성 = 다중 시설 격리 키.
노드: Facility, Floor, Room, Ahu, Equipment
엣지: (Facility)-[:HAS]->(Floor)-[:HAS]->(Room),
      (Room)-[:ADJACENT_TO]->(Room)  (무방향; a<b 로 1회만)
      (Room)-[:PRESSURE_OVER]->(Room) (Stage 2 방향 확정 후)
      (Room)-[:SERVED_BY]->(Ahu), (Room)-[:CONTAINS]->(Equipment)
"""
SCHEMA_VERSION = "1"

NODES = ["Facility", "Floor", "Room", "Ahu", "Equipment"]
EDGES = ["HAS", "ADJACENT_TO", "PRESSURE_OVER", "SERVED_BY", "CONTAINS"]
