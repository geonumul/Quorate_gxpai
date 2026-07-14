# -*- coding: utf-8 -*-
"""실패한 방 하나를 골라, **그 방을 둘러싼 선분이 어느 레이어에 있는지** 전수조사한다.

벽 레이어를 이름으로 짐작하지 않는다. 방 주변에서 **세어본다.**
"""
import math, sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8")
import ezdxf
from gxpai.core.config import raw_dir
from gxpai.core.db import connect

doc = ezdxf.readfile(str(next(p for p in (raw_dir()/"f_1ae3a266").iterdir() if "평면" in p.name)))
TARGET = sys.argv[1] if len(sys.argv) > 1 else "3301"
R = 6000.0   # 방 라벨 주변 6m

with connect() as c, c.cursor() as cur:
    cur.execute("SELECT id FROM run WHERE facility_id='f_1ae3a266' ORDER BY started_at DESC LIMIT 1")
    rid = cur.fetchone()[0]
    cur.execute("SELECT room_no, name, plan_x, plan_y FROM room WHERE run_id=%s AND room_no=%s",
                (rid, TARGET))
    no, nm, px, py = cur.fetchone()
print(f"{no} {nm}  @({px:.0f},{py:.0f})  반경 {R:.0f}mm 안의 축-나란 선분")

stats = defaultdict(lambda: [0, 0.0])

def add(lay, ax, ay, bx, by):
    if math.hypot((ax+bx)/2 - px, (ay+by)/2 - py) > R:
        return
    L = math.hypot(bx-ax, by-ay)
    if L < 200:                      # 짧은 잡선은 벽이 아니다
        return
    if abs(bx-ax) > 1 and abs(by-ay) > 1:   # 축에 안 나란하면 벽이 아니다
        return
    s = stats[lay]; s[0] += 1; s[1] += L

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
for lay, (n, L) in sorted(stats.items(), key=lambda kv: -kv[1][1])[:14]:
    print(f"   {lay!r:34} 선분 {n:4d}  총길이 {L/1000:7.1f}m")
