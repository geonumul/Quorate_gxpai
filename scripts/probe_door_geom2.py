# -*- coding: utf-8 -*-
"""문 블록의 로컬 기하를 전부 덤프. **문틀 선분**(벽 구멍을 막을 선)을 어떻게 뽑을지 정한다."""
import sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
import ezdxf
from gxpai.core.config import raw_dir

doc = ezdxf.readfile(str(next(p for p in (raw_dir()/"f_1ae3a266").iterdir() if "평면" in p.name)))

# 문 블록 INSERT 를 이름별로 센다
cnt = Counter()
for e in doc.modelspace().query("INSERT"):
    if e.dxf.layer in ("DOR", "DOOR", "DOOR-HID", "DOOR(HIDDEN)"):
        cnt[e.dxf.name] += 1
print("문 레이어에 놓인 블록")
for k, v in cnt.most_common():
    print(f"   {k!r}: {v}")

for name in [k for k, _ in cnt.most_common(4)]:
    b = doc.blocks.get(name)
    if b is None:
        continue
    print(f"\n블록 {name!r} 로컬 기하")
    for e in b:
        t = e.dxftype()
        if t == "ARC":
            print(f"   ARC  중심({e.dxf.center.x:.0f},{e.dxf.center.y:.0f}) r={e.dxf.radius:.0f} "
                  f"{e.dxf.start_angle:.0f}°~{e.dxf.end_angle:.0f}°")
        elif t == "LWPOLYLINE":
            pts = [(round(p[0]), round(p[1])) for p in e.get_points("xy")]
            print(f"   LWPOLY closed={e.closed} {pts}")
        elif t == "LINE":
            print(f"   LINE ({e.dxf.start.x:.0f},{e.dxf.start.y:.0f})→({e.dxf.end.x:.0f},{e.dxf.end.y:.0f})")
        else:
            print(f"   {t}")
