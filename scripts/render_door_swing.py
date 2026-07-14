# -*- coding: utf-8 -*-
"""못 열린다는 문을 **그림으로** 본다. 숫자만 믿지 않는다."""
import math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
import ezdxf, numpy as np, yaml
from PIL import Image
from gxpai.core.config import raw_dir
from gxpai.geometry import boundaries as B
from gxpai.geometry.door_swing import check
from gxpai.geometry.door_barriers import iter_door_arcs

fac = sys.argv[1] if len(sys.argv) > 1 else "f_c783b865"
pf = {"f_1ae3a266": "osd_hs_2025", "f_c783b865": "ref_2f_2026"}[fac]
prof = yaml.safe_load(Path(f"profiles/{pf}.yaml").read_text(encoding="utf-8"))
bc = prof["boundaries"]
doc = ezdxf.readfile(str(next(p for p in (raw_dir()/fac).iterdir() if "평면" in p.name)))
CELL = 25.0

segs = list(B._iter_wall_segments(doc, list(bc["wall_layers"]), skip_blocks=bc.get("skip_blocks")))
dsegs = list(B._iter_wall_segments(doc, list(bc.get("door_layers") or [])))
res = check(doc, prof, np.zeros((1,1),np.uint8), 0, 0, 1, lambda x,y: None)  # dummy, 아래서 다시

# 실제 격자
xs=[s[0] for s in segs]+[s[2] for s in segs]; ys=[s[1] for s in segs]+[s[3] for s in segs]
minx,miny = min(xs)-100, min(ys)-100
w=int((max(xs)+100-minx)/CELL)+1; h=int((max(ys)+100-miny)/CELL)+1
walls=np.zeros((h,w),np.uint8)
gx=lambda x:int((x-minx)/CELL); gy=lambda y:int((y-miny)/CELL)
for a,b,cx,cy in segs: B._draw_line(walls,gx(a),gy(b),gx(cx),gy(cy))
res = check(doc, prof, walls, minx, miny, CELL, lambda x,y: None)
print(f"못 여는 문 {len(res)}개")

out=Path("out"); out.mkdir(exist_ok=True)
for i, r in enumerate(sorted(res, key=lambda r: r['open_deg'])[:3]):
    R = 3500
    X0,X1 = r['x']-R, r['x']+R
    Y0,Y1 = r['y']-R, r['y']+R
    sw=int((X1-X0)/CELL); sh=int((Y1-Y0)/CELL)
    img=np.full((sh,sw,3),255,np.uint8)
    sx0,sy0 = gx(X0), gy(Y0)
    sub = walls[sy0:sy0+sh, sx0:sx0+sw]
    if sub.shape == (sh,sw): img[sub.astype(bool)] = (0,0,0)     # 벽 = 검정
    # 문(스윙 호) = 파랑
    dg=np.zeros((sh,sw),np.uint8)
    for a,b,cx,cy in dsegs:
        if X0<=a<=X1 and Y0<=b<=Y1:
            B._draw_line(dg,int((a-X0)/CELL),int((b-Y0)/CELL),int((cx-X0)/CELL),int((cy-Y0)/CELL))
    img[dg.astype(bool)] = (40,90,220)
    # 경첩 = 초록, 막힌 곳 = 빨강
    for (px,py,col) in ((r['x'],r['y'],(20,160,80)), (r['hit_x'],r['hit_y'],(220,30,30))):
        X,Y=int((px-X0)/CELL),int((py-Y0)/CELL)
        if 0<=X<sw and 0<=Y<sh: img[max(0,Y-4):Y+5, max(0,X-4):X+5]=col
    Image.fromarray(img[::-1]).save(out/f"swing_{fac}_{i}.png")
    print(f"  out/swing_{fac}_{i}.png  {r['open_deg']}°만 열림 @({r['x']:.0f},{r['y']:.0f})")
