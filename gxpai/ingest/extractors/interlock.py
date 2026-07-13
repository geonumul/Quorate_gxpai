# -*- coding: utf-8 -*-
"""인터락(연동장치) 추출기. **신규 (2026-07-14).**

## 조문 — 현행판과 구판이 **다르다**. 구판을 인용했으면 놓쳤다.

    현행 (법제처) 고시 별표1 제4호 파목
      "이송해치 및 에어락(물품 및 작업원용)의 경우 입구용과 출구용 문이
       **동시에 열려서는 안 된다.**
       **A등급과 B등급 구역으로 연결되는 에어락의 경우 인터락 시스템을 사용해야 한다.**
       C등급과 D등급 청정실로 연결되는 에어락의 경우, 최소한 시각경고시스템 및
       필요한 경우 음성경고시스템 …"

    구판 (식약처 게시판 · **인용금지**)
      "에어락이 설치된 양쪽 문은 동시에 열려서는 안 된다. … 인터락 시스템(interlocking
       system) **또는** 시각적 및 청각적 … 경보장치가 가동되어야 한다."

★구판은 "인터락 **또는** 경보장치"로 뭉뚱그렸는데, **현행은 등급별로 갈라놨다** —
  A/B 는 인터락 **필수**, C/D 는 시각경고면 된다.
  구판을 인용했으면 A/B 의 인터락 의무를 놓쳤을 것이다.
  **근거가 둘이면 반드시 대조한다. 그게 우리 규칙이다.**

## 도면에서 어떻게 생겼나

레이어 `u-interlock` 에 **2점 선** 24개.
에어락의 **두 문을 잇는 연결선**이다 — "이 둘은 동시에 열리면 안 된다".
→ 선의 **중점**이 그 에어락 방이다.

⚠ 한계: 전실이 아주 작으면(무균 전실 1.5㎡) 중점이 옆방 라벨에 더 가까울 수 있다.
   그래서 **최근접 방 하나**에만 붙이고, 반경을 넘으면 붙이지 않는다.
   귀속이 의심스러우면 규칙이 '보류'로 내보낸다. 조용히 틀리지 않는다.
"""
from __future__ import annotations

from .base import BaseExtractor, Record


class InterlockExtractor(BaseExtractor):
    kind = "interlock"

    def extract(self, doc, profile) -> list[Record]:
        cfg = profile.get("interlock") or {}
        layers = {l for l in (cfg.get("layers") or [])}
        if not layers:
            return []

        out: list[Record] = []
        for e in doc.modelspace():
            try:
                if e.dxf.layer not in layers:
                    continue
            except AttributeError:
                continue
            t = e.dxftype()
            pts: list[tuple[float, float]] = []
            try:
                if t == "LWPOLYLINE":
                    pts = [(p[0], p[1]) for p in e.get_points("xy")]
                elif t == "LINE":
                    pts = [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]
                elif t == "INSERT":
                    pts = [(e.dxf.insert.x, e.dxf.insert.y)]
            except Exception:               # noqa: BLE001
                continue
            if not pts:
                continue
            mx = sum(p[0] for p in pts) / len(pts)
            my = sum(p[1] for p in pts) / len(pts)
            out.append(Record(kind="interlock", payload={
                "x": round(mx, 1), "y": round(my, 1), "n_pts": len(pts),
            }))
        return out
