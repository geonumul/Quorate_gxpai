# -*- coding: utf-8 -*-
"""Run - 파이프라인 1회 실행 단위. 도면 추출 → 병합 → room/equipment/ahu 적재.

로드맵: S1.1(재현성) + T1.1.2(방/차압) + T1.2.1(AHU) + T1.2.3(장비) + T1.2.4(Grade 스켈레톤)
멱등(R-E3): run 단위로 적재. run_id 는 실행마다 발급되어 이력이 쌓인다.
"""
from __future__ import annotations

import math
import time
from pathlib import Path

import ezdxf
from ezdxf import recover
from psycopg.types.json import Json          # 방 경계 폴리곤을 JSONB 로 적재

from ..ingest.extractors.equipment import EquipmentExtractor
from ..ingest.extractors.floorplan import FloorplanExtractor
from ..ingest.extractors.airflow import AirflowExtractor
from ..ingest.extractors.gauge import GaugeExtractor
from ..ingest.extractors.interlock import InterlockExtractor
from ..ingest.extractors.grades import GradeExtractor
from ..ingest.extractors.hvac import HvacExtractor
from ..ingest.extractors.overview import OverviewExtractor
from ..ingest.extractors.pressure import PressureExtractor
from .config import load_profile, raw_dir
from .db import connect

PIPELINE_VERSION = "0.1.0"

# 문 검출률이 이보다 낮으면 **문 데이터를 쓰지 않는다.**
#   방에는 대개 문이 하나씩 있다. 이 값이 낮으면 도면에 문이 없어서가 아니라
#   **우리 문 검출이 실패한 것**이다. 그런데도 쓰면 ADJ-001/002/003/004 가
#   검출 못 한 문에 대해 "문이 없으니 위반 아님"으로 **진짜 위반을 숨긴다.**
#
#   예전엔 함수 **지역변수**여서 시험이 import 할 수 없었다. 그래서 시험이
#   임계값을 손으로 다시 정의했고, **임계값을 0.1로 바꿔도 시험이 통과했다**(껍데기 시험).
#   → 모듈 상수로 끌어올린다. 시험이 이 값을 실제로 태운다.
DOOR_TRUST = 0.8

# 발주처 확인이 필요한 미결 항목 (question 테이블 시드)
_QUESTION_SEEDS = [
    ("TA 단위", "TA 레이어 수치가 급기량(CMH)인지 차압(Pa)인지 확정 필요. 확정 전 규칙 참조 금지 (R-D2)."),
    ("Grade 도면", "청정등급(Grade) 도면 미수령. 등급 기반 violations 의 전제조건 (T1.2.4)."),
    ("화살표 방향", "차압 화살표 rotation 의 고압→저압 방향 의미 확정 필요. 틀리면 PRES-001 정반대 (S-1)."),
]


def _same_source_warning(drawings: list[dict]) -> str | None:
    """평면도와 차압도가 같은 파일(같은 sha256)이면 경고 문구를 돌려준다.

    LBL-001(이름 불일치), LBL-002(도면 간 방 차이)는 **두 도면을 대조**하는 검사다.
    같은 파일을 두 종류로 등록하면 **자기 자신과 비교**하게 되어 늘 0건이 나온다.
    "0건 = 깨끗하다"가 아니라 **"0건 = 대조할 게 없다"** 이다.
    """
    by_kind: dict[str, str] = {}
    for d in drawings:
        if d.get("kind") in ("floorplan", "pressure") and d.get("sha256"):
            by_kind[d["kind"]] = d["sha256"]
    if len(by_kind) == 2 and len(set(by_kind.values())) == 1:
        return ("평면도와 차압도가 **같은 파일**입니다(sha256 일치). "
                "LBL-001/002 는 두 도면을 대조하는 검사라 **판정 불가**입니다 — "
                "0건이 나와도 '대조했더니 깨끗하다'는 뜻이 아닙니다.")
    return None


def _read_dxf(path, warnings: list[str] | None = None):
    """DXF 로드. 손상 파일은 recover 모드 폴백 (R-E2: recover는 느리므로 폴백으로만).

    단위계 검사를 **여기서** 한다. 호출부 7군데에 흩뿌리면 새 호출부에서 또 빠진다.
    """
    try:
        doc = ezdxf.readfile(path)
    except ezdxf.DXFStructureError:
        doc, _auditor = recover.readfile(path)
    if warnings is not None:
        w = check_units(doc, path)
        if w and w not in warnings:
            warnings.append(w)
    return doc


# $INSUNITS 코드 → (이름, mm 환산 배율). DXF 규격값이다.
_INSUNITS = {
    1: ("인치", 25.4), 2: ("피트", 304.8), 4: ("밀리미터", 1.0),
    5: ("센티미터", 10.0), 6: ("미터", 1000.0),
}


def check_units(doc, path) -> str | None:
    """도면의 **단위계**가 밀리미터인지 확인한다. 아니면 경고 문장을 돌려준다.

    우리 코드는 **전부 mm 를 가정한다.** 그런데 아무도 확인하지 않고 있었다.

        격자 `cell_mm=50`, 틈메우기 `close_gap_mm`, 방 면적 상, 하한(㎡)
        화살표 탐색 반경 `MAX_DIST=6000`, 이름 매칭 `name_match_dist_mm`

    **미터 단위 도면(INSUNITS=6)이 오면 전부 1000배 어긋난다.**
    그런데 예외도 안 나고 0건도 아니다 — **그럴듯하게 틀린 숫자**가 나온다:

        - 벽 선분이 전부 격자 한 칸(50mm) 안에 들어가 방이 **하나로 뭉친다**
        - 면적 상한을 넘겨 방이 전부 **버려진다** (경계 0건)
        - 아니면 면적이 1,000,000 배가 되어 **말도 안 되는 ㎡** 가 DB 에 들어간다

    조용히 틀리는 게 제일 나쁘다. 우리가 가진 도면 3장은 전부 INSUNITS=4(mm) 라
    **지금까지 운이 좋았을 뿐이다.** 다른 사무소 도면이 오면 터진다.

    [주의]INSUNITS=0 은 '단위 없음'이다 — 드물지 않다. 그땐 **막지 말고 알린다**
      (실제 좌표 크기로 상식성을 따로 볼 수 있다).
    """
    try:
        code = int(doc.header.get("$INSUNITS", 0) or 0)
    except (TypeError, ValueError):
        code = 0
    if code == 4:
        return None                                  # 밀리미터 — 정상
    name = _INSUNITS.get(code, (f"코드 {code}", None))[0]
    if code == 0:
        return (f"{Path(path).name}: 단위계($INSUNITS)가 **지정되지 않았다**(0). "
                f"우리는 mm 로 가정하고 처리한다 — 좌표, 면적이 상식적인지 확인하라")
    scale = _INSUNITS.get(code, (None, None))[1]
    return (f"{Path(path).name}: 단위계가 **{name}**($INSUNITS={code})다. "
            f"우리 코드는 전부 **밀리미터**를 가정한다"
            + (f" (1{name} = {scale:g}mm → 모든 거리, 면적이 {scale:g}배 어긋난다)"
               if scale else "")
            + ". 방 경계, 면적, 화살표 귀속이 **조용히 틀린 값**을 낸다. "
              "도면을 mm 로 변환해 다시 넣어라")


def ingest(facility_id: str) -> dict:
    """시설 도면을 추출, 병합해 room/equipment/ahu 에 적재하고 요약을 반환."""
    from . import registry

    fac = registry.get_facility(facility_id)
    if not fac:
        raise ValueError(f"시설 없음: {facility_id}. 먼저 facility add 하세요.")
    profile = load_profile(fac["profile_id"])
    profile_version = str(profile.get("profile_version", "0"))
    raw = raw_dir() / facility_id

    from ..ingest.extractors.pressure_value import PressureValueExtractor

    fp_ex, pr_ex = FloorplanExtractor(), PressureExtractor()
    ga_ex, il_ex, af_ex = GaugeExtractor(), InterlockExtractor(), AirflowExtractor()
    eq_ex, hv_ex, gr_ex = EquipmentExtractor(), HvacExtractor(), GradeExtractor()
    ov_ex, pv_ex = OverviewExtractor(), PressureValueExtractor()
    floor_rooms: list[dict] = []
    pres_rooms: list[dict] = []
    equipment: list[dict] = []
    ahus: list[dict] = []
    overview: list[dict] = []
    arrows: list[dict] = []
    ta_values: list[dict] = []
    airflows: list[dict] = []        # 급기 풍량(CMH). 규칙 없음 — 데이터만 적재
    interlocks: list[dict] = []      # 인터락 위치 (별표1 4-파: A/B 연결 에어락은 인터락 필수)
    gauges: list[dict] = []          # 차압계 위치 (별표1 4-너: 청정실 경계에 설치 의무)
    grade_recs: list[dict] = []      # 방번호 → 청정등급
    pa_recs: list[dict] = []         # 방번호 → 절대압력(Pa)
    floor_doc = None                 # 방 경계(벽) 추출용 평면도 DXF
    counts = {"floorplan": 0, "pressure": 0, "hvac": 0, "overview": 0,
              "ta_value": 0, "pressure_arrow": 0, "grade_zone": 0,
              "room_grade": 0, "room_pressure": 0, "pressure_unmatched": 0,
              "gauge": 0, "interlock": 0, "airflow": 0}

    missing_files: list[str] = []
    unit_warnings: list[str] = []       # 단위계(mm) 위반 — 조용히 틀리면 안 된다
    name_conflicts: list[dict] = []     # 한 이름을 두 방번호가 가져감 = 옆방 이름을 훔침
    for d in fac["drawings"]:
        path = raw / d["filename"]
        if not path.exists():
            missing_files.append(d["filename"])  # 조용히 건너뛰지 말고 기록(완결성 감사)
            continue
        if d["kind"] == "floorplan":
            doc = _read_dxf(str(path), unit_warnings)
            floor_doc = doc                      # 방 경계(벽) 추출에 다시 쓴다
            for rec in fp_ex.extract(doc, profile):
                # **kind 를 확인한다.** 예전엔 추출기가 내는 걸 전부 방으로 취급했다 —
                #   추출기가 새 레코드 종류를 하나라도 내면 **가짜 방**이 생긴다.
                if rec.kind == "name_conflict":
                    # 두 방번호가 같은 이름 텍스트를 가져갔다 = 한 방이 옆방 이름을 훔쳤다.
                    # 기준 도면에선 0건이지만 이름이 성긴 도면에서는 일어난다.
                    name_conflicts.append(rec.payload)
                    continue
                if rec.kind != "room":
                    continue
                rec.payload["source_drawing_id"] = d["id"]
                floor_rooms.append(rec.payload)
            for rec in eq_ex.extract(doc, profile):
                equipment.append(rec.payload)
            # 등급을 '세기만' 하고 버리던 버그: room_grade 를 실제로 모은다.
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
            doc = _read_dxf(str(path), unit_warnings)
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
        elif d["kind"] == "gauge":
            # 차압계 배치도. **다른 시트**라서 좌표를 기준 시트로 맞춰 잘라 둬야 한다
            #   (scripts/cut_ref_sheet_aligned.py). 안 맞추면 전부 헛것이 된다.
            doc = _read_dxf(str(path), unit_warnings)
            for rec in ga_ex.extract(doc, profile):
                gauges.append(rec.payload)
                counts["gauge"] += 1
        elif d["kind"] == "ceiling":
            # 천정기구배치도. 급기 풍량(CMH)이 여기 있다.
            #   단위는 도면이 명시했다(레이어 B-ZONE 의 '풍량(CMH)').
            #   [주의]환기 횟수(ACH) 규칙은 **만들지 않는다** — 현행 고시에 수치가 없다.
            #     자사 환기 기준 + 천장고가 오면 그때 만든다.
            doc = _read_dxf(str(path), unit_warnings)
            for rec in af_ex.extract(doc, profile):
                airflows.append(rec.payload)
                counts["airflow"] += 1
        elif d["kind"] == "interlock":
            doc = _read_dxf(str(path), unit_warnings)
            for rec in il_ex.extract(doc, profile):
                interlocks.append(rec.payload)
                counts["interlock"] += 1
        elif d["kind"] == "hvac":
            doc = _read_dxf(str(path), unit_warnings)
            for rec in hv_ex.extract(doc, profile):
                ahus.append(rec.payload)
            counts["hvac"] += 1
        elif d["kind"] == "overview":
            doc = _read_dxf(str(path), unit_warnings)
            for rec in ov_ex.extract(doc, profile):
                rec.payload["source_drawing_id"] = d["id"]
                overview.append(rec.payload)
            counts["overview"] += 1

    # 평면도와 차압도가 **같은 파일**이면 LBL-001/002(도면 간 대조)는 무의미하다.
    #   참고도면 2층이 그렇다 — 차압 화살표가 평면도 **위에 겹쳐진** 구성이라 시트가 하나다.
    #   그런데도 LBL 이 "0건"을 내면 읽는 사람은 **"대조했더니 깨끗하다"** 로 오해한다.
    #   0건의 뜻은 "위반 없음"이 아니라 **"대조할 게 없음"** 이다. 구분해서 알린다.
    same_src = _same_source_warning(fac["drawings"])
    if same_src:
        print(f"  [주의] {same_src}")

    # 단위계 경고는 **크게** 띄운다. 요약 dict 에만 넣으면 아무도 안 본다.
    #   미터 단위 도면은 예외도 0건도 아닌 **그럴듯하게 틀린 숫자**를 낸다.
    for w in unit_warnings:
        print(f"  [경고] 단위계: {w}")
    for nc in name_conflicts:
        print(f"  [주의] 이름 충돌: '{nc['name']}' 를 방 {', '.join(nc['room_nos'])} 가 "
              f"함께 가져갔다 — 한쪽은 **옆방 이름을 훔친 것**이다")

    room_no_collisions: list[dict] = []      # 같은 방번호가 두 방에 → 한쪽이 사라진다
    merged = _merge(floor_rooms, pres_rooms, room_no_collisions)
    for c in room_no_collisions:
        # 조용히 덮어쓰지 않는다. 감지기를 만들자마자 기준 시설에서 2건이 나왔다 —
        #   4504 가 '(N)타정4실' 과 '(N)타정2실 전실' **두 방**에 붙어 있다(6m 떨어져 있다).
        #   그동안 한 방이 사라지고 있었는데 아무도 몰랐다.
        d = f"{c['dist_mm']:,.0f}mm 떨어짐" if c.get("dist_mm") else "거리 미상"
        print(f"  [경고] 방번호 충돌 {c['room_no']}: "
              f"'{c['lost_name']}' 를 '{c['kept_name']}' 가 덮어씀 ({d})")

    # ── 병합된 방에 등급, 절대압력, 압력유형을 얹는다 ────────────────
    n_grade = apply_grades(merged, grade_recs)
    n_pa = apply_pressures(merged, pa_recs)
    regime_counts = apply_regimes(merged, profile)

    # 등급 구역 — 도면에 등급이 없는 것은 **정상**이다 (1차 미팅 대표님:
    #   "방별로는 안 하고 … 구역 … 나중에 'a부터 b는 그레이드 B' 이렇게 해주면
    #    [AI]가 알아서 가게끔 해야죠").
    #   나는 이걸 '도면 결함, 최대 병목' 이라고 잘못 써왔다. 결함이 아니다.
    #   → 프로파일의 grade_zones(사람이 지정) → 제형 기본값 순으로 채운다.
    from .grade_zones import apply_grade_zones
    grade_src = apply_grade_zones(merged, profile)

    # ── 인터락을 방에 붙인다 ────────────────────────────────────
    # 인터락 도면이 없는 시설이면 interlock_count 를 **NULL 로 둔다**.
    #   0 으로 채우면 "인터락이 하나도 없다"는 거짓 사실이 되어 전 에어락이 위반이 된다.
    #   (rels=[], door_pairs=[], has_gauge=false 에 이어 **네 번째** 같은 함정이다)
    if interlocks:
        _attach_interlocks(merged, interlocks)

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

        # 장비도 **방 경계 안**에 들어가는지로 붙인다.
        #   급기 풍량은 경계 기반으로 고쳤는데 **장비는 안 고쳤다**(반경 8,000mm 최근접).
        #   72㎡ 충진실의 장비가 1.5㎡ 전실에 붙는다 — 풍량에서 겪은 것과 **완전히 같은 오귀속**.
        for _eq in equipment:
            _no = boundary_res.room_at(_eq.get("x"), _eq.get("y"))                 if (_eq.get("x") is not None and _eq.get("y") is not None) else None
            if _no:
                _eq["room_no_by_boundary"] = _no

        # 급기 풍량을 **방 경계 안**에 들어가는지로 붙인다.
        #   예전엔 '반경 4m 최근접 방'이었다 → 72㎡ 충진실의 급기구가 1.5㎡ 전실에 붙었다
        #   (NC 3㎡ 방에 1,697 CMH = 환기 187회/hr 이라는 말도 안 되는 값이 나왔다).
        #   방 경계를 이미 갖고 있는데 안 쓰고 있었다.
        if airflows:
            _attach_airflow_by_boundary(merged, airflows, boundary_res)

    # 나노초 해상도로 run_id 발급: 같은 초에 두 번 ingest 해도 PK 충돌하지 않게(M5).
    run_id = f"run_{facility_id}_{time.time_ns()}"
    # 감사추적(M6/M7): run 행을 먼저 'running' 으로 별도 커밋 → 이후 실패해도 이력이 남는다.
    # 이력은 append-only(불변): 매 ingest = 새 run. 과거 run 은 지우지 않는다(감사).
    _create_run(facility_id, run_id, profile_version)
    try:
        n_eq = _load(facility_id, run_id, profile_version, merged, equipment, ahus,
                     overview, arrows, ta_values)
        # 사라진 방을 기록한다. LBL-003 이 이걸 읽어 위반으로 보고한다.
        _persist_room_no_conflicts(facility_id, run_id, room_no_collisions)
        _seed_questions(facility_id)
        # 인접 + 화살표↔방 귀속도 성공 판정에 포함(M8): 파생까지 끝나야 'done'.
        from ..geometry import adjacency, pressure_links
        # 방 경계가 잡혔으면 **폴리곤 기반 정밀 인접**을 쓴다(최근접-k 근사보다 정확).
        #   근사 인접은 오탐/누락이 나서 ADJ-001, PRES-002/003 을 못 켰다.
        if boundary_res and boundary_res.adjacency:
            # 문 데이터를 **믿을 수 있을 때만** 쓴다.
            #
            #   방에는 대개 문이 하나씩 있다. 그러니 '문이 닿은 방'의 비율(door_coverage)이
            #   낮으면 그건 도면에 문이 없어서가 아니라 **우리 문 검출이 실패한 것**이다.
            #   (참고도면 14%, 기준 시설 44% — 둘 다 실패다)
            #
            #   그런데도 문 인접을 쓰면 ADJ-001 이 검출 못 한 문에 대해
            #   "문이 없으니 동선 위반 아님" 으로 **진짜 위반을 숨긴다.**
            #   **불완전한 문 데이터는 문 데이터가 없는 것보다 나쁘다.**
            #
            #   → 검출률이 임계값 미만이면 None 을 넘겨 via_door 를 NULL 로 둔다.
            #     ADJ-001 이 벽 인접으로 폴백하고, 근거에 "문 정보 없음, 보류"를 남긴다.
            #     판정을 포기하지도, 확정하지도 않는다.
            cov = boundary_res.door_coverage
            dpairs = boundary_res.door_adjacency if cov >= DOOR_TRUST else None
            if boundary_res.door_adjacency and dpairs is None:
                print(f"  [주의] 문 검출률 {cov:.0%} < {DOOR_TRUST:.0%} → 문 인접을 쓰지 않는다"
                      f"(ADJ-001 은 벽 인접으로 폴백, 근거에 '보류' 표시)")
            n_adj = adjacency.load_pairs(run_id, boundary_res.adjacency, method="polygon",
                                         door_pairs=dpairs)
            adj_method = "polygon"
        else:
            n_adj = adjacency.build(run_id)
            adj_method = "nearest"
        n_plinks = pressure_links.build(run_id)
        # 차압 설정 구간에 **차압계가 있는가** (별표1 4-너: 청정실 경계에 설치 의무)
        #   차압계 도면이 없는 시설이면 has_gauge 를 NULL 로 둔다 → PRES-005 는 판정하지 않는다.
        #   빈 목록을 "차압계가 하나도 없다"로 오해하면 전 구간이 거짓 위반이 된다.
        n_gauge = _attach_gauges(run_id, gauges) if gauges else 0
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
        # 추출 개수와 **귀속 개수**를 나란히 찍는다. 개수만 세면 속는다.
        "n_gauges": f"{n_gauge}/{len(gauges)}" if gauges else 0,
        "n_airflow": len(airflows),
        "grade_source": grade_src,
        "n_ta_values": len(ta_values),
        "n_adjacency": n_adj,
        "adjacency_method": adj_method,          # polygon(정밀) | nearest(근사)
        "n_pressure_links": n_plinks,
        "n_grade_applied": n_grade,              # 등급이 붙은 방 수 (0 이면 도면에 표기 없음)
        "n_pressure_pa_applied": n_pa,           # 절대압력이 붙은 방 수
        "regime_counts": regime_counts,          # protect/contain/hazard/neutral 분포
        "n_boundary_rooms": len(boundary_res.rooms) if boundary_res else 0,
        "boundary_failed": boundary_res.failed if boundary_res else [],
        # 벽으로 태우지 **못한** 기하 타입. 비어 있어야 정상이다.
        #   기준 평면도에서 SPLINE, CIRCLE 등 88,356 개가 조용히 버려지고 있었다.
        #   벽이 그 타입으로 그려진 도면이 오면 방이 뭉개지는데 로그 한 줄 안 남았다.
        "boundary_unsupported": (boundary_res.unsupported_types
                                 if boundary_res else {}),
        # 단위계(mm) 위반. 미터 단위 도면이 오면 **모든 거리, 면적이 1000배 어긋난다.**
        #   예외도 안 나고 0건도 아니다 — **그럴듯하게 틀린 숫자**가 나온다. 그게 제일 나쁘다.
        "unit_warnings": unit_warnings,
        # 같은 방번호가 두 번 나왔다 = **한쪽이 덮어써져 사라졌다.**
        #   비어 있어야 정상이다. 층마다 번호를 재사용하는 도면에서 터진다.
        "room_no_collisions": room_no_collisions,
        # 한 이름 텍스트를 여러 방번호가 가져갔다 = 한 방이 **옆방 이름을 훔쳤다.**
        #   기준 도면에선 0건(이름 후보 242 > 방번호 96). 이름이 성긴 도면에서 터진다.
        #   이름이 틀리면 그 방의 압력 유형, 에어락, 복도 판정이 전부 틀어진다.
        "name_conflicts": name_conflicts,
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


def _merge(floor_rooms, pres_rooms, collisions: list[str] | None = None) -> list[dict]:
    """방번호를 키로 평면도/차압도 병합 (v0.1 merge_dataset 이식).

    **방번호 충돌을 조용히 덮어쓰고 있었다.**

      기준 시설은 번호에 층이 들어간다(3101 = 3층, 4101 = 4층) → 충돌이 없다.
      그런데 **층마다 101, 102 로 매기는 사무소**가 오면 3층 101 과 4층 101 이 같은 키가 되어
      **한쪽이 통째로 사라진다.** 예외도, 로그도, 0건도 아니다 — 방 개수가 조용히 줄 뿐이다.

      우리 번호 체계가 마침 안전했을 뿐이다. → 충돌을 **세어서 알린다.**
      (진짜 해법은 키를 `(floor, room_no)` 로 바꾸는 것인데, 그러면 층 판정이 틀린 방이
       유령 방으로 갈라진다. 지금은 **감지**만 하고, 실제 충돌 도면이 오면 그때 고친다.)
    """
    master: dict = {}
    for r in floor_rooms:
        if r["room_no"] is None:
            # 무번호 공간 키: 좌표 튜플(부동소수 f-string 은 '100' vs '100.0' 등에 취약).
            # 같은 좌표의 두 무번호 방은 여전히 한 항목으로 합쳐짐(현 데이터엔 발생 안 함).
            master[("_u", r["plan_x"], r["plan_y"])] = dict(r, pressure_name=None)
            continue
        prev = master.get(r["room_no"])
        if prev is not None and collisions is not None:
            # 거리로 **서로 다른 방**인지 판단한다.
            #   멀리 떨어져 있으면 도면이 같은 번호를 두 방에 붙인 것이고(=결함),
            #   가까우면 같은 방에 번호를 두 번 쓴 것이다(=무해한 중복 표기).
            dist = None
            if (prev.get("plan_x") is not None and r.get("plan_x") is not None
                    and prev.get("plan_y") is not None and r.get("plan_y") is not None):
                dist = math.hypot(r["plan_x"] - prev["plan_x"],
                                  r["plan_y"] - prev["plan_y"])
            collisions.append({
                "room_no": r["room_no"],
                # prev 가 덮어써져 사라진다(뒤에 온 r 이 이긴다)
                "lost_name": prev.get("name"), "lost_floor": prev.get("floor"),
                "lost_x": prev.get("plan_x"), "lost_y": prev.get("plan_y"),
                "kept_name": r.get("name"), "kept_floor": r.get("floor"),
                "kept_x": r.get("plan_x"), "kept_y": r.get("plan_y"),
                "dist_mm": dist,
            })
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


AIRFLOW_RADIUS_MM = 4000.0    # 급기구 풍량 숫자를 방에 붙이는 반경


def _attach_airflow_by_boundary(rooms: list[dict], flows: list[dict], bres) -> int:
    """급기 풍량(CMH)을 **방 경계 안**에 들어가는지로 붙여 합산한다.

    예전엔 '반경 4m 최근접 방'으로 붙였다. 그러면 **큰 방의 급기구가 옆 작은 방에 붙는다** —
      72㎡ 충진실의 디퓨저가 1.5㎡ 무균 전실에 붙고, NC 3㎡ 방에 1,697 CMH
      (환기 187회/hr)라는 말도 안 되는 값이 나왔다.
      **방 경계를 이미 갖고 있는데 안 쓰고 있었다.**

    경계 밖(복도 사이, 벽 위)에 찍힌 풍량은 **아무 방에도 붙이지 않는다.** 추측하지 않는다.
    """
    by_no = {r.get("room_no"): r for r in rooms if r.get("room_no")}
    n = orphan = 0
    for f in flows:
        no = bres.room_at(f["x"], f["y"])
        if not no or no not in by_no:
            orphan += 1
            continue
        r = by_no[no]
        r["airflow_cmh"] = (r.get("airflow_cmh") or 0.0) + f["cmh"]
        n += 1
    if orphan:
        print(f", 급기 풍량 {orphan}개는 방 경계 밖이라 붙이지 않았다(추측하지 않는다)")
    return n


INTERLOCK_RADIUS_MM = 3000.0  # 인터락 선 중점에서 이 거리 안의 방에 귀속


# 귀속률이 이보다 낮으면 **좌표계가 안 맞은 것**이다. 0/false 로 채우지 말고 NULL 을 유지한다.
#   (차압계, 인터락은 **다른 시트**에서 온다. 시트마다 x 원점이 106,026mm 다르다.
#    정렬 안 한 DXF 를 등록하면 전부 100m 밖 → 붙는 게 0개 →
#    "전 방이 인터락 0개", "전 구간 차압계 없음" → **critical 거짓 위반이 쏟아진다**)
ATTACH_MIN_RATE = 0.3


def _attach_interlocks(rooms: list[dict], locks: list[dict]) -> int:
    """인터락 선의 중점을 **가장 가까운 방 하나**에 붙인다.

    [주의] 전실이 아주 작으면(무균 전실 1.5㎡) 중점이 옆방 라벨에 더 가까울 수 있다.
      그래서 '가장 가까운 하나'에만 붙이고, 반경을 넘으면 붙이지 않는다.
      귀속이 의심스러우면 규칙이 '보류'로 내보낸다. 조용히 틀리지 않는다.
    """
    # `or` 를 쓰면 좌표 0.0 이 falsy 라 탈락한다. 그리고 `"x"` 키는 병합 방에 없다.
    pts = []
    for r in rooms:
        x, y = r.get("plan_x"), r.get("plan_y")
        if x is None or y is None:
            x, y = r.get("pres_x"), r.get("pres_y")
        if x is not None and y is not None:
            pts.append([r, x, y])
    if not pts:
        return 0

    got: dict[int, int] = {}
    for lk in locks:
        cand = [(math.hypot(x - lk["x"], y - lk["y"]), i)
                for i, (_r, x, y) in enumerate(pts)]
        d, i = min(cand)
        if d <= INTERLOCK_RADIUS_MM:
            got[i] = got.get(i, 0) + 1

    rate = len(got) and (sum(got.values()) / len(locks))
    if not locks or rate < ATTACH_MIN_RATE:
        # 붙은 게 거의 없다 = **좌표계가 안 맞은 것**이다.
        #   0 으로 채우면 "인터락이 하나도 없다"는 **거짓 사실**이 되어
        #   A/B 에 연결된 **모든 에어락이 critical 거짓 위반**이 된다.
        #   → interlock_count 를 **NULL 로 남긴다**(규칙이 판정하지 않는다).
        print(f"  [주의] 인터락 {len(locks)}개 중 방에 붙은 것 {sum(got.values())}개 "
              f"({rate:.0%}) — **좌표계가 안 맞는다.** 다른 시트에서 왔다면 "
              f"scripts/cut_ref_sheet_aligned.py 로 정렬할 것. "
              f"interlock_count 를 NULL 로 둔다(판정 안 함)")
        return 0

    for i, (r, _x, _y) in enumerate(pts):
        r["interlock_count"] = got.get(i, 0)
    return sum(got.values())


GAUGE_RADIUS_MM = 3000.0     # 화살표에서 이 거리 안의 차압계를 '그 구간의 것'으로 본다


def _attach_gauges(run_id: str, gauges: list[dict]) -> int:
    """차압 화살표마다 **근처에 차압계가 있는지** 표시한다.

    화살표(=차압이 설정된 문 구간) 옆에 차압계가 있어야 그 차압을 유지, 기록할 수 있다.
    반경 안에 없으면 has_gauge=false. 청정실 경계라면 PRES-005 가 위반으로 본다.
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, evidence_x, evidence_y FROM pressure_relation WHERE run_id=%s",
                    (run_id,))
        rows = cur.fetchall()
        hits = []
        for pr_id, ex, ey in rows:
            best, bk = None, None
            for g in gauges:
                d = math.hypot(g["x"] - ex, g["y"] - ey)
                if d <= GAUGE_RADIUS_MM and (best is None or d < best):
                    best, bk = d, g["gauge_kind"]
            hits.append((pr_id, best is not None, bk))

        n = sum(1 for _i, ok, _k in hits if ok)
        rate = n / len(gauges) if gauges else 0.0
        if rate < ATTACH_MIN_RATE:
            # 차압계가 거의 안 붙었다 = 좌표계가 안 맞은 것이다.
            #   false 로 채우면 **청정실 경계 전 구간이 "차압계 없음" 위반**이 된다.
            #   → has_gauge 를 **NULL 로 남긴다**(PRES-005 가 판정하지 않는다).
            print(f"  [주의] 차압계 {len(gauges)}개 중 화살표에 붙은 것 {n}개 ({rate:.0%}) — "
                  f"**좌표계가 안 맞는다.** has_gauge 를 NULL 로 둔다(판정 안 함)")
            conn.rollback()
            return 0

        for pr_id, ok, bk in hits:
            cur.execute("UPDATE pressure_relation SET has_gauge=%s, gauge_kind=%s WHERE id=%s",
                        (ok, bk, pr_id))
        conn.commit()
        return n


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
    """run 을 done/failed 로 마감(별도 트랜잭션). finished_at, error 기록."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE run SET status=%s, finished_at=now(), error=%s WHERE id=%s",
            (status, error, run_id),
        )
        conn.commit()


def _persist_room_no_conflicts(facility_id: str, run_id: str,
                               conflicts: list[dict]) -> None:
    """방번호 충돌을 남긴다 — **우리 버그가 아니라 도면의 결함**이다.

    감지기를 만들자마자 기준 시설에서 2건이 나왔다. 그동안 `_merge` 가 한쪽을
    **조용히 덮어썼다.** 방이 하나 사라지는데 예외도 로그도 없었다.

    병합 동작(한쪽이 이긴다)은 그대로 둔다 — 방번호는 우리 데이터의 **키**라
    중복을 허용하면 화살표, 차압 관계가 어느 방을 가리키는지 알 수 없게 된다.
    **버리되, 버렸다는 사실을 기록한다.** LBL-003 이 이걸 읽어 위반으로 보고한다.
    """
    if not conflicts:
        return
    with connect() as conn, conn.cursor() as cur:
        for c in conflicts:
            cur.execute(
                """INSERT INTO room_no_conflict
                       (run_id, facility_id, room_no,
                        kept_name, kept_floor, kept_x, kept_y,
                        lost_name, lost_floor, lost_x, lost_y, dist_mm)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (run_id, facility_id, c["room_no"],
                 c.get("kept_name"), c.get("kept_floor"),
                 c.get("kept_x"), c.get("kept_y"),
                 c.get("lost_name"), c.get("lost_floor"),
                 c.get("lost_x"), c.get("lost_y"), c.get("dist_mm")),
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
                                     area_m2, boundary, boundary_method, interlock_count,
                                     airflow_cmh, grade_source)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'unreviewed',
                           %s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (facility_id, run_id, r.get("room_no"), r.get("name"), r.get("pressure_name"),
                 r.get("floor"), r.get("sheet"), r.get("plan_x"), r.get("plan_y"),
                 r.get("pres_x"), r.get("pres_y"), r.get("source_drawing_id"),
                 r.get("grade"), r.get("pressure_pa"), r.get("regime"), r.get("regime_source"),
                 r.get("area_m2"),
                 Json(r["boundary"]) if r.get("boundary") else None,
                 r.get("boundary_method"),
                 # 인터락 도면이 없으면 None(NULL). 0 으로 채우면 "인터락이 하나도 없다"는
                 #   거짓 사실이 되어 전 에어락이 위반이 된다.
                 r.get("interlock_count"),
                 # 급기 풍량(CMH). 규칙은 없다 — 데이터로만 둔다.
                 r.get("airflow_cmh"),
                 # 등급이 **어디서 왔나**: drawing / zone / product_default
                 r.get("grade_source")),
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
        # 방향 의미 확정(S-1), 방 귀속은 Stage 2 에서 채운다.
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
