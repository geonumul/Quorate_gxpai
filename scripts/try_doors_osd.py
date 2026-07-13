# -*- coding: utf-8 -*-
"""문 막기를 켜고/끄고 기준 시설 flood-fill 을 비교한다. 좋아지지 않으면 쓰지 않는다."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
import copy, ezdxf, yaml
from gxpai.core.config import raw_dir
from gxpai.core.db import connect
from gxpai.geometry import boundaries
from gxpai.geometry.door_barriers import iter_door_arcs, door_barriers

prof = yaml.safe_load(Path("profiles/osd_hs_2025.yaml").read_text(encoding="utf-8"))
doc = ezdxf.readfile(str(next(p for p in (raw_dir()/"f_1ae3a266").iterdir() if "평면" in p.name)))

with connect() as c, c.cursor() as cur:
    cur.execute("SELECT id FROM run WHERE facility_id='f_1ae3a266' ORDER BY started_at DESC LIMIT 1")
    rid = cur.fetchone()[0]
    cur.execute("""SELECT room_no, plan_x, plan_y, floor FROM room WHERE run_id=%s
                    AND room_no ~ '^[0-9]{4}' AND plan_x IS NOT NULL""", (rid,))
    rooms = [{"room_no": r[0], "plan_x": r[1], "plan_y": r[2], "floor": r[3]} for r in cur.fetchall()]

DOOR_LAYERS = (sys.argv[1].split(",") if len(sys.argv) > 1
               else ["DOR", "DOOR", "DOOR-HID", "DOOR(HIDDEN)"])
arcs = list(iter_door_arcs(doc, DOOR_LAYERS))
print(f"■ 문 레이어 {DOOR_LAYERS}")
print(f"   블록 재귀로 찾은 호(ARC): {len(arcs)}개")
print(f"   방 라벨(번호방): {len(rooms)}개\n")

base = {
    # ★B-WAL 을 놓치고 있었다. 실패한 방 주변 6m 안의 축-나란 선분을 레이어별로
    #   세어 보고 찾았다("이름으로 짐작하지 말고 방 주변에서 세어라").
    "wall_layers": ["하니컴패널", "B-WAL", "계단실", "COL", "창호", "WIN-1",
                    "크린판넬", "판넬", "GW PANEL", "스테인레스 칸막이벽",
                    "일반철골조(기둥)"],
    "cell_mm": 60, "close_gap_mm": 200, "adj_gap_mm": 300,
    "min_area_m2": 0.8, "max_area_m2": 400,
}
by_floor = lambda rr: {f: sum(1 for x in rr if x["floor"] == f) for f in ("3F", "4F")}

for label, seal in (("문 막기 끔", False), ("문 막기 켬", True)):
    cfg = copy.deepcopy(prof)
    cfg["boundaries"] = dict(base, door_layers=DOOR_LAYERS, seal_doors=seal)
    res = boundaries.build(doc, rooms, cfg)
    ok = {r.room_no for r in res.rooms}
    got = [r for r in rooms if r["room_no"] in ok]
    print(f"▸ {label}: {len(res.rooms)}/{len(rooms)} 방  "
          f"(3F {by_floor(got).get('3F',0)} · 4F {by_floor(got).get('4F',0)})  "
          f"인접 {len(res.adjacency)}")
