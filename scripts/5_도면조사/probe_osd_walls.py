# -*- coding: utf-8 -*-
"""기준 시설(내용고형제) 평면도의 벽 구성을 진단한다. (야간작업 A1)

확인할 것
  1) 한 DXF 에 여러 층 평면이 나란히 있는가? (x 범위로 시트가 갈리는가)
  2) 층마다 벽 레이어가 다른가? (크린판넬 / wall / 판넬 …)
  3) 방 라벨과 벽이 같은 좌표계에 있는가?
     예전 분석은 "좌표계가 뒤섞였다"고 봤다. 그게 사실인지, 아니면
       그냥 '여러 층이 나란히 배치된 것'인지 여기서 가린다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import ezdxf

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8")

from gxpai.core.config import load_profile  # noqa: E402
from gxpai.ingest.dxftext import iter_label_texts  # noqa: E402

DXF = Path("raw/f_1ae3a266/A-201~207 평면도(증축후).dxf")
WALL_LAYERS = ["크린판넬", "wall", "판넬", "스테인레스 칸막이벽", "GW PANEL"]
DOOR_LAYERS = ["DOOR", "DOOR(HIDDEN)", "DOOR-HID"]

doc = ezdxf.readfile(str(DXF))
prof = load_profile("osd_hs_2025")


def seg_points(layers):
    want = {l.lower() for l in layers}
    pts = []
    for e in doc.modelspace():
        try:
            if e.dxf.layer.lower() not in want:
                continue
        except AttributeError:
            continue
        t = e.dxftype()
        if t == "LINE":
            pts += [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]
        elif t == "LWPOLYLINE":
            pts += [(p[0], p[1]) for p in e.get_points()]
        elif t == "ARC":
            pts.append((e.dxf.center.x, e.dxf.center.y))
    return pts


# ── 방 라벨(번호) 위치 ─────────────────────────────────────────
import re  # noqa: E402

fp = prof["floorplan"]
num_re = re.compile(fp["room_no_regex"])
bare_re = re.compile(fp["bare_no_regex"])
labels = []
for x, y, t, _h in iter_label_texts(doc, fp["room_layers"], prof["label_entity_types"]):
    m = num_re.match(t)
    no = m.group(1) if m else (t if bare_re.match(t) else None)
    if no:
        labels.append((no, x, y))
print(f"방번호 라벨 {len(labels)}개")

# 층(방번호 첫자리)별 x 범위 → 시트가 나란히 있는지 본다
by_floor: dict[str, list] = {}
for no, x, y in labels:
    by_floor.setdefault(no[0], []).append((x, y))
print("\n층별 방 라벨 x 범위 (시트가 나란히 배치됐는지)")
for f in sorted(by_floor):
    xs = [p[0] for p in by_floor[f]]
    ys = [p[1] for p in by_floor[f]]
    print(f"  {f}층대  {len(xs):3d}개   x {min(xs):8.0f}~{max(xs):8.0f}   y {min(ys):7.0f}~{max(ys):7.0f}")

print("\n벽 레이어별 x 범위")
for lay in WALL_LAYERS:
    p = seg_points([lay])
    if not p:
        print(f"  {lay:16s} 없음")
        continue
    xs = [q[0] for q in p]
    ys = [q[1] for q in p]
    print(f"  {lay:16s} {len(p):6d}점  x {min(xs):8.0f}~{max(xs):8.0f}  y {min(ys):7.0f}~{max(ys):7.0f}")

allp = seg_points(WALL_LAYERS)
xs = [q[0] for q in allp]
print(f"\n  벽 전체 합치면: {len(allp):,}점  x {min(xs):.0f}~{max(xs):.0f}")

dp = seg_points(DOOR_LAYERS)
if dp:
    dxs = [q[0] for q in dp]
    print(f"  문 전체:        {len(dp):,}점  x {min(dxs):.0f}~{max(dxs):.0f}")

# ── 각 층 라벨이 벽 범위 안에 들어오는가 ─────────────────────────
print("\n층별 라벨이 '벽이 있는 구역' 안에 있는가")
for f in sorted(by_floor):
    xs_l = [p[0] for p in by_floor[f]]
    inside = sum(1 for x in xs_l if min(xs) <= x <= max(xs))
    print(f"  {f}층대: {inside}/{len(xs_l)} 개가 벽 x범위 안")
