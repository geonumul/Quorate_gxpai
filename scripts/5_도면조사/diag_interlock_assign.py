# -*- coding: utf-8 -*-
"""인터락 귀속을 의심한다. 작은 전실(0.8~1.2㎡)의 인터락이 옆방으로 샜을 수 있다.

각 인터락 선마다 가까운 방 3개를 거리와 함께 보여 준다.
"""
import math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8")
import ezdxf
from gxpai.core.config import raw_dir
from gxpai.core.db import connect

doc = ezdxf.readfile(str(raw_dir()/"f_c783b865"/"인터락도.dxf"))
lines = []
for e in doc.modelspace():
    if e.dxf.layer == "u-interlock" and e.dxftype() == "LWPOLYLINE":
        pts = [(q[0], q[1]) for q in e.get_points("xy")]
        if len(pts) >= 2:
            lines.append(pts)

with connect() as c, c.cursor() as cur:
    cur.execute("SELECT id FROM run WHERE facility_id='f_c783b865' ORDER BY started_at DESC LIMIT 1")
    rid = cur.fetchone()[0]
    cur.execute("""SELECT room_no,name,grade,area_m2,COALESCE(pres_x,plan_x),COALESCE(pres_y,plan_y)
                     FROM room WHERE run_id=%s AND room_no IS NOT NULL AND plan_x IS NOT NULL""", (rid,))
    rooms = cur.fetchall()

TGT = {"F2I19", "F2I21", "F2I20", "F2I23", "F2I25", "F2I22"}
print("관심 방")
for r in rooms:
    if r[0] in TGT:
        a = f"{r[3]:.1f}㎡" if r[3] else "-"
        print(f"   {r[0]} {r[1]:22} 등급={r[2]:4} {a:8} @({r[4]:.0f},{r[5]:.0f})")

print("\n무균 구역 근처(y 43000~50000) 인터락 선과 가까운 방 3개")
for pts in lines:
    mx = sum(p[0] for p in pts)/len(pts); my = sum(p[1] for p in pts)/len(pts)
    if not (43000 <= my <= 52000 and 300000 <= mx <= 310000):
        continue
    near = sorted(((math.hypot(r[4]-mx, r[5]-my), r[0], r[1], r[2]) for r in rooms))[:3]
    seg = f"({pts[0][0]:.0f},{pts[0][1]:.0f})→({pts[-1][0]:.0f},{pts[-1][1]:.0f})"
    print(f"   선 {seg}  중점({mx:.0f},{my:.0f})")
    for d, no, nm, gr in near:
        print(f"        {d:7.0f}mm  {no} {nm} ({gr})")
