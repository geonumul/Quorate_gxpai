# -*- coding: utf-8 -*-
"""차압 화살표의 **화살촉 방향을 블록 기하에서 직접 계산**한다.

★왜 이 모듈이 생겼나 — 가정 하나가 화살표 28개 중 9개를 거꾸로 읽게 했다

예전 코드는 이렇게 **가정**했다:
    "화살표는 rotation=0 일 때 화살촉이 -y 를 향한다"  → head_vector(rotation) 하나로 끝.

실제 도면(참고도면 2층)을 뜯어보니 화살표 블록이 **여러 종류**였고, 로컬 좌표에서
화살촉이 향하는 방향이 **블록마다 달랐다**:

    'Air Flow 15Pa'   뾰족한 끝 (0,0) · 꼬리 +x 쪽  → 화살촉 = **-x**
    'zw$E99B'         뾰족한 끝 (0,0) · 꼬리 -x 쪽  → 화살촉 = **+x**   ← 정반대!
    'Air Flow no차압'  뾰족한 끝 (1338,994) · 몸통 -x 쪽 → 화살촉 = **+x**

게다가 일부 INSERT 는 `xscale = -1.125` — **좌우 거울반사**가 걸려 있었다.
회전각만 보면 거울반사를 통째로 놓친다.

이 오독을 잡아낸 방법: 도면에는 **독립된 근거가 둘** 있다.
  ① 차압 화살표(꼬리=고압 → 화살촉=저압)   ② 방마다 적힌 절대압력(예: 15Pa)
둘을 대조하니 9건이 "공기가 5Pa 방에서 10Pa 방으로 흐른다"는 물리적으로 불가능한 말을 했다.
(scripts/xcheck_arrow_vs_pa.py)

## 지금 방식 — 가정하지 않고 **재는** 것

화살표 모양은 [뾰족한 머리 + 직사각형 꼬리]다. 그러면 외곽선 꼭짓점들의 **무게중심에서
가장 먼 꼭짓점이 곧 화살촉**이다. 도면 세 블록 모두에서 성립한다(그리고 시험이 고정한다).
방향은 `무게중심 → 화살촉`.

세계 좌표로 옮길 때는 INSERT 의 `matrix44()` 를 쓴다. 회전·축척·**음수 축척(거울반사)** 을
한꺼번에 처리한다. 직접 삼각함수를 쓰면 거울반사를 또 놓친다.

## 한계 (기록해 둔다)
- 외곽선이 닫힌 LWPOLYLINE 이 아닌 화살표(HATCH 만 있거나 LINE 조각뿐)는 못 읽고 None 을
  돌려준다. 그런 화살표는 **판정 대상에서 빼야지, 추측해 채우면 안 된다.**
- 좌우 대칭인 이상한 화살표(양쪽 다 뾰족)는 무게중심 규칙이 무너진다. 현재 도면엔 없다.
"""
from __future__ import annotations

import math

# 무게중심 대비 화살촉이 이 배율만큼은 튀어나와야 "뾰족하다"고 본다.
# 1.0 이면 아무 꼭짓점이나 통과한다 → 신뢰할 수 없는 화살표를 걸러내기 위한 최소 마진.
TIP_MARGIN = 1.15


def _outline(blk) -> list[tuple[float, float]]:
    """블록 정의에서 화살표 외곽선(닫힌 LWPOLYLINE)의 꼭짓점을 뽑는다."""
    best: list[tuple[float, float]] = []
    for e in blk:
        if e.dxftype() != "LWPOLYLINE" or not e.closed:
            continue
        pts = [(float(p[0]), float(p[1])) for p in e.get_points("xy")]
        if len(pts) > len(best):
            best = pts
    return best


def block_tip_local(blk) -> tuple[float, float] | None:
    """블록의 화살촉 방향(로컬 단위벡터). 못 정하면 None.

    무게중심에서 가장 먼 꼭짓점이 화살촉이다. 다만 그 거리가 두 번째로 먼 꼭짓점보다
    확실히 멀어야 한다(TIP_MARGIN) — 안 그러면 '뾰족한 데가 없는' 모양을 억지로 읽는 것이다.
    """
    pts = _outline(blk)
    if len(pts) < 5:            # 화살표는 최소 7~8 꼭짓점. 사각형(4)은 화살표가 아니다
        return None
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    d = sorted(((math.hypot(p[0] - cx, p[1] - cy), p) for p in pts), reverse=True,
               key=lambda t: t[0])
    (d1, tip), (d2, _) = d[0], d[1]
    if d1 <= 0 or d2 <= 0 or d1 < d2 * TIP_MARGIN:
        return None             # 뾰족한 끝이 뚜렷하지 않다 → 읽지 않는다
    dx, dy = tip[0] - cx, tip[1] - cy
    n = math.hypot(dx, dy)
    return (dx / n, dy / n)


def head_deg(insert, blk) -> float | None:
    """INSERT 하나의 **세계 좌표** 화살촉 방향(도, 0~360). 못 정하면 None.

    matrix44() 가 회전·축척·거울반사를 전부 반영한다.
    """
    v = block_tip_local(blk)
    if v is None:
        return None
    m = insert.matrix44()
    o = m.transform((0.0, 0.0, 0.0))
    p = m.transform((v[0], v[1], 0.0))
    dx, dy = p.x - o.x, p.y - o.y
    if math.isclose(dx, 0.0, abs_tol=1e-9) and math.isclose(dy, 0.0, abs_tol=1e-9):
        return None
    return math.degrees(math.atan2(dy, dx)) % 360.0


def head_vector_from_deg(deg: float) -> tuple[float, float]:
    """세계 각도(도) → 단위벡터."""
    th = math.radians(deg)
    return math.cos(th), math.sin(th)
