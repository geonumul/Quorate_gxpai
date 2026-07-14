# -*- coding: utf-8 -*-
"""3F 벽 격자를 그림으로 뽑는다. 숫자로 안 보이는 걸 눈으로 본다."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8")
import ezdxf, numpy as np
from PIL import Image
from gxpai.core.config import raw_dir
from gxpai.core.db import connect
from gxpai.geometry import boundaries as B

doc = ezdxf.readfile(str(next(p for p in (raw_dir()/"f_1ae3a266").iterdir() if "평면" in p.name)))
CELL = 40.0
LAYERSETS = {
    "1_하니컴만":  ["하니컴패널"],
    "2_하니컴+구조": ["하니컴패널", "계단실", "COL", "창호", "WIN-1", "일반철골조(기둥)",
                  "크린판넬", "판넬", "GW PANEL", "스테인레스 칸막이벽"],
    "3_전부+문":   ["하니컴패널", "계단실", "COL", "창호", "WIN-1", "일반철골조(기둥)",
                  "크린판넬", "판넬", "GW PANEL", "스테인레스 칸막이벽",
                  "DOOR", "DOOR-HID", "DOOR(HIDDEN)", "DOR"],
}
with connect() as c, c.cursor() as cur:
    cur.execute("SELECT id FROM run WHERE facility_id='f_1ae3a266' ORDER BY started_at DESC LIMIT 1")
    rid = cur.fetchone()[0]
    cur.execute("""SELECT plan_x, plan_y FROM room WHERE run_id=%s AND floor='3F'
                    AND room_no ~ '^3' AND plan_x IS NOT NULL""", (rid,))
    pts = cur.fetchall()

X0, X1 = min(p[0] for p in pts)-8000, max(p[0] for p in pts)+8000
Y0, Y1 = min(p[1] for p in pts)-8000, max(p[1] for p in pts)+8000
w = int((X1-X0)/CELL)+1; h = int((Y1-Y0)/CELL)+1
print(f"3F 구역 {X1-X0:.0f} x {Y1-Y0:.0f} mm → 격자 {w}x{h}")
gx = lambda x: int((x-X0)/CELL); gy = lambda y: int((y-Y0)/CELL)

# 검수용 렌더는 artifacts/ 로 쓴다. out/ 에 쓰면 git 에 딸려 들어간다.
# 실제로 발주처 도면을 그린 PNG 9장이 커밋돼 있었다.
out = Path("artifacts"); out.mkdir(exist_ok=True)
for name, lays in LAYERSETS.items():
    g = np.zeros((h, w), dtype=np.uint8)
    n = 0
    for a, b, cx, cy in B._iter_wall_segments(doc, lays):
        if not (X0 <= a <= X1 or X0 <= cx <= X1):
            continue
        B._draw_line(g, gx(a), gy(b), gx(cx), gy(cy)); n += 1
    img = np.full((h, w, 3), 255, np.uint8)
    img[g.astype(bool)] = (0, 0, 0)
    for px, py in pts:
        X, Y = gx(px), gy(py)
        img[max(0,Y-3):Y+4, max(0,X-3):X+4] = (220, 0, 0)   # 방 라벨 = 빨강
    Image.fromarray(img[::-1]).save(out / f"3f_{name}.png")
    print(f"  {name}: 선분 {n} → artifacts/3f_{name}.png")
