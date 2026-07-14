# -*- coding: utf-8 -*-
"""방 경계 폴리곤 - 벽 기반 flood-fill. **구현 (2026-07-13).**

무엇을 하나
  벽 선분을 격자에 태운 뒤(rasterize), 방 라벨 좌표에서 **번져나가기(flood-fill)** 하여
  그 방이 차지하는 영역을 얻는다. 거기서 **면적**과 **정확한 인접**을 계산한다.

왜 필요한가 (이게 없으면 못 켜는 규칙들)
  - ADJ-001  : 인접이 지금 '최근접 k개' 근사라 오탐/누락이 난다
  - PRES-002 : 인접 실 쌍의 차압 비교
  - PRES-003 : 봉쇄실 ↔ **인접 복도** 비교 ← 복도가 진짜 옆에 있는지 알아야 한다
  - 장비 귀속: 지금 nearest(376/418) → contains 로 승격

전략 (기존 문서의 3전략 중 3번)
  1) 닫힌 폴리라인이 방 외곽 → **이 도면엔 없다**(크린판넬 = 얇은 벽 단면, 면적 ~0)
  2) XREF 원본의 방 폴리곤 → **없다**
  3) **벽 LINE 을 격자에 태우고 flood-fill** ← 이걸 구현한다

문(door)이 뚫려 있으면 옆방으로 새어나간다
  CAD 평면도는 문 자리에 벽이 끊겨 있다. 그대로 fill 하면 두 방이 하나로 합쳐진다.
  → `door_layers` 의 선분도 **장벽으로 함께 태운다**(문틀, 문짝 선, 스윙 호).
  → 그래도 남는 틈은 `close_gap_mm` 만큼 **모폴로지 닫기**로 메운다.
  두 값 모두 프로파일에서 온다. 하드코딩 금지.

한계(정직)
  - 격자 해상도(`cell_mm`)보다 얇은 틈은 못 막고, 그보다 좁은 통로는 막힌다. 트레이드오프다.
  - fill 이 도면 전체로 번지면(=벽이 안 닫힘) 그 방은 **버린다**(면적 상한 초과 → failed 로 기록).
    조용히 이상한 값을 넣는 것보다 "못 구했다"가 낫다.
  - 결과에 `cell_mm` 과 실패 사유를 남겨 신뢰도를 추적한다(boundary_method='floodfill').
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage


# 문 양옆에서 방을 찾을 때 훑는 거리(mm). 가까운 데부터.
# 한 거리만 찍으면 그 점이 벽 두께 안이거나 가구 위일 때 방을 못 읽는다.
_DOOR_PROBE_STEPS = (300, 500, 700, 1000, 1400, 1900, 2500)


@dataclass
class RoomRegion:
    room_no: str
    area_m2: float
    polygon: list[tuple[float, float]]
    mask_id: int = -1


@dataclass
class BoundaryResult:
    rooms: list[RoomRegion] = field(default_factory=list)
    # 벽을 맞댄 방 쌍 (구획, 차압 검사용)
    adjacency: list[tuple[str, str]] = field(default_factory=list)
    # **문으로 이어진** 방 쌍 (동선 검사용 - ADJ-001 이 써야 하는 것).
    #   조문은 "작업원 **동선**", "**연결된** 구역"을 말한다. 벽만 맞대고 문이 없으면
    #   사람이 오갈 수 없으니 동선 위반이 아니다. 문 데이터가 없는 도면에서는 비어 있다.
    door_adjacency: list[tuple[str, str]] = field(default_factory=list)
    # 문 검출률 = 문이 하나라도 닿은 방 / 전체 방.
    #   방에는 대개 문이 하나씩 있다. 이 값이 낮으면 **우리 문 검출이 실패한 것**이다.
    #   낮은데도 문 인접을 쓰면 ADJ-001 이 "문이 없으니 위반 아님"으로
    #   **진짜 위반을 숨긴다.** 불완전한 문 데이터는 없느니만 못하다.
    door_coverage: float = 0.0
    cell_mm: float = 50.0
    failed: list[str] = field(default_factory=list)
    # 장벽으로 태우지 **못한** 기하 타입과 개수(벽/문 레이어 위에서).
    #   예전엔 이걸 안 세서 **조용히 사라졌다** - 기준 평면도에서 ELLIPSE 32, POLYLINE 22.
    #   벽을 구형 POLYLINE 으로 그리는 사무소가 오면 벽이 통째로 뭉개지는데
    #   로그 한 줄 안 남는다. 이 카운터가 유일한 단서다.
    unsupported_types: dict[str, int] = field(default_factory=dict)

    # 좌표 → 방번호. **경계 안에 들어가는지**로 붙인다.
    #   예전엔 '반경 안의 최근접 방'으로 붙였다. 그러면 72㎡ 충진실의 급기구가
    #   1.5㎡ 전실에 붙는다(실제로 NC 3㎡ 방에 1,697 CMH = 187회/hr 이 붙었다).
    #   방 경계를 이미 갖고 있는데 안 쓰고 있었다.
    _lab: object = None
    _minx: float = 0.0
    _miny: float = 0.0
    _by_lid: dict = field(default_factory=dict)

    def room_at(self, x: float, y: float) -> str | None:
        """이 좌표가 **어느 방 안**인가. 방 밖이면 None."""
        if self._lab is None:
            return None
        import numpy as _np
        lab = self._lab
        px = int((x - self._minx) / self.cell_mm)
        py = int((y - self._miny) / self.cell_mm)
        h, w = lab.shape
        if not (0 <= py < h and 0 <= px < w):
            return None
        return self._by_lid.get(int(lab[py, px]))


# 곡선을 선분으로 풀 때의 현(chord) 오차. 벽 두께(≈100mm)보다 훨씬 작으면 충분하다.
FLATTEN_MM = 20.0

# 우리가 **장벽으로 태울 수 있는** 기하 타입 전부.
_GEOM_TYPES = ("LINE", "LWPOLYLINE", "ARC", "POLYLINE", "CIRCLE", "SPLINE", "ELLIPSE")

# 기본 장벽 타입 - **실측으로 정했다. 짐작이 아니다.**
#
#   기준 평면도(f_1ae3a266, 방 라벨 111개)로 타입을 켜 가며 **방 경계 성공 수를 쟀다**:
#
#       LINE+LWPOLYLINE+ARC (기존)        경계 79/111
#       + POLYLINE                        경계 80/111   ← 한 방 늘었다
#       + POLYLINE+CIRCLE+SPLINE+ELLIPSE  경계 80/111   ← 더 켜도 변화 없다
#
#   → POLYLINE 은 **켠다.** 벽 레이어 위에 실제로 22개가 있었고(그동안 버려졌다),
#     켜니 방이 하나 늘고 아무것도 안 깨졌다. 구형 폴리라인(LWPOLYLINE 이전 표기)이라
#     벽을 이걸로 그리는 사무소가 오면 **벽이 통째로 사라진다.**
#
#   → CIRCLE, SPLINE, ELLIPSE 는 **끈다.** 이 도면에선 켜도 이득이 없다(80 그대로).
#     그리고 `wall_layers: ["*"]`(전 레이어) 프로파일에서 켜면 가구, 기호, 조경이
#     전부 장벽이 되어 **방이 잘게 쪼개진다.** 이득 없는 위험은 지지 않는다.
#
#   [주의]다른 사무소는 다를 수 있다. 프로파일 `boundaries.barrier_types` 로 덮어써라.
#     그리고 **켠 뒤 방 개수로 반드시 확인해라. 짐작으로 정하지 마라.**
#     못 태운 타입은 `BoundaryResult.unsupported_types` 에 세어 둔다 - 그게 유일한 단서다.
BARRIER_TYPES_DEFAULT = ("LINE", "LWPOLYLINE", "ARC", "POLYLINE")


def _iter_wall_segments(doc, layers: list[str], max_depth: int = 5,
                        skip_blocks: list[str] | None = None,
                        barrier_types: tuple[str, ...] = BARRIER_TYPES_DEFAULT,
                        unsupported: dict[str, int] | None = None):
    """벽/문 레이어에서 선분(2점)을 뽑는다. LINE, LWPOLYLINE, ARC(현으로 근사) 지원.

    **블록(INSERT) 안까지 재귀로 들어간다.**

    안 들어갔더니 기준 시설 3층이 37방 중 32방이 **하나의 41,227㎡ 덩어리**로 뭉쳤다.
    벽이 없어서가 아니라 **벽을 못 본 것**이었다 - 벽 선분이 블록 정의 안에 들어 있었다.
    (텍스트 쪽은 이미 재귀로 고쳤는데(dxftext) 벽은 안 고쳐 둔 채였다. 같은 함정을 두 번 밟았다.)

    레이어는 **실효 레이어**로 본다: 블록 안에서 레이어가 '0' 이면 INSERT 의 레이어를 상속한다.
    """
    from ezdxf.math import Matrix44

    want = {l.lower() for l in layers}
    # `wall_layers: ["*"]` = **레이어를 가리지 않고 선/호를 전부 장벽으로 태운다.**
    #
    #   참고도면에서 이게 유일한 방법이었다. 평면도 블록 안 엔티티가 **전부 레이어 '0'** 이라
    #   (블록이 INSERT 의 레이어를 상속) 레이어 이름으로 벽만 골라낼 수가 없다.
    #   레이어를 지정하면 벽 선분이 0개가 되고, 방 51개가 전부 실패한다.
    #
    #   대가: 가구, 치수선까지 장벽이 된다 → 방이 잘게 쪼개질 수 있다.
    #   참고도면에서는 문제되지 않았다(51/51). 안 되는 도면이 나오면 그때 걸러낸다.
    #   **어느 쪽이든 결과를 방 개수로 확인하고 쓴다. 짐작으로 정하지 않는다.**
    all_layers = "*" in want
    # 프로파일 문법 불일치를 흡수한다(정규식, 부분문자열 둘 다 받는다).
    from ..ingest.blockwalk import block_skipper
    skip = block_skipper(skip_blocks)
    barrier_types = tuple(barrier_types)
    if unsupported is None:
        unsupported = {}

    def emit(e, mat, lay):
        if not all_layers and lay.lower() not in want:
            return
        t = e.dxftype()
        if t not in barrier_types:
            # **조용히 버리지 않는다.** 무엇을 못 다뤘는지 세어서 호출자에게 알린다.
            #   이 카운터가 없어서 기준 평면도에서 88,356 개가 사라지는 걸 아무도 몰랐다.
            if t in _GEOM_TYPES:
                unsupported[t] = unsupported.get(t, 0) + 1
            return

        def tp(x, y):
            if mat is None:
                return (x, y)
            p = mat.transform((x, y, 0.0))
            return (p.x, p.y)

        if t == "LINE":
            a = tp(e.dxf.start.x, e.dxf.start.y)
            b = tp(e.dxf.end.x, e.dxf.end.y)
            yield (a[0], a[1], b[0], b[1])
        elif t == "LWPOLYLINE":
            pts = [tp(p[0], p[1]) for p in e.get_points()]
            if e.closed and len(pts) > 2:
                pts.append(pts[0])
            for i in range(len(pts) - 1):
                yield (pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
        elif t == "ARC":
            # 문 스윙 호 등: 현(chord) 여러 개로 근사하면 장벽 역할을 한다
            c, r = e.dxf.center, e.dxf.radius
            a0, a1 = math.radians(e.dxf.start_angle), math.radians(e.dxf.end_angle)
            if a1 < a0:
                a1 += 2 * math.pi
            n = max(2, int((a1 - a0) / 0.35) + 1)
            prev = None
            for i in range(n + 1):
                a = a0 + (a1 - a0) * i / n
                p = tp(c.x + r * math.cos(a), c.y + r * math.sin(a))
                if prev:
                    yield (prev[0], prev[1], p[0], p[1])
                prev = p
        # ── 아래 4종은 **예전에 조용히 버려졌다** ────────────────────
        #
        # 처음엔 "기준 평면도에서 88,356 개가 버려진다"고 썼다. **부풀린 숫자였다.**
        #   그건 문서 **전체**의 개수다(SPLINE 51,883, CIRCLE 27,954 …).
        #   대부분 가구, 조경, 표제란이라 **레이어 필터에서 이미 걸러진다.**
        #
        #   실제로 재 보니 **벽/문 레이어 위**에서 버려지던 건 이만큼이다:
        #       ELLIPSE 32, POLYLINE 22   (기준 평면도, 총 54개)
        #
        #   작지만 **진짜 손실**이다. 그리고 이 도면이 마침 그럴 뿐이다 -
        #   벽을 구형 POLYLINE 으로 그리는 사무소가 오면 **벽이 통째로 사라진다.**
        #   (POLYLINE 은 LWPOLYLINE 이전 표기다. 오래된 CAD 가 만든 블록은 아직도 쓴다)
        #
        # [주의]그렇다고 다 켜면 안 된다. `wall_layers: ["*"]`(참고도면) 이면
        #   **전 레이어가 장벽이 된다** - 원, 스플라인은 벽이 아니라 가구, 기호다.
        #   → `barrier_types` 로 타입별로 켜고 끈다. 기본값은 실측으로 정했다.
        elif t == "POLYLINE":
            try:
                pts = [tp(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
            except AttributeError:
                return
            if getattr(e, "is_closed", False) and len(pts) > 2:
                pts.append(pts[0])
            for i in range(len(pts) - 1):
                yield (pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
        elif t in ("CIRCLE", "SPLINE", "ELLIPSE"):
            # ezdxf 가 곡선을 선분열로 풀어 준다(현 오차 FLATTEN_MM).
            try:
                pts = [tp(p.x, p.y) for p in e.flattening(FLATTEN_MM)]
            except (AttributeError, ValueError, ZeroDivisionError):
                return                       # 퇴화 도형(반지름 0 등) - 벽이 아니다
            for i in range(len(pts) - 1):
                yield (pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])

    def walk(container, mat: "Matrix44 | None", parent_layer: str | None, depth: int):
        for e in container:
            try:
                lay = e.dxf.layer
            except AttributeError:
                continue
            if lay == "0" and parent_layer:
                lay = parent_layer

            if e.dxftype() == "INSERT":
                if depth >= max_depth:
                    continue
                if skip(e.dxf.name):
                    continue
                blk = doc.blocks.get(e.dxf.name)
                if blk is None:
                    continue
                m = e.matrix44()
                if mat is not None:
                    m = m @ mat
                yield from walk(blk, m, lay, depth + 1)
                continue

            yield from emit(e, mat, lay)

    yield from walk(doc.modelspace(), None, None, 0)


def _draw_line(grid: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> None:
    """Bresenham. 격자에 벽을 1 로 찍는다."""
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    h, w = grid.shape
    while True:
        if 0 <= y0 < h and 0 <= x0 < w:
            grid[y0, x0] = 1
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy


def _contour(mask: np.ndarray, minx: float, miny: float, cell: float,
             max_pts: int = 200) -> list[tuple[float, float]]:
    """영역의 외곽을 성기게 뽑는다(리포트 표시, 눈 검증용).

    정밀 폴리곤이 목표가 아니다 - 규칙이 쓰는 건 **면적과 인접**이다.
    외곽 픽셀을 무게중심 기준 각도순으로 정렬해 단순 다각형을 만든다.
    (오목한 방은 형태가 다소 뭉개진다. 면적은 마스크에서 직접 세므로 영향 없다.)
    """
    edge = mask & ~ndimage.binary_erosion(mask)
    ys, xs = np.nonzero(edge)
    if len(xs) == 0:
        return []
    cx, cy = xs.mean(), ys.mean()
    order = np.argsort(np.arctan2(ys - cy, xs - cx))
    xs, ys = xs[order], ys[order]
    if len(xs) > max_pts:
        idx = np.linspace(0, len(xs) - 1, max_pts).astype(int)
        xs, ys = xs[idx], ys[idx]
    return [(round(minx + float(x) * cell, 1), round(miny + float(y) * cell, 1))
            for x, y in zip(xs, ys)]


def _seed(lab: np.ndarray, cx: int, cy: int, w: int, h: int,
          cell_m2: float, min_area: float, max_area: float, radius: int) -> int:
    """라벨이 가리키는 자유 덩어리의 id 를 찾는다.

    전략(순서가 중요하다)
      1) **라벨 점이 그대로 얹힌 덩어리**가 조건(min~max)을 만족하면 그것이 정답이다.
      2) 아니면(장비선 안에 갇혔거나 벽 위에 얹혔으면) 주변을 훑되
         **가장 가까운** 유효 덩어리를 고른다.

    '가장 큰 덩어리'를 고르게 했더니 **옆방을 훔쳐왔다**(F2I05 가 F2I06 의 면적을 가져감).
      크기가 아니라 **거리**가 기준이어야 한다. 시행착오로 배웠다.
    """
    def valid(lid: int) -> bool:
        if lid == 0:
            return False
        a = float((lab == lid).sum()) * cell_m2
        return min_area <= a <= max_area

    # 1) 라벨 점 그대로
    if 0 <= cy < h and 0 <= cx < w:
        lid0 = int(lab[cy, cx])
        if valid(lid0):
            return lid0

    # 2) 가까운 순으로 확장 탐색
    r = max(1, radius)
    for d in range(1, r + 1):
        cands: list[tuple[float, int]] = []
        for dy in range(-d, d + 1):
            for dx in range(-d, d + 1):
                if max(abs(dy), abs(dx)) != d:       # 링(ring)만 본다
                    continue
                yy, xx = cy + dy, cx + dx
                if not (0 <= yy < h and 0 <= xx < w):
                    continue
                lid = int(lab[yy, xx])
                if valid(lid):
                    cands.append((float(dy * dy + dx * dx), lid))
        if cands:
            cands.sort()
            return cands[0][1]
    return 0


def build(doc, rooms: list[dict], profile: dict) -> BoundaryResult:
    """벽 + 방 라벨 좌표 → 방별 영역, 면적, 인접.

    rooms: [{"room_no": "3117", "plan_x": .., "plan_y": ..}, ...]
    profile["boundaries"]:
        wall_layers   : 벽 레이어 (필수)
        door_layers   : 문 레이어 (선택. 장벽으로 함께 태운다)
        cell_mm       : 격자 한 칸 (기본 50)
        close_gap_mm  : 남은 틈을 메울 폭 (기본 150)
        max_area_m2   : 초과하면 '벽이 안 닫힘'으로 보고 버린다 (기본 2000)
        min_area_m2   : 미만이면 라벨이 벽에 박힌 것 (기본 1)
    """
    cfg = profile.get("boundaries") or {}
    wall_layers = cfg.get("wall_layers")
    if not wall_layers:
        return BoundaryResult(failed=["profile.boundaries.wall_layers 미설정"])

    door_layers = cfg.get("door_layers") or []
    cell = float(cfg.get("cell_mm", 50))
    close_gap = float(cfg.get("close_gap_mm", 150))
    max_area = float(cfg.get("max_area_m2", 2000))
    min_area = float(cfg.get("min_area_m2", 1))

    # 프로파일이 장벽 타입을 덮어쓸 수 있다(사무소마다 벽을 그리는 타입이 다르다).
    bt = tuple(cfg.get("barrier_types") or BARRIER_TYPES_DEFAULT)
    unsupported: dict[str, int] = {}
    segs = list(_iter_wall_segments(doc, list(wall_layers) + list(door_layers),
                                    skip_blocks=cfg.get("skip_blocks"),
                                    barrier_types=bt, unsupported=unsupported))
    pts = [(r["plan_x"], r["plan_y"]) for r in rooms
           if r.get("plan_x") is not None and r.get("plan_y") is not None]
    if not segs or not pts:
        return BoundaryResult(cell_mm=cell,
                              unsupported_types=unsupported,
                              failed=["벽 선분 없음" if not segs else "방 라벨 좌표 없음"])

    xs = [s[0] for s in segs] + [s[2] for s in segs] + [p[0] for p in pts]
    ys = [s[1] for s in segs] + [s[3] for s in segs] + [p[1] for p in pts]
    pad = cell * 4
    minx, miny = min(xs) - pad, min(ys) - pad
    w = int((max(xs) + pad - minx) / cell) + 1
    h = int((max(ys) + pad - miny) / cell) + 1
    if w * h > 80_000_000:           # 안전장치: 격자가 너무 크면 해상도를 낮추라고 알린다
        return BoundaryResult(cell_mm=cell,
                              failed=[f"격자 과대({w}x{h}). cell_mm 을 키우세요"])

    def gx(x: float) -> int: return int((x - minx) / cell)
    def gy(y: float) -> int: return int((y - miny) / cell)

    walls = np.zeros((h, w), dtype=np.uint8)
    for x0, y0, x1, y1 in segs:
        _draw_line(walls, gx(x0), gy(y0), gx(x1), gy(y1))

    # ── 문 구멍 막기 ────────────────────────────────────────────
    # CAD 평면도는 **문 자리에 벽을 그리지 않는다.** 그대로 두면 fill 이 그 구멍으로
    # 옆방, 복도까지 줄줄 새어나가 여러 방이 하나의 거대한 덩어리가 된다
    # (기준 시설에서 96방 중 45방만 잡혔다. 3F 는 38 중 9).
    #
    # 문 블록의 **호(문이 열리는 궤적)** 에서 경첩과 '닫힌 위치'를 구해 선을 긋는다.
    # 어느 끝이 닫힌 위치인지는 **방금 만든 벽 격자에게 물어본다** - 닫힌 문의 끝은
    # 반대쪽 문설주(벽)에 닿고, 열린 문의 끝은 방 한가운데 떠 있다.
    # 각도로 추측하지 않는다(회전, 거울반사에 또 당한다. 차압 화살표에서 겪었다).
    door_segs: list[tuple[float, float, float, float]] = []
    if door_layers and cfg.get("seal_doors", True):
        from .door_barriers import door_barriers
        door_segs = door_barriers(doc, list(door_layers), walls, minx, miny, cell)
        for x0, y0, x1, y1 in door_segs:
            _draw_line(walls, gx(x0), gy(y0), gx(x1), gy(y1))

    # 남은 틈 메우기(문 자리 등). 닫기(closing)=팽창 후 침식 → 얇은 틈만 메운다.
    k = max(1, int(round(close_gap / cell)))
    if k > 1:
        st = np.ones((k, k), dtype=bool)
        walls = ndimage.binary_closing(walls.astype(bool), structure=st).astype(np.uint8)

    lab, _n = ndimage.label(walls == 0)      # 벽으로 나뉜 자유공간 덩어리
    cell_m2 = (cell / 1000.0) ** 2

    # 버려진 기하 타입을 **성공 경로에도** 실어 보낸다.
    #   처음엔 실패 경로(벽 0개)에만 배선해서, 정상 실행에선 계속 0 으로 보였다 -
    #   벽 레이어 위에 실제로 54개(ELLIPSE 32, POLYLINE 22)가 버려지고 있는데도.
    #   **경고를 만들어 놓고 정작 그 경고가 안 뜨는 경로에 뒀다.** 측정하다 잡았다.
    res = BoundaryResult(cell_mm=cell, unsupported_types=unsupported)
    owner: dict[int, str] = {}

    for r in rooms:
        no = r.get("room_no")
        if not no or r.get("plan_x") is None:
            continue
        cx, cy = gx(r["plan_x"]), gy(r["plan_y"])
        if not (0 <= cx < w and 0 <= cy < h):
            res.failed.append(f"{no}: 라벨이 도면 밖")
            continue

        # '벽이 안 닫힘'은 **먼저** 진단한다.
        #   _seed 는 범위 밖 덩어리를 걸러내므로, 그냥 맡기면 "못 찾음"으로 뭉개진다.
        #   사유가 정확해야 사람이 도면을 고칠 수 있다(시험이 이 퇴행을 잡았다).
        raw = int(lab[cy, cx])
        if raw and float((lab == raw).sum()) * cell_m2 > max_area:
            a = float((lab == raw).sum()) * cell_m2
            res.failed.append(f"{no}: 벽이 안 닫힘(면적 {a:.0f}㎡ > {max_area:.0f})")
            continue

        # 라벨 점이 '갇혀' 있을 수 있다. 실제 도면에서 겪은 두 경우:
        #   ① 라벨이 장비 외곽선(SOB 벤치, 오토클레이브) 안에 찍혀 작은 조각에 갇힘
        #   ② 라벨 점이 벽 픽셀 위에 정확히 얹힘
        # → 라벨 주변을 가까운 순으로 훑어 유효한 자유 덩어리를 찾는다.
        lid = _seed(lab, cx, cy, w, h, cell_m2, min_area, max_area,
                    int(cfg.get("seed_search_mm", 2500) / cell))
        if lid == 0:
            res.failed.append(f"{no}: 자유공간을 못 찾음(라벨이 벽/장비에 갇힘)")
            continue

        mask = lab == lid
        area = float(mask.sum()) * cell_m2
        if area > max_area:
            res.failed.append(f"{no}: 벽이 안 닫힘(면적 {area:.0f}㎡ > {max_area:.0f})")
            continue
        if area < min_area:
            res.failed.append(f"{no}: 면적 과소({area:.2f}㎡)")
            continue

        if lid in owner:
            # 두 방 라벨이 같은 덩어리 = 그 사이에 벽이 없다(또는 라벨 중복). 조용히 넘기지 않는다.
            res.failed.append(f"{no}: {owner[lid]} 와 같은 공간으로 판정됨(벽 누락 의심)")
            continue
        owner[lid] = no

        res.rooms.append(RoomRegion(room_no=no, area_m2=round(area, 2),
                                    polygon=_contour(mask, minx, miny, cell),
                                    mask_id=lid))

    # ── 인접: 각 방 영역을 **벽 두께만큼** 팽창시켜 다른 방과 닿는지 본다 ──
    # `close_gap` 과 **분리된 파라미터**여야 한다.
    #   틈 메우기(close_gap)는 작아야 좋다 - 크면 **작은 방(전실 2~4㎡)을 통째로 삼킨다**
    #   (900mm 로 뒀더니 무균 전실, 갱의실 6개가 벽에 먹혀 사라졌다).
    #   반면 인접 판정은 **벽 두께를 건너뛸 만큼** 커야 한다. 두 요구가 정반대다.
    #   같은 값에 묶어 뒀더니 close_gap=200 에서 방 51개를 다 찾고도 인접이 9쌍뿐이었다.
    # `adj_gap_mm` = **건너뛸 벽 두께(반경)**. 구조요소 크기가 아니다.
    #   (처음엔 크기로 썼다가 실제 반경이 절반이라 헷갈렸다 - 시험이 잡았다.)
    adj_gap = float(cfg.get("adj_gap_mm", max(close_gap, 300.0)))
    r = max(1, int(round(adj_gap / cell)))
    st = np.ones((2 * r + 1, 2 * r + 1), dtype=bool)
    own = {rr.room_no: (lab == rr.mask_id) for rr in res.rooms}
    dil = {no: ndimage.binary_dilation(m, structure=st) for no, m in own.items()}

    names = list(own)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            if (dil[a] & own[b]).any() or (dil[b] & own[a]).any():
                res.adjacency.append((a, b))

    # ── 문으로 이어진 인접 (동선) ───────────────────────────────
    # 위의 `adjacency` 는 **벽을 맞댄** 방이다. 그런데 조문이 말하는 건 그게 아니다.
    #
    #   고시 별표1 제4호 타목: "작업원 **동선**은 D→C→B 로 점진적"
    #   고시 별표17 제3.3호 라목: "청정도에 따른 타당한 순서로 **연결된** 구역에 배치"
    #
    #   둘 다 **사람, 물건이 오가는 길**을 말한다. 벽만 맞대고 문이 없으면 오갈 수 없다.
    #   벽 맞댐으로 ADJ-001 을 판정하면 **지나갈 수도 없는 두 방**을 '등급 급변'이라 우긴다.
    #
    #   → 문 장벽의 **양옆**을 찍어 두 방을 읽는다. 그것이 동선 인접이다.
    #   문 데이터가 없는 도면(참고도면)에서는 비어 있다 → 규칙이 벽 인접으로 폴백한다.
    if door_segs:
        seen_d: set[tuple[str, str]] = set()
        by_lid = {rr.mask_id: rr.room_no for rr in res.rooms}
        for x0, y0, x1, y1 in door_segs:
            dx, dy = x1 - x0, y1 - y0
            L = math.hypot(dx, dy)
            if L < 1:
                continue
            nx, ny = -dy / L, dx / L                 # 문틀에 **수직**인 방향
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2    # 문 한가운데
            # 한 점만 찍으면 안 된다 - 그 점이 벽 두께 안이거나 가구 위면 방을 못 읽는다.
            #   실제로 참고도면에서 호 85개 중 **4쌍**만 건졌다(검출률 14%).
            #   → 수직 방향으로 **여러 거리를 훑어** 처음 만나는 방을 쓴다.
            side: list[str] = []
            for s in (+1, -1):
                for step in _DOOR_PROBE_STEPS:
                    r_ = max(1, int(round(step / cell)))
                    px = gx(mx) + int(round(nx * r_ * s))
                    py = gy(my) + int(round(ny * r_ * s))
                    if not (0 <= py < h and 0 <= px < w):
                        continue
                    no = by_lid.get(int(lab[py, px]))
                    if no:
                        side.append(no)
                        break
            if len(side) == 2 and side[0] != side[1]:
                key = tuple(sorted(side))
                if key not in seen_d:
                    seen_d.add(key)
                    res.door_adjacency.append(key)   # type: ignore[arg-type]

        touched = {x for pr in res.door_adjacency for x in pr}
        res.door_coverage = len(touched) / len(res.rooms) if res.rooms else 0.0

    # 좌표 → 방 조회에 쓸 것들을 남긴다 (급기, 리턴, 장비 귀속에 쓴다)
    res._lab = lab
    res._minx, res._miny = minx, miny
    res._by_lid = {rr.mask_id: rr.room_no for rr in res.rooms}
    return res
