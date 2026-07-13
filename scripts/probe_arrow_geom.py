# -*- coding: utf-8 -*-
"""블록 정의 안의 기하를 뜯어 **화살촉이 로컬 어느 방향인지**를 데이터로 구한다.

가정을 세우지 않는다. 화살표는 [삼각형 머리 + 가는 꼬리]다.
→ 전체 점들의 중심(centroid) 대비 **가장 멀리 튀어나온 뾰족한 점**이 화살촉이다.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
import ezdxf
from gxpai.core.config import raw_dir

doc = ezdxf.readfile(str(raw_dir() / "f_c783b865" / "차압흐름도.dxf"))
for bname in ("Air Flow 15Pa", "Air Flow 10Pa", "zw$E99B", "Air Flow no차압"):
    if bname not in doc.blocks:
        print(f"■ {bname!r}: 블록 정의 없음"); continue
    blk = doc.blocks[bname]
    print(f"\n■ 블록 {bname!r}")
    for e in blk:
        t = e.dxftype()
        if t == "SOLID":
            pts = [tuple(round(v, 1) for v in e.dxf.get(f"vtx{i}")[:2]) for i in range(4)]
            print(f"   SOLID  {pts}")
        elif t == "LWPOLYLINE":
            pts = [(round(p[0], 1), round(p[1], 1)) for p in e.get_points("xy")]
            print(f"   LWPOLYLINE closed={e.closed}  {pts}")
        elif t == "LINE":
            print(f"   LINE   ({e.dxf.start.x:.1f},{e.dxf.start.y:.1f}) → "
                  f"({e.dxf.end.x:.1f},{e.dxf.end.y:.1f})")
        elif t == "HATCH":
            print(f"   HATCH  paths={len(e.paths)}")
        else:
            print(f"   {t}")
