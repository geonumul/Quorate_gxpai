# -*- coding: utf-8 -*-
"""★모순 화살표 9개의 정체: 레이어가 다른가? 스케일이 음수인가? 주변에 더 가까운 방이 있나?

레이어 이름 자체가 차압 설정값이다: 'Air Flow 10Pa' / 'Air Flow 15Pa' / 'Air Flow no차압'.
"""
import math, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
import ezdxf, yaml
from gxpai.core.config import raw_dir
from gxpai.core.db import connect

prof = yaml.safe_load(Path("profiles/ref_2f_2026.yaml").read_text(encoding="utf-8"))
ALAY = set(prof["pressure"]["arrow_layers"])

with connect() as conn, conn.cursor() as cur:
    cur.execute("SELECT id FROM run WHERE facility_id='f_c783b865' ORDER BY started_at DESC LIMIT 1")
    run_id = cur.fetchone()[0]
    cur.execute("""SELECT room_no, name, pressure_pa, COALESCE(pres_x,plan_x), COALESCE(pres_y,plan_y)
                     FROM room WHERE run_id=%s AND room_no IS NOT NULL
                       AND COALESCE(pres_x,plan_x) IS NOT NULL""", (run_id,))
    rooms = cur.fetchall()

doc = ezdxf.readfile(str(raw_dir() / "f_c783b865" / "차압흐름도.dxf"))
msp = doc.modelspace()

BAD = [(303638,66455),(302252,66496),(299079,56518),(301831,58830),(302614,54745),
       (300570,46126),(307831,38284),(304839,45452),(304804,33023)]

print("■ 화살표 레이어별 개수")
c = Counter(e.dxf.layer for e in msp.query("INSERT") if e.dxf.layer in ALAY)
for k, n in c.most_common():
    print(f"   {k!r}: {n}")

print("\n■ 모순 화살표 9개의 레이어·스케일")
for e in msp.query("INSERT"):
    if e.dxf.layer not in ALAY:
        continue
    x, y = e.dxf.insert.x, e.dxf.insert.y
    for bx, by in BAD:
        if math.hypot(x-bx, y-by) < 5:
            xs = getattr(e.dxf, "xscale", 1.0); ys = getattr(e.dxf, "yscale", 1.0)
            print(f"   @({bx},{by})  레이어={e.dxf.layer!r}  블록={e.dxf.name!r} "
                  f"rot={e.dxf.rotation:g}  xs={xs:g} ys={ys:g}")

print("\n■ 첫 모순 화살표 @(303638,66455) 주변 8m 내 방 (가까운 순)")
near = sorted(((math.hypot(rx-303638, ry-66455), rno, rn, pa, rx, ry)
               for rno, rn, pa, rx, ry in rooms), key=lambda t: t[0])
for d, rno, rn, pa, rx, ry in near[:6]:
    print(f"   {d:7.0f}mm  {rno} {rn} {pa}Pa  @({rx:.0f},{ry:.0f})")
