# -*- coding: utf-8 -*-
"""DXF 인벤토리 - 도면 안의 레이어/텍스트/블록 통계.

로드맵: T1.1.3 근거 출력 (profile wizard 의 입력)
리스크 반영: 인벤토리에 진단 지표를 함께 산출.
  R-F1(halign/valign 분포), R-F2(extrusion 미러), R-F3(z≠0), S-10(frozen/off 레이어),
  R-A2(TEXT vs MTEXT), 헤더($INSUNITS/$DWGCODEPAGE).
"""
from __future__ import annotations

from collections import Counter

import ezdxf
from ezdxf import recover

from .dxftext import normalize_dxf_text


def _read(path):
    try:
        return ezdxf.readfile(path)
    except ezdxf.DXFStructureError:
        doc, _ = recover.readfile(path)
        return doc


def inventory(dxf_path: str) -> dict:
    doc = _read(dxf_path)
    msp = doc.modelspace()

    layer_text = Counter()      # 레이어별 TEXT/MTEXT 수 (한글 라벨 밀도)
    layer_insert = Counter()    # 레이어별 INSERT(블록) 수
    block_names = Counter()     # 블록명 반복 (화살표/타이틀 후보)
    entity_types = Counter()
    halign_nonzero = 0
    valign_nonzero = 0
    ocs_mirror = 0
    z_nonzero = 0
    text_total = 0

    frozen_off = []
    for layer in doc.layers:
        if layer.is_off() or layer.is_frozen():
            frozen_off.append(layer.dxf.name)

    for e in msp:
        et = e.dxftype()
        entity_types[et] += 1
        if et in ("TEXT", "MTEXT"):
            text_total += 1
            layer_text[e.dxf.layer] += 1
            if et == "TEXT":
                if e.dxf.get("halign", 0):
                    halign_nonzero += 1
                if e.dxf.get("valign", 0):
                    valign_nonzero += 1
            ins = e.dxf.insert
            if abs(getattr(ins, "z", 0.0)) > 1e-6:
                z_nonzero += 1
        elif et == "INSERT":
            layer_insert[e.dxf.layer] += 1
            block_names[e.dxf.name] += 1
        if e.dxf.hasattr("extrusion"):
            ext = e.dxf.extrusion
            if tuple(round(v, 3) for v in ext) == (0.0, 0.0, -1.0):
                ocs_mirror += 1

    return {
        "source_file": dxf_path,
        "header": {
            "insunits": doc.header.get("$INSUNITS"),
            "dwgcodepage": doc.header.get("$DWGCODEPAGE"),
            "dxf_version": doc.dxfversion,
        },
        "entity_types": entity_types.most_common(),
        "text_total": text_total,
        "top_text_layers": layer_text.most_common(12),
        "top_insert_layers": layer_insert.most_common(12),
        "top_block_names": block_names.most_common(12),
        "frozen_off_layers": frozen_off,
        "diagnostics": {
            "text_halign_nonzero": halign_nonzero,   # R-F1: 정렬 텍스트 수
            "text_valign_nonzero": valign_nonzero,
            "ocs_mirror_entities": ocs_mirror,       # R-F2
            "z_nonzero_entities": z_nonzero,         # R-F3
        },
    }


def print_report(inv: dict) -> None:
    h = inv["header"]
    print(f"[inventory] {inv['source_file']}")
    print(f"  DXF버전 {h['dxf_version']} · INSUNITS={h['insunits']} · codepage={h['dwgcodepage']}")
    print(f"  전체 엔티티 종류: {inv['entity_types'][:6]}")
    print(f"  글자(TEXT+MTEXT) 총 {inv['text_total']}")
    print("  글자 많은 레이어 top:")
    for name, n in inv["top_text_layers"]:
        print(f"    {name:16s} {n}")
    print("  블록(INSERT) 많은 레이어 top:")
    for name, n in inv["top_insert_layers"]:
        print(f"    {name:16s} {n}")
    print("  반복 블록명 top:")
    for name, n in inv["top_block_names"]:
        print(f"    {name:24s} {n}")
    d = inv["diagnostics"]
    print(f"  진단: 정렬텍스트 {d['text_halign_nonzero']} · OCS미러 {d['ocs_mirror_entities']} "
          f"· z오염 {d['z_nonzero_entities']} · frozen/off레이어 {len(inv['frozen_off_layers'])}")
