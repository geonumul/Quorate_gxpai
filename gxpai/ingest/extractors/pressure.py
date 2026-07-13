# -*- coding: utf-8 -*-
"""차압도 추출기 - 방번호·이름, TA 수치, 차압 화살표(rotation).

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
        num_re = re.compile(r"^\(?(\d{4}(?:-\d+)?)\)?$")
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
        # ★예전엔 rotation 만 저장하고 "화살촉은 -y" 라고 **가정**했다. 그 가정 때문에
        #   28개 중 9개를 거꾸로 읽었다(블록마다 화살촉 방향이 다르고, 일부는 거울반사).
        #   이제 블록 기하에서 **재서** 세계 각도(head_deg)를 낸다. arrowgeom 모듈 참조.
        #
        # ★레이어 이름이 곧 **차압 설정값**이다: 'Air Flow 10Pa' / 'Air Flow 15Pa' /
        #   'Air Flow no차압'. 도면이 구간별 목표 차압을 직접 말해주는데 예전엔 버렸다.
        prefix = pr.get("arrow_block_prefix", "")
        arrow_layers = set(pr.get("arrow_layers") or [])
        for e in doc.modelspace():
            if e.dxftype() != "INSERT":
                continue
            if arrow_layers and e.dxf.layer not in arrow_layers:
                continue
            if not arrow_layers and not e.dxf.name.startswith(prefix):
                continue
            blk = doc.blocks.get(e.dxf.name)
            hd = arrowgeom.head_deg(e, blk) if blk is not None else None
            records.append(Record(kind="pressure_arrow", payload={
                "x": round(e.dxf.insert.x, 1), "y": round(e.dxf.insert.y, 1),
                "rotation_deg": round(e.dxf.rotation, 1),
                # None 이면 화살촉을 못 읽은 것 — 추측해 채우지 않는다. 규칙이 건너뛴다.
                "head_deg": round(hd, 1) if hd is not None else None,
                "layer": e.dxf.layer,
                "setpoint_pa": _setpoint_from_layer(e.dxf.layer),
                "floor": floor_of(e.dxf.insert.x),
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
