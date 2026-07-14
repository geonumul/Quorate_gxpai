# -*- coding: utf-8 -*-
"""인터락 24개가 **어느 에어락(전실)에** 붙어 있나. A/B 등급 연결 에어락에 다 있나?

조문: 고시 별표1 제4호 파목
  "이송해치 및 에어락(물품 및 작업원용)의 경우 입구용과 출구용 문이 **동시에 열려서는 안 된다**.
   **A등급과 B등급 구역으로 연결되는 에어락의 경우 인터락 시스템을 사용해야 한다.**
   C등급과 D등급 청정실로 연결되는 에어락의 경우, 최소한 시각경고시스템 …"
  → **등급별로 요구가 다르다.** A/B 는 인터락 필수, C/D 는 시각경고면 된다.
"""
import math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
import ezdxf
from gxpai.core.config import raw_dir
from gxpai.core.db import connect

doc = ezdxf.readfile(str(raw_dir()/"f_c783b865"/"인터락도.dxf"))
# 인터락은 **2점 선**이다 — 에어락의 두 문을 잇는 연결선("이 둘은 동시에 열리면 안 된다").
#   선의 **중점**이 곧 그 에어락 방이다.
locks = []
for e in doc.modelspace():
    if e.dxf.layer != "u-interlock" or e.dxftype() != "LWPOLYLINE":
        continue
    pts = [(q[0], q[1]) for q in e.get_points("xy")]
    if len(pts) < 2:
        continue
    mx = sum(q[0] for q in pts) / len(pts)
    my = sum(q[1] for q in pts) / len(pts)
    locks.append((mx, my, "line"))
print(f"인터락 연결선 {len(locks)}개 (중점으로 방에 귀속)")

with connect() as c, c.cursor() as cur:
    cur.execute("SELECT id FROM run WHERE facility_id='f_c783b865' ORDER BY started_at DESC LIMIT 1")
    rid = cur.fetchone()[0]
    cur.execute("""SELECT room_no,name,grade,COALESCE(pres_x,plan_x),COALESCE(pres_y,plan_y)
                     FROM room WHERE run_id=%s AND plan_x IS NOT NULL""", (rid,))
    rooms = cur.fetchall()
    cur.execute("""SELECT ra.room_no, rb.room_no FROM room_adjacency adj
                     JOIN room ra ON ra.id=adj.room_a JOIN room rb ON rb.id=adj.room_b
                    WHERE adj.run_id=%s AND adj.via_door""", (rid,))
    doors = cur.fetchall()

R = 3000.0
by = {r[0]: r for r in rooms if r[0]}
lock_of = {}
for lx, ly, _ in locks:
    cand = [(math.hypot(r[3]-lx, r[4]-ly), r[0]) for r in rooms if r[0]]
    if not cand:
        continue
    d, no = min(cand)
    if d <= R:
        lock_of[no] = lock_of.get(no, 0) + 1

AIRLOCK = ("전실", "에어락", "갱의", "탈의")
print(f"\n인터락이 붙은 방 {len(lock_of)}개")
for no, n in sorted(lock_of.items(), key=lambda kv: kv[0] or ""):
    r = by[no]
    print(f"   {no} {r[1]:22} 등급={r[2] or '-':4} × {n}")

print("\n에어락/전실 중 **A, B 등급 방과 문으로 이어진** 것 — 인터락 필수")
RANK = {"A":5,"B":4,"C":3,"D":2,"CNC":1,"NC":0}
for no, r in sorted(by.items(), key=lambda kv: kv[0] or ""):
    if not any(w in (r[1] or "") for w in AIRLOCK):
        continue
    nb = [b if a == no else a for a, b in doors if no in (a, b)]
    hi = [x for x in nb if x in by and by[x][2] in ("A", "B")]
    if hi:
        mark = "인터락 O" if no in lock_of else "인터락 없음"
        names = ", ".join(f"{x}({by[x][1]},{by[x][2]})" for x in hi)
        print(f"   {no} {r[1]:20} → {names}   {mark}")
