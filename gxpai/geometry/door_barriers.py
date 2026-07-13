# -*- coding: utf-8 -*-
"""문(door)으로 **벽에 뚫린 구멍을 막는다**. flood-fill 이 옆방으로 새지 않게.

## 무엇이 문제였나

기준 시설 평면도에서 flood-fill 이 96방 중 **45방**만 잡았다(3F 는 38 중 9). 원인:
CAD 평면도는 **문 자리에 벽을 그리지 않는다.** 벽에 구멍이 뚫려 있으니 fill 이
그 구멍으로 옆방·복도로 줄줄 새어나가 여러 방이 하나의 거대한 덩어리가 됐다.

`close_gap_mm`(모폴로지 닫기)로 메우려 했지만, 문 폭이 900~2000mm 라 그만큼 키우면
**작은 방(전실 2~4㎡)이 통째로 삼켜진다.** 실제로 그렇게 망가뜨렸다.
문 폭만큼의 틈은 문 자체로 막아야지, 뭉뚱그려 메울 수 없다.

## 문 블록이 답을 갖고 있다

기준 시설 평면도에는 문 블록이 102개 있다(`Panel Door 11` ×52, `Panel Door 12` ×33 …).
블록 안을 뜯어보니:

    ARC  중심(222837,6354) r=970  180°~270°     ← 문이 열리는 궤적
    LWPOLY (222837,6354)(222797,6354)(222797,5384)(222837,5384)   ← 열린 문짝

**호의 중심 = 경첩.** 호의 두 끝점 중
    · 하나는 **닫힌 위치** — 벽 구멍을 정확히 가로지른다
    · 하나는 **열린 위치** — 방 안쪽 허공을 가리킨다 (문짝이 그려진 곳)
경첩에서 닫힌 위치까지 선을 그으면 **구멍이 정확히 막힌다.**

## 어느 끝점이 닫힌 위치인가 — 벽에게 물어본다

각도로 추측하지 않는다(회전·거울반사에 또 당한다. 화살표에서 겪었다).
**벽에 붙어 있는 쪽이 닫힌 위치다.** 닫힌 문의 끝은 반대쪽 문설주(벽)에 닿는다.
열린 문의 끝은 방 한가운데 떠 있다.
→ 이미 만들어 둔 **벽 격자**에서 각 끝점 주변에 벽이 있는지 세어 보고 고른다.
   틀리면 벽 격자가 알려준다. **자기검증이 되는 방법이다.**

## 한계 (정직하게)
- 미닫이문(`SD(W-1050)` = Sliding Door, 8개)은 호가 문짝의 궤적이 아니다.
  같은 규칙을 적용하면 엉뚱한 선을 그을 수 있다 → **양쪽 끝점 다 벽에서 멀면 그린다**
  대신 **아무것도 그리지 않는다**. 조용히 틀린 것보다 안 막는 게 낫다(그 방은 실패로 남는다).
- 호가 아예 없는 문 블록(`SD 양개도어`)은 손대지 않는다.
- 막은 결과는 반드시 방 개수로 확인한다. **좋아지지 않으면 쓰지 않는다.**
"""
from __future__ import annotations

import math

import numpy as np

# 끝점 주변에서 벽을 찾을 반경(격자 칸). 문설주가 격자 한 칸에 정확히 안 떨어져도 잡히게.
_PROBE = 2
# 이 정도 벽 픽셀도 없으면 "벽에 안 닿았다"고 본다.
_MIN_WALL_HITS = 1


def iter_door_arcs(doc, door_layers: list[str], max_depth: int = 4):
    """문 레이어에 놓인 **블록 안까지 들어가** 호(ARC)를 세계좌표로 뽑는다.

    (center_x, center_y, radius, start_deg, end_deg) 를 내놓는다.

    ★블록 재귀가 꼭 필요하다. 문 기하는 블록 **정의 안**에 있다.
      모델스페이스만 훑으면 `Panel Door 11` 102개가 통째로 안 보인다.
      텍스트에서 똑같은 함정에 빠졌었다(dxftext.iter_label_texts).
    """
    from ezdxf.math import Matrix44

    want = {lay.lower() for lay in door_layers}

    def walk(container, mat, parent_layer, depth):
        for e in container:
            t = e.dxftype()
            if t == "INSERT":
                if depth >= max_depth:
                    continue
                blk = doc.blocks.get(e.dxf.name)
                if blk is None:
                    continue
                m = e.matrix44()
                if mat is not None:
                    m = m @ mat
                # 블록 안 엔티티의 레이어가 '0' 이면 INSERT 의 레이어를 상속한다(CAD 규칙)
                yield from walk(blk, m, e.dxf.layer, depth + 1)
                continue

            if t != "ARC":
                continue
            lay = e.dxf.layer
            if lay == "0" and parent_layer:
                lay = parent_layer
            if lay.lower() not in want:
                continue

            c, r = e.dxf.center, e.dxf.radius
            a0, a1 = e.dxf.start_angle, e.dxf.end_angle
            p0 = (c.x + r * math.cos(math.radians(a0)), c.y + r * math.sin(math.radians(a0)))
            p1 = (c.x + r * math.cos(math.radians(a1)), c.y + r * math.sin(math.radians(a1)))
            cc = (c.x, c.y)
            if mat is not None:
                cc = mat.transform((c.x, c.y, 0.0))
                q0 = mat.transform((p0[0], p0[1], 0.0))
                q1 = mat.transform((p1[0], p1[1], 0.0))
                cc, p0, p1 = (cc.x, cc.y), (q0.x, q0.y), (q1.x, q1.y)
            yield (cc, p0, p1)

    yield from walk(doc.modelspace(), None, None, 0)


def _wall_near(walls: np.ndarray, x: int, y: int, probe: int = _PROBE) -> int:
    """격자 (x,y) 둘레 probe 칸 안의 벽 픽셀 수."""
    h, w = walls.shape
    y0, y1 = max(0, y - probe), min(h, y + probe + 1)
    x0, x1 = max(0, x - probe), min(w, x + probe + 1)
    if y0 >= y1 or x0 >= x1:
        return 0
    return int(walls[y0:y1, x0:x1].sum())


def door_barriers(doc, door_layers: list[str], walls: np.ndarray,
                  minx: float, miny: float, cell: float) -> list[tuple[float, float, float, float]]:
    """문마다 **닫힌 위치** 선분을 하나씩 돌려준다(세계좌표 x0,y0,x1,y1).

    walls: 이미 벽만으로 만든 격자(1=벽). **이 격자에게 어느 쪽이 벽인지 물어본다.**
    """
    out: list[tuple[float, float, float, float]] = []

    def g(p):
        return int((p[0] - minx) / cell), int((p[1] - miny) / cell)

    for c, p0, p1 in iter_door_arcs(doc, door_layers):
        gx0, gy0 = g(p0)
        gx1, gy1 = g(p1)
        h0 = _wall_near(walls, gx0, gy0)
        h1 = _wall_near(walls, gx1, gy1)

        if h0 < _MIN_WALL_HITS and h1 < _MIN_WALL_HITS:
            # 두 끝 다 벽에서 떨어져 있다 → 이 호는 여닫이문의 궤적이 아닐 수 있다
            # (미닫이문·장식 호). **추측해서 그리지 않는다.**
            continue
        if h0 == h1:
            # 둘 다 벽에 닿았다(문설주 사이가 좁거나 호가 짧다). 판단 불가 → 그리지 않는다.
            continue

        closed = p0 if h0 > h1 else p1
        out.append((c[0], c[1], closed[0], closed[1]))
    return out
