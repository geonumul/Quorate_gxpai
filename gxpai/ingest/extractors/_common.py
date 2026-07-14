# -*- coding: utf-8 -*-
"""추출기 공통 헬퍼 (평면도, 차압도가 함께 쓰는 로직)."""
from __future__ import annotations

import math
import re


def merge_multiline_names(names, max_dy, max_dx):
    """여러 줄로 쪼개진 방 이름을 하나로 병합 (S-3: 평면도, 차압도 공통 적용).

    names: (x, y, text) 리스트. 바로 아래(dy<=max_dy, dx<=max_dx) 텍스트를 이어붙인다.
    """
    items = sorted(names, key=lambda n: -n[1])  # 위 → 아래
    used = [False] * len(items)
    out = []
    for i, (x, y, t) in enumerate(items):
        if used[i]:
            continue
        parts, cy = [t], y
        used[i] = True
        for j in range(i + 1, len(items)):
            if used[j]:
                continue
            x2, y2, t2 = items[j]
            if 0 < cy - y2 <= max_dy and abs(x2 - x) <= max_dx:
                parts.append(t2)
                used[j] = True
                cy = y2
        out.append((x, y, " ".join(parts)))
    return out


def match_name_to_anchor(nx, ny, names, max_dist, above_max=None, above_penalty=0.0):
    """번호 앵커(nx, ny)에 가장 가까운 이름 텍스트를 고른다.

    이름은 번호 바로 위에 오는 관례가 있어, 위쪽 후보에 가산점(거리 감점)을 준다.
    return: (best_index, name) 또는 (None, None)
    """
    best_i, best_score = None, None
    for i, (x, y, t) in enumerate(names):
        d = math.hypot(x - nx, y - ny)
        if d > max_dist:
            continue
        penalty = 0.0
        if above_max is not None:
            penalty = 0.0 if 0 < (y - ny) < above_max else above_penalty
        score = d + penalty
        if best_score is None or score < best_score:
            best_i, best_score = i, score
    if best_i is None:
        return None, None
    return best_i, names[best_i][2]


def load_sheet_titles(doc, attrib_tag):
    """타이틀블록 INSERT의 ATTRIB(도면명) → (x, 도면명) 리스트."""
    sheets = []
    for e in doc.modelspace():
        if e.dxftype() == "INSERT" and e.attribs:
            d = {a.dxf.tag: a.dxf.text for a in e.attribs}
            title = d.get(attrib_tag)
            if title:
                sheets.append((e.dxf.insert.x, title.strip()))
    sheets.sort()
    return sheets


def sheet_of(x, sheets):
    """x좌표에서 가장 가까운 타이틀블록의 도면명."""
    if not sheets:
        return None
    return min(sheets, key=lambda s: abs(s[0] - x))[1]


def floor_from_number(no, mapping):
    """방번호 첫자리 → 층 라벨 (프로파일 mapping 사용)."""
    if not no:
        return None
    return mapping.get(no[0])


def has_hangul(t):
    return bool(re.search(r"[가-힣]", t))
