# -*- coding: utf-8 -*-
"""Run - 파이프라인 1회 실행 단위. 도면 추출 → 병합 → room/equipment/ahu 적재.

로드맵: S1.1(재현성) + T1.1.2(방/차압) + T1.2.1(AHU) + T1.2.3(장비) + T1.2.4(Grade 스켈레톤)
멱등(R-E3): run 단위로 적재. run_id 는 실행마다 발급되어 이력이 쌓인다.
"""
from __future__ import annotations

import math
import time

import ezdxf
from ezdxf import recover

from ..ingest.extractors.equipment import EquipmentExtractor
from ..ingest.extractors.floorplan import FloorplanExtractor
from ..ingest.extractors.grades import GradeExtractor
from ..ingest.extractors.hvac import HvacExtractor
from ..ingest.extractors.pressure import PressureExtractor
from .config import load_profile, raw_dir
from .db import connect

PIPELINE_VERSION = "0.1.0"

# 발주처 확인이 필요한 미결 항목 (question 테이블 시드)
_QUESTION_SEEDS = [
    ("TA 단위", "TA 레이어 수치가 급기량(CMH)인지 차압(Pa)인지 확정 필요. 확정 전 규칙 참조 금지 (R-D2)."),
    ("Grade 도면", "청정등급(Grade) 도면 미수령. 등급 기반 violations 의 전제조건 (T1.2.4)."),
    ("화살표 방향", "차압 화살표 rotation 의 고압→저압 방향 의미 확정 필요. 틀리면 PRES-001 정반대 (S-1)."),
]


def _read_dxf(path):
    """DXF 로드. 손상 파일은 recover 모드 폴백 (R-E2: recover는 느리므로 폴백으로만)."""
    try:
        return ezdxf.readfile(path)
    except ezdxf.DXFStructureError:
        doc, _auditor = recover.readfile(path)
        return doc


def ingest(facility_id: str) -> dict:
    """시설 도면을 추출·병합해 room/equipment/ahu 에 적재하고 요약을 반환."""
    from . import registry

    fac = registry.get_facility(facility_id)
    if not fac:
        raise ValueError(f"시설 없음: {facility_id}. 먼저 facility add 하세요.")
    profile = load_profile(fac["profile_id"])
    profile_version = str(profile.get("profile_version", "0"))
    raw = raw_dir() / facility_id

    fp_ex, pr_ex = FloorplanExtractor(), PressureExtractor()
    eq_ex, hv_ex, gr_ex = EquipmentExtractor(), HvacExtractor(), GradeExtractor()
    floor_rooms: list[dict] = []
    pres_rooms: list[dict] = []
    equipment: list[dict] = []
    ahus: list[dict] = []
    counts = {"floorplan": 0, "pressure": 0, "hvac": 0,
              "ta_value": 0, "pressure_arrow": 0, "grade_zone": 0}

    for d in fac["drawings"]:
        path = raw / d["filename"]
        if not path.exists():
            continue
        if d["kind"] == "floorplan":
            doc = _read_dxf(str(path))
            for rec in fp_ex.extract(doc, profile):
                rec.payload["source_drawing_id"] = d["id"]
                floor_rooms.append(rec.payload)
            for rec in eq_ex.extract(doc, profile):
                equipment.append(rec.payload)
            for rec in gr_ex.extract(doc, profile):
                counts["grade_zone"] += 1
            counts["floorplan"] += 1
        elif d["kind"] == "pressure":
            doc = _read_dxf(str(path))
            for rec in pr_ex.extract(doc, profile):
                if rec.kind == "pressure_room":
                    rec.payload["source_drawing_id"] = d["id"]
                    pres_rooms.append(rec.payload)
                elif rec.kind in counts:
                    counts[rec.kind] += 1
            counts["pressure"] += 1
        elif d["kind"] == "hvac":
            doc = _read_dxf(str(path))
            for rec in hv_ex.extract(doc, profile):
                ahus.append(rec.payload)
            counts["hvac"] += 1

    merged = _merge(floor_rooms, pres_rooms)

    run_id = f"run_{facility_id}_{int(time.time())}"
    n_eq = _load(facility_id, run_id, profile_version, merged, equipment, ahus)
    _seed_questions(facility_id)

    return {
        "run_id": run_id,
        "drawings_processed": counts,
        "n_floorplan_rooms": len(floor_rooms),
        "n_pressure_rooms": len(pres_rooms),
        "n_merged_rooms": len(merged),
        "n_equipment_attributed": n_eq,
        "n_ahu": len(ahus),
    }


def _merge(floor_rooms, pres_rooms) -> list[dict]:
    """방번호를 키로 평면도/차압도 병합 (v0.1 merge_dataset 이식)."""
    master: dict = {}
    for r in floor_rooms:
        if r["room_no"] is None:
            master[f"_u_{r['plan_x']}_{r['plan_y']}"] = dict(r, pressure_name=None)
            continue
        master[r["room_no"]] = {
            "room_no": r["room_no"], "name": r["name"], "floor": r["floor"],
            "sheet": r["sheet"], "plan_x": r["plan_x"], "plan_y": r["plan_y"],
            "source_drawing_id": r.get("source_drawing_id"), "pressure_name": None,
        }
    for r in pres_rooms:
        key = r["room_no"]
        entry = master.setdefault(key, {
            "room_no": key, "name": r["name"], "floor": r["floor"], "sheet": None,
            "plan_x": None, "plan_y": None,
            "source_drawing_id": r.get("source_drawing_id"), "pressure_name": None,
        })
        entry["pressure_name"] = r["name"]
        if entry.get("name") is None:
            entry["name"] = r["name"]
        if entry.get("floor") is None:
            entry["floor"] = r["floor"]
    return list(master.values())


def _nearest_room_id(x, y, room_points, max_d=8000):
    best, best_d = None, None
    for rid, rx, ry in room_points:
        if rx is None or ry is None:
            continue
        d = math.hypot(rx - x, ry - y)
        if d < max_d and (best_d is None or d < best_d):
            best, best_d = rid, d
    return best


def _load(facility_id, run_id, profile_version, rooms, equipment, ahus) -> int:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO run (id, facility_id, pipeline_version, profile_version, status)
               VALUES (%s, %s, %s, %s, 'running')""",
            (run_id, facility_id, PIPELINE_VERSION, profile_version),
        )
        cur.execute("DELETE FROM room WHERE run_id=%s", (run_id,))
        room_points = []  # (room_id, plan_x, plan_y) - 장비 귀속용
        for r in rooms:
            cur.execute(
                """INSERT INTO room (facility_id, run_id, room_no, name, floor, sheet,
                                     plan_x, plan_y, source_drawing_id, review_status)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'unreviewed') RETURNING id""",
                (facility_id, run_id, r.get("room_no"), r.get("name"), r.get("floor"),
                 r.get("sheet"), r.get("plan_x"), r.get("plan_y"),
                 r.get("source_drawing_id")),
            )
            rid = cur.fetchone()[0]
            room_points.append((rid, r.get("plan_x"), r.get("plan_y")))

        # 장비 → 최근접 방 귀속 (method=nearest, Stage 2 에서 contains 승격)
        n_eq = 0
        for e in equipment:
            room_id = _nearest_room_id(e["x"], e["y"], room_points)
            cur.execute(
                """INSERT INTO equipment (run_id, facility_id, name, room_id, x, y, method)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (run_id, facility_id, e["name"], room_id, e["x"], e["y"], e["method"]),
            )
            if room_id is not None:
                n_eq += 1

        for a in ahus:
            cur.execute(
                """INSERT INTO ahu (run_id, facility_id, ahu_id, x, y, floor)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (run_id, facility_id, a["ahu_id"], a["x"], a["y"], a.get("floor")),
            )

        cur.execute("UPDATE run SET status='done' WHERE id=%s", (run_id,))
        conn.commit()
        return n_eq


def _seed_questions(facility_id) -> None:
    """미결 질문 시드 (중복 없이). 발주처 확인 대상을 DB로 승격."""
    with connect() as conn, conn.cursor() as cur:
        for topic, body in _QUESTION_SEEDS:
            cur.execute(
                """INSERT INTO question (facility_id, topic, body, status)
                   SELECT %s, %s, %s, 'open'
                   WHERE NOT EXISTS (
                     SELECT 1 FROM question WHERE facility_id=%s AND topic=%s)""",
                (facility_id, topic, body, facility_id, topic),
            )
        conn.commit()
