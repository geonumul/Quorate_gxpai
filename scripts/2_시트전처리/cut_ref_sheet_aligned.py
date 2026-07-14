# -*- coding: utf-8 -*-
"""참고도면의 **다른 시트**를 잘라 **평면도 시트(2번)와 같은 좌표계로 옮긴다.**

왜 옮겨야 하나
  참고도면(2).dxf 에는 같은 평면도 블록이 **6번** 배치돼 있고, 시트마다 다른 겹이 얹혀 있다.
      0 천정기구배치(HEPA BOX)  1 return풍도  2 차압흐름도  3 **차압계배치**  4 온습도계  5 인터락
  우리는 시트 2만 잘라 쓰고 있었다. 그래서 **차압계, HEPA 를 통째로 못 보고 있었다.**

  시트마다 x 원점이 다르므로(간격 106,026mm), 그냥 자르면 방 좌표와 안 맞는다.
  → 자른 뒤 **기준 시트(2번) 원점으로 평행이동**한다. 그러면 방, 화살표와 같은 좌표계가 된다.

  python scripts/2_시트전처리/cut_ref_sheet_aligned.py 3 차압계도    # 차압계 배치도
  python scripts/2_시트전처리/cut_ref_sheet_aligned.py 0 천정기구도  # HEPA BOX
"""
from __future__ import annotations

import sys
from pathlib import Path

import ezdxf
from ezdxf.addons import Importer
from ezdxf.math import Matrix44

sys.stdout.reconfigure(encoding="utf-8")

SRC = Path(r"D:\14. Dev Project\Quorate\02_참고도면\dxf\참고도면(2).dxf")
PLAN_BLOCK = "2층평면도(260320)"
SHEET_W = 100_000.0
BASE = 2                                  # 기준 시트 = 차압흐름도(우리 방 좌표의 기준)

idx = int(sys.argv[1]) if len(sys.argv) > 1 else 3
name = sys.argv[2] if len(sys.argv) > 2 else f"sheet{idx}"

doc = ezdxf.readfile(str(SRC))
msp = doc.modelspace()
sheets = sorted((e for e in msp.query("INSERT") if e.dxf.name == PLAN_BLOCK),
                key=lambda e: e.dxf.insert.x)
x_src = sheets[idx].dxf.insert.x
x_base = sheets[BASE].dxf.insert.x
dx = x_base - x_src                       # 평행이동량
print(f"시트{idx} x={x_src:,.0f} → 기준 시트{BASE} x={x_base:,.0f}  (이동 {dx:+,.0f}mm)")

x0, x1 = x_src, x_src + SHEET_W


def rep_x(e):
    """엔티티의 대표 x. 없으면 None."""
    t = e.dxftype()
    try:
        if t in ("INSERT", "TEXT", "ATTRIB", "MTEXT"):
            return e.dxf.insert.x
        if t == "LINE":
            return e.dxf.start.x
        if t == "LWPOLYLINE":
            pts = list(e.get_points())
            return pts[0][0] if pts else None
        if t in ("CIRCLE", "ARC"):
            return e.dxf.center.x
    except Exception:
        return None
    return None


keep = [e for e in msp if (rx := rep_x(e)) is not None and x0 <= rx <= x1]
print(f"시트 안 엔티티 {len(keep):,}개")

new = ezdxf.new(dxfversion=doc.dxfversion, setup=True)
imp = Importer(doc, new)
imp.import_entities(keep, new.modelspace())
imp.finalize()

# 평행이동: 자른 엔티티를 기준 시트 좌표계로 옮긴다
m = Matrix44.translate(dx, 0, 0)
for e in new.modelspace():
    try:
        e.transform(m)
    except Exception:
        pass                              # 변환 못 하는 엔티티는 남겨 둔다(개수를 뒤에서 센다)

out = Path("raw/f_c783b865") / f"{name}.dxf"
new.saveas(str(out))
print(f"저장: {out}  ({len(new.modelspace()):,} 엔티티)")

from collections import Counter
c = Counter(e.dxf.layer for e in new.modelspace())
print("레이어:", dict(c.most_common(8)))
