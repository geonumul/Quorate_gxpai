# -*- coding: utf-8 -*-
"""문이 기둥, 벽에 걸려 못 열리는지 — **실제 도면에 돌려 본다.**

대표님(1차 미팅): "여기 기둥이 있어 — 그러면 문을 못 열잖아요.
  '얘는 접촉이 돼서 문을 못 연다'고 메시지를 띄운다든지만 해주면 사람들이 보고 고치죠"
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8")
import ezdxf, numpy as np, yaml
from gxpai.core.config import raw_dir
from gxpai.geometry import boundaries as B
from gxpai.geometry.door_swing import check

fac = sys.argv[1] if len(sys.argv) > 1 else "f_1ae3a266"
pf = {"f_1ae3a266": "osd_hs_2025", "f_c783b865": "ref_2f_2026"}[fac]
prof = yaml.safe_load(Path(f"profiles/{pf}.yaml").read_text(encoding="utf-8"))
bc = prof["boundaries"]
d = raw_dir()/fac
f = next(p for p in d.iterdir() if "평면" in p.name)
doc = ezdxf.readfile(str(f))
cell = float(bc["cell_mm"])

# 장애물 격자에 **문 레이어를 넣으면 안 된다.**
#   문짝, 문틀 선이 그대로 장애물이 되어 **문이 자기 자신에 막힌다.**
#   처음에 그렇게 했더니 589개가 "0°만 열림"으로 나왔다 — 말이 안 되는 값이라 바로 들통났다.
segs = list(B._iter_wall_segments(doc, list(bc["wall_layers"]),
                                  skip_blocks=bc.get("skip_blocks")))
xs = [s[0] for s in segs]+[s[2] for s in segs]; ys = [s[1] for s in segs]+[s[3] for s in segs]
minx, miny = min(xs)-cell*4, min(ys)-cell*4
w = int((max(xs)+cell*4-minx)/cell)+1; h = int((max(ys)+cell*4-miny)/cell)+1
walls = np.zeros((h, w), np.uint8)
for a, b, cx, cy in segs:
    B._draw_line(walls, int((a-minx)/cell), int((b-miny)/cell), int((cx-minx)/cell), int((cy-miny)/cell))

print(f"{fac}  격자 {w}x{h}  벽 선분 {len(segs):,}")
res = check(doc, prof, walls, minx, miny, cell, lambda x, y: None)
print(f"\n90° 못 여는 문: {len(res)}개")
for r in sorted(res, key=lambda r: r['open_deg'])[:15]:
    print(f"   {r['open_deg']:>3}°만 열림  경첩@({r['x']:.0f},{r['y']:.0f}) r={r['radius_mm']}mm"
          f"  막힌 곳@({r['hit_x']:.0f},{r['hit_y']:.0f})")
