# -*- coding: utf-8 -*-
"""방 라벨과 벽이 **같은 시트**에 있는가? 아니면 라벨은 장비배치도, 벽은 평면도인가?

이 DXF 는 A-201~207 = **시트 7장**이 한 파일에 나란히 놓여 있다.
방 라벨이 있는 x구간과 벽이 있는 x구간이 어긋나면, 우리는 엉뚱한 시트를 보고 있는 것이다.
"""
import sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
import ezdxf
from gxpai.core.config import raw_dir
from gxpai.core.db import connect

doc = ezdxf.readfile(str(next(p for p in (raw_dir()/"f_1ae3a266").iterdir() if "평면" in p.name)))

# 시트 제목 텍스트
print("시트 제목처럼 보이는 텍스트 (x 순)")
titles = []
for e in doc.modelspace():
    if e.dxftype() in ("TEXT", "MTEXT"):
        t = (e.plain_text() if e.dxftype()=="MTEXT" else e.dxf.text).strip()
        if any(w in t for w in ("평면도", "배치도", "층")) and len(t) < 30:
            p = e.dxf.insert
            titles.append((p.x, p.y, t, e.dxf.layer))
for x, y, t, l in sorted(titles)[:20]:
    print(f"   x={x:9.0f} y={y:8.0f}  {t!r:24} 레이어={l!r}")

# 방번호 라벨의 x 분포 (10만 단위 구간)
with connect() as c, c.cursor() as cur:
    cur.execute("SELECT id FROM run WHERE facility_id='f_1ae3a266' ORDER BY started_at DESC LIMIT 1")
    rid = cur.fetchone()[0]
    cur.execute("""SELECT room_no, plan_x FROM room WHERE run_id=%s AND room_no ~ '^[34]'
                    AND plan_x IS NOT NULL""", (rid,))
    rows = cur.fetchall()
b = defaultdict(lambda: Counter())
for no, x in rows:
    b[int(x // 50000) * 50] [no[0]] += 1
print("\n방번호 라벨의 x 분포 (5만mm 구간별, 3xxx / 4xxx)")
for k in sorted(b):
    print(f"   x {k:4d}k~ : 3F {b[k]['3']:3d}  4F {b[k]['4']:3d}")

# 벽(하니컴패널, B-WAL)의 x 분포
wc = Counter()
for e in doc.modelspace():
    if e.dxf.layer in ("하니컴패널", "B-WAL") and e.dxftype() == "LINE":
        wc[int(e.dxf.start.x // 50000) * 50] += 1
print("\n벽(하니컴패널, B-WAL) 선분의 x 분포")
for k in sorted(wc):
    print(f"   x {k:4d}k~ : {wc[k]}")
