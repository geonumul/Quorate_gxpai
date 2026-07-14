# -*- coding: utf-8 -*-
"""DOOR 레이어, 문 블록의 기하를 본다. 벽 구멍을 막을 '문턱선'을 만들 수 있는가?"""
import sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
import ezdxf
from gxpai.core.config import raw_dir

f = next(p for p in (raw_dir() / "f_1ae3a266").iterdir() if "평면" in p.name)
doc = ezdxf.readfile(str(f))
msp = doc.modelspace()

print("DOOR 레이어 엔티티 종류 (모델스페이스 최상위)")
t = Counter(e.dxftype() for e in msp if e.dxf.layer.startswith("DOOR"))
print("  ", dict(t))

print("\n문 블록 INSERT 의 레이어, 크기 (샘플)")
DOORBLK = ("Panel Door", "SD(", "SD ", "양개")
n = 0
xs, ys = [], []
for e in msp.query("INSERT"):
    if any(e.dxf.name.startswith(d) or d in e.dxf.name for d in DOORBLK):
        n += 1
        if n <= 6:
            print(f"   {e.dxf.name!r:20} 레이어={e.dxf.layer!r:14} "
                  f"@({e.dxf.insert.x:.0f},{e.dxf.insert.y:.0f}) rot={e.dxf.rotation:g}")
        b = doc.blocks.get(e.dxf.name)
        if b is not None:
            pts = []
            for be in b:
                if be.dxftype() == "LINE":
                    pts += [(be.dxf.start.x, be.dxf.start.y), (be.dxf.end.x, be.dxf.end.y)]
            if pts:
                xs.append(max(p[0] for p in pts) - min(p[0] for p in pts))
                ys.append(max(p[1] for p in pts) - min(p[1] for p in pts))
print(f"   문 블록 INSERT 총 {n}개")
if xs:
    print(f"   블록 크기(가로) 중앙값 ~{sorted(xs)[len(xs)//2]:.0f}mm  "
          f"(세로) ~{sorted(ys)[len(ys)//2]:.0f}mm")

print("\n문 블록의 정의 안 기하 (Panel Door 11)")
b = doc.blocks.get("Panel Door 11")
if b:
    c = Counter(e.dxftype() for e in b)
    print("  ", dict(c))
    for e in list(b)[:8]:
        if e.dxftype() == "LINE":
            print(f"   LINE ({e.dxf.start.x:.0f},{e.dxf.start.y:.0f}) → "
                  f"({e.dxf.end.x:.0f},{e.dxf.end.y:.0f})  레이어={e.dxf.layer!r}")
        elif e.dxftype() == "ARC":
            print(f"   ARC  중심({e.dxf.center.x:.0f},{e.dxf.center.y:.0f}) r={e.dxf.radius:.0f} "
                  f"{e.dxf.start_angle:.0f}°~{e.dxf.end_angle:.0f}°  레이어={e.dxf.layer!r}")
