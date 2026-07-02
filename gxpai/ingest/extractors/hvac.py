# -*- coding: utf-8 -*-
"""HVAC 추출기 - AHU 태그·위치.

로드맵: T1.2.1 (폴백: 태그만)
AHU는 이 도면에서 'AHU-*' 레이어명 또는 'AHU' 를 포함한 텍스트로 나타난다.
존 경계는 실측 후 가능 시(현재 미구현). 층 판정은 이후 시트 정렬로 승격.
"""
from __future__ import annotations

import re

from ..dxftext import iter_label_texts, text_position
from .base import BaseExtractor, Record


class HvacExtractor(BaseExtractor):
    kind = "hvac"

    def extract(self, doc, profile) -> list[Record]:
        hv = profile.get("hvac", {})
        prefix = hv.get("ahu_layer_prefix", "AHU")
        tag_re = re.compile(hv.get("ahu_tag_regex", r"AHU[-\s]?\w+"), re.I)
        entity_types = profile.get("label_entity_types", ["TEXT", "MTEXT"])

        seen = set()
        records: list[Record] = []

        # (1) 텍스트 태그: 'AHU...' 를 포함하는 라벨
        for e in doc.modelspace():
            if e.dxftype() not in entity_types:
                continue
            from ..dxftext import normalize_dxf_text
            t = normalize_dxf_text(e)
            m = tag_re.search(t)
            if not m:
                continue
            pos = text_position(e)
            tag = m.group(0).upper().replace(" ", "")
            key = (tag, round(pos.x), round(pos.y))
            if key in seen:
                continue
            seen.add(key)
            records.append(Record(kind="ahu", payload={
                "ahu_id": tag, "x": round(pos.x, 1), "y": round(pos.y, 1), "floor": None,
            }))

        # (2) 레이어명이 AHU-* 인 INSERT 위치 (텍스트 태그가 없는 경우 폴백)
        for e in doc.modelspace():
            if e.dxftype() != "INSERT":
                continue
            layer = e.dxf.layer
            if not layer.upper().startswith(prefix.upper()):
                continue
            tag = layer.upper().replace(" ", "")
            key = (tag, round(e.dxf.insert.x), round(e.dxf.insert.y))
            if key in seen:
                continue
            seen.add(key)
            records.append(Record(kind="ahu", payload={
                "ahu_id": tag, "x": round(e.dxf.insert.x, 1),
                "y": round(e.dxf.insert.y, 1), "floor": None,
            }))
        return records
