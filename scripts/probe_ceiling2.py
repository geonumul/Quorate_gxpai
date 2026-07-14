# -*- coding: utf-8 -*-
"""천정 시트의 `풍량` 121개 — **단위가 도면 안에서 확정되는가?**

TA 단위(CMH 인지 Pa 인지)는 지금 '보류'다. 확정 전엔 어떤 규칙도 이 값을 못 쓴다(R-D2).
도면에 범례나 단위 표기가 있으면 확정할 수 있다.
"""
import re, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
import ezdxf
from gxpai.core.config import raw_dir

doc = ezdxf.readfile(str(raw_dir()/"f_c783b865"/"천정기구도.dxf"))
msp = doc.modelspace()

texts = []
for e in msp:
    if e.dxftype() not in ("TEXT", "MTEXT"):
        continue
    t = (e.plain_text() if e.dxftype() == "MTEXT" else e.dxf.text).strip()
    if t:
        texts.append((e.dxf.layer, t, e.dxf.insert.x, e.dxf.insert.y))

print("레이어별 텍스트")
for lay, n in Counter(l for l, *_ in texts).most_common(8):
    print(f"   {lay!r}: {n}")

print("\n`풍량` 레이어 텍스트 (앞 20)")
w = [t for l, t, *_ in texts if l == "풍량"]
for t in w[:20]:
    print(f"   {t!r}")
print(f"   … 총 {len(w)}개")

print("\n단위처럼 보이는 텍스트 (모든 레이어)")
UNIT = ("CMH", "㎥", "m3", "M3", "CFM", "Pa", "㎩", "회", "ACH", "/h", "hr")
hits = [(l, t) for l, t, *_ in texts if any(u.lower() in t.lower() for u in UNIT)]
for l, t in hits[:20]:
    print(f"   [{l}] {t!r}")
print(f"   총 {len(hits)}건")

print("\n범례, 제목 텍스트")
for l, t, x, y in texts:
    if l in ("TITLE", "TEXT", "TXT") or any(k in t for k in ("범례", "LEGEND", "주기", "NOTE")):
        print(f"   [{l}] {t!r}")
