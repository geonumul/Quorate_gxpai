# -*- coding: utf-8 -*-
"""급기−리턴의 **부호** = 이웃 대비 상대 압력. (첫 모델이 틀려서 다시 세운 것)

첫 모델: "급기 − 리턴 > 0 = 양압" → 19방 중 10방이 불일치. **틀렸다.**
  방에는 **이웃에서 넘어오는 공기**가 있다. 복도는 리턴이 급기보다 많은 게 정상이다
  (다른 방에서 흘러든 공기를 복도에서 뽑아낸다).

맞는 모델: 순유출(+) → 이웃보다 고압 / 순유입(−) → 이웃보다 저압.
"""
import math, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8")
import ezdxf
from gxpai.core.config import raw_dir
from gxpai.core.db import connect

NUM = re.compile(r"^\d{2,6}(?:\.\d+)?$")
def flows(fn):
    doc = ezdxf.readfile(str(raw_dir()/"f_c783b865"/fn))
    return [(e.dxf.insert.x, e.dxf.insert.y, float(e.dxf.text.strip()))
            for e in doc.modelspace()
            if e.dxftype() == "TEXT" and e.dxf.layer == "풍량" and NUM.match(e.dxf.text.strip())]

sa, ra = flows("천정기구도.dxf"), flows("리턴풍도도.dxf")
with connect() as c, c.cursor() as cur:
    cur.execute("SELECT id FROM run WHERE facility_id='f_c783b865' ORDER BY started_at DESC LIMIT 1")
    rid = cur.fetchone()[0]
    cur.execute("""SELECT room_no,name,pressure_pa,COALESCE(pres_x,plan_x),COALESCE(pres_y,plan_y)
                     FROM room WHERE run_id=%s AND plan_x IS NOT NULL AND room_no IS NOT NULL""",(rid,))
    rooms = cur.fetchall()
    cur.execute("""SELECT ra.room_no, rb.room_no FROM room_adjacency adj
                     JOIN room ra ON ra.id=adj.room_a JOIN room rb ON rb.id=adj.room_b
                    WHERE adj.run_id=%s AND adj.via_door""",(rid,))
    doors = cur.fetchall()

def attach(fl, R=4000.0):
    d = {}
    for fx, fy, v in fl:
        cand = [(math.hypot(rx-fx, ry-fy), no) for no,_n,_p,rx,ry in rooms]
        dist, no = min(cand)
        if dist <= R: d[no] = d.get(no, 0.0) + v
    return d
SA, RA = attach(sa), attach(ra)
pa_of = {no: p for no,_n,p,*_ in rooms}
nbr = {}
for a,b in doors:
    nbr.setdefault(a,[]).append(b); nbr.setdefault(b,[]).append(a)

print(f"급기 {len(sa)}개({sum(v for *_,v in sa):,.0f} CMH), 리턴 {len(ra)}개({sum(v for *_,v in ra):,.0f} CMH)")
print(f"\n  {'방':7} {'이름':20} {'급기-리턴':>10} {'이 방':>7} {'이웃평균':>8}  판정")
ok = bad = hold = 0
for no,nm,pa,_x,_y in sorted(rooms):
    if no not in SA or no not in RA or pa is None: continue
    ns = [pa_of[x] for x in nbr.get(no,[]) if pa_of.get(x) is not None]
    if not ns: continue
    avg = sum(ns)/len(ns); diff = SA[no]-RA[no]; dp = pa-avg
    if abs(dp) < 2 or abs(diff) < 100:
        v, hold = "보류(차이 미미)", hold+1
    elif (diff > 0) == (dp > 0):
        v, ok = "", ok+1
    else:
        v, bad = "불일치", bad+1
    print(f"  {no:7} {(nm or '')[:18]:20} {diff:>+10,.0f} {pa:>6.0f}Pa {avg:>7.1f}Pa  {v}")
print(f"\n  일치 {ok}, 불일치 {bad}, 보류 {hold}")
