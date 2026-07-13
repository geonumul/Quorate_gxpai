# -*- coding: utf-8 -*-
"""규칙 **미리보기(dry-run)** — 게이트를 열지 않고 무엇이 잡히는지만 본다.

왜 이렇게 하나
  PRES/ADJ 규칙은 `review: unreviewed`(컨설턴트 미검수)다. 동결 게이트 원칙상
  **실제 파이프라인에서 돌리면 안 된다** — 틀린 규칙이 위반 이력을 오염시킨다.
  그러나 "켜면 무엇이 나올지"는 알아야 검수를 요청할 수 있다.
  → 순수 함수 evaluate() 를 DB 데이터로 직접 호출한다. **DB 에 아무것도 쓰지 않는다.**

  python scripts/preview_rules.py f_1ae3a266
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from gxpai.compliance.checks import (adj_001, pres_001, pres_002,  # noqa: E402
                                     pres_003, pres_004)
from gxpai.compliance.checks._model import (load_adjacency, load_pressure_rels,  # noqa: E402
                                            load_rooms)
from gxpai.core.db import connect  # noqa: E402

facility = sys.argv[1] if len(sys.argv) > 1 else "f_1ae3a266"
rules = {r["id"]: r for r in yaml.safe_load(
    Path("rules/gmp_osd_v1.yaml").read_text(encoding="utf-8"))["rules"]}

with connect() as conn, conn.cursor() as cur:
    cur.execute(
        "SELECT id FROM run WHERE facility_id=%s ORDER BY started_at DESC LIMIT 1",
        (facility,))
    row = cur.fetchone()
    if not row:
        sys.exit(f"run 이 없습니다: {facility}")
    run_id = row[0]

    rooms = load_rooms(cur, run_id)
    rels = load_pressure_rels(cur, run_id)
    adj = load_adjacency(cur, run_id)

linked = [r for r in rels if r.room_high_no and r.room_low_no and not r.approx]
graded = [r for r in rooms if r.grade]
with_pa = [r for r in rooms if r.pressure_pa is not None]

print(f"■ {facility} / run {run_id}")
print(f"  방 {len(rooms)} (등급 {len(graded)} · 절대압력 {len(with_pa)})")
print(f"  차압관계 {len(rels)} (방 귀속 확정 {len(linked)})")
print(f"  인접 {len(adj)}쌍\n")

CHECKS = [
    ("PRES-001", lambda c: pres_001.evaluate(rels, rooms, c)),
    ("PRES-002", lambda c: pres_002.evaluate(adj, rooms, c, rels)),
    ("PRES-003", lambda c: pres_003.evaluate(rels, adj, rooms, c)),
    ("PRES-004", lambda c: pres_004.evaluate(rels, rooms, c)),
    ("ADJ-001", lambda c: adj_001.evaluate(adj, rooms, c)),
]

for rid, fn in CHECKS:
    rule = rules.get(rid, {})
    cfg = dict(rule.get("config") or {})
    cfg["enabled"] = True                       # 미리보기에서만 켠다(DB 미기록)
    try:
        found = fn(cfg)
    except Exception as exc:                    # noqa: BLE001
        print(f"▸ {rid}: 실행 오류 — {exc}")
        continue

    gate = "잠김" if not (rule.get("config") or {}).get("enabled") else "켜짐"
    print(f"▸ {rid}  [{rule.get('review')}, 게이트 {gate}]  → {len(found)}건")
    for v in found[:6]:
        print(f"     · {v['message']}")
    if len(found) > 6:
        print(f"     … 외 {len(found) - 6}건")
    if not found:
        why = []
        if rid in ("PRES-001", "ADJ-001") and not graded:
            why.append("등급 데이터 없음(도면에 표기 없음)")
        if rid == "PRES-002" and not with_pa:
            why.append("절대압력(Pa) 없음")
        if rid == "PRES-003" and not linked and not with_pa:
            why.append("화살표 방 귀속·절대압력 둘 다 없음")
        if why:
            print(f"     (판정 불가: {', '.join(why)})")
    print()
