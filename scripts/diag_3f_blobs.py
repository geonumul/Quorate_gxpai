# -*- coding: utf-8 -*-
"""3F 방들이 각각 **어떤 크기의 덩어리**에 빠지는지 센다.

  · 덩어리가 거대하다  → 벽이 안 닫혀 여러 방이 하나로 뭉쳤다 (구멍이 있다)
  · 덩어리가 0 이다    → 라벨이 벽/장비선 안에 갇혔다
  · 몇 방이 같은 덩어리를 공유하나 → 그 방들 사이의 벽이 없다
"""
import sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
import ezdxf, numpy as np, yaml
from scipy import ndimage
from gxpai.core.config import raw_dir
from gxpai.core.db import connect
from gxpai.geometry import boundaries as B
from gxpai.geometry.door_barriers import door_barriers

doc = ezdxf.readfile(str(next(p for p in (raw_dir()/"f_1ae3a266").iterdir() if "평면" in p.name)))
WALL = ["하니컴패널", "계단실", "COL", "창호", "WIN-1", "크린판넬", "판넬",
        "GW PANEL", "스테인레스 칸막이벽", "일반철골조(기둥)"]
DOOR = ["DOR", "DOOR", "DOOR-HID", "DOOR(HIDDEN)"]
CELL, GAP = 60.0, 200.0

with connect() as c, c.cursor() as cur:
    cur.execute("SELECT id FROM run WHERE facility_id='f_1ae3a266' ORDER BY started_at DESC LIMIT 1")
    rid = cur.fetchone()[0]
    cur.execute("""SELECT room_no, name, plan_x, plan_y FROM room WHERE run_id=%s
                    AND floor='3F' AND room_no ~ '^3' AND plan_x IS NOT NULL ORDER BY room_no""", (rid,))
    rooms = cur.fetchall()

segs = list(B._iter_wall_segments(doc, WALL + DOOR))
xs = [s[0] for s in segs] + [s[2] for s in segs]
ys = [s[1] for s in segs] + [s[3] for s in segs]
minx, miny = min(xs) - 240, min(ys) - 240
w = int((max(xs) + 240 - minx) / CELL) + 1
h = int((max(ys) + 240 - miny) / CELL) + 1
gx = lambda x: int((x - minx) / CELL)
gy = lambda y: int((y - miny) / CELL)

walls = np.zeros((h, w), dtype=np.uint8)
for a, b, cx, cy in segs:
    B._draw_line(walls, gx(a), gy(b), gx(cx), gy(cy))
nd = 0
for a, b, cx, cy in door_barriers(doc, DOOR, walls, minx, miny, CELL):
    B._draw_line(walls, gx(a), gy(b), gx(cx), gy(cy)); nd += 1

k = max(1, int(GAP / CELL))
closed = ndimage.binary_closing(walls.astype(bool), np.ones((k, k), bool))
free = ~closed
lab, n = ndimage.label(free)
sizes = ndimage.sum(free, lab, range(1, n + 1))
cell_m2 = (CELL / 1000.0) ** 2

print(f"■ 격자 {w}x{h}  문 장벽 {nd}개  자유 덩어리 {n}개")
blob_rooms = defaultdict(list)
for no, nm, px, py in rooms:
    lid = int(lab[gy(py), gx(px)])
    area = sizes[lid - 1] * cell_m2 if lid > 0 else 0.0
    blob_rooms[lid].append((no, nm, area))

print(f"\n■ 3F 방 {len(rooms)}개가 빠진 덩어리")
for lid, rr in sorted(blob_rooms.items(), key=lambda kv: -len(kv[1])):
    a = rr[0][2]
    tag = ("벽/장비선에 갇힘" if lid == 0 else
           f"{a:,.0f}㎡" + ("  ← 거대(벽이 안 닫힘)" if a > 400 else ""))
    print(f"   덩어리 {lid:5d}  방 {len(rr):2d}개  {tag}")
    if len(rr) > 1 or lid == 0:
        for no, nm, _ in rr[:8]:
            print(f"         {no} {nm}")
