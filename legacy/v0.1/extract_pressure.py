# -*- coding: utf-8 -*-
"""
extract_pressure.py — PRESSURIZATION PLAN DXF에서 차압 정보 구조화

추출 대상:
  1. RM 레이어: 방번호 + 방이름 TEXT 쌍 (라벨박스 LWPOLYLINE 내부)
  2. TA 레이어: 수치 TEXT (급기량/차압 후보값 — 단위 발주처 확인 필요)
  3. 차압 화살표 심볼 INSERT (블록명 A$*, rotation → 압력 방향)
  4. 기준압 표기 ("50 Pa" 등)

사용:
  python src/extract_pressure.py <PRESSURIZATION.dxf> -o output/pressure.json
"""
import argparse
import json
import math
import re
import sys

import ezdxf

NUM_RE = re.compile(r"^\(?(\d{4}(?:-\d+)?)\)?$")


def extract(dxf_path):
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    rm_texts, ta_values, titles = [], [], []
    for e in msp:
        if e.dxftype() != "TEXT":
            continue
        t = e.dxf.text.strip()
        if not t:
            continue
        x, y = e.dxf.insert.x, e.dxf.insert.y
        if e.dxf.layer == "RM":
            rm_texts.append((x, y, t))
        elif e.dxf.layer == "TA":
            if re.fullmatch(r"\d+(?:\.\d+)?", t):
                ta_values.append({"x": round(x, 1), "y": round(y, 1),
                                  "value": float(t)})
        elif e.dxf.layer in ("TIT", "TXT"):
            titles.append((x, t))

    # 층 판정: 시트 타이틀 x좌표 기준 (3rd/4th 두 시트 병렬 배치)
    floor_anchors = []
    for x, t in titles:
        m = re.search(r"(\d)(?:rd|th|st|nd)\s+FLOOR", t, re.I)
        if m:
            floor_anchors.append((x, f"{m.group(1)}F"))
    floor_anchors.sort()

    def floor_of(x):
        if not floor_anchors:
            return None
        return min(floor_anchors, key=lambda a: abs(a[0] - x))[1]

    # RM 레이어: 번호 텍스트 → 최근접 이름 텍스트 매칭
    numbers, raw_names = [], []
    for x, y, t in rm_texts:
        m = NUM_RE.match(t)
        if m:
            numbers.append((x, y, m.group(1)))
        elif re.search(r"[가-힣A-Za-z]", t) and t not in ("UP", "DN", "Pa"):
            raw_names.append((x, y, t))

    # 여러 줄로 쪼개진 이름 병합: 좌표상 바로 아래(dy<=800, dx<=1200) 텍스트를 이어붙임
    raw_names.sort(key=lambda n: -n[1])
    used = [False] * len(raw_names)
    names = []
    for i, (x, y, t) in enumerate(raw_names):
        if used[i]:
            continue
        parts, cy = [t], y
        used[i] = True
        for j in range(i + 1, len(raw_names)):
            if used[j]:
                continue
            x2, y2, t2 = raw_names[j]
            if 0 < cy - y2 <= 800 and abs(x2 - x) <= 1200:
                parts.append(t2)
                used[j] = True
                cy = y2
        names.append((x, y, " ".join(parts)))

    rooms = []
    for nx, ny, no in numbers:
        best, best_d = None, None
        for x, y, t in names:
            d = math.hypot(x - nx, y - ny)
            if d < 3000 and (best_d is None or d < best_d):
                best, best_d = t, d
        rooms.append({
            "room_no": no,
            "name": best,
            "floor": floor_of(nx) or floor_from_no(no),
            "x": round(nx, 1),
            "y": round(ny, 1),
        })

    # 이름만 있는 방 (계단실 등 번호 미부여)
    matched_names = {r["name"] for r in rooms}
    unnumbered = [
        {"room_no": None, "name": t, "floor": floor_of(x),
         "x": round(x, 1), "y": round(y, 1)}
        for x, y, t in names if t not in matched_names
    ]

    # 차압 화살표 심볼: 익명블록 INSERT (rotation = 압력 흐름 방향)
    arrows = []
    for e in msp:
        if e.dxftype() == "INSERT" and e.dxf.name.startswith("A$"):
            arrows.append({
                "x": round(e.dxf.insert.x, 1),
                "y": round(e.dxf.insert.y, 1),
                "rotation_deg": round(e.dxf.rotation, 1),
                "floor": floor_of(e.dxf.insert.x),
            })

    # 기준압 표기
    ref_pressure = []
    for x, y, t in rm_texts:
        if t == "Pa":
            # 좌측 최근접 숫자와 결합
            cand = [(abs(x - nx), v) for nx, ny2, v in
                    [(a, b, c) for a, b, c in rm_texts if re.fullmatch(r"\d+", c)]
                    if abs(ny2 - y) < 300]
            if cand:
                ref_pressure.append({"value_pa": int(min(cand)[1]),
                                     "x": round(x, 1), "y": round(y, 1)})

    return rooms, unnumbered, ta_values, arrows, ref_pressure


def floor_from_no(no):
    return {"1": "1F", "2": "2F", "3": "3F", "4": "4F"}.get(no[0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dxf")
    ap.add_argument("-o", "--out", default="output/pressure.json")
    args = ap.parse_args()

    rooms, unnumbered, ta, arrows, ref = extract(args.dxf)
    payload = {
        "source_file": args.dxf,
        "note_ta_unit": "TA 레이어 수치의 단위(CMH 급기량 vs Pa 차압)는 발주처 확인 필요",
        "n_rooms": len(rooms),
        "rooms": sorted(rooms, key=lambda r: r["room_no"]),
        "unnumbered": unnumbered,
        "ta_values": ta,
        "pressure_arrows": arrows,
        "reference_pressure": ref,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[extract_pressure] rooms={len(rooms)} ta={len(ta)} "
          f"arrows={len(arrows)} → {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
