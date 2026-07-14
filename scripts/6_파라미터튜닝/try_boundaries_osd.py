# -*- coding: utf-8 -*-
"""기준 시설(내용고형제)에 방 경계 flood-fill 을 돌려본다. (야간작업 A1/A3)

새 참고도면에서 배운 것을 그대로 적용:
  - 벽은 여러 레이어에 흩어져 있다 → 전부 합친다
  - close_gap 은 작게(작은 방을 삼키지 않게), adj_gap 은 크게(벽을 건너뛰게)
  - 실패는 조용히 넘기지 않고 사유와 함께 기록
  - **그림으로 눈 검증** (자동 판정을 믿지 않는다)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import ezdxf

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8")

from gxpai.core.config import load_profile  # noqa: E402
from gxpai.geometry import boundaries  # noqa: E402
from gxpai.ingest.dxftext import iter_label_texts  # noqa: E402

DXF = Path("raw/f_1ae3a266/A-201~207 평면도(증축후).dxf")
# 내 임시폴더 절대경로가 박혀 있었다 - **다른 기계에선 아예 안 돈다.**
OUT = Path("artifacts")
OUT.mkdir(parents=True, exist_ok=True)

doc = ezdxf.readfile(str(DXF))
prof = load_profile("osd_hs_2025")
fp = prof["floorplan"]
num_re = re.compile(fp["room_no_regex"])
bare_re = re.compile(fp["bare_no_regex"])

rooms = []
for x, y, t, _h in iter_label_texts(doc, fp["room_layers"], prof["label_entity_types"]):
    m = num_re.match(t)
    no = m.group(1) if m else (t if bare_re.match(t) else None)
    if no:
        rooms.append({"room_no": no, "plan_x": x, "plan_y": y})
print(f"방번호 라벨 {len(rooms)}개")

BOUND = {
    # 벽 레이어를 처음에 잘못 잡았다.
    #   `크린판넬`, `판넬`, `wall` 은 **다른 시트**(방 라벨이 없는 상세도)의 것이었다.
    #   그걸로 돌렸더니 96개 방이 전부 하나의 덩어리(40,710㎡)로 뭉쳤다 - 벽이 하나도 없었으니까.
    #   방 라벨이 있는 시트(3층 x392k~485k, 4층 x521k~611k)의 벽은 **`하니컴패널`** 이다
    #   (허니컴 패널 = 클린룸 벽체. 3층 614개, 4층 606개).
    #   → **"벽 레이어를 이름으로 짐작하지 말고, 라벨이 있는 구역 안에서 세어라."**
    "wall_layers": ["하니컴패널", "계단실", "COL", "창호", "WIN-1",
                    "크린판넬", "판넬", "GW PANEL", "스테인레스 칸막이벽"],
    "door_layers": ["DOOR", "DOOR(HIDDEN)", "DOOR-HID"],
    "cell_mm": 60,
    "close_gap_mm": 200,
    "adj_gap_mm": 300,
    "min_area_m2": 0.8,
    "max_area_m2": 400,
}

for cg, ag in [(200, 300), (300, 400), (450, 500)]:
    b = dict(BOUND, close_gap_mm=cg, adj_gap_mm=ag)
    res = boundaries.build(doc, rooms, {"boundaries": b})
    print(f"  close_gap={cg:3d} adj_gap={ag:3d} → 방 {len(res.rooms):3d}/{len(rooms)} "
          f", 실패 {len(res.failed):3d}, 인접 {len(res.adjacency):3d}")

res = boundaries.build(doc, rooms, {"boundaries": BOUND})
print(f"\n채택(close_gap=200): 방 {len(res.rooms)}/{len(rooms)}, 인접 {len(res.adjacency)}쌍")
for r in sorted(res.rooms, key=lambda r: -r.area_m2)[:10]:
    print(f"   {r.room_no:8s} {r.area_m2:8.1f} ㎡")
print("\n실패 사유 (상위 10)")
for f in res.failed[:10]:
    print("   ", f)

Path("artifacts").mkdir(exist_ok=True)
Path("artifacts/boundaries_osd.json").write_text(json.dumps({
    "rooms": [{"room_no": r.room_no, "area_m2": r.area_m2, "polygon": r.polygon}
              for r in res.rooms],
    "adjacency": res.adjacency, "failed": res.failed,
}, ensure_ascii=False, indent=2), encoding="utf-8")

# ── 눈으로 검증 ────────────────────────────────────────────────
import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Polygon as MplPoly  # noqa: E402

segs = list(boundaries._iter_wall_segments(doc, BOUND["wall_layers"] + BOUND["door_layers"]))
fig, ax = plt.subplots(figsize=(26, 10), dpi=100)
for x0, y0, x1, y1 in segs:
    ax.plot([x0, x1], [y0, y1], lw=0.2, color="0.7", zorder=1)
cmap = plt.get_cmap("tab20")
for i, r in enumerate(res.rooms):
    if len(r.polygon) < 3:
        continue
    ax.add_patch(MplPoly(r.polygon, closed=True, alpha=0.45, facecolor=cmap(i % 20),
                         edgecolor="k", lw=0.3, zorder=2))
    cx = sum(p[0] for p in r.polygon) / len(r.polygon)
    cy = sum(p[1] for p in r.polygon) / len(r.polygon)
    ax.text(cx, cy, f"{r.room_no}\n{r.area_m2:.0f}", ha="center", va="center",
            fontsize=4, zorder=3)
failed_no = {f.split(":")[0] for f in res.failed}
for rm in rooms:
    if rm["room_no"] in failed_no:
        ax.plot(rm["plan_x"], rm["plan_y"], "rx", ms=7, mew=1.6, zorder=4)
ax.set_aspect("equal")
ax.axis("off")
p = OUT / "boundaries_osd.png"
fig.savefig(p, bbox_inches="tight", facecolor="white")
print(f"\n→ 검증 그림: {p.name} (빨간 X = 실패)")
