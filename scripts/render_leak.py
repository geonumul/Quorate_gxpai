# -*- coding: utf-8 -*-
"""새는 덩어리를 **색칠해서** 본다. 어디로 새는지 눈으로 찾는다."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
import ezdxf, numpy as np, yaml
from PIL import Image
from scipy import ndimage
from gxpai.core.config import raw_dir
from gxpai.core.db import connect
from gxpai.geometry import boundaries as B
from gxpai.geometry.door_barriers import door_barriers

prof = yaml.safe_load(Path("profiles/osd_hs_2025.yaml").read_text(encoding="utf-8"))
bc = prof["boundaries"]
doc = ezdxf.readfile(str(next(p for p in (raw_dir()/"f_1ae3a266").iterdir() if "평면" in p.name)))
CELL = float(bc["cell_mm"])

with connect() as c, c.cursor() as cur:
    cur.execute("SELECT id FROM run WHERE facility_id='f_1ae3a266' ORDER BY started_at DESC LIMIT 1")
    rid = cur.fetchone()[0]
    cur.execute("""SELECT room_no, plan_x, plan_y FROM room WHERE run_id=%s
                    AND room_no ~ '^[0-9]{4}' AND plan_x IS NOT NULL""", (rid,))
    rows = cur.fetchall()

segs = list(B._iter_wall_segments(doc, list(bc["wall_layers"]) + list(bc["door_layers"])))
xs = [s[0] for s in segs]+[s[2] for s in segs]; ys = [s[1] for s in segs]+[s[3] for s in segs]
minx, miny = min(xs)-240, min(ys)-240
w = int((max(xs)+240-minx)/CELL)+1; h = int((max(ys)+240-miny)/CELL)+1
gx = lambda x: int((x-minx)/CELL); gy = lambda y: int((y-miny)/CELL)
walls = np.zeros((h, w), np.uint8)
for a, b, cx, cy in segs: B._draw_line(walls, gx(a), gy(b), gx(cx), gy(cy))
for a, b, cx, cy in door_barriers(doc, bc["door_layers"], walls, minx, miny, CELL):
    B._draw_line(walls, gx(a), gy(b), gx(cx), gy(cy))

k = max(1, int(bc["close_gap_mm"]/CELL))
closed = ndimage.binary_closing(walls.astype(bool), np.ones((k, k), bool))
lab, n = ndimage.label(~closed)
# 3501(종합포장실)이 빠진 덩어리를 찾는다
tgt = {r[0]: (r[1], r[2]) for r in rows}
px, py = tgt["3501"]
lid = int(lab[gy(py), gx(px)])
mask = lab == lid
print(f"새는 덩어리 id={lid}  픽셀 {mask.sum():,}  면적 {mask.sum()*(CELL/1000)**2:,.0f}㎡")

# 3F 구역만 잘라 본다
X0, X1 = 390000, 500000
Y0, Y1 = 20000, 50000
sx0, sx1, sy0, sy1 = gx(X0), gx(X1), gy(Y0), gy(Y1)
sub_w, sub_h = sx1-sx0, sy1-sy0
img = np.full((sub_h, sub_w, 3), 255, np.uint8)
sm = mask[sy0:sy1, sx0:sx1]
img[sm] = (255, 210, 210)                      # 새는 영역 = 연분홍
img[walls[sy0:sy1, sx0:sx1].astype(bool)] = (0, 0, 0)
for no, rx, ry in rows:
    X, Y = gx(rx)-sx0, gy(ry)-sy0
    if 0 <= X < sub_w and 0 <= Y < sub_h:
        img[max(0,Y-3):Y+4, max(0,X-3):X+4] = (200, 0, 0)
Path("out").mkdir(exist_ok=True)
Image.fromarray(img[::-1]).save("out/leak_3f.png")
print(f"out/leak_3f.png  ({sub_w}x{sub_h})")
