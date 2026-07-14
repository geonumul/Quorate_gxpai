# -*- coding: utf-8 -*-
"""전수 의심 감사 — "그럴듯한 숫자"가 실제로 맞는지 캔다."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
from gxpai.core.db import connect

BAD = []
def chk(ok, msg):
    print(f"   {'' if ok else '✘'} {msg}")
    if not ok:
        BAD.append(msg)

with connect() as c, c.cursor() as cur:
    for fac in ("f_1ae3a266", "f_c783b865"):
        cur.execute("SELECT id FROM run WHERE facility_id=%s ORDER BY started_at DESC LIMIT 1", (fac,))
        rid = cur.fetchone()[0]
        print(f"\n{fac}")

        # 1) 압력 유형이 NULL 인 방이 있나 (전부 채워져야 한다)
        cur.execute("SELECT count(*) FROM room WHERE run_id=%s AND regime IS NULL", (rid,))
        chk(cur.fetchone()[0] == 0, "모든 방에 압력 유형(regime)이 있다")

        # 2) 인접이 자기 자신을 가리키나
        cur.execute("SELECT count(*) FROM room_adjacency WHERE run_id=%s AND room_a=room_b", (rid,))
        chk(cur.fetchone()[0] == 0, "자기 자신과 인접한 방이 없다")

        # 3) 인접이 중복 저장됐나 (a,b) 와 (b,a)
        cur.execute("""SELECT count(*) FROM room_adjacency x JOIN room_adjacency y
                        ON x.run_id=y.run_id AND x.room_a=y.room_b AND x.room_b=y.room_a
                       WHERE x.run_id=%s""", (rid,))
        chk(cur.fetchone()[0] == 0, "인접이 양방향 중복 저장되지 않았다")

        # 4) 화살표가 자기 자신을 가리키나
        cur.execute("""SELECT count(*) FROM pressure_relation
                        WHERE run_id=%s AND room_high=room_low AND room_high IS NOT NULL""", (rid,))
        chk(cur.fetchone()[0] == 0, "고압=저압인 화살표가 없다")

        # 5) 면적이 말이 되나 (0.3㎡ 미만, 500㎡ 초과)
        cur.execute("""SELECT count(*) FROM room WHERE run_id=%s
                        AND area_m2 IS NOT NULL AND (area_m2 < 0.3 OR area_m2 > 500)""", (rid,))
        n = cur.fetchone()[0]
        chk(n == 0, f"면적이 상식 범위(0.3~500㎡) 안이다 (벗어남 {n})")

        # 6) 화살표 ↔ 절대압력 모순 (PRES-004 가 잡는 것)
        cur.execute("""SELECT count(*) FROM pressure_relation pr
                         JOIN room h ON h.id=pr.room_high JOIN room l ON l.id=pr.room_low
                        WHERE pr.run_id=%s AND NOT pr.approx
                          AND h.pressure_pa IS NOT NULL AND l.pressure_pa IS NOT NULL
                          AND h.pressure_pa < l.pressure_pa""", (rid,))
        n = cur.fetchone()[0]
        chk(n <= 1, f"화살표↔압력 모순 {n}건 (참고도면 1건은 도면 문제로 확인됨)")

        # 7) 방번호 중복
        cur.execute("""SELECT count(*) FROM (SELECT room_no FROM room WHERE run_id=%s
                        AND room_no IS NOT NULL GROUP BY room_no HAVING count(*)>1) t""", (rid,))
        n = cur.fetchone()[0]
        chk(n == 0, f"방번호가 중복되지 않았다 (중복 {n})")

        # 8) 게이트가 열린 규칙이 없나 (LBL 만 internal 로 허용)
        cur.execute("""SELECT DISTINCT rule_id FROM violation WHERE run_id=%s
                        AND rule_id NOT LIKE 'LBL%%'""", (rid,))
        leaked = [r[0] for r in cur.fetchall()]
        chk(not leaked, f"검수 안 된 규칙이 DB에 적재되지 않았다 (샌 것: {leaked})")

print("\n" + "="*60)
print(f"감사 결과: {'모두 통과' if not BAD else f'{len(BAD)}건 실패'}")
for b in BAD:
    print("   ✘", b)
