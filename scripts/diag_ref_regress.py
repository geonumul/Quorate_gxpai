# -*- coding: utf-8 -*-
"""참고도면이 51 → 2 로 깨졌다. 벽 재귀 깊이별로 무엇이 달라지는지 본다."""
import sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
import copy, ezdxf, yaml
from gxpai.core.config import raw_dir
from gxpai.core.db import connect
from gxpai.geometry import boundaries as B

prof = yaml.safe_load(Path("profiles/ref_2f_2026.yaml").read_text(encoding="utf-8"))
doc = ezdxf.readfile(str(raw_dir()/"f_c783b865"/"평면도.dxf"))
with connect() as c, c.cursor() as cur:
    cur.execute("SELECT id FROM run WHERE facility_id='f_c783b865' ORDER BY started_at DESC LIMIT 1")
    rid = cur.fetchone()[0]
    cur.execute("""SELECT room_no, plan_x, plan_y FROM room WHERE run_id=%s
                    AND plan_x IS NOT NULL""", (rid,))
    rooms = [{"room_no": r[0], "plan_x": r[1], "plan_y": r[2]} for r in cur.fetchall()]

bc = prof["boundaries"]
print(f"프로파일 boundaries: {bc}\n")
for depth in (0, 1, 2, 3, 5):
    segs = list(B._iter_wall_segments(doc, bc["wall_layers"], max_depth=depth,
                                      skip_blocks=bc.get("skip_blocks")))
    xs = [s[0] for s in segs] + [s[2] for s in segs]
    ys = [s[1] for s in segs] + [s[3] for s in segs]
    ext = (f"x {min(xs):.0f}~{max(xs):.0f}  y {min(ys):.0f}~{max(ys):.0f}") if segs else "없음"
    print(f"  깊이 {depth}: 벽 선분 {len(segs):6d}   범위 {ext}")

# 재귀를 켜면 어느 블록에서 벽이 새로 나오나
print("\n■ ARCH-변경 레이어가 나오는 블록 (재귀)")
cnt = Counter()
def walk(cont, name, d):
    for e in cont:
        if e.dxftype() == "INSERT":
            if d >= 5: continue
            b = doc.blocks.get(e.dxf.name)
            if b is not None:
                walk(b, e.dxf.name, d+1)
            continue
        lay = e.dxf.layer
        if lay in bc["wall_layers"] and e.dxftype() in ("LINE", "LWPOLYLINE", "ARC"):
            cnt[name] += 1
walk(doc.modelspace(), "(모델스페이스)", 0)
for k, v in cnt.most_common(10):
    print(f"   {k!r}: {v}")

print("\n■ 깊이별 build() 결과")
import gxpai.geometry.boundaries as BB
_orig = BB._iter_wall_segments
for depth in (2, 3, 5):
    BB._iter_wall_segments = (lambda d: (lambda doc_, lays, max_depth=5, skip_blocks=None:
        _orig(doc_, lays, max_depth=d, skip_blocks=skip_blocks)))(depth)
    cfg = copy.deepcopy(prof)
    res = BB.build(doc, rooms, cfg)
    print(f"   깊이 {depth}: 방 {len(res.rooms):3d}/{len(rooms)}  인접 {len(res.adjacency):3d}  "
          f"실패 {len(res.failed)}  {res.failed[:1]}")
BB._iter_wall_segments = _orig
