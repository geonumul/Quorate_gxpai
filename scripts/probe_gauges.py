# -*- coding: utf-8 -*-
"""차압계가 **어느 화살표(차압 설정 구간) 옆에** 있는지 대조한다.

조문: 고시 별표1 제4호 너목
  "청정실 및 필요한 경우 아이솔레이터와 주변구역 사이에 **차압계가 설치되어야 한다.**
   … 중요하다고 확인된 차압은 **연속적으로 모니터하고 기록**하여야 한다."

도면이 이미 구간별로 말해준다:
  Air Flow 10Pa / 15Pa  = 차압이 **설정된** 구간
  Air Flow no차압       = 차압계 설치가 **요구되지 않는** 위치 (도면 범례 3번)
→ 설정된 구간인데 차압계가 없으면, 유지, 기록할 방법이 없다.
"""
import math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
import ezdxf
from gxpai.core.config import raw_dir
from gxpai.core.db import connect

g = ezdxf.readfile(str(raw_dir()/"f_c783b865"/"차압계도.dxf"))
GLAY = ("차압계-아날로그", "차압계-디지털")
gauges = []
for e in g.modelspace():
    if e.dxf.layer in GLAY:
        try:
            p = e.dxf.insert if e.dxftype() == "INSERT" else e.dxf.center
        except Exception:
            continue
        gauges.append((p.x, p.y, e.dxf.layer))
print(f"차압계 {len(gauges)}개")
xs = [p[0] for p in gauges]; ys = [p[1] for p in gauges]
print(f"   좌표 범위 x {min(xs):.0f}~{max(xs):.0f}  y {min(ys):.0f}~{max(ys):.0f}")

with connect() as c, c.cursor() as cur:
    cur.execute("SELECT id FROM run WHERE facility_id='f_c783b865' ORDER BY started_at DESC LIMIT 1")
    rid = cur.fetchone()[0]
    cur.execute("""SELECT rh.room_no, rl.room_no, pr.evidence_x, pr.evidence_y,
                          pr.setpoint_pa, pr.layer
                     FROM pressure_relation pr
                     LEFT JOIN room rh ON rh.id=pr.room_high
                     LEFT JOIN room rl ON rl.id=pr.room_low
                    WHERE pr.run_id=%s AND NOT pr.approx""", (rid,))
    rels = cur.fetchall()
    cur.execute("""SELECT min(COALESCE(pres_x,plan_x)), max(COALESCE(pres_x,plan_x)),
                          min(COALESCE(pres_y,plan_y)), max(COALESCE(pres_y,plan_y))
                     FROM room WHERE run_id=%s AND plan_x IS NOT NULL""", (rid,))
    print("   방 좌표 범위 x {:.0f}~{:.0f}  y {:.0f}~{:.0f}".format(*cur.fetchone()))

R = 3000.0
print(f"\n차압 설정 구간 {len(rels)}개 — 반경 {R:.0f}mm 안에 차압계가 있는가")
miss = []
for hi, lo, ex, ey, sp, lay in rels:
    near = [gg for gg in gauges if math.hypot(gg[0]-ex, gg[1]-ey) <= R]
    tag = f"{sp:g}Pa" if sp else ("no차압" if lay and "no차압" in lay else "?")
    if near:
        pass
    elif sp:
        miss.append((hi, lo, tag, ex, ey))
print(f"   차압계 있음 {len(rels)-len(miss)}, **없음 {len(miss)}**")
for hi, lo, tag, ex, ey in miss[:10]:
    print(f"      {hi} → {lo}  설정 {tag}  @({ex:.0f},{ey:.0f})")
