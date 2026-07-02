# -*- coding: utf-8 -*-
"""차압도 추출기 - 방번호·이름, TA 수치, 차압 화살표(rotation).

로드맵: T1.1.2 (v0.1 extract_pressure 이식)
리스크 반영: R-A1/A2/S-10 (dxftext 경유), S-3 (여러 줄 이름 병합).
             R-D2 (TA 값은 단위 미확정이므로 ta_value_raw 로만 저장, 어떤 규칙도 참조 금지).
"""
from __future__ import annotations

import re

from ..dxftext import iter_label_texts, normalize_dxf_text
from ._common import floor_from_number, match_name_to_anchor, merge_multiline_names
from .base import BaseExtractor, Record


class PressureExtractor(BaseExtractor):
    kind = "pressure"

    def extract(self, doc, profile) -> list[Record]:
        pr = profile["pressure"]
        floors = profile["floors"]
        entity_types = profile.get("label_entity_types", ["TEXT", "MTEXT"])
        num_re = re.compile(r"^\(?(\d{4}(?:-\d+)?)\)?$")
        merge = pr.get("multiline_merge", {})
        name_d = pr["name_match_dist_mm"]

        # 방번호/이름 (RM 레이어)
        rm_texts = list(iter_label_texts(doc, [pr["rm_layer"]], entity_types))
        numbers, raw_names = [], []
        for x, y, t, _h in rm_texts:
            m = num_re.match(t)
            if m:
                numbers.append((x, y, m.group(1)))
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
                    floor_anchors.append((e.dxf.insert.x, f"{m.group(1)}F"))
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
        for x, y, t, _h in iter_label_texts(doc, [pr["ta_layer"]], entity_types):
            if re.fullmatch(r"\d+(?:\.\d+)?", t):
                records.append(Record(kind="ta_value", payload={
                    "x": round(x, 1), "y": round(y, 1), "value_raw": float(t),
                    "unit": pr.get("ta_unit", "UNKNOWN"),
                }))

        # 차압 화살표: 익명블록 INSERT (rotation = 방향, R-D1 의미는 별도 확정 필요)
        prefix = pr["arrow_block_prefix"]
        for e in doc.modelspace():
            if e.dxftype() == "INSERT" and e.dxf.name.startswith(prefix):
                records.append(Record(kind="pressure_arrow", payload={
                    "x": round(e.dxf.insert.x, 1), "y": round(e.dxf.insert.y, 1),
                    "rotation_deg": round(e.dxf.rotation, 1), "floor": floor_of(e.dxf.insert.x),
                }))
        return records
