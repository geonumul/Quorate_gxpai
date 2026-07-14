# -*- coding: utf-8 -*-
"""규칙 **미리보기(dry-run)** - 게이트를 열지 않고 무엇이 잡히는지만 본다.

왜 이렇게 하나
  PRES/ADJ 규칙은 `review: unreviewed`(컨설턴트 미검수)다. 동결 게이트 원칙상
  **실제 파이프라인에서 돌리면 안 된다** - 틀린 규칙이 위반 이력을 오염시킨다.
  그러나 "켜면 무엇이 나올지"는 알아야 검수를 요청할 수 있다.
  → 순수 함수 evaluate() 를 DB 데이터로 직접 호출한다. **DB 에 아무것도 쓰지 않는다.**

  python scripts/1_운영/preview_rules.py f_1ae3a266
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8")

from gxpai.compliance.checks import (adj_001, adj_002, adj_003,  # noqa: E402
                                     adj_004, adj_005, pres_001, pres_002,
                                     pres_003, pres_004, pres_005)
from gxpai.compliance.checks import hvac_001  # noqa: E402
from gxpai.compliance.checks._model import (load_adjacency, load_pressure_rels,  # noqa: E402
                                            load_rooms)
from gxpai.compliance.checks._scope import applies, product_scope, why_not  # noqa: E402
from gxpai.core.config import load_profile  # noqa: E402
from gxpai.core.db import connect  # noqa: E402
from gxpai.core import registry  # noqa: E402

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

from gxpai.compliance.checks.adj_003 import is_toilet          # noqa: E402
from gxpai.compliance.checks.adj_004 import is_rest_area        # noqa: E402

linked = [r for r in rels if r.room_high_no and r.room_low_no and not r.approx]
gauged = [r for r in rels if r.has_gauge]
locked = [r for r in rooms if r.interlock_count]
doors = [p for p in adj if p.via_door]
toilets = [r for r in rooms if is_toilet(r.name)]
rests = [r for r in rooms if is_rest_area(r.name) and r.plan_x is not None]
graded = [r for r in rooms if r.grade]
with_pa = [r for r in rooms if r.pressure_pa is not None]

print(f"{facility} / run {run_id}")
print(f"  방 {len(rooms)} (등급 {len(graded)}, 절대압력 {len(with_pa)})")
print(f"  차압관계 {len(rels)} (방 귀속 확정 {len(linked)})")
print(f"  인접 {len(adj)}쌍 (그중 **문으로 이어짐** {len(doors)} - 동선)")
print(f"  화장실 {len(toilets)}, 휴게실/식당(좌표있음) {len(rests)}\n")

CHECKS = [
    ("PRES-001", lambda c: pres_001.evaluate(rels, rooms, c)),
    ("PRES-002", lambda c: pres_002.evaluate(adj, rooms, c, rels)),
    ("PRES-003", lambda c: pres_003.evaluate(rels, adj, rooms, c)),
    ("PRES-004", lambda c: pres_004.evaluate(rels, rooms, c)),
    ("PRES-005", lambda c: pres_005.evaluate(rels, rooms, c)),
    ("ADJ-001", lambda c: adj_001.evaluate(adj, rooms, c)),
    ("ADJ-002", lambda c: adj_002.evaluate(adj, rooms, c)),
    ("ADJ-003", lambda c: adj_003.evaluate(adj, rooms, c)),
    ("ADJ-004", lambda c: adj_004.evaluate(adj, rooms, c)),
    ("ADJ-005", lambda c: adj_005.evaluate(adj, rooms, c)),
    ("HVAC-001", lambda c: hvac_001.evaluate(rooms, c)),
]

# 제형 게이트 - **무균 조문으로 완제 시설을 판정하면 안 된다.**
#   코퍼스 확인: 별표17(완제)에 '청정등급', '차압계', '인터락' 조문이 **0건**이다.
_fac = registry.get_facility(facility) or {}
_pt = _fac.get("product_type") or (load_profile(_fac.get("profile_id") or "") or {}).get("product_type")
_scope = product_scope(_pt)
print(f"  제형: {_pt or '미상'} → {_scope or '판정 불가'}\n")

for rid, fn in CHECKS:
    rule = rules.get(rid, {})
    cfg = dict(rule.get("config") or {})
    if not applies(cfg, _scope):
        print(f"{rid}  ⊘ **적용 대상 아님**")
        print(f"     {why_not(cfg, _scope, _pt)}\n")
        continue
    cfg["enabled"] = True                       # 미리보기에서만 켠다(DB 미기록)
    try:
        found = fn(cfg)
    except Exception as exc:                    # noqa: BLE001
        print(f"{rid}: 실행 오류 - {exc}")
        continue

    gate = "잠김" if not (rule.get("config") or {}).get("enabled") else "켜짐"
    print(f"{rid}  [{rule.get('review')}, 게이트 {gate}]  → {len(found)}건")
    for v in found[:6]:
        print(f", {v['message']}")
    if len(found) > 6:
        print(f"     … 외 {len(found) - 6}건")
    if not found:
        # "위반이 없다" 와 "검사할 게 없다" 는 **완전히 다르다.**
        #   구분하지 않으면 리포트를 읽는 사람이 "검사했는데 깨끗하다"로 오해한다.
        why = []
        if rid in ("PRES-001", "ADJ-001") and not graded:
            why.append("등급 데이터 없음(도면에 표기 없음)")
        if rid == "PRES-002" and not with_pa:
            why.append("절대압력(Pa) 없음")
        if rid == "PRES-003" and not linked and not with_pa:
            why.append("화살표 방 귀속, 절대압력 둘 다 없음")
        if rid == "PRES-004" and not (linked and with_pa):
            why.append("화살표 방 귀속, 절대압력 둘 다 있어야 대조 가능")
        if rid == "HVAC-001":
            if not (cfg.get("ach_by_grade") and cfg.get("ceiling_height_m")):
                why.append("**자사 환기 기준 + 천장고가 없다** - 발주처가 줘야 한다. "
                           "법정 수치(A 600회/hr)는 구 KGMP 해설서다. 쓰지 않는다")
            elif not [r for r in rooms if r.airflow_cmh is not None]:
                why.append("급기 풍량 없음")
        if rid == "PRES-005" and not gauged:
            why.append("차압계 도면 없음 - '차압계가 없다'와 혼동하면 안 된다")
        if rid == "ADJ-005" and not locked:
            why.append("인터락 도면 없음 - '인터락이 없다'와 혼동하면 안 된다")
        if rid in ("ADJ-003", "ADJ-004") and not doors:
            why.append("문 인접(동선) 없음 - 문 데이터를 못 믿는 도면")
        if rid == "ADJ-003" and not toilets:
            why.append("도면에 **화장실이 없다** → 판정 대상 0")
        if rid == "ADJ-004" and not rests:
            why.append("도면에 좌표 있는 **휴게실, 식당이 없다** → 판정 대상 0")
        if why:
            print(f"     (판정 불가: {', '.join(why)})")
        else:
            print("     (검사했고 위반 없음)")
    print()
