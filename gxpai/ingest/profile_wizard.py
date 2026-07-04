# -*- coding: utf-8 -*-
"""프로파일 자동 초안 - 인벤토리에서 시설 설정서 초안을 생성.

로드맵: T1.1.3 ("데이터 많아져도 그대로 작동"의 실체)
핵심: 레이어 '이름'을 하드코딩하지 않고 '내용(패턴)'으로 후보를 스코어링한다.
  - 방번호 레이어: (dddd) 또는 dddd 패턴 매칭률 상위
  - 방이름 레이어: 한글 텍스트 밀도 상위
  - 화살표 블록: 익명블록(A$*) INSERT 반복 상위 → 접두 추정
사람은 이 초안을 검토·수정만 한다. 초안이므로 status: draft 로 표기.
"""
from __future__ import annotations

import re
from collections import Counter

import ezdxf
from ezdxf import recover

from .dxftext import iter_label_texts_any_layer

PAREN_NUM = re.compile(r"^\((\d{3,5})(?:-\d+)?\)$")
BARE_NUM = re.compile(r"^(\d{3,5})(?:-\d+)?$")
HANGUL = re.compile(r"[가-힣]")


def _read(path):
    try:
        return ezdxf.readfile(path)
    except ezdxf.DXFStructureError:
        doc, _ = recover.readfile(path)
        return doc


def wizard_from_floorplan(dxf_path: str) -> dict:
    """평면도 1장에서 방번호/이름 레이어와 번호 패턴을 추정."""
    doc = _read(dxf_path)
    per_layer_num = Counter()
    per_layer_name = Counter()
    first_digits = Counter()
    num_lens = Counter()          # 방번호 자릿수 분포 → 정규식을 감지값에 맞춘다
    paren_hits, bare_hits = 0, 0

    for _x, _y, t, layer in iter_label_texts_any_layer(doc):
        m = PAREN_NUM.match(t)
        b = BARE_NUM.match(t)
        if m:
            per_layer_num[layer] += 1
            first_digits[m.group(1)[0]] += 1
            num_lens[len(m.group(1))] += 1
            paren_hits += 1
        elif b:
            per_layer_num[layer] += 1
            first_digits[b.group(1)[0]] += 1
            num_lens[len(b.group(1))] += 1
            bare_hits += 1
        elif HANGUL.search(t):
            per_layer_name[layer] += 1

    room_layers = sorted(
        {l for l, n in per_layer_num.items() if n >= 3}
        | {l for l, n in per_layer_name.items() if n >= 10},
        key=lambda l: -(per_layer_num[l] + per_layer_name[l]),
    )
    # 감지한 자릿수 범위로 정규식 생성(예전엔 \d{4} 하드코딩이라 3·5자리 번호를 통째로 놓쳤다)
    if num_lens:
        lo, hi = min(num_lens), max(num_lens)
        digits = f"\\d{{{lo}}}" if lo == hi else f"\\d{{{lo},{hi}}}"
    else:
        digits = r"\d{4}"
    room_no_regex = (rf"^\(({digits}(?:-\d+)?)\)$" if paren_hits >= bare_hits
                     else rf"^({digits}(?:-\d+)?)$")
    floors = {d: f"{d}F" for d in sorted(first_digits) if d.isdigit()}
    equip_candidates = [l for l, _ in per_layer_name.most_common()
                        if l not in room_layers][:2]

    return {
        "room_layers": room_layers[:4],
        "room_no_regex": room_no_regex,
        "floors": floors,
        "equipment_layer_candidates": equip_candidates,
        "_evidence": {"paren_hits": paren_hits, "bare_hits": bare_hits,
                      "top_name_layers": per_layer_name.most_common(6)},
    }


def wizard_from_pressure(dxf_path: str) -> dict:
    """차압도 1장에서 화살표 블록 접두를 추정."""
    doc = _read(dxf_path)
    anon = sum(1 for e in doc.modelspace()
               if e.dxftype() == "INSERT" and e.dxf.name.startswith("A$"))
    return {"arrow_block_prefix": "A$" if anon else None,
            "_evidence": {"anon_arrow_inserts": anon}}


def build_draft(profile_id: str, floorplan_dxf: str, pressure_dxf: str | None = None) -> dict:
    """검토용 프로파일 초안(dict) 생성. status: draft."""
    fp = wizard_from_floorplan(floorplan_dxf)
    draft = {
        "profile_id": profile_id,
        "profile_version": "draft",
        "status": "draft",
        "label_entity_types": ["TEXT", "MTEXT"],
        "floors": fp["floors"],
        "floorplan": {
            "room_layers": fp["room_layers"],
            "room_no_regex": fp["room_no_regex"],
            "bare_no_regex": r"^\d{4}(?:-\d+)?$",
            "max_match_dist_mm": 6000,
            "name_above_max_mm": 2500,
            "name_above_penalty": 1500,
            "skip_names": ["UP", "DN"],
            "title_attrib_tag": "도면명",
            "multiline_merge": {"max_dy_mm": 800, "max_dx_mm": 1200},
        },
        "equipment": {"layers": fp["equipment_layer_candidates"]},
        "_wizard_evidence": fp["_evidence"],
    }
    if pressure_dxf:
        pr = wizard_from_pressure(pressure_dxf)
        draft["pressure"] = {
            "rm_layer": "RM", "ta_layer": "TA", "title_layers": ["TIT", "TXT"],
            "floor_regex": r"(\d)(?:rd|th|st|nd)\s+FLOOR",
            "arrow_block_prefix": pr["arrow_block_prefix"] or "A$",
            "ref_pressure_token": "Pa", "name_match_dist_mm": 3000,
            "multiline_merge": {"max_dy_mm": 800, "max_dx_mm": 1200},
            "ta_unit": "UNKNOWN",
        }
    return draft
