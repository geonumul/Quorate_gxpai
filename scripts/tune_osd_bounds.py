# -*- coding: utf-8 -*-
"""벽 재귀를 켠 뒤 남은 15방을 마저 잡는다. 격자·틈메우기 값을 훑는다."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
import copy, ezdxf, yaml
from gxpai.core.config import raw_dir
from gxpai.core.db import connect
from gxpai.geometry import boundaries

prof = yaml.safe_load(Path("profiles/osd_hs_2025.yaml").read_text(encoding="utf-8"))
doc = ezdxf.readfile(str(next(p for p in (raw_dir()/"f_1ae3a266").iterdir() if "평면" in p.name)))
with connect() as c, c.cursor() as cur:
    cur.execute("SELECT id FROM run WHERE facility_id='f_1ae3a266' ORDER BY started_at DESC LIMIT 1")
    rid = cur.fetchone()[0]
    cur.execute("""SELECT room_no, plan_x, plan_y, floor FROM room WHERE run_id=%s
                    AND room_no ~ '^[0-9]{4}' AND plan_x IS NOT NULL""", (rid,))
    rooms = [{"room_no": r[0], "plan_x": r[1], "plan_y": r[2], "floor": r[3]} for r in cur.fetchall()]

WALL = ["하니컴패널", "B-WAL", "계단실", "COL", "창호", "WIN-1", "크린판넬", "판넬",
        "GW PANEL", "스테인레스 칸막이벽", "일반철골조(기둥)"]
DOOR = ["DOR", "DOOR", "DOOR-HID", "DOOR(HIDDEN)"]
n3 = sum(1 for r in rooms if r["floor"] == "3F")
n4 = sum(1 for r in rooms if r["floor"] == "4F")
print(f"방 {len(rooms)} (3F {n3} · 4F {n4})\n")
print(f"{'cell':>5} {'close':>6} {'adj':>5} {'min㎡':>6} │ {'방':>7} {'3F':>6} {'4F':>6} {'인접':>5}")
best = None
for cell in (60,):
    for cg in (100, 200, 300):
        for mn in (0.5,):
            cfg = copy.deepcopy(prof)
            cfg["boundaries"] = {"wall_layers": WALL, "door_layers": DOOR,
                                 "cell_mm": cell, "close_gap_mm": cg, "adj_gap_mm": 300,
                                 "min_area_m2": mn, "max_area_m2": 400}
            res = boundaries.build(doc, rooms, cfg)
            ok = {r.room_no for r in res.rooms}
            g3 = sum(1 for r in rooms if r["floor"] == "3F" and r["room_no"] in ok)
            g4 = sum(1 for r in rooms if r["floor"] == "4F" and r["room_no"] in ok)
            print(f"{cell:>5} {cg:>6} {300:>5} {mn:>6} │ {len(res.rooms):>3}/{len(rooms):<3} "
                  f"{g3:>3}/{n3:<2} {g4:>3}/{n4:<2} {len(res.adjacency):>5}")
            if best is None or len(res.rooms) > best[0]:
                best = (len(res.rooms), cell, cg, mn, len(res.adjacency))
print(f"\n■ 최고: 방 {best[0]}/{len(rooms)}  cell={best[1]} close_gap={best[2]} "
      f"min_area={best[3]}  인접 {best[4]}")
