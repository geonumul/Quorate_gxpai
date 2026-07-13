# -*- coding: utf-8 -*-
"""'SC2 H-350X350X12X19' 같은 철골 기둥 규격이 어느 레이어/블록에서 오는지 캔다."""
import re, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
import ezdxf, yaml
from gxpai.core.config import raw_dir
from gxpai.ingest.dxftext import normalize_dxf_text

prof = yaml.safe_load(Path("profiles/osd_hs_2025.yaml").read_text(encoding="utf-8"))
print("평면도 room_layers:", prof["floorplan"]["room_layers"])

f = next(p for p in (raw_dir() / "f_1ae3a266").iterdir() if "평면" in p.name)
doc = ezdxf.readfile(str(f))
PAT = re.compile(r"(SC\d|H-\d+X\d+|\bC\d+\b|SG\d)", re.I)

hits = Counter()
def walk(container, where):
    for e in container:
        t = e.dxftype()
        if t in ("TEXT", "MTEXT"):
            s = normalize_dxf_text(e)
            if s and PAT.search(s):
                hits[(e.dxf.layer, where, s[:40])] += 1
        elif t == "INSERT":
            blk = doc.blocks.get(e.dxf.name)
            if blk is not None and where.count(">") < 3:
                walk(blk, f"{where}>{e.dxf.name}")

walk(doc.modelspace(), "MS")
print(f"\n■ 철골/기둥 규격 같은 텍스트 {sum(hits.values())}개")
for (lay, where, s), n in hits.most_common(18):
    print(f"   레이어={lay!r:28} 경로={where:22} {s!r} ×{n}")
