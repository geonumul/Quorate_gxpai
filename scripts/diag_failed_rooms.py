# -*- coding: utf-8 -*-
"""실패한 방 7개가 왜 옆방과 같은 공간으로 판정되는지 진단한다.

가설 두 개 중 어느 쪽인지 가린다:
  A) 벽이 실제로 새어 두 방이 이어져 있다 (flood-fill 이 옳고 도면/파라미터가 문제)
  B) 라벨 점이 자기 방이 아니라 옆방/복도에 찍혀 있다 (라벨 위치 문제)

방법: 실패한 방들의 라벨 좌표와, 그 좌표가 속한 덩어리의 면적·중심을 찍는다.
      면적이 '두 방 합친 크기'면 A, '전혀 다른 방 크기'면 B다.
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

import ezdxf
import numpy as np
from ezdxf.math import Matrix44
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from gxpai.geometry.boundaries import _draw_line, _iter_wall_segments  # noqa: E402

DXF = Path(r"D:\14. Dev Project\Quorate\참고도면_원본_CAD\dxf\참고도면(2).dxf")
ROOMNO = re.compile(r"^(F\d[A-Z]\d{2}|\d{4})$")
SKIP_BLOCKS = {"B20260107094054"}
FAILED = {"F2I04", "F2I19", "F2I25", "F2I13", "F2P16", "F2I21", "F2I20",
          "F2I23", "F2I26", "F2I10"}

doc = ezdxf.readfile(str(DXF))
msp = doc.modelspace()
sheet = sorted((e for e in msp.query("INSERT") if e.dxf.name == "2층평면도(260320)"),
               key=lambda e: e.dxf.insert.x)[0]
blk = doc.blocks.get("2층평면도(260320)")
m = Matrix44.chain(
    Matrix44.scale(sheet.dxf.xscale, sheet.dxf.yscale, 1),
    Matrix44.z_rotate(math.radians(sheet.dxf.rotation)),
    Matrix44.translate(sheet.dxf.insert.x, sheet.dxf.insert.y, 0),
)

# 방번호 + (참고용) 이름
nums, names = [], []
for e in blk:
    if e.dxftype() != "TEXT":
        continue
    t = e.dxf.text.strip()
    p = m.transform(e.dxf.insert)
    if ROOMNO.match(t):
        nums.append((t, p.x, p.y))
    else:
        names.append((t, p.x, p.y))

tmp = ezdxf.new()
tsp = tmp.modelspace()


def bake(entity, mat):
    t = entity.dxftype()
    if t == "INSERT":
        if entity.dxf.name in SKIP_BLOCKS:
            return
        inner = doc.blocks.get(entity.dxf.name)
        if inner is None:
            return
        mm = Matrix44.chain(
            Matrix44.scale(entity.dxf.xscale, entity.dxf.yscale, 1),
            Matrix44.z_rotate(math.radians(entity.dxf.rotation)),
            Matrix44.translate(entity.dxf.insert.x, entity.dxf.insert.y, 0), mat)
        for sub in inner:
            bake(sub, mm)
    elif t == "LINE":
        a, b = mat.transform(entity.dxf.start), mat.transform(entity.dxf.end)
        tsp.add_line((a.x, a.y), (b.x, b.y), dxfattribs={"layer": "WALL"})
    elif t == "LWPOLYLINE":
        pts = [mat.transform((p[0], p[1], 0)) for p in entity.get_points()]
        if entity.closed and len(pts) > 2:
            pts.append(pts[0])
        for i in range(len(pts) - 1):
            tsp.add_line((pts[i].x, pts[i].y), (pts[i + 1].x, pts[i + 1].y),
                         dxfattribs={"layer": "WALL"})
    elif t == "ARC":
        c, r = entity.dxf.center, entity.dxf.radius
        a0, a1 = math.radians(entity.dxf.start_angle), math.radians(entity.dxf.end_angle)
        if a1 < a0:
            a1 += 2 * math.pi
        n = max(2, int((a1 - a0) / 0.35) + 1)
        prev = None
        for i in range(n + 1):
            ang = a0 + (a1 - a0) * i / n
            p = mat.transform((c.x + r * math.cos(ang), c.y + r * math.sin(ang), 0))
            if prev is not None:
                tsp.add_line((prev.x, prev.y), (p.x, p.y), dxfattribs={"layer": "WALL"})
            prev = p


for e in blk:
    bake(e, m)

cell, close_gap = 60.0, 900.0
segs = list(_iter_wall_segments(tmp, ["WALL"]))
xs = [s[0] for s in segs] + [s[2] for s in segs] + [n[1] for n in nums]
ys = [s[1] for s in segs] + [s[3] for s in segs] + [n[2] for n in nums]
pad = cell * 4
minx, miny = min(xs) - pad, min(ys) - pad
w = int((max(xs) + pad - minx) / cell) + 1
h = int((max(ys) + pad - miny) / cell) + 1
grid = np.zeros((h, w), dtype=np.uint8)
for x0, y0, x1, y1 in segs:
    _draw_line(grid, int((x0 - minx) / cell), int((y0 - miny) / cell),
               int((x1 - minx) / cell), int((y1 - miny) / cell))
k = max(1, int(round(close_gap / cell)))
grid = ndimage.binary_closing(grid.astype(bool), structure=np.ones((k, k), bool)).astype(np.uint8)
lab, _ = ndimage.label(grid == 0)
cell_m2 = (cell / 1000) ** 2

print(f"격자 {w}x{h} · cell {cell:g}mm · close_gap {close_gap:g}mm\n")
print(f"{'방번호':8s} {'덩어리':>7s} {'면적㎡':>8s}  가까운 이름")
print("-" * 62)
rows = []
for no, x, y in sorted(nums):
    cx, cy = int((x - minx) / cell), int((y - miny) / cell)
    lid = int(lab[cy, cx]) if (0 <= cy < h and 0 <= cx < w) else -1
    area = float((lab == lid).sum()) * cell_m2 if lid > 0 else 0.0
    nm = min(names, key=lambda t: (t[1] - x) ** 2 + (t[2] - y) ** 2)[0] if names else ""
    rows.append((lid, no, area, nm))

# 같은 덩어리를 공유하는 방들을 묶어 보여준다 = 합쳐진 방
from collections import defaultdict
by = defaultdict(list)
for lid, no, area, nm in rows:
    by[lid].append((no, area, nm))
for lid, items in sorted(by.items()):
    if len(items) > 1:
        print(f"★ 덩어리 {lid} ({items[0][1]:.1f}㎡) 를 {len(items)}개 방이 공유:")
        for no, area, nm in items:
            print(f"      {no:8s} ← 라벨 근처 이름 '{nm}'")
print()
for lid, no, area, nm in rows:
    if no in FAILED:
        print(f"{no:8s} {lid:7d} {area:8.1f}  {nm}")
