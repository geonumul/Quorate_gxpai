# -*- coding: utf-8 -*-
"""층별 SVG 렌더 - 방 위치 점 + violations 마커.

로드맵: T2.4.1
경계 폴리곤 미확보 상태이므로 방은 점(라벨 마커)으로 표시한다. 경계 확보 시 폴리곤으로 승격.
각 방에 data-room-no 속성(기계 가독). 위반 방은 빨간 링으로 강조.
"""
from __future__ import annotations

import html

_W = 760
_PAD = 30


def render_floor(floor: str, rooms: list[dict], violation_room_nos: set[str]) -> str:
    """rooms: [{room_no, name, x, y}]. y 는 DXF(위가 +) → SVG(아래가 +) 로 뒤집는다."""
    # x, y 둘 다 있어야 점을 찍는다(한쪽만 있으면 min/뒤집기에서 TypeError).
    pts = [(r["x"], r["y"]) for r in rooms
           if r.get("x") is not None and r.get("y") is not None]
    if not pts:
        return f'<p>{html.escape(floor)}: 좌표 있는 방 없음</p>'
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    spanx = (maxx - minx) or 1.0
    spany = (maxy - miny) or 1.0
    scale = (_W - 2 * _PAD) / spanx
    height = spany * scale + 2 * _PAD

    def sx(x):
        return _PAD + (x - minx) * scale

    def sy(y):
        return _PAD + (maxy - y) * scale  # y 뒤집기

    parts = [f'<svg viewBox="0 0 {_W:.0f} {height:.0f}" '
             f'xmlns="http://www.w3.org/2000/svg" class="floor-svg" '
             f'role="img" aria-label="{html.escape(floor)} 평면 배치">']
    parts.append(f'<rect x="0" y="0" width="{_W}" height="{height:.0f}" fill="#0f1115"/>')
    for r in rooms:
        if r.get("x") is None or r.get("y") is None:
            continue
        cx, cy = sx(r["x"]), sy(r["y"])
        no = r.get("room_no") or ""
        viol = no in violation_room_nos
        fill = "#e5484d" if viol else "#4c9aff"
        parts.append(
            f'<circle data-room-no="{html.escape(str(no))}" cx="{cx:.1f}" cy="{cy:.1f}" '
            f'r="4" fill="{fill}"/>')
        if viol:
            parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="8" fill="none" '
                         f'stroke="#e5484d" stroke-width="1.5"/>')
        label = html.escape(str(no))
        parts.append(f'<text x="{cx + 6:.1f}" y="{cy + 3:.1f}" font-size="8" '
                     f'fill="#9aa4b2">{label}</text>')
    parts.append("</svg>")
    return "".join(parts)
