# -*- coding: utf-8 -*-
"""새 참고도면 DXF 로 방 경계 flood-fill 을 실제로 돌려본다(수동 검증용 스크립트).

합성 시험이 통과해도 **실제 도면에서 되는지는 별개**다. 여기서 확인한다:
  - 벽 레이어가 진짜 벽인가
  - 방이 문틈으로 합쳐지지 않는가
  - 면적이 상식적인가 (탈의실 10~20㎡, 복도는 길쭉하게 큼)
  - 인접이 말이 되는가
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import ezdxf
from ezdxf.math import Matrix44

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8")

from gxpai.geometry import boundaries  # noqa: E402

DXF = Path(r"D:\14. Dev Project\Quorate\참고도면_원본_CAD\dxf\참고도면(2).dxf")
GRADE = re.compile(r"^\((A|B|C|D|CNC|NC)\)$")
ROOMNO = re.compile(r"^(F\d[A-Z]\d{2}|\d{4})$")

doc = ezdxf.readfile(str(DXF))
msp = doc.modelspace()

# 시트 6장 중 하나(차압 흐름도)를 고른다. 평면도 블록의 첫 배치를 쓴다.
sheets = sorted((e for e in msp.query("INSERT") if e.dxf.name == "2층평면도(260320)"),
                key=lambda e: e.dxf.insert.x)
sheet = sheets[0]
print(f"평면도 블록 배치 {len(sheets)}회 → 첫 시트 사용 @({sheet.dxf.insert.x:.0f},{sheet.dxf.insert.y:.0f})")

# ── 방 라벨(블록 안 TEXT) 을 세계좌표로 ─────────────────────────
blk = doc.blocks.get("2층평면도(260320)")
m = Matrix44.chain(
    Matrix44.scale(sheet.dxf.xscale, sheet.dxf.yscale, 1),
    Matrix44.z_rotate(math.radians(sheet.dxf.rotation)),
    Matrix44.translate(sheet.dxf.insert.x, sheet.dxf.insert.y, 0),
)
nums = []
for e in blk:
    if e.dxftype() != "TEXT":
        continue
    t = e.dxf.text.strip()
    if ROOMNO.match(t):
        p = m.transform(e.dxf.insert)
        nums.append({"room_no": t, "plan_x": p.x, "plan_y": p.y})
print(f"방번호 라벨 {len(nums)}개")

# ── 평면도 기하를 **재귀적으로** 펼쳐 임시 문서에 굽는다 ──────────
# 블록이 3단 중첩이다: 2층평면도(260320) → zw$F5F8 → 2층 평면 변경후(벽 97k)
#   그리고 **안쪽 엔티티가 전부 레이어 '0'** 이다(블록이 INSERT 의 레이어를 상속).
#   → 레이어로 벽만 고를 수 없다. 일단 선/호를 전부 장벽으로 태우고 결과를 눈으로 본다.
#     (가구, 치수선까지 장벽이 되면 방이 잘게 쪼개질 수 있다 — 그때 걸러낸다.)
tmp = ezdxf.new()
tsp = tmp.modelspace()
n_seg = 0


# 방 라벨은 **네모 박스 안에** 그려져 있다(블록 B20260107094054, 51개 × 5선).
#   그 박스를 장벽으로 태우면 flood-fill 이 **라벨 박스 안에 갇힌다**(면적 0.7㎡).
#   실제로 51개 방이 전부 '면적 과소'로 실패했다. → 라벨 박스 블록은 장벽에서 제외한다.
SKIP_BLOCKS = {"B20260107094054"}


def bake(entity, mat: Matrix44) -> None:
    """INSERT 를 재귀적으로 펼쳐 선분을 임시 문서에 굽는다."""
    global n_seg
    t = entity.dxftype()
    if t == "INSERT":
        if entity.dxf.name in SKIP_BLOCKS:
            return                       # 방 라벨 박스 — 벽이 아니다
        inner = doc.blocks.get(entity.dxf.name)
        if inner is None:
            return
        mm = Matrix44.chain(
            Matrix44.scale(entity.dxf.xscale, entity.dxf.yscale, 1),
            Matrix44.z_rotate(math.radians(entity.dxf.rotation)),
            Matrix44.translate(entity.dxf.insert.x, entity.dxf.insert.y, 0),
            mat,
        )
        for sub in inner:
            bake(sub, mm)
    elif t == "LINE":
        a = mat.transform(entity.dxf.start)
        b = mat.transform(entity.dxf.end)
        tsp.add_line((a.x, a.y), (b.x, b.y), dxfattribs={"layer": "WALL"})
        n_seg += 1
    elif t == "LWPOLYLINE":
        pts = [mat.transform((p[0], p[1], 0)) for p in entity.get_points()]
        if entity.closed and len(pts) > 2:
            pts.append(pts[0])
        for i in range(len(pts) - 1):
            tsp.add_line((pts[i].x, pts[i].y), (pts[i + 1].x, pts[i + 1].y),
                         dxfattribs={"layer": "WALL"})
            n_seg += 1
    elif t == "ARC":
        c, r = entity.dxf.center, entity.dxf.radius
        a0 = math.radians(entity.dxf.start_angle)
        a1 = math.radians(entity.dxf.end_angle)
        if a1 < a0:
            a1 += 2 * math.pi
        n = max(2, int((a1 - a0) / 0.35) + 1)
        prev = None
        for i in range(n + 1):
            ang = a0 + (a1 - a0) * i / n
            p = mat.transform((c.x + r * math.cos(ang), c.y + r * math.sin(ang), 0))
            if prev is not None:
                tsp.add_line((prev.x, prev.y), (p.x, p.y), dxfattribs={"layer": "WALL"})
                n_seg += 1
            prev = p


for e in blk:
    bake(e, m)
print(f"장벽 선분 {n_seg:,}개 (평면도 블록 재귀 전개)")

PROFILE = {"boundaries": {
    "wall_layers": ["WALL"],
    "door_layers": [],
    "cell_mm": 60,
    "close_gap_mm": 200,
    "max_area_m2": 400,
    "min_area_m2": 0.8,
    "adj_gap_mm": 300,
}}

res = boundaries.build(tmp, nums, PROFILE)
print(f"\n결과: 방 {len(res.rooms)}개 / 실패 {len(res.failed)}개 / 인접 {len(res.adjacency)}쌍")
print(f"  격자 {res.cell_mm}mm\n")

for r in sorted(res.rooms, key=lambda r: -r.area_m2)[:12]:
    print(f"   {r.room_no:8s} {r.area_m2:8.1f} ㎡")
print("\n실패 사유 (상위 8)")
for f in res.failed[:8]:
    print("   ", f)

out = Path(__file__).resolve().parents[2] / "artifacts" / "boundaries_ref.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps({
    "rooms": [{"room_no": r.room_no, "area_m2": r.area_m2, "polygon": r.polygon}
              for r in res.rooms],
    "adjacency": res.adjacency, "failed": res.failed, "cell_mm": res.cell_mm,
}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n→ {out.name}")

# ── 눈으로 검증: 방 영역을 색칠해 그린다 ──────────────────────────
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPoly

fig, ax = plt.subplots(figsize=(24, 12), dpi=100)
for x0, y0, x1, y1 in ((s.dxf.start.x, s.dxf.start.y, s.dxf.end.x, s.dxf.end.y)
                       for s in tsp.query("LINE")):
    ax.plot([x0, x1], [y0, y1], lw=0.15, color="0.75", zorder=1)

cmap = plt.get_cmap("tab20")
for i, r in enumerate(res.rooms):
    if len(r.polygon) < 3:
        continue
    ax.add_patch(MplPoly(r.polygon, closed=True, alpha=0.45,
                         facecolor=cmap(i % 20), edgecolor="k", lw=0.4, zorder=2))
    cx = sum(p[0] for p in r.polygon) / len(r.polygon)
    cy = sum(p[1] for p in r.polygon) / len(r.polygon)
    ax.text(cx, cy, f"{r.room_no}\n{r.area_m2:.0f}㎡", ha="center", va="center",
            fontsize=5, zorder=3)

failed_no = {f.split(":")[0] for f in res.failed}
for n in nums:
    if n["room_no"] in failed_no:
        ax.plot(n["plan_x"], n["plan_y"], "rx", ms=9, mew=2, zorder=4)
        ax.text(n["plan_x"], n["plan_y"] + 700, n["room_no"], color="red",
                fontsize=6, ha="center", zorder=4)

ax.set_aspect("equal")
ax.axis("off")
# 내 임시폴더 절대경로가 박혀 있었다 — 다른 기계에선 안 돈다.
p = Path("artifacts") / "boundaries_check.png"
p.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(p, bbox_inches="tight", facecolor="white")
print(f"→ 검증 그림: {p.name}  (빨간 X = 실패한 방)")
