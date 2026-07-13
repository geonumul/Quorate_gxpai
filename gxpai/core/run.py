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
from psycopg.types.json import Json          # 방 경계 폴리곤을 JSONB 로 적재

from ..ingest.extractors.equipment import EquipmentExtractor
from ..ingest.extractors.floorplan import FloorplanExtractor
from ..ingest.extractors.grades import GradeExtractor
from ..ingest.extractors.hvac import HvacExtractor
from ..ingest.extractors.overview import OverviewExtractor
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

    from ..ingest.extractors.pressure_value import PressureValueExtractor

    fp_ex, pr_ex = FloorplanExtractor(), PressureExtractor()
    eq_ex, hv_ex, gr_ex = EquipmentExtractor(), HvacExtractor(), GradeExtractor()
    ov_ex, pv_ex = OverviewExtractor(), PressureValueExtractor()
    floor_rooms: list[dict] = []
    pres_rooms: list[dict] = []
    equipment: list[dict] = []
    ahus: list[dict] = []
    overview: list[dict] = []
    arrows: list[dict] = []
    ta_values: list[dict] = []
    grade_recs: list[dict] = []      # 방번호 → 청정등급
    pa_recs: list[dict] = []         # 방번호 → 절대압력(Pa)
    floor_doc = None                 # 방 경계(벽) 추출용 평면도 DXF
    counts = {"floorplan": 0, "pressure": 0, "hvac": 0, "overview": 0,
              "ta_value": 0, "pressure_arrow": 0, "grade_zone": 0,
              "room_grade": 0, "room_pressure": 0, "pressure_unmatched": 0}

    missing_files: list[str] = []
    for d in fac["drawings"]:
        path = raw / d["filename"]
        if not path.exists():
            missing_files.append(d["filename"])  # 조용히 건너뛰지 말고 기록(완결성 감사)
            continue
        if d["kind"] == "floorplan":
            doc = _read_dxf(str(path))
            floor_doc = doc                      # 방 경계(벽) 추출에 다시 쓴다
            for rec in fp_ex.extract(doc, profile):
                rec.payload["source_drawing_id"] = d["id"]
                floor_rooms.append(rec.payload)
            for rec in eq_ex.extract(doc, profile):
                equipment.append(rec.payload)
            # ★등급을 '세기만' 하고 버리던 버그: room_grade 를 실제로 모은다.
            for rec in gr_ex.extract(doc, profile):
                if rec.kind == "room_grade":
                    grade_recs.append(rec.payload)
                    counts["room_grade"] += 1
                else:
                    counts["grade_zone"] += 1
            # 절대압력(Pa) - 평면도에 표기된 경우
            for rec in pv_ex.extract(doc, profile):
                if rec.kind == "room_pressure":
                    pa_recs.append(rec.payload)
                    counts["room_pressure"] += 1
                elif rec.kind == "pressure_unmatched":
                    counts["pressure_unmatched"] += rec.payload["count"]
            counts["floorplan"] += 1
        elif d["kind"] == "pressure":
            doc = _read_dxf(str(path))
            for rec in pr_ex.extract(doc, profile):
                if rec.kind == "pressure_room":
                    rec.payload["source_drawing_id"] = d["id"]
                    pres_rooms.append(rec.payload)
                elif rec.kind == "ta_value":
                    ta_values.append(rec.payload)
                    counts["ta_value"] += 1
                elif rec.kind == "pressure_arrow":
                    arrows.append(rec.payload)
                    counts["pressure_arrow"] += 1
            counts["pressure"] += 1
        elif d["kind"] == "hvac":
            doc = _read_dxf(str(path))
            for rec in hv_ex.extract(doc, profile):
                ahus.append(rec.payload)
            counts["hvac"] += 1
        elif d["kind"] == "overview":
            doc = _read_dxf(str(path))
            for rec in ov_ex.extract(doc, profile):
                rec.payload["source_drawing_id"] = d["id"]
                overview.append(rec.payload)
            counts["overview"] += 1

    merged = _merge(floor_rooms, pres_rooms)

    # ── 병합된 방에 등급·절대압력·압력유형을 얹는다 ────────────────
    n_grade = apply_grades(merged, grade_recs)
    n_pa = apply_pressures(merged, pa_recs)
    regime_counts = apply_regimes(merged, profile)

    # ── 방 경계(벽 flood-fill): 면적 + 정밀 인접 ──────────────────
    # 프로파일에 boundaries.wall_layers 가 없으면 조용히 건너뛴다(기존 최근접-k 인접 유지).
    boundary_res = None
    if floor_doc is not None and (profile.get("boundaries") or {}).get("wall_layers"):
        from ..geometry import boundaries as _b
        boundary_res = _b.build(floor_doc, merged, profile)
        area_by = {r.room_no: r for r in boundary_res.rooms}
        for r in merged:
            br = area_by.get(r.get("room_no"))
            if br:
                r["area_m2"] = br.area_m2
                r["boundary"] = br.polygon
                r["boundary_method"] = "floodfill"

    # 나노초 해상도로 run_id 발급: 같은 초에 두 번 ingest 해도 PK 충돌하지 않게(M5).
    run_id = f"run_{facility_id}_{time.time_ns()}"
    # 감사추적(M6/M7): run 행을 먼저 'running' 으로 별도 커밋 → 이후 실패해도 이력이 남는다.
    # 이력은 append-only(불변): 매 ingest = 새 run. 과거 run 은 지우지 않는다(감사).
    _create_run(facility_id, run_id, profile_version)
    try:
        n_eq = _load(facility_id, run_id, profile_version, merged, equipment, ahus,
                     overview, arrows, ta_values)
        _seed_questions(facility_id)
        # 인접 + 화살표↔방 귀속도 성공 판정에 포함(M8): 파생까지 끝나야 'done'.
        from ..geometry import adjacency, pressure_links
        # ★방 경계가 잡혔으면 **폴리곤 기반 정밀 인접**을 쓴다(최근접-k 근사보다 정확).
        #   근사 인접은 오탐/누락이 나서 ADJ-001·PRES-002/003 을 못 켰다.
        if boundary_res and boundary_res.adjacency:
            # door_adjacency 가 비면(문 데이터 없는 도면) None 을 넘겨 via_door 를 NULL 로 둔다.
            # 빈 리스트를 넘기면 "문이 하나도 없다"는 **거짓 사실**이 되어
            # ADJ-001 이 모든 쌍을 '동선 아님'으로 보고 전부 무시해 버린다.
            # (`rels=[]` vs `rels=None` 에서 똑같은 함정을 밟았다 — 없음과 비어있음은 다르다)
            dpairs = boundary_res.door_adjacency or None
            n_adj = adjacency.load_pairs(run_id, boundary_res.adjacency, method="polygon",
                                         door_pairs=dpairs)
            adj_method = "polygon"
        else:
            n_adj = adjacency.build(run_id)
            adj_method = "nearest"
        n_plinks = pressure_links.build(run_id)
    except Exception as exc:  # noqa: BLE001 - 어떤 실패든 감사에 남긴다
        _finish_run(run_id, "failed", str(exc)[:2000])
        raise
    _finish_run(run_id, "done")

    return {
        "run_id": run_id,
        "drawings_processed": counts,
        "n_floorplan_rooms": len(floor_rooms),
        "n_pressure_rooms": len(pres_rooms),
        "n_merged_rooms": len(merged),
        "n_equipment_attributed": n_eq,
        "n_ahu": len(ahus),
        "n_overview_items": len(overview),
        "n_pressure_arrows": len(arrows),
        "n_ta_values": len(ta_values),
        "n_adjacency": n_adj,
        "adjacency_method": adj_method,          # polygon(정밀) | nearest(근사)
        "n_pressure_links": n_plinks,
        "n_grade_applied": n_grade,              # 등급이 붙은 방 수 (0 이면 도면에 표기 없음)
        "n_pressure_pa_applied": n_pa,           # 절대압력이 붙은 방 수
        "regime_counts": regime_counts,          # protect/contain/hazard/neutral 분포
        "n_boundary_rooms": len(boundary_res.rooms) if boundary_res else 0,
        "boundary_failed": boundary_res.failed if boundary_res else [],
        "missing_drawings": missing_files,
    }


def apply_grades(merged: list[dict], grades: list[dict]) -> int:
    """등급 추출 결과(room_grade)를 병합된 방에 얹는다. 순수 함수.

    등급은 **방번호로** 붙인다(좌표 매칭은 추출기가 이미 끝냈다).
    도면에 등급 표기가 없으면 grades 가 비고, 방의 grade 는 None 으로 남는다 — 그게 정상이다.
    """
    by_no = {g["room_no"]: g["grade"] for g in grades if g.get("room_no")}
    n = 0
    for r in merged:
        g = by_no.get(r.get("room_no"))
        if g:
            r["grade"] = g
            n += 1
    return n


def apply_pressures(merged: list[dict], pas: list[dict]) -> int:
    """절대압력(Pa) 추출 결과를 병합된 방에 얹는다. 순수 함수."""
    by_no = {p["room_no"]: p["pressure_pa"] for p in pas if p.get("room_no")}
    n = 0
    for r in merged:
        pa = by_no.get(r.get("room_no"))
        if pa is not None:
            r["pressure_pa"] = pa
            n += 1
    return n


def apply_regimes(merged: list[dict], profile: dict) -> dict[str, int]:
    """압력 유형(regime)을 방마다 정한다. 순수 함수.

    이름으로 **추정**하고, 프로파일 `pressure_regime.overrides` 가 있으면 그게 이긴다.
    regime_source 로 어디서 온 값인지 남긴다(감사 추적).
    ※이름 추론은 확정이 아니다 — 특히 '충전/충진'은 시설 종류에 따라 정반대다.
    """
    from ..compliance.checks._regime import resolve_regime

    overrides = ((profile.get("pressure_regime") or {}).get("overrides")) or {}
    counts: dict[str, int] = {}
    for r in merged:
        reg, src = resolve_regime(r.get("name"), r.get("grade"), overrides, r.get("room_no"))
        r["regime"] = reg
        r["regime_source"] = src
        counts[reg] = counts.get(reg, 0) + 1
    return counts


def _merge(floor_rooms, pres_rooms) -> list[dict]:
    """방번호를 키로 평면도/차압도 병합 (v0.1 merge_dataset 이식)."""
    master: dict = {}
    for r in floor_rooms:
        if r["room_no"] is None:
            # 무번호 공간 키: 좌표 튜플(부동소수 f-string 은 '100' vs '100.0' 등에 취약).
            # 같은 좌표의 두 무번호 방은 여전히 한 항목으로 합쳐짐(현 데이터엔 발생 안 함).
            master[("_u", r["plan_x"], r["plan_y"])] = dict(r, pressure_name=None)
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
        # 차압도 방 위치 보존(화살표↔방 귀속용). 평면도와 좌표계가 달라 plan_x/y 와 별개 컬럼.
        entry["pres_x"] = r.get("x")
        entry["pres_y"] = r.get("y")
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


def _create_run(facility_id, run_id, profile_version) -> None:
    """run 행을 'running' 으로 별도 트랜잭션에 커밋(payload 실패해도 이력이 남게)."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO run (id, facility_id, pipeline_version, profile_version, status)
               VALUES (%s, %s, %s, %s, 'running')""",
            (run_id, facility_id, PIPELINE_VERSION, profile_version),
        )
        conn.commit()


def _finish_run(run_id, status, error=None) -> None:
    """run 을 done/failed 로 마감(별도 트랜잭션). finished_at·error 기록."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE run SET status=%s, finished_at=now(), error=%s WHERE id=%s",
            (status, error, run_id),
        )
        conn.commit()


def _load(facility_id, run_id, profile_version, rooms, equipment, ahus, overview,
          arrows, ta_values) -> int:
    # run 행은 이미 _create_run 이 만들었다. 여기선 payload 만 적재(멱등 DELETE 는 append-only
    # 모델에선 무의미하므로 제거). 매 ingest = 새 run_id 라 room 재삽입 충돌 없음.
    with connect() as conn, conn.cursor() as cur:
        room_points = []  # (room_id, plan_x, plan_y) - 장비 귀속용
        for r in rooms:
            cur.execute(
                """INSERT INTO room (facility_id, run_id, room_no, name, pressure_name,
                                     floor, sheet, plan_x, plan_y, pres_x, pres_y,
                                     source_drawing_id, review_status,
                                     grade, pressure_pa, regime, regime_source,
                                     area_m2, boundary, boundary_method)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'unreviewed',
                           %s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (facility_id, run_id, r.get("room_no"), r.get("name"), r.get("pressure_name"),
                 r.get("floor"), r.get("sheet"), r.get("plan_x"), r.get("plan_y"),
                 r.get("pres_x"), r.get("pres_y"), r.get("source_drawing_id"),
                 r.get("grade"), r.get("pressure_pa"), r.get("regime"), r.get("regime_source"),
                 r.get("area_m2"),
                 Json(r["boundary"]) if r.get("boundary") else None,
                 r.get("boundary_method")),
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

        # 설계개요 표 항목 → facility_meta (T1.2.2)
        for m in overview:
            cur.execute(
                """INSERT INTO facility_meta (facility_id, run_id, key, value, source_drawing_id)
                   VALUES (%s,%s,%s,%s,%s)
                   ON CONFLICT (facility_id, run_id, key) DO UPDATE SET value = EXCLUDED.value""",
                (facility_id, run_id, m["key"], m["value"], m.get("source_drawing_id")),
            )

        # 차압 화살표 → pressure_relation 에 원시 보관 (방 미귀속, approx=true).
        # 방향 의미 확정(S-1)·방 귀속은 Stage 2 에서 채운다.
        # head_deg 는 블록 기하에서 **잰** 세계 각도다(가정 아님). NULL 이면 못 읽은 것.
        # layer/setpoint_pa: 레이어 이름이 곧 차압 설정값('Air Flow 15Pa' → 15).
        for a in arrows:
            cur.execute(
                """INSERT INTO pressure_relation
                     (run_id, room_high, room_low, evidence_x, evidence_y, rotation, approx,
                      head_deg, layer, setpoint_pa)
                   VALUES (%s, NULL, NULL, %s, %s, %s, true, %s, %s, %s)""",
                (run_id, a["x"], a["y"], a["rotation_deg"],
                 a.get("head_deg"), a.get("layer"), a.get("setpoint_pa")),
            )

        # TA 수치 → ta_value (단위 미확정, 어떤 규칙도 참조 금지 R-D2)
        for t in ta_values:
            cur.execute(
                """INSERT INTO ta_value (run_id, facility_id, x, y, value_raw, unit)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (run_id, facility_id, t["x"], t["y"], t["value_raw"], t.get("unit")),
            )

        conn.commit()   # payload 커밋. done/failed 마감은 ingest() 가 _finish_run 으로.
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
