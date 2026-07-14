# -*- coding: utf-8 -*-
"""
merge_dataset.py - rooms.json + pressure.json → 마스터 방 스키마

방번호를 키로 평면도/차압도 정보를 병합.
차압 화살표는 각 층 시트 내에서 최근접 방에 귀속(참고용 raw 좌표 유지).

사용:
  python src/merge_dataset.py output/rooms.json output/pressure.json -o output/master_rooms.json
"""
import argparse
import json
import math
import sys


def nearest_room(x, y, rooms, max_d=8000):
    best, best_d = None, None
    for r in rooms:
        d = math.hypot(r["x"] - x, r["y"] - y)
        if d < max_d and (best_d is None or d < best_d):
            best, best_d = r, d
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rooms_json")
    ap.add_argument("pressure_json")
    ap.add_argument("-o", "--out", default="output/master_rooms.json")
    args = ap.parse_args()

    plan = json.load(open(args.rooms_json, encoding="utf-8"))
    pres = json.load(open(args.pressure_json, encoding="utf-8"))

    master = {}
    for r in plan["rooms"]:
        master[r["room_no"]] = {
            "room_no": r["room_no"],
            "name": r["name"],
            "floor": r["floor"],
            "sheet": r["sheet"],
            "plan_xy": [r["x"], r["y"]],
            "pressure_plan": None,
        }

    for r in pres["rooms"]:
        key = r["room_no"]
        entry = master.setdefault(key, {
            "room_no": key, "name": None, "floor": r["floor"],
            "sheet": None, "plan_xy": None, "pressure_plan": None,
        })
        entry["pressure_plan"] = {
            "name_on_pressure_plan": r["name"],
            "xy": [r["x"], r["y"]],
        }
        if entry["name"] is None:
            entry["name"] = r["name"]

    # 화살표 → 차압도 좌표계 기준 최근접 방 귀속
    pr_rooms = pres["rooms"]
    for a in pres.get("pressure_arrows", []):
        near = nearest_room(a["x"], a["y"], pr_rooms)
        if near:
            entry = master.get(near["room_no"])
            if entry:
                pp = entry.setdefault("pressure_plan", {})
                pp.setdefault("arrows", []).append(
                    {"xy": [a["x"], a["y"]],
                     "rotation_deg": a["rotation_deg"]})

    # 이름 불일치 리포트 (평면도 vs 차압도)
    mismatches = []
    for no, e in master.items():
        pp = e.get("pressure_plan") or {}
        n2 = pp.get("name_on_pressure_plan")
        if e["name"] and n2 and _norm(e["name"]) != _norm(n2):
            mismatches.append({"room_no": no,
                               "floorplan": e["name"],
                               "pressure_plan": n2})

    out = {
        "n_rooms": len(master),
        "n_name_mismatch": len(mismatches),
        "name_mismatches": mismatches,
        "rooms": [master[k] for k in sorted(master)],
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[merge] master rooms={len(master)}, "
          f"name mismatches={len(mismatches)} → {args.out}", file=sys.stderr)


def _norm(s):
    import re
    return re.sub(r"[\s()N\-]", "", s or "")


if __name__ == "__main__":
    main()
