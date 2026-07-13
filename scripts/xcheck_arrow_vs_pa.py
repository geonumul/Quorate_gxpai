# -*- coding: utf-8 -*-
"""★교차검증: 화살표 방향 ↔ 절대압력(Pa) 이 서로 맞는가.

도면에 **두 가지 독립된 근거**가 있다.
  ① 차압 화살표(꼬리=고압 → 화살촉=저압)
  ② 방마다 적힌 절대압력 (예: 15Pa)
둘은 같은 사실을 말해야 한다. 어긋나면 셋 중 하나다.
  (a) 화살표를 방에 잘못 붙였다(우리 버그)  (b) 압력을 잘못 읽었다(우리 버그)
  (c) 도면 자체가 모순이다(발주처 확인 필요)
우리 버그부터 의심한다.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
from gxpai.core.db import connect

fac = sys.argv[1] if len(sys.argv) > 1 else "f_c783b865"
with connect() as conn, conn.cursor() as cur:
    cur.execute("SELECT id FROM run WHERE facility_id=%s ORDER BY started_at DESC LIMIT 1", (fac,))
    run_id = cur.fetchone()[0]
    cur.execute("""
        SELECT hi.room_no, hi.name, hi.pressure_pa, lo.room_no, lo.name, lo.pressure_pa,
               pr.rotation, pr.evidence_x, pr.evidence_y
          FROM pressure_relation pr
          JOIN room hi ON hi.id = pr.room_high
          JOIN room lo ON lo.id = pr.room_low
         WHERE pr.run_id=%s AND pr.approx = false
      ORDER BY hi.room_no""", (run_id,))
    rows = cur.fetchall()

agree = contra = unknown = equal = 0
bad = []
for hno, hname, hpa, lno, lname, lpa, rot, ex, ey in rows:
    if hpa is None or lpa is None:
        unknown += 1; continue
    if hpa > lpa: agree += 1
    elif hpa == lpa: equal += 1
    else:
        contra += 1
        bad.append((hno, hname, hpa, lno, lname, lpa, rot, ex, ey))

print(f"■ {fac} 화살표 {len(rows)}개 (방 귀속 확정)")
print(f"  일치   {agree:3d}  (꼬리쪽 Pa > 화살촉쪽 Pa)")
print(f"  동압   {equal:3d}  (양쪽 Pa 같음 — 판단 불가)")
print(f"  압력없음 {unknown:3d}")
print(f"  ★모순  {contra:3d}\n")
for hno, hname, hpa, lno, lname, lpa, rot, ex, ey in bad:
    print(f"  {hno}({hname},{hpa:g}Pa) →화살표→ {lno}({lname},{lpa:g}Pa)   "
          f"rot={rot:g}  @({ex:.0f},{ey:.0f})")
