# -*- coding: utf-8 -*-
"""평면도 추출기 - 방번호, 이름, 좌표, 층.

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

        # label_exclude_blocks: 기둥, 치수 블록 안으로 들어가지 않는다.
        #   블록 재귀를 켠 뒤 `SC2(기둥)` 안의 철골 규격이 방 이름으로 빨려 들어왔다.
        _skip = profile.get("label_exclude_blocks")
        texts = list(iter_label_texts(doc, fp["room_layers"], entity_types,
                                      exclude_blocks=_skip))
        sheets = load_sheet_titles(doc, fp.get("title_attrib_tag", "도면명"))

        numbers, names = [], []
        for x, y, t, _h in texts:
            m = num_re.match(t)
            if m:
                # 캡처 그룹 없는 정규식(`^\d{4}$`)이면 group(1) 이 IndexError 로 죽는다
                numbers.append((x, y, m.group(1) if m.groups() else t))
            elif bare_re.match(t):
                numbers.append((x, y, t))
            elif t not in skip:
                names.append((x, y, t))

        # S-3: 여러 줄로 쪼개진 이름 병합 (예: "(Bin/DRUM 포함)" 같은 분리 라벨)
        if merge:
            names = merge_multiline_names(names, merge["max_dy_mm"], merge["max_dx_mm"])

        records: list[Record] = []
        used = set()
        # **이름 귀속은 배타적이지 않다** - 두 방번호가 같은 이름 텍스트를 둘 다 가져갈 수 있다.
        #   그러면 한 방이 **옆방 이름을 훔친다**. 이름이 틀리면 그 방의 압력 유형, 에어락, 복도
        #   판정이 전부 틀어진다(우리 규칙 상당수가 이름을 본다).
        #
        #   [주의]그런데 **기준 평면도에서 재 보니 0건이었다.** 이름 후보가 242개인데 방번호가 96개라
        #     각자 자기 이름을 찾아간다. → **알고리즘을 바꾸지 않는다.**
        #     근거 없이 배타 매칭으로 바꾸면 기준값(111방)만 흔들린다.
        #
        #   대신 **일어나면 알려준다.** 조용히 틀리는 것만은 막는다.
        #   (방번호 충돌 감지기도 이렇게 만들었고, 첫 실행에서 진짜 결함 2건을 잡았다)
        claimed: dict[int, list[str]] = {}
        for nx, ny, no in numbers:
            idx, name = match_name_to_anchor(nx, ny, names, max_d, above_max, penalty)
            if idx is not None:
                used.add(idx)
                claimed.setdefault(idx, []).append(no)
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

        # 한 이름을 여러 방번호가 가져갔다 = 한 방이 **옆방 이름을 훔쳤다.**
        #   기준 도면에선 0건이지만, 이름이 성긴 도면에서는 일어난다.
        #   조용히 넘어가면 그 방의 압력 유형, 에어락, 복도 판정이 전부 틀어진다.
        for idx, nos in claimed.items():
            if len(nos) > 1:
                records.append(Record(kind="name_conflict", payload={
                    "name": names[idx][2], "room_nos": nos,
                    "x": round(names[idx][0], 1), "y": round(names[idx][1], 1),
                }))
        return records
