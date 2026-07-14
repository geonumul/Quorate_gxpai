# -*- coding: utf-8 -*-
"""차압도 추출기 - 방번호, 이름, TA 수치, 차압 화살표(rotation).

로드맵: T1.1.2 (v0.1 extract_pressure 이식)
리스크 반영: R-A1/A2/S-10 (dxftext 경유), S-3 (여러 줄 이름 병합).
             R-D2 (TA 값은 단위 미확정이므로 ta_value_raw 로만 저장, 어떤 규칙도 참조 금지).
"""
from __future__ import annotations

import re

from .. import arrowgeom
from ..dxftext import iter_label_texts, normalize_dxf_text, text_position
from ._common import floor_from_number, match_name_to_anchor, merge_multiline_names
from .base import BaseExtractor, Record


class PressureExtractor(BaseExtractor):
    kind = "pressure"

    def extract(self, doc, profile) -> list[Record]:
        pr = profile["pressure"]
        floors = profile["floors"]
        entity_types = profile.get("label_entity_types", ["TEXT", "MTEXT"])
        # 방번호 정규식을 **하드코딩하고 있었다** — `^\(?(\d{4}(?:-\d+)?)\)?$`.
        #   평면도 추출기는 프로파일(`floorplan.room_no_regex`)에서 읽는데 여기만 박아뒀다.
        #
        #   그 바람에 참고도면(방번호가 `F2I01` 꼴)의 **차압도 방이 0개**가 됐고,
        #   LBL-002(도면 간 방 차이)가 **51건의 거짓 위반**을 냈다.
        #   (LBL-002 는 review: internal 이라 게이트가 열려 있어 **DB에 실제로 적재됐다**)
        #
        #   미리보기(preview_rules.py)만 돌리고 **validate 를 안 돌려봐서** 놓쳤다.
        #   → 규칙을 미리보기로만 검증하지 말고 **실제 파이프라인도 돌려볼 것.**
        #
        #   이제 평면도와 **같은 프로파일 정규식**을 쓴다. 차압도의 방번호 표기가 평면도와
        #   다를 수 있으므로 `pressure.room_no_regex` 로 따로 덮어쓸 수 있게 둔다.
        fp = profile.get("floorplan", {})
        num_re = re.compile(pr.get("room_no_regex") or fp.get("room_no_regex")
                            or r"^\(?(\d{4}(?:-\d+)?)\)?$")
        bare_src = pr.get("bare_no_regex") or fp.get("bare_no_regex")
        bare_re = re.compile(bare_src) if bare_src else None
        merge = pr.get("multiline_merge", {})
        name_d = pr["name_match_dist_mm"]

        # 방번호/이름 (RM 레이어)
        _skip = profile.get("label_exclude_blocks")
        rm_texts = list(iter_label_texts(doc, [pr["rm_layer"]], entity_types,
                                         exclude_blocks=_skip))
        numbers, raw_names = [], []
        for x, y, t, _h in rm_texts:
            m = num_re.match(t)
            if m:
                # 정규식에 캡처 그룹이 없을 수도 있다 → 그럴 땐 전체 문자열을 쓴다
                numbers.append((x, y, m.group(1) if m.groups() else t))
            elif bare_re is not None and bare_re.match(t):
                numbers.append((x, y, t))
            elif re.search(r"[가-힣A-Za-z]", t) and t not in ("UP", "DN", "Pa"):
                raw_names.append((x, y, t))
        if merge:
            names = merge_multiline_names(raw_names, merge["max_dy_mm"], merge["max_dx_mm"])
        else:
            names = [(x, y, t) for x, y, t in raw_names]

        # 층 판정: 시트 타이틀 x좌표 기준
        floor_anchors = []
        fre = re.compile(pr["floor_regex"], re.I)
        for e in doc.modelspace():
            if e.dxftype() in ("TEXT", "MTEXT") and e.dxf.layer in pr.get("title_layers", []):
                t = normalize_dxf_text(e)
                m = fre.search(t)
                if m:
                    # R-F1: 정렬(center/right) 텍스트는 insert 가 (0,0) 쓰레기값일 수 있어
                    # align_point 보정 위치를 쓴다(안 그러면 층 판정이 x≈0 로 오배정).
                    floor_anchors.append((text_position(e).x, f"{m.group(1)}F"))
        floor_anchors.sort()

        def floor_of(x):
            if floor_anchors:
                return min(floor_anchors, key=lambda a: abs(a[0] - x))[1]
            return None

        records: list[Record] = []
        for nx, ny, no in numbers:
            _idx, name = match_name_to_anchor(nx, ny, names, name_d)
            records.append(Record(
                kind="pressure_room",
                payload={
                    "room_no": no,
                    "name": name,
                    "floor": floor_of(nx) or floor_from_number(no, floors),
                    "x": round(nx, 1), "y": round(ny, 1),
                },
            ))

        # TA 수치 (단위 미확정 - raw 로만)
        for x, y, t, _h in iter_label_texts(doc, [pr["ta_layer"]], entity_types,
                                            exclude_blocks=_skip):
            if re.fullmatch(r"\d+(?:\.\d+)?", t):
                records.append(Record(kind="ta_value", payload={
                    "x": round(x, 1), "y": round(y, 1), "value_raw": float(t),
                    "unit": pr.get("ta_unit", "UNKNOWN"),
                }))

        # ── 차압 화살표 ────────────────────────────────────────────
        # 예전엔 rotation 만 저장하고 "화살촉은 -y" 라고 **가정**했다. 그 가정 때문에
        #   28개 중 9개를 거꾸로 읽었다(블록마다 화살촉 방향이 다르고, 일부는 거울반사).
        #   이제 블록 기하에서 **재서** 세계 각도(head_deg)를 낸다. arrowgeom 모듈 참조.
        #
        # 레이어 이름이 곧 **차압 설정값**이다: 'Air Flow 10Pa' / 'Air Flow 15Pa' /
        #   'Air Flow no차압'. 도면이 구간별 목표 차압을 직접 말해주는데 예전엔 버렸다.
        # **블록 재귀로 바꿨다.** 예전엔 `doc.modelspace()` 만 훑었다.
        #   방 라벨, 벽, 문은 재귀로 고쳤는데 **화살표만 안 고쳤다.**
        #   같은 도면에서 화살표가 시트 블록 안에 있으면 **화살표 0개** → pressure_relation 이
        #   비고 → **PRES 규칙 전부가 조용히 "위반 없음"처럼 보인다.**
        #
        #   [주의]재귀를 켜면 블록 안 구성 선분(507개)까지 나온다 → **INSERT 만** 집는다.
        #   [주의]좌표도 matrix44 로 변환한다. 직접 계산하면 **거울반사**를 놓친다.
        from ..blockwalk import walk, world_point

        prefix = pr.get("arrow_block_prefix", "")
        arrow_layers = set(pr.get("arrow_layers") or [])
        for e, mat, lay in walk(doc, yield_inserts=True):
            if e.dxftype() != "INSERT":
                continue
            if arrow_layers and lay not in arrow_layers:
                continue
            if not arrow_layers and not e.dxf.name.startswith(prefix):
                continue
            blk = doc.blocks.get(e.dxf.name)
            hd = arrowgeom.head_deg(e, blk) if blk is not None else None
            # 블록 안 화살표면 세계각도로 다시 변환한다
            if hd is not None and mat is not None:
                from ..blockwalk import world_angle
                hd = world_angle(hd, mat)
            x, y = world_point(e.dxf.insert, mat)
            records.append(Record(kind="pressure_arrow", payload={
                "x": round(x, 1), "y": round(y, 1),
                "rotation_deg": round(e.dxf.rotation, 1),
                # None 이면 화살촉을 못 읽은 것 — 추측해 채우지 않는다. 규칙이 건너뛴다.
                "head_deg": round(hd, 1) if hd is not None else None,
                "layer": lay,
                "setpoint_pa": _setpoint_from_layer(lay),
                "floor": floor_of(x),
            }))
        return records


_SET_RE = re.compile(r"(\d+(?:\.\d+)?)\s*Pa", re.I)


def _setpoint_from_layer(layer: str) -> float | None:
    """레이어 이름에서 차압 설정값을 읽는다. 'Air Flow no차압' → None(차압 불필요).

    도면 범례 3번: *"기류흐름 및 차압계 설치가 요구되지 않는 위치"*.
    → 설정값이 없는 구간은 **차압 기준 자체가 없다.** 위반으로 찍으면 안 된다.
    """
    if "no차압" in layer or "no 차압" in layer:
        return None
    m = _SET_RE.search(layer)
    return float(m.group(1)) if m else None
