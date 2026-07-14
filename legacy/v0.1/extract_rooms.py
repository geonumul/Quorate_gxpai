# -*- coding: utf-8 -*-
"""
extract_rooms.py - 평면도 DXF에서 방(room) 목록을 구조화 JSON으로 추출

원리:
  평면도 DXF의 TEX/TMP_TXT/11 레이어에 방이름 TEXT와 방번호 "(####)" TEXT가
  세로로 인접 배치되어 있음. 방번호 텍스트를 앵커로 잡고, 가장 가까운
  이름 텍스트를 근접 매칭(위쪽 우선)하여 (번호, 이름, 좌표, 층) 레코드 생성.

  층 판정은 2중:
    1) 방번호 첫자리 (3xxx = 3층, 4xxx = 4층)
    2) 시트 타이틀블록 x좌표 기반 bin (검증용 cross-check)

사용:
  python src/extract_rooms.py <평면도.dxf> -o output/rooms.json
"""
import argparse
import json
import math
import re
import sys

import ezdxf

ROOM_LAYERS = {"TEX", "TMP_TXT", "11"}
NUM_RE = re.compile(r"^\((\d{4}(?:-\d+)?)\)$")   # (3301), (3501-1)
BARE_NUM_RE = re.compile(r"^\d{4}(?:-\d+)?$")

SKIP_NAMES = {"UP", "DN", "PD/AV", "PD", "AV", "EPS", "TPS"}


def load_texts(msp):
    """방 관련 레이어의 TEXT를 (x, y, text, height) 리스트로."""
    out = []
    for e in msp:
        if e.dxftype() != "TEXT":
            continue
        if e.dxf.layer not in ROOM_LAYERS:
            continue
        t = e.dxf.text.strip()
        if not t:
            continue
        out.append((e.dxf.insert.x, e.dxf.insert.y, t, e.dxf.height))
    return out


def load_sheet_titles(msp):
    """타이틀블록 INSERT의 ATTRIB '도면명' → (x, 도면명) 리스트."""
    sheets = []
    for e in msp:
        if e.dxftype() == "INSERT" and e.attribs:
            d = {a.dxf.tag: a.dxf.text for a in e.attribs}
            if d.get("도면명"):
                sheets.append((e.dxf.insert.x, d["도면명"]))
    sheets.sort()
    return sheets


def sheet_of(x, sheets):
    """x좌표 → 가장 가까운 타이틀블록의 도면명."""
    if not sheets:
        return None
    return min(sheets, key=lambda s: abs(s[0] - x))[1]


def floor_from_number(no):
    d = no[0]
    return {"1": "1F", "2": "2F", "3": "3F", "4": "4F"}.get(d)


def extract_rooms(dxf_path):
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    texts = load_texts(msp)
    sheets = load_sheet_titles(msp)

    numbers = []   # (x, y, room_no)
    names = []     # (x, y, name, height)
    for x, y, t, h in texts:
        m = NUM_RE.match(t)
        if m:
            numbers.append((x, y, m.group(1)))
        elif BARE_NUM_RE.match(t):
            numbers.append((x, y, t))
        else:
            if t in SKIP_NAMES:
                continue
            names.append((x, y, t, h))

    rooms = []
    used_names = set()
    for nx, ny, no in numbers:
        # 이름 후보: 번호 위쪽(dy>0) 근접 텍스트 우선, 없으면 전방위 최근접
        best, best_d = None, None
        for i, (x, y, t, h) in enumerate(names):
            dx, dy = x - nx, y - ny
            d = math.hypot(dx, dy)
            if d > 6000:            # 도면단위(mm) 기준 상한
                continue
            penalty = 0 if 0 < dy < 2500 else 1500  # 이름은 번호 바로 위 관례
            score = d + penalty
            if best_d is None or score < best_d:
                best, best_d = i, score
        name = None
        if best is not None:
            name = names[best][2]
            used_names.add(best)
        rooms.append({
            "room_no": no,
            "name": name,
            "floor": floor_from_number(no),
            "sheet": sheet_of(nx, sheets),
            "x": round(nx, 1),
            "y": round(ny, 1),
            "source": "floorplan",
        })

    # 번호 없이 이름만 있는 방(복도/계단 등)도 별도 수집
    orphans = []
    for i, (x, y, t, h) in enumerate(names):
        if i in used_names:
            continue
        if re.search(r"[가-힣]", t):
            orphans.append({
                "room_no": None,
                "name": t,
                "floor": None,
                "sheet": sheet_of(x, sheets),
                "x": round(x, 1),
                "y": round(y, 1),
                "source": "floorplan_unnumbered",
            })
    return rooms, orphans, sheets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dxf")
    ap.add_argument("-o", "--out", default="output/rooms.json")
    args = ap.parse_args()

    rooms, orphans, sheets = extract_rooms(args.dxf)
    payload = {
        "source_file": args.dxf,
        "sheets": [s[1] for s in sheets],
        "n_rooms": len(rooms),
        "n_unnumbered": len(orphans),
        "rooms": sorted(rooms, key=lambda r: (r["room_no"] or "")),
        "unnumbered": orphans,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[extract_rooms] {len(rooms)} numbered rooms, "
          f"{len(orphans)} unnumbered → {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
