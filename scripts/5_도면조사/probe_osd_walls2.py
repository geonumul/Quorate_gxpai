# -*- coding: utf-8 -*-
"""방 라벨이 있는 구역에 **벽이 실제로 있는가**를 센다. (야간작업 A1 진단)

flood-fill 이 96개 방 전부 "벽이 안 닫힘(40,710㎡)"으로 실패했다.
그림을 보니 **라벨이 있는 시트에는 벽이 거의 없고, 벽 상세는 다른 시트에 있다.**
= 방 라벨과 벽이 **서로 다른 시트**에 그려져 있다는 뜻.

여기서 그걸 숫자로 확정한다: 각 층 라벨의 바운딩 박스 안에 어느 레이어의 선이 몇 개 있는가.
"""
from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

import ezdxf

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8")

from gxpai.core.config import load_profile  # noqa: E402
from gxpai.ingest.dxftext import iter_label_texts  # noqa: E402

doc = ezdxf.readfile("raw/f_1ae3a266/A-201~207 평면도(증축후).dxf")
prof = load_profile("osd_hs_2025")
fp = prof["floorplan"]
num_re = re.compile(fp["room_no_regex"])
bare_re = re.compile(fp["bare_no_regex"])

labels = []
for x, y, t, _h in iter_label_texts(doc, fp["room_layers"], prof["label_entity_types"]):
    m = num_re.match(t)
    no = m.group(1) if m else (t if bare_re.match(t) else None)
    if no:
        labels.append((no, x, y))

boxes = {}
for no, x, y in labels:
    f = no[0]
    b = boxes.setdefault(f, [x, x, y, y])
    b[0] = min(b[0], x); b[1] = max(b[1], x)
    b[2] = min(b[2], y); b[3] = max(b[3], y)

PAD = 3000.0


def points_of(e):
    t = e.dxftype()
    if t == "LINE":
        return [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]
    if t == "LWPOLYLINE":
        return [(p[0], p[1]) for p in e.get_points()]
    if t == "ARC":
        return [(e.dxf.center.x, e.dxf.center.y)]
    return []


for f, (x0, x1, y0, y1) in sorted(boxes.items()):
    x0 -= PAD; x1 += PAD; y0 -= PAD; y1 += PAD
    cnt = collections.Counter()
    for e in doc.modelspace():
        if e.dxftype() not in ("LINE", "LWPOLYLINE", "ARC"):
            continue
        pts = points_of(e)
        if not pts:
            continue
        if any(x0 <= px <= x1 and y0 <= py <= y1 for px, py in pts):
            cnt[e.dxf.layer] += 1
    n_lab = sum(1 for no, _x, _y in labels if no[0] == f)
    print(f"\n{f}층대 (방 라벨 {n_lab}개)  x {x0:.0f}~{x1:.0f}")
    print(f"   이 구역 안의 선/호 레이어 상위 12:")
    for k, v in cnt.most_common(12):
        print(f"     {v:6d}  {k}")
