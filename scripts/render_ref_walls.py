# -*- coding: utf-8 -*-
"""참고도면 벽을 레이어 조합별로 그려서 **눈으로** 본다. 숫자만 보고 정하지 않는다."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
import ezdxf, numpy as np
from PIL import Image
from gxpai.core.config import raw_dir
from gxpai.core.db import connect
from gxpai.geometry import boundaries as B

doc = ezdxf.readfile(str(raw_dir()/"f_c783b865"/"평면도.dxf"))
W50 = "008_P__Wall 50T"
SETS = {"A_전부": ["*"], "B_기존변경Wall50": ["ARCH-기존", "ARCH-변경", W50], "C_Wall50만": [W50]}
CELL = 30.0
with connect() as c, c.cursor() as cur:
    cur.execute("SELECT id FROM run WHERE facility_id='f_c783b865' ORDER BY started_at DESC LIMIT 1")
    rid = cur.fetchone()[0]
    cur.execute("SELECT plan_x, plan_y FROM room WHERE run_id=%s AND plan_x IS NOT NULL", (rid,))
    pts = cur.fetchall()

# 벽 레이어(Wall50) 범위로 화면을 잡는다 — 이게 진짜 건물이다
segs = list(B._iter_wall_segments(doc, [W50]))
xs = [s[0] for s in segs]+[s[2] for s in segs]; ys = [s[1] for s in segs]+[s[3] for s in segs]
X0, X1 = min(xs)-2000, max(xs)+2000
Y0, Y1 = min(ys)-2000, max(ys)+2000
w = int((X1-X0)/CELL)+1; h = int((Y1-Y0)/CELL)+1
gx = lambda x: int((x-X0)/CELL); gy = lambda y: int((y-Y0)/CELL)
out = Path("out"); out.mkdir(exist_ok=True)
print(f"화면 {X1-X0:.0f} x {Y1-Y0:.0f} mm → {w}x{h}")

for name, lays in SETS.items():
    g = np.zeros((h, w), np.uint8)
    n = 0
    for a, b, cx, cy in B._iter_wall_segments(doc, lays):
        if not (X0-5000 <= a <= X1+5000 and Y0-5000 <= b <= Y1+5000):
            continue
        B._draw_line(g, gx(a), gy(b), gx(cx), gy(cy)); n += 1
    img = np.full((h, w, 3), 255, np.uint8)
    img[g.astype(bool)] = (0, 0, 0)
    for px, py in pts:
        X, Y = gx(px), gy(py)
        if 0 <= X < w and 0 <= Y < h:
            img[max(0,Y-4):Y+5, max(0,X-4):X+5] = (230, 0, 0)
    Image.fromarray(img[::-1]).save(out/f"ref_{name}.png")
    print(f"  {name}: 선분 {n} → out/ref_{name}.png")
