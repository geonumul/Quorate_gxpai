# -*- coding: utf-8 -*-
"""참고도면 평면도 블록 안의 **실효 레이어**를 전수조사한다.

"블록 안이 전부 레이어 0 이라 벽만 못 고른다"는 것이 **사실인지** 확인한다.
  사실이 아니면(진짜 레이어 이름이 있으면) 가구를 걸러낼 수 있다.
  지금은 전부 태우고 있어서 **가구선이 방을 잘게 썰었다**(무균 전실 0.8㎡, 갱의실 1.6㎡).
  51/51 은 '숫자가 나왔다'였지 '숫자가 맞다'가 아니었다.
"""
import math, sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
import ezdxf
from gxpai.core.config import raw_dir

doc = ezdxf.readfile(str(raw_dir()/"f_c783b865"/"평면도.dxf"))
stats = defaultdict(lambda: {"n": 0, "len": 0.0, "axis": 0})

def add(lay, ax, ay, bx, by):
    L = math.hypot(bx-ax, by-ay)
    if L < 1: return
    s = stats[lay]; s["n"] += 1; s["len"] += L
    if abs(bx-ax) < 1 or abs(by-ay) < 1: s["axis"] += 1

def walk(cont, mat, plr, d):
    for e in cont:
        t = e.dxftype()
        lay = e.dxf.layer if hasattr(e.dxf, "layer") else "0"
        if lay == "0" and plr: lay = plr
        if t == "INSERT":
            if d >= 5: continue
            b = doc.blocks.get(e.dxf.name)
            if b is None: continue
            m = e.matrix44()
            if mat is not None: m = m @ mat
            walk(b, m, lay, d+1); continue
        def tp(x, y):
            if mat is None: return (x, y)
            p = mat.transform((x, y, 0.0)); return (p.x, p.y)
        if t == "LINE":
            a = tp(e.dxf.start.x, e.dxf.start.y); b_ = tp(e.dxf.end.x, e.dxf.end.y)
            add(lay, a[0], a[1], b_[0], b_[1])
        elif t == "LWPOLYLINE":
            ps = [tp(p[0], p[1]) for p in e.get_points("xy")]
            if e.closed and len(ps) > 2: ps.append(ps[0])
            for i in range(len(ps)-1):
                add(lay, ps[i][0], ps[i][1], ps[i+1][0], ps[i+1][1])

walk(doc.modelspace(), None, None, 0)
print("평면도 안의 실효 레이어별 선분 (긴 것 순)")
print(f"{'레이어':<28} {'선분':>7} {'축나란%':>8} {'총길이m':>10}")
for lay, s in sorted(stats.items(), key=lambda kv: -kv[1]["len"])[:20]:
    print(f"{lay!r:<28} {s['n']:>7} {s['axis']/s['n']*100:>7.1f}% {s['len']/1000:>9.0f}")
