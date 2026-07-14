# -*- coding: utf-8 -*-
"""기준 시설 도면 **전부**에서 청정등급의 흔적을 사냥한다.

"등급 표기 0건"이 정말 사실인가? 우리는 **평면도만** 뒤졌을 수 있다.
차압도(PRESSURIZATION PLAN)·HVAC 도면에 등급 구역이 있는 경우가 흔하다.
"""
import re, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
import ezdxf
from gxpai.core.config import raw_dir

# 등급처럼 보이는 것: (D) / GRADE C / CLASS 100 / 청정도 / 1급지 / CNC / NC ...
PAT = re.compile(r"(^\(?\s*(A|B|C|D|CNC|NC)\s*\)?$)|(GRADE)|(CLASS\s*\d)|(청정)|(등급)|(급지)|(ISO\s*\d)",
                 re.I)

for f in sorted((raw_dir()/"f_1ae3a266").iterdir()):
    try:
        doc = ezdxf.readfile(str(f))
    except Exception as e:
        print(f"■ {f.name}: 못 읽음 {e}"); continue
    hits = Counter()
    lays = Counter()

    def walk(cont, plr, d):
        for e in cont:
            lay = e.dxf.layer if hasattr(e.dxf, "layer") else "0"
            if lay == "0" and plr:
                lay = plr
            if e.dxftype() == "INSERT":
                if d >= 4: continue
                b = doc.blocks.get(e.dxf.name)
                if b is not None: walk(b, lay, d + 1)
                continue
            if e.dxftype() not in ("TEXT", "MTEXT"):
                continue
            t = (e.plain_text() if e.dxftype() == "MTEXT" else e.dxf.text).strip()
            if t and PAT.search(t):
                hits[t[:30]] += 1
                lays[lay] += 1

    walk(doc.modelspace(), None, 0)
    print(f"\n■ {f.name}  → 등급 후보 {sum(hits.values())}건")
    if hits:
        print("   레이어:", dict(lays.most_common(5)))
        for t, n in hits.most_common(12):
            print(f"      {t!r} ×{n}")
