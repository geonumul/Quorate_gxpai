# -*- coding: utf-8 -*-
"""참고도면 원본의 시트 6장에 각각 뭐가 있는지 본다. 2장만 쓰고 4장은 손도 안 댔다."""
import sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8")
import ezdxf

DXF = Path(r"D:\14. Dev Project\Quorate\참고도면_원본_CAD\dxf\참고도면(2).dxf")
if not DXF.exists():
    sys.exit(f"없음: {DXF}")
doc = ezdxf.readfile(str(DXF))
msp = doc.modelspace()

print("모델스페이스 최상위 INSERT (= 시트)")
for e in sorted(msp.query("INSERT"), key=lambda e: e.dxf.insert.x):
    blk = doc.blocks.get(e.dxf.name)
    n = sum(1 for _ in blk) if blk else 0
    if n > 50:
        print(f"   x={e.dxf.insert.x:9.0f}  {e.dxf.name!r:28} 엔티티 {n:6d}")

print("\n시트 제목 텍스트")
for e in msp:
    if e.dxftype() in ("TEXT", "MTEXT"):
        t = (e.plain_text() if e.dxftype() == "MTEXT" else e.dxf.text).strip()
        if 3 < len(t) < 40 and any(w in t for w in ("도", "PLAN", "층", "표", "범례")):
            print(f"   x={e.dxf.insert.x:9.0f}  {t!r}")
