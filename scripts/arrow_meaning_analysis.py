# -*- coding: utf-8 -*-
"""화살표 의미 교차검증 (재현용, 스키마 미변경).

docs/기존데이터_분석.md 발견 3의 근거를 뽑는 일회성 분석. 원본 차압도에서 방 라벨과
화살표를 같은 좌표계로 읽어, 각 화살표가 어느 두 방 사이에 있고 화살촉이 어느 방을 향하는지
구한 뒤, 방향 그래프의 출발점(source)/도착점(sink)을 낸다.

핵심 논리: 계단실·샤프트(PD/AV)는 물리적으로 가장 저압인 '공기가 최종적으로 빠지는 곳'이다.
이들이 전부 도착점(화살촉이 향하는 곳)이면 → 화살촉은 저압 쪽을 가리킨다(고압→저압).

화살표 기하(S-1 확정): rotation=0 에서 화살촉 -y(아래). 세계각도 = 270° + rotation.

실행: 고객 원본 차압도가 raw/<facility_id>/ 에 있어야 함(git 밖). 예:
  PYTHONUTF8=1 python scripts/arrow_meaning_analysis.py f_1ae3a266 osd_hs_2025
"""
from __future__ import annotations

import math
import re
import sys
from collections import defaultdict
from pathlib import Path

import ezdxf
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from gxpai.ingest.dxftext import iter_label_texts  # noqa: E402
from gxpai.ingest.extractors._common import match_name_to_anchor, merge_multiline_names  # noqa: E402

FACILITY = sys.argv[1] if len(sys.argv) > 1 else "f_1ae3a266"
PROFILE = sys.argv[2] if len(sys.argv) > 2 else "osd_hs_2025"
AMBIENT = ("계단", "PD/AV", "샤프트", "E/V", "덕트")   # 주변부(저압일 수밖에 없는 곳)
MAXD, LAT = 6000.0, 3500.0                            # 방 탐색 반경 / 측면 허용(mm)


def head_vec(rot):
    th = math.radians(270.0 + rot)
    return math.cos(th), math.sin(th)


def main() -> int:
    prof = yaml.safe_load((REPO / "profiles" / f"{PROFILE}.yaml").read_text(encoding="utf-8"))
    pr = prof["pressure"]
    etypes = prof.get("label_entity_types", ["TEXT", "MTEXT"])

    raw = REPO / "raw" / FACILITY
    dxf = next((p for p in raw.glob("*.dxf") if "PRESSUR" in p.name.upper()), None)
    if not dxf:
        print(f"차압도 DXF 없음: {raw} (고객 원본이 git 밖에 있어야 함)")
        return 1
    doc = ezdxf.readfile(str(dxf))

    # 방번호/이름 (RM 레이어)
    num_re = re.compile(r"^\(?(\d{4}(?:-\d+)?)\)?$")
    numbers, raw_names = [], []
    for x, y, t, _h in iter_label_texts(doc, [pr["rm_layer"]], etypes):
        m = num_re.match(t)
        if m:
            numbers.append((x, y, m.group(1)))
        elif re.search(r"[가-힣A-Za-z]", t) and t not in ("UP", "DN", "Pa"):
            raw_names.append((x, y, t))
    mg = pr.get("multiline_merge", {})
    names = merge_multiline_names(raw_names, mg["max_dy_mm"], mg["max_dx_mm"]) if mg else raw_names
    rooms = []
    for nx, ny, no in numbers:
        _i, name = match_name_to_anchor(nx, ny, names, pr["name_match_dist_mm"])
        rooms.append((no, name, nx, ny))

    # 화살표 (익명블록)
    prefix = pr["arrow_block_prefix"]
    arrows = [(e.dxf.insert.x, e.dxf.insert.y, e.dxf.rotation)
              for e in doc.modelspace()
              if e.dxftype() == "INSERT" and e.dxf.name.startswith(prefix)]
    print(f"차압도 방 라벨 {len(rooms)}개 / 화살표 {len(arrows)}개")

    # 화살표 → 꼬리쪽/머리쪽 방
    edges, name_of = [], {}
    for ax, ay, rot in arrows:
        hx, hy = head_vec(rot)
        head_best = tail_best = None
        head_s = tail_s = None
        for no, name, rx, ry in rooms:
            dx, dy = rx - ax, ry - ay
            if math.hypot(dx, dy) > MAXD:
                continue
            proj = dx * hx + dy * hy
            if abs(dx * -hy + dy * hx) > LAT:
                continue
            if proj > 0 and (head_s is None or proj > head_s):
                head_best, head_s = (no, name), proj
            if proj < 0 and (tail_s is None or -proj > tail_s):
                tail_best, tail_s = (no, name), -proj
        if head_best and tail_best and head_best[0] != tail_best[0]:
            edges.append((tail_best, head_best))
            name_of[tail_best[0]] = tail_best[1]
            name_of[head_best[0]] = head_best[1]
    print(f"양쪽 방 귀속 화살표 {len(edges)}/{len(arrows)}")

    outd, ind = defaultdict(int), defaultdict(int)
    for (t, _tn), (h, _hn) in edges:
        outd[t] += 1
        ind[h] += 1
    allrooms = set(outd) | set(ind)

    dir_pairs = {(t[0], h[0]) for t, h in edges}
    contra = [(a, b) for (a, b) in dir_pairs if (b, a) in dir_pairs and a < b]
    print(f"방향 간선(고유) {len(dir_pairs)}개, 모순 {len(contra)}개 "
          f"→ 일관도 {100*(1-len(contra)/max(len(dir_pairs),1)):.0f}%")

    sinks = [no for no in allrooms if ind[no] > 0 and outd[no] == 0]
    amb = [no for no in sinks if any(k in (name_of.get(no) or "") for k in AMBIENT)]
    amb_src = [no for no in allrooms if outd[no] > 0 and ind[no] == 0
               and any(k in (name_of.get(no) or "") for k in AMBIENT)]
    print(f"계단/샤프트: 도착점(SINK) {len(amb)}개 / 출발점(SOURCE) {len(amb_src)}개")
    print("판정: 계단·샤프트가 전부 도착점이면 화살촉=저압 쪽(고압→저압).")
    print(f"  도착점인 계단/샤프트: {[name_of.get(n) for n in amb]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
