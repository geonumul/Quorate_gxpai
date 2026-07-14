# -*- coding: utf-8 -*-
"""남은 모순 3건: 화살표 축 위에 놓인 방을 앞뒤로 전부 나열한다.
우리가 엉뚱한 방을 붙였는지, 도면이 정말 모순인지 가른다."""
import math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8")
from gxpai.core.db import connect
from gxpai.geometry.pressure_links import MAX_DIST, MAX_LAT

BAD = [(299079, 56518), (303970, 36900), (304885, 47007)]
with connect() as c, c.cursor() as cur:
    cur.execute("SELECT id FROM run WHERE facility_id='f_c783b865' ORDER BY started_at DESC LIMIT 1")
    run_id = cur.fetchone()[0]
    cur.execute("""SELECT room_no, name, pressure_pa, COALESCE(pres_x,plan_x), COALESCE(pres_y,plan_y)
                     FROM room WHERE run_id=%s AND room_no IS NOT NULL
                       AND COALESCE(pres_x,plan_x) IS NOT NULL""", (run_id,))
    rooms = cur.fetchall()
    for bx, by in BAD:
        cur.execute("""SELECT head_deg, layer, setpoint_pa, rotation FROM pressure_relation
                        WHERE run_id=%s AND abs(evidence_x-%s)<2 AND abs(evidence_y-%s)<2""",
                    (run_id, bx, by))
        hd, lay, sp, rot = cur.fetchone()
        hx, hy = math.cos(math.radians(hd)), math.sin(math.radians(hd))
        print(f"\n화살표 @({bx},{by})  화살촉 {hd:g}°  레이어={lay!r} 설정={sp}Pa (rot={rot:g})")
        cand = []
        for rno, rn, pa, rx, ry in rooms:
            dx, dy = rx - bx, ry - by
            dist = math.hypot(dx, dy)
            lat = abs(dx * -hy + dy * hx)
            proj = dx * hx + dy * hy
            if dist <= MAX_DIST and lat <= MAX_LAT:
                cand.append((proj, lat, rno, rn, pa))
        for proj, lat, rno, rn, pa in sorted(cand):
            side = "화살촉쪽(저압이어야)" if proj > 0 else "꼬리쪽(고압이어야)"
            print(f"   proj={proj:+8.0f} 측면={lat:6.0f}  {rno} {rn} {pa}Pa   ← {side}")
