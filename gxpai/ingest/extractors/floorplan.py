# -*- coding: utf-8 -*-
"""평면도 추출기 - 방번호·이름·좌표·층.

로드맵: T1.1.2 (v0.1 extract_rooms 이식)
리스크 반영: R-A1/A2/S-10 (dxftext 경유), S-3 (여러 줄 이름 병합을 평면도에도 적용).
하드코딩 상수는 전부 profile['floorplan'] 에서 읽는다.
"""
from __future__ import annotations

import re

from ..dxftext import iter_label_texts
from ._common import (
    floor_from_number,
    has_hangul,
    load_sheet_titles,
    match_name_to_anchor,
    merge_multiline_names,
    sheet_of,
)
from .base import BaseExtractor, Record


class FloorplanExtractor(BaseExtractor):
    kind = "floorplan"

    def extract(self, doc, profile) -> list[Record]:
        fp = profile["floorplan"]
        floors = profile["floors"]
        entity_types = profile.get("label_entity_types", ["TEXT", "MTEXT"])

        num_re = re.compile(fp["room_no_regex"])
        bare_re = re.compile(fp["bare_no_regex"])
        skip = set(fp.get("skip_names", []))
        max_d = fp["max_match_dist_mm"]
        above_max = fp.get("name_above_max_mm")
        penalty = fp.get("name_above_penalty", 0.0)
        merge = fp.get("multiline_merge", {})

        # ★label_exclude_blocks: 기둥·치수 블록 안으로 들어가지 않는다.
        #   블록 재귀를 켠 뒤 `SC2(기둥)` 안의 철골 규격이 방 이름으로 빨려 들어왔다.
        _skip = profile.get("label_exclude_blocks")
        texts = list(iter_label_texts(doc, fp["room_layers"], entity_types,
                                      exclude_blocks=_skip))
        sheets = load_sheet_titles(doc, fp.get("title_attrib_tag", "도면명"))

        numbers, names = [], []
        for x, y, t, _h in texts:
            m = num_re.match(t)
            if m:
                numbers.append((x, y, m.group(1)))
            elif bare_re.match(t):
                numbers.append((x, y, t))
            elif t not in skip:
                names.append((x, y, t))

        # S-3: 여러 줄로 쪼개진 이름 병합 (예: "(Bin/DRUM 포함)" 같은 분리 라벨)
        if merge:
            names = merge_multiline_names(names, merge["max_dy_mm"], merge["max_dx_mm"])

        records: list[Record] = []
        used = set()
        for nx, ny, no in numbers:
            idx, name = match_name_to_anchor(nx, ny, names, max_d, above_max, penalty)
            if idx is not None:
                used.add(idx)
            records.append(Record(
                kind="room",
                payload={
                    "room_no": no,
                    "name": name,
                    "floor": floor_from_number(no, floors),
                    "sheet": sheet_of(nx, sheets),
                    "plan_x": round(nx, 1),
                    "plan_y": round(ny, 1),
                    "source": "floorplan",
                },
            ))

        # 번호 없이 이름만 있는 공간(복도/계단 등)
        for i, (x, y, t) in enumerate(names):
            if i in used or not has_hangul(t):
                continue
            records.append(Record(
                kind="room",
                payload={
                    "room_no": None, "name": t, "floor": None,
                    "sheet": sheet_of(x, sheets),
                    "plan_x": round(x, 1), "plan_y": round(y, 1),
                    "source": "floorplan_unnumbered",
                },
            ))
        return records
