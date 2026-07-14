# -*- coding: utf-8 -*-
"""HVAC 추출기 - AHU 태그·위치.

로드맵: T1.2.1 (폴백: 태그만)
AHU는 이 도면에서 'AHU-*' 레이어명 또는 'AHU' 를 포함한 텍스트로 나타난다.
존 경계는 실측 후 가능 시(현재 미구현). 층 판정은 이후 시트 정렬로 승격.
"""
from __future__ import annotations

import re

from ..dxftext import _layer_visible, normalize_dxf_text, text_position
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

        # ★★**블록 재귀로 바꿨다.** 예전엔 `doc.modelspace()` 만 훑었다.
        #   AHU 태그·기기는 대개 **장비 블록 안**에 있다. 모델스페이스만 보면 **AHU 0개**가
        #   나오는데 예외도 경고도 없다 — 그냥 "AHU 가 없는 시설"처럼 보인다.
        #   (방 라벨·벽·문·화살표·차압계에 이어 **여섯 번째** 같은 함정이다)
        #
        #   walk() 가 꺼진·동결 레이어를 이미 걸러 준다(S-10). 좌표는 matrix44 변환 —
        #   직접 계산하면 **거울반사(xscale<0)** 를 놓친다.
        from ...ingest.blockwalk import walk, world_point

        entities = list(walk(doc, yield_inserts=True))

        # (1) 텍스트 태그: 'AHU...' 를 포함하는 라벨
        for e, mat, _lay in entities:
            if e.dxftype() not in entity_types:
                continue
            t = normalize_dxf_text(e)
            m = tag_re.search(t)
            if not m:
                continue
            x, y = world_point(text_position(e), mat)
            tag = m.group(0).upper().replace(" ", "")
            key = (tag, round(x), round(y))
            if key in seen:
                continue
            seen.add(key)
            records.append(Record(kind="ahu", payload={
                "ahu_id": tag, "x": round(x, 1), "y": round(y, 1), "floor": None,
            }))

        # (2) 레이어명이 AHU-* 인 INSERT 위치 (텍스트 태그가 없는 경우 폴백)
        #     ★**실효 레이어**로 본다 — 블록 안 엔티티가 레이어 '0' 이면 INSERT 레이어를
        #       상속한다. `e.dxf.layer` 를 그대로 보면 블록 안에서 '0' 이 나와 다 놓친다.
        for e, mat, layer in entities:
            if e.dxftype() != "INSERT":
                continue
            if not layer.upper().startswith(prefix.upper()):
                continue
            tag = layer.upper().replace(" ", "")
            ix, iy = world_point(e.dxf.insert, mat)
            key = (tag, round(ix), round(iy))
            if key in seen:
                continue
            seen.add(key)
            records.append(Record(kind="ahu", payload={
                # ★세계좌표(ix, iy)를 쓴다. `e.dxf.insert` 는 **블록 로컬 좌표**라
                #   블록 안 AHU 면 엉뚱한 자리에 찍힌다(그 좌표로 방에 귀속시킨다).
                "ahu_id": tag, "x": round(ix, 1), "y": round(iy, 1), "floor": None,
            }))
        return records
