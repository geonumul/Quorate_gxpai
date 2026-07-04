# -*- coding: utf-8 -*-
"""DXF 텍스트 읽기 공통 도구.

리스크 문서 반영:
- R-A1: AutoCAD 포맷 코드(%%C, %%D, MTEXT 인라인 코드)를 사람이 읽는 글자로 정규화.
- R-A2: TEXT 뿐 아니라 MTEXT 도 순회 (방 라벨이 MTEXT인 설계사 대비).
- S-10: 꺼진(off)·동결(frozen) 레이어의 텍스트는 제외 (구버전 잔재 '유령 방' 차단).
모든 추출기는 반드시 이 모듈의 iter_label_texts 를 통해 텍스트를 읽는다.
"""
from __future__ import annotations

from ezdxf.tools.text import plain_text


def normalize_dxf_text(entity) -> str:
    """엔티티의 표시 텍스트를 포맷 코드가 제거된 순수 문자열로 반환 (R-A1)."""
    if entity.dxftype() == "MTEXT":
        return entity.plain_text().strip()
    return plain_text(entity.dxf.text).strip()


def text_position(entity):
    """텍스트의 실제 삽입 위치 (R-F1: 정렬 텍스트는 insert 가 아니라 align_point).

    TEXT가 가운데/오른쪽/중앙 정렬이면 dxf.insert 는 쓰레기 값이고 dxf.align_point 가
    진짜 위치다. MTEXT의 insert 는 부착점이라 그대로 신뢰한다.
    """
    if entity.dxftype() == "MTEXT":
        return entity.dxf.insert
    halign = entity.dxf.get("halign", 0)
    valign = entity.dxf.get("valign", 0)
    if (halign or valign) and entity.dxf.hasattr("align_point"):
        return entity.dxf.align_point
    return entity.dxf.insert


def _layer_visible(doc, layer_name: str) -> bool:
    """레이어가 켜져 있고 동결되지 않았는지 (S-10)."""
    try:
        layer = doc.layers.get(layer_name)
    except Exception:
        return True  # 레이어 정의가 없으면 보수적으로 통과
    return not (layer.is_off() or layer.is_frozen())


def iter_label_texts_any_layer(doc, entity_types=("TEXT", "MTEXT")):
    """모든 레이어의 보이는 TEXT/MTEXT를 (x, y, text, layer) 로 순회 (profile wizard 용)."""
    types = tuple(entity_types)
    for e in doc.modelspace():
        if e.dxftype() not in types:
            continue
        if not _layer_visible(doc, e.dxf.layer):
            continue
        t = normalize_dxf_text(e)
        if not t:
            continue
        pos = text_position(e)
        yield (pos.x, pos.y, t, e.dxf.layer)


def iter_label_texts(doc, layers, entity_types=("TEXT", "MTEXT")):
    """지정 레이어의 보이는 TEXT/MTEXT를 (x, y, text, height) 로 순회 (R-A1/A2/S-10)."""
    if isinstance(layers, str):          # 프로파일이 "RM" 처럼 문자열이면 문자로 쪼개짐 방지
        layers = [layers]
    layers = set(layers)
    types = tuple(entity_types)
    msp = doc.modelspace()
    for e in msp:
        if e.dxftype() not in types:
            continue
        if e.dxf.layer not in layers:
            continue
        if not _layer_visible(doc, e.dxf.layer):
            continue
        t = normalize_dxf_text(e)
        if not t:
            continue
        ins = text_position(e)  # R-F1: 정렬 보정된 실제 위치
        height = getattr(e.dxf, "height", None) or getattr(e.dxf, "char_height", None)
        yield (ins.x, ins.y, t, height)
