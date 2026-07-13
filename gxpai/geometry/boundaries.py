# -*- coding: utf-8 -*-
"""방 경계 폴리곤 — 벽 기반 flood-fill. **구현 (2026-07-13).**

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

★문(door)이 뚫려 있으면 옆방으로 새어나간다
  CAD 평면도는 문 자리에 벽이 끊겨 있다. 그대로 fill 하면 두 방이 하나로 합쳐진다.
  → `door_layers` 의 선분도 **장벽으로 함께 태운다**(문틀·문짝 선·스윙 호).
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


@dataclass
class RoomRegion:
    room_no: str
    area_m2: float
    polygon: list[tuple[float, float]]
    mask_id: int = -1


@dataclass
class BoundaryResult:
    rooms: list[RoomRegion] = field(default_factory=list)
    adjacency: list[tuple[str, str]] = field(default_factory=list)
    cell_mm: float = 50.0
    failed: list[str] = field(default_factory=list)


def _iter_wall_segments(doc, layers: list[str]):
    """벽/문 레이어에서 선분(2점)을 뽑는다. LINE·LWPOLYLINE·ARC(현으로 근사) 지원."""
    want = {l.lower() for l in layers}
    for e in doc.modelspace():
        try:
            if e.dxf.layer.lower() not in want:
                continue
        except AttributeError:
            continue
        t = e.dxftype()
        if t == "LINE":
            a, b = e.dxf.start, e.dxf.end
            yield (a.x, a.y, b.x, b.y)
        elif t == "LWPOLYLINE":
            pts = [(p[0], p[1]) for p in e.get_points()]
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
                p = (c.x + r * math.cos(a), c.y + r * math.sin(a))
                if prev:
                    yield (prev[0], prev[1], p[0], p[1])
                prev = p


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
    """영역의 외곽을 성기게 뽑는다(리포트 표시·눈 검증용).

    정밀 폴리곤이 목표가 아니다 — 규칙이 쓰는 건 **면적과 인접**이다.
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

    ★'가장 큰 덩어리'를 고르게 했더니 **옆방을 훔쳐왔다**(F2I05 가 F2I06 의 면적을 가져감).
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
    """벽 + 방 라벨 좌표 → 방별 영역·면적·인접.

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

    segs = list(_iter_wall_segments(doc, list(wall_layers) + list(door_layers)))
    pts = [(r["plan_x"], r["plan_y"]) for r in rooms
           if r.get("plan_x") is not None and r.get("plan_y") is not None]
    if not segs or not pts:
        return BoundaryResult(cell_mm=cell,
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

    # 남은 틈 메우기(문 자리 등). 닫기(closing)=팽창 후 침식 → 얇은 틈만 메운다.
    k = max(1, int(round(close_gap / cell)))
    if k > 1:
        st = np.ones((k, k), dtype=bool)
        walls = ndimage.binary_closing(walls.astype(bool), structure=st).astype(np.uint8)

    lab, _n = ndimage.label(walls == 0)      # 벽으로 나뉜 자유공간 덩어리
    cell_m2 = (cell / 1000.0) ** 2

    res = BoundaryResult(cell_mm=cell)
    owner: dict[int, str] = {}

    for r in rooms:
        no = r.get("room_no")
        if not no or r.get("plan_x") is None:
            continue
        cx, cy = gx(r["plan_x"]), gy(r["plan_y"])
        if not (0 <= cx < w and 0 <= cy < h):
            res.failed.append(f"{no}: 라벨이 도면 밖")
            continue

        # ★'벽이 안 닫힘'은 **먼저** 진단한다.
        #   _seed 는 범위 밖 덩어리를 걸러내므로, 그냥 맡기면 "못 찾음"으로 뭉개진다.
        #   사유가 정확해야 사람이 도면을 고칠 수 있다(시험이 이 퇴행을 잡았다).
        raw = int(lab[cy, cx])
        if raw and float((lab == raw).sum()) * cell_m2 > max_area:
            a = float((lab == raw).sum()) * cell_m2
            res.failed.append(f"{no}: 벽이 안 닫힘(면적 {a:.0f}㎡ > {max_area:.0f})")
            continue

        # 라벨 점이 '갇혀' 있을 수 있다. 실제 도면에서 겪은 두 경우:
        #   ① 라벨이 장비 외곽선(SOB 벤치·오토클레이브) 안에 찍혀 작은 조각에 갇힘
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
    # ★`close_gap` 과 **분리된 파라미터**여야 한다.
    #   틈 메우기(close_gap)는 작아야 좋다 — 크면 **작은 방(전실 2~4㎡)을 통째로 삼킨다**
    #   (900mm 로 뒀더니 무균 전실·갱의실 6개가 벽에 먹혀 사라졌다).
    #   반면 인접 판정은 **벽 두께를 건너뛸 만큼** 커야 한다. 두 요구가 정반대다.
    #   같은 값에 묶어 뒀더니 close_gap=200 에서 방 51개를 다 찾고도 인접이 9쌍뿐이었다.
    # `adj_gap_mm` = **건너뛸 벽 두께(반경)**. 구조요소 크기가 아니다.
    #   (처음엔 크기로 썼다가 실제 반경이 절반이라 헷갈렸다 — 시험이 잡았다.)
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
    return res
