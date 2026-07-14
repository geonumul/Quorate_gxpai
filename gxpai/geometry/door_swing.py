# -*- coding: utf-8 -*-
"""문이 **실제로 열리는가** — 스윙 반경에 기둥, 벽, 장비가 걸려 있는지 본다. 신규 (2026-07-14).

## 대표님이 **직접 요청한 기능**이다 (1차 미팅 2026-07-09)

> "(문 방향이) 꼭 이렇게 돼야 되는데 **경우에 따라서는 안 될 수도 있잖아요.**
>  소방법에 걸린다거나, 하다 보니까 **여기 기둥이 있어** — 그러면 **문을 못 열잖아요.**
>  그런 경우는 어쩔 수 없이 반대로 갈 수도 있다.
>  그런 건 나중에 **'얘는 (기둥에) 접촉이 돼서 문을 못 연다'고 메시지를 띄운다든지**만
>  해주면 사람들이 보고 문 방식을 바꾼다든지, 위치를 바꾼다든지"

**순수 기하 문제다. 법 해석이 필요 없다.** 그래서 확신을 갖고 판정할 수 있는
몇 안 되는 검사다(우리 규칙은 대부분 '보류'다).

## [주의]현재 상태: **실험 중. 규칙으로 등록하지 않았다.**

구현하고 실제 도면에 돌렸다. **두 번 자가 수정**했다:

  ① 장애물 격자에 **문 자신의 기하**(문짝, 문틀)를 넣었다 → **589개가 "0°만 열림"**.
     문이 자기 자신에 막힌 것이다. 말이 안 되는 값이라 바로 들통났다.
  ② 닫힌 위치 근처를 각도(8°)로 잘라냈다 → 반지름에 따라 실제 거리가 달라져 부정확.
     **닫힌 위치 선에서의 수직거리**(300mm)로 자르도록 바꿨다.

지금: 기준 시설 **48개**, 참고도면 **4개** 가 "90° 못 연다"고 나온다.
**그림으로 봐도 아직 애매하다.** 진짜 막힌 것인지, 우리가 가구, 마감선을 벽으로 태운 탓인지
(참고도면 `ARCH-기존` 에는 벽과 가구가 섞여 있다) 가리지 못했다.

→ **거짓 위반을 내느니 미완성으로 둔다.** 규칙(DOOR-001)으로 등록하지 않는다.
   남은 일: 장애물 레이어를 **기둥, 구조벽만**으로 좁히고, 눈으로 전수 검증한다.

## 어떻게 보나

문 블록의 **호(arc)** 가 곧 문짝이 지나가는 길이다 — 경첩(중심)에서 반지름 r 만큼.
그 **부채꼴을 훑어** 장애물(기둥, 벽, 장비)이 있는지 본다.

    - 경첩 근처(r 의 30% 안쪽)는 **보지 않는다** — 문틀, 문설주가 거기 있는 게 정상이다
    - 닫힌 위치(호의 양 끝)도 **보지 않는다** — 문이 닫히면 벽에 닿는 게 정상이다
    - 그 사이 구간에서 장애물이 나오면 → **문이 그만큼밖에 안 열린다**

몇 도까지 열리는지(`open_deg`)를 함께 낸다. 90° 를 못 열면 사람이 못 지나간다.
"""
from __future__ import annotations

import math

import numpy as np

# 경첩에서 이 비율 안쪽은 문틀이라 보고 무시한다
_INNER = 0.30
# 사람이 지나가려면 최소 이만큼은 열려야 한다
MIN_OPEN_DEG = 80.0

# 닫힌 위치의 **벽에서 이만큼 떨어진 곳만** 본다 (mm).
#
#   문은 **벽에 붙어 있는 게 정상**이다. 닫힌 위치 근처를 그대로 훑으면
#   **그 벽 자체를 장애물로 세어** 모든 문이 "0°만 열림"으로 나온다.
#   실제로 그렇게 했다가 589개가 0° 로 나왔다 — **말이 안 되는 값이라 바로 들통났다.**
#
#   각도로 잘라내면(예: 앞뒤 8°) 반지름에 따라 실제 거리가 달라져 부정확하다.
#   → **닫힌 위치 선에서의 수직거리**로 자른다. 벽 두께(50~150mm)를 넉넉히 넘긴다.
_WALL_CLEAR_MM = 300.0

# 그리고 **문 자신의 기하(문짝, 문틀)를 장애물에 넣으면 안 된다.**
#   문이 자기 자신에 막힌다. 장애물 격자는 **벽 레이어만**으로 만든다.


def swing_blocked(cx: float, cy: float, r: float, a0: float, a1: float,
                  obstacle: np.ndarray, minx: float, miny: float, cell: float,
                  ) -> tuple[float, tuple[float, float] | None]:
    """문이 **몇 도까지 열리는지** 와 **처음 막히는 지점**을 돌려준다.

    obstacle: 장애물 격자(1=막힘). 기둥, 벽, 장비를 태워 만든다.
    돌려주는 값: (열리는 각도, 막힌 지점 세계좌표 or None)
    """
    h, w = obstacle.shape
    sweep = (a1 - a0) % 360.0
    if sweep < 1e-6:
        sweep = 360.0

    steps = max(8, int(sweep))                # 1° 간격
    radii = [r * f for f in (0.45, 0.65, 0.85, 0.98)]

    # 닫힌 위치(호의 양 끝) 방향 단위벡터 — 이 선이 곧 **벽**이다
    e0 = (math.cos(math.radians(a0)), math.sin(math.radians(a0)))
    e1 = (math.cos(math.radians(a1)), math.sin(math.radians(a1)))

    def near_wall(dx: float, dy: float) -> bool:
        """닫힌 위치 선(=벽)에서 수직으로 _WALL_CLEAR_MM 안쪽인가."""
        for ex, ey in (e0, e1):
            along = dx * ex + dy * ey
            if along <= 0:
                continue                      # 반대쪽은 상관없다
            perp = abs(dx * -ey + dy * ex)
            if perp < _WALL_CLEAR_MM:
                return True
        return False

    for i in range(steps + 1):
        t = i / steps
        deg = sweep * t
        ang = a0 + deg
        ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        for rr in radii:
            if rr < r * _INNER:
                continue
            dx, dy = rr * ca, rr * sa
            # 문이 **벽에 붙어 있는 건 정상**이다. 그 벽을 장애물로 세면 안 된다.
            if near_wall(dx, dy):
                continue
            px = int((cx + dx - minx) / cell)
            py = int((cy + dy - miny) / cell)
            if not (0 <= py < h and 0 <= px < w):
                continue
            if obstacle[py, px]:
                return (deg, (cx + dx, cy + dy))   # 여기까지밖에 못 연다
    return (sweep, None)


def check(doc, profile, walls: np.ndarray, minx: float, miny: float, cell: float,
          rooms_at) -> list[dict]:
    """도면의 모든 문을 훑어 **못 열리는 문**을 찾는다.

    walls: 벽 격자(1=벽). 여기에 기둥, 장비를 더해 장애물 격자를 만든다.
    rooms_at(x, y) -> room_no | None : 좌표가 어느 방인지 알려주는 함수
    """
    from ..ingest.office_profile import scan  # noqa: F401  (재사용 없음, 의존 표시용)
    from .boundaries import _draw_line, _iter_wall_segments
    from .door_barriers import iter_door_arcs

    cfg = (profile.get("boundaries") or {})
    door_layers = list(cfg.get("door_layers") or [])
    if not door_layers:
        return []

    # 장애물 = 벽 + 기둥 + 장비.
    #   기둥은 벽 레이어에 이미 들어 있을 수도 있고(COL), 따로 있을 수도 있다.
    obs_layers = list(cfg.get("obstacle_layers") or [])
    obstacle = walls.astype(bool).copy()
    if obs_layers:
        extra = np.zeros_like(walls)
        for x0, y0, x1, y1 in _iter_wall_segments(doc, obs_layers):
            _draw_line(extra, int((x0 - minx) / cell), int((y0 - miny) / cell),
                       int((x1 - minx) / cell), int((y1 - miny) / cell))
        obstacle |= extra.astype(bool)

    out: list[dict] = []
    for c, p0, p1 in iter_door_arcs(doc, door_layers):
        r = math.hypot(p0[0] - c[0], p0[1] - c[1])
        if r < 300:                            # 문이라기엔 너무 작다
            continue
        a0 = math.degrees(math.atan2(p0[1] - c[1], p0[0] - c[0])) % 360
        a1 = math.degrees(math.atan2(p1[1] - c[1], p1[0] - c[0])) % 360
        open_deg, hit = swing_blocked(c[0], c[1], r, a0, a1,
                                      obstacle, minx, miny, cell)
        if open_deg >= MIN_OPEN_DEG or hit is None:
            continue
        out.append({
            "x": round(c[0], 1), "y": round(c[1], 1),
            "radius_mm": round(r),
            "open_deg": round(open_deg),
            "hit_x": round(hit[0], 1), "hit_y": round(hit[1], 1),
            "room_no": rooms_at(c[0], c[1]),
        })
    return out
