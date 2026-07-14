# -*- coding: utf-8 -*-
"""장비 추출기 - 평면도 장비 레이어의 장비명, 좌표.

로드맵: T1.2.3
좌표만 수집한다. 방 귀속(method=nearest)은 run 단계에서 방 좌표로 계산하고,
Stage 2 에서 point-in-polygon(method=contains)으로 승격한다.
"""
from __future__ import annotations

from ..dxftext import iter_label_texts
from .base import BaseExtractor, Record


class EquipmentExtractor(BaseExtractor):
    kind = "equipment"

    def extract(self, doc, profile) -> list[Record]:
        eq = profile.get("equipment", {})
        layers = eq.get("layers")
        if not layers:
            return []
        entity_types = profile.get("label_entity_types", ["TEXT", "MTEXT"])
        records: list[Record] = []
        _skip = profile.get("label_exclude_blocks")
        for x, y, t, _h in iter_label_texts(doc, layers, entity_types, exclude_blocks=_skip):
            records.append(Record(kind="equipment", payload={
                "name": t, "x": round(x, 1), "y": round(y, 1), "method": "nearest",
            }))
        return records
