# -*- coding: utf-8 -*-
"""급기(SA) − 리턴(RA) = 차압. 대표님이 알려준 메커니즘을 **검증**한다.

1차 미팅(2026-07-09) 대표님:
  "**풍량을 환기횟수에 맞게 주고**, 이 두 개 **차압을 맞추기 위해서 여기서 빼 나가는 거예요.**
   공기를 많이 뺄 거냐 적게 뺄 거냐, 거기에 맞춰서 **차압이 형성**될 거"

→ 급기 − 리턴 > 0  이면 **양압**(공기가 밀려나감)
   급기 − 리턴 < 0  이면 **음압**(공기가 빨려들어옴)

방마다 절대압력(Pa)이 적혀 있으니 **대조할 수 있다.** 근거가 둘이면 반드시 대조한다.
"""
import math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
import ezdxf, re
from gxpai.core.config import raw_dir
from gxpai.core.db import connect

NUM = re.compile(r"^\d{2,6}(?:\.\d+)?$")

def read_flows(fname, layer):
    doc = ezdxf.readfile(str(raw_dir()/"f_c783b865"/fname))
    out = []
    for e in doc.modelspace():
        if e.dxftype() not in ("TEXT", "MTEXT"):
            continue
        if e.dxf.layer != layer:
            continue
        t = (e.plain_text() if e.dxftype() == "MTEXT" else e.dxf.text).strip()
        if NUM.match(t):
            p = e.dxf.insert
            out.append((p.x, p.y, float(t)))
    return out

sa = read_flows("천정기구도.dxf", "풍량")     # 급기 (천장 HEPA/디퓨저)
ra = read_flows("리턴풍도도.dxf", "풍량")     # 리턴 (빼내는 공기)
print(f"■ 급기(SA) {len(sa)}개 · 합 {sum(v for *_ , v in sa):,.0f} CMH")
print(f"■ 리턴(RA) {len(ra)}개 · 합 {sum(v for *_ , v in ra):,.0f} CMH")

with connect() as c, c.cursor() as cur:
    cur.execute("SELECT id FROM run WHERE facility_id='f_c783b865' ORDER BY started_at DESC LIMIT 1")
    rid = cur.fetchone()[0]
    cur.execute("""SELECT room_no,name,pressure_pa,area_m2,COALESCE(pres_x,plan_x),COALESCE(pres_y,plan_y)
                     FROM room WHERE run_id=%s AND plan_x IS NOT NULL AND room_no IS NOT NULL""", (rid,))
    rooms = cur.fetchall()

R = 4000.0
def attach(flows):
    d = {}
    for fx, fy, v in flows:
        cand = [(math.hypot(rx-fx, ry-fy), no) for no, _n, _p, _a, rx, ry in rooms]
        if not cand: continue
        dist, no = min(cand)
        if dist <= R:
            d[no] = d.get(no, 0.0) + v
    return d

SA, RA = attach(sa), attach(ra)
print(f"\n■ 급기·리턴이 **둘 다** 붙은 방 (급기−리턴 vs 실제 압력 대조)")
print(f"  {'방':7} {'이름':22} {'급기':>7} {'리턴':>7} {'차이':>7} {'실제Pa':>7}  일치?")
agree = disagree = 0
for no, nm, pa, area, *_ in sorted(rooms):
    if no not in SA or no not in RA or pa is None:
        continue
    diff = SA[no] - RA[no]
    # 양압이면 diff>0 이어야, 음압이면 diff<0 이어야 한다 (복도 0Pa 기준)
    ok = (diff > 0 and pa > 0) or (diff < 0 and pa < 0) or (abs(diff) < 50 and abs(pa) < 1)
    agree += ok; disagree += (not ok)
    print(f"  {no:7} {(nm or '')[:20]:22} {SA[no]:>7,.0f} {RA[no]:>7,.0f} {diff:>+7,.0f} {pa:>6.0f}Pa  {'✔' if ok else '★불일치'}")
print(f"\n  일치 {agree} · 불일치 {disagree}")
