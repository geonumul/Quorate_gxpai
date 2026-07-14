# -*- coding: utf-8 -*-
"""문 검출률이 왜 낮은가. 호 하나하나가 **어디서 탈락하는지** 센다."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8")
import ezdxf, numpy as np, yaml
from gxpai.core.config import raw_dir
from gxpai.core.db import connect
from gxpai.geometry import boundaries as B
from gxpai.geometry.door_barriers import iter_door_arcs, _wall_near

for fac, pf, fn in (("f_c783b865", "ref_2f_2026", "평면도.dxf"),
                    ("f_1ae3a266", "osd_hs_2025", None)):
    prof = yaml.safe_load(Path(f"profiles/{pf}.yaml").read_text(encoding="utf-8"))
    bc = prof["boundaries"]
    d = raw_dir()/fac
    doc = ezdxf.readfile(str(d/fn if fn else next(p for p in d.iterdir() if "평면" in p.name)))
    cell = float(bc.get("cell_mm", 60))

    segs = list(B._iter_wall_segments(doc, list(bc["wall_layers"]) + list(bc.get("door_layers") or []),
                                      skip_blocks=bc.get("skip_blocks")))
    xs = [s[0] for s in segs]+[s[2] for s in segs]; ys = [s[1] for s in segs]+[s[3] for s in segs]
    minx, miny = min(xs)-cell*4, min(ys)-cell*4
    w = int((max(xs)+cell*4-minx)/cell)+1; h = int((max(ys)+cell*4-miny)/cell)+1
    gx = lambda x: int((x-minx)/cell); gy = lambda y: int((y-miny)/cell)
    walls = np.zeros((h, w), np.uint8)
    for a, b, cx, cy in segs:
        B._draw_line(walls, gx(a), gy(b), gx(cx), gy(cy))

    arcs = list(iter_door_arcs(doc, list(bc.get("door_layers") or [])))
    both0 = tie = ok = 0
    for c, p0, p1 in arcs:
        h0 = _wall_near(walls, gx(p0[0]), gy(p0[1]))
        h1 = _wall_near(walls, gx(p1[0]), gy(p1[1]))
        if h0 < 1 and h1 < 1: both0 += 1
        elif h0 == h1: tie += 1
        else: ok += 1
    print(f"{fac}  호 {len(arcs)}개")
    print(f"   양끝 다 벽에서 멂  {both0:4d}  ← 벽 격자가 성기거나 호가 문이 아님")
    print(f"   양끝 벽 개수 같음   {tie:4d}  ← 양쪽 다 그린다(완화 적용)")
    print(f"   한쪽만 벽에 닿음    {ok:4d}  ← 정상 판별")
