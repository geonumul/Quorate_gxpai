# -*- coding: utf-8 -*-
"""참고도면 '2층 천정 기구 배치도' 시트에 뭐가 있나. HEPA, 급기구를 뽑을 수 있는가?"""
import sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8")
import ezdxf
from gxpai.core.config import raw_dir

DXF = Path(r"D:\14. Dev Project\Quorate\02_참고도면\dxf\참고도면(2).dxf")
doc = ezdxf.readfile(str(DXF))
msp = doc.modelspace()

# 시트 = '2층평면도(260320)' 블록 INSERT 6개. x 순으로 1~6번.
sheets = sorted((e for e in msp.query("INSERT") if e.dxf.name == "2층평면도(260320)"),
                key=lambda e: e.dxf.insert.x)
print("시트 6장 (x 순)")
for i, e in enumerate(sheets, 1):
    print(f"   {i}: x={e.dxf.insert.x:9.0f}")

# 각 시트 폭(간격)으로 구간을 나눠, 시트별로 모델스페이스 엔티티의 레이어를 센다
xs = [e.dxf.insert.x for e in sheets]
W = (xs[1] - xs[0]) if len(xs) > 1 else 100000
print(f"\n시트 간격 {W:.0f}mm - 시트별 레이어 분포 (모델스페이스 최상위)")
for i, x0 in enumerate(xs, 1):
    lo, hi = x0 - W * 0.15, x0 + W * 0.85
    c = Counter()
    for e in msp:
        try:
            p = e.dxf.insert if e.dxftype() == "INSERT" else (
                e.dxf.center if e.dxftype() in ("CIRCLE", "ARC") else
                e.dxf.start if e.dxftype() == "LINE" else None)
            if p is None or not (lo <= p.x <= hi):
                continue
        except Exception:
            continue
        c[e.dxf.layer] += 1
    top = ", ".join(f"{k}:{v}" for k, v in c.most_common(6))
    print(f"   시트{i}: {top or '(없음)'}")

print("\n문서 전체 레이어 중 공조, 필터로 보이는 것")
KW = ("HEPA", "FILTER", "필터", "급기", "SA", "RA", "EA", "디퓨", "DIFF",
      "천정", "천장", "CEIL", "AIR", "SUPPLY", "RETURN", "풍도", "덕트", "DUCT", "장비")
for l in sorted(doc.layers, key=lambda x: x.dxf.name):
    n = l.dxf.name
    if any(k.lower() in n.lower() for k in KW):
        print(f"   {n!r}")
