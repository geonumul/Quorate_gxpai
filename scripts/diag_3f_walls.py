# -*- coding: utf-8 -*-
"""3F 가 왜 안 닫히나. **벽 레이어를 아직 다 못 찾았는지** 본다.

방법: 3F 방 라벨이 있는 x구간 안에서, 레이어별로 선분 개수와 '벽스러움'을 센다.
    벽스러움 = 짧고(문/창 아님) 축에 나란한(수평, 수직) 선분의 비율.
"""
import math, sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
import ezdxf
from gxpai.core.config import raw_dir
from gxpai.core.db import connect

doc = ezdxf.readfile(str(next(p for p in (raw_dir()/"f_1ae3a266").iterdir() if "평면" in p.name)))

with connect() as c, c.cursor() as cur:
    cur.execute("SELECT id FROM run WHERE facility_id='f_1ae3a266' ORDER BY started_at DESC LIMIT 1")
    rid = cur.fetchone()[0]
    cur.execute("""SELECT plan_x, plan_y FROM room WHERE run_id=%s AND floor='3F'
                    AND room_no ~ '^3' AND plan_x IS NOT NULL""", (rid,))
    pts = cur.fetchall()
x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
print(f"3F 방 라벨 {len(pts)}개  x {x0:.0f}~{x1:.0f}  y {y0:.0f}~{y1:.0f}")
PAD = 20000

stats = defaultdict(lambda: {"n": 0, "axis": 0, "len": 0.0})

def inside(px, py):
    return x0-PAD <= px <= x1+PAD and y0-PAD <= py <= y1+PAD

def add(lay, ax, ay, bx, by):
    if not (inside(ax, ay) or inside(bx, by)):
        return
    L = math.hypot(bx-ax, by-ay)
    if L < 1:
        return
    s = stats[lay]
    s["n"] += 1; s["len"] += L
    if abs(bx-ax) < 1 or abs(by-ay) < 1:
        s["axis"] += 1

def walk(cont, mat, plr, d):
    for e in cont:
        t = e.dxftype()
        if t == "INSERT":
            if d >= 3: continue
            b = doc.blocks.get(e.dxf.name)
            if b is None: continue
            m = e.matrix44()
            if mat is not None: m = m @ mat
            walk(b, m, e.dxf.layer, d+1); continue
        lay = e.dxf.layer
        if lay == "0" and plr: lay = plr
        def tp(p):
            if mat is None: return (p[0], p[1])
            q = mat.transform((p[0], p[1], 0.0)); return (q.x, q.y)
        if t == "LINE":
            a = tp((e.dxf.start.x, e.dxf.start.y)); b_ = tp((e.dxf.end.x, e.dxf.end.y))
            add(lay, a[0], a[1], b_[0], b_[1])
        elif t == "LWPOLYLINE":
            ps = [tp((p[0], p[1])) for p in e.get_points("xy")]
            if e.closed and len(ps) > 2: ps.append(ps[0])
            for i in range(len(ps)-1):
                add(lay, ps[i][0], ps[i][1], ps[i+1][0], ps[i+1][1])

walk(doc.modelspace(), None, None, 0)

print(f"\n3F 구역 안 레이어별 선분 (축에 나란한 비율 = 벽스러움)")
rows = sorted(stats.items(), key=lambda kv: -kv[1]["n"])[:22]
for lay, s in rows:
    ratio = s["axis"] / s["n"] if s["n"] else 0
    print(f"   {lay!r:30} 선분 {s['n']:5d}  축나란 {ratio*100:5.1f}%  총길이 {s['len']/1000:8.0f}m")
