# -*- coding: utf-8 -*-
"""참고도면 벽 레이어를 제대로 잡는다. 면적이 **말이 되는지**로 판정한다.

51/51 은 '숫자가 나왔다'였지 '숫자가 맞다'가 아니었다.
  전부 태우기(`*`)로 51방을 얻었지만 면적 합계가 505㎡ 뿐이었다
  (무균 전실 0.8㎡, 갱의실 1.6㎡ - 사람이 못 들어간다).
  가구, 치수, 덕트선이 벽이 되어 방을 잘게 썰었다.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8")
import copy, ezdxf, yaml
from gxpai.core.config import raw_dir
from gxpai.core.db import connect
from gxpai.geometry import boundaries

prof = yaml.safe_load(Path("profiles/ref_2f_2026.yaml").read_text(encoding="utf-8"))
doc = ezdxf.readfile(str(raw_dir()/"f_c783b865"/"평면도.dxf"))
with connect() as c, c.cursor() as cur:
    cur.execute("SELECT id FROM run WHERE facility_id='f_c783b865' ORDER BY started_at DESC LIMIT 1")
    rid = cur.fetchone()[0]
    cur.execute("""SELECT room_no, plan_x, plan_y FROM room WHERE run_id=%s AND plan_x IS NOT NULL""", (rid,))
    rooms = [{"room_no": r[0], "plan_x": r[1], "plan_y": r[2]} for r in cur.fetchall()]

BASE = dict(prof["boundaries"])
W50 = "008_P__Wall 50T"
SETS = {
    "A 전부 태우기(현재)":  ["*"],
    "B 기존+변경+Wall50":  ["ARCH-기존", "ARCH-변경", W50],
    "C Wall50 단독":       [W50],
    "D Wall50+변경":       [W50, "ARCH-변경"],
    "E Wall50+변경+창":    [W50, "ARCH-변경", "FIX창 1000X1000"],
    "F 기존만":            ["ARCH-기존"],
}
# '무균 갱의실' 같은 방이 말이 되는 크기인가로 검증한다
SANITY = {"F2I20": "무균 갱의실", "F2I03": "갱의실(남)", "F2I21": "무균 전실",
          "F2I22": "바이알 충진및동결건조실"}

for label, lays in SETS.items():
    for doors in (["DOOR"],):
        cfg = copy.deepcopy(prof)
        cfg["boundaries"] = dict(BASE, wall_layers=lays, door_layers=doors)
        res = boundaries.build(doc, rooms, cfg)
        tot = sum(r.area_m2 for r in res.rooms)
        by = {r.room_no: r.area_m2 for r in res.rooms}
        s = "  ".join(f"{SANITY[k].split()[0]}={by.get(k, 0):.0f}㎡" for k in SANITY)
        print(f"{label:<20} 문={'O' if doors else 'X'}  방 {len(res.rooms):2d}/{len(rooms)}  "
              f"합계 {tot:6,.0f}㎡  문인접 {len(res.door_adjacency):2d}")
        print(f"     {s}")
