# -*- coding: utf-8 -*-
"""차압계(差壓計) 위치 추출기. **신규 (2026-07-14).**

## 왜 필요한가 — 우리는 시트를 **하나만** 보고 있었다

참고도면(2).dxf 에는 같은 평면도에 서로 다른 겹을 얹은 **시트가 6장** 있다.

    0 천정기구배치(HEPA BOX)   1 return 풍도   2 **차압흐름도**
    3 **차압계배치**            4 온습도계      5 인터락

우리는 **시트 2만** 잘라 쓰고 있었다. 그래서 `차압계-아날로그`(21) · `차압계-디지털`(7),
`HEPA BOX` 를 **통째로 못 보고 있었다.**

## 조문 (도면만으로 판정 가능하다)

    고시 별표1 제4호 너목
      "청정실 및 필요한 경우 아이솔레이터와 주변구역 사이에 **차압계가 설치되어야 한다.**
       … 중요하다고 확인된 차압은 **연속적으로 모니터하고 기록**하여야 한다."

도면이 구간별로 이미 답을 갖고 있다:
    `Air Flow 10Pa` / `Air Flow 15Pa` = 차압이 **설정된** 구간
    `Air Flow no차압`                 = 차압계 설치가 **요구되지 않는** 위치 (도면 범례 3번)
    `차압계-아날로그` / `차압계-디지털` = **실제로 설치된 차압계**

→ 차압이 설정됐는데 차압계가 없으면, 그 차압을 **유지·기록할 방법이 없다.**

## 좌표 정렬 (여기서 틀리면 전부 헛것이다)

시트마다 x 원점이 다르다(간격 106,026mm). 차압계 시트를 그냥 자르면 방 좌표와 안 맞는다.
→ `scripts/cut_ref_sheet_aligned.py` 가 **기준 시트(차압흐름도) 원점으로 평행이동**해서 저장한다.
   정렬이 맞았는지는 **좌표 범위가 겹치는지**로 확인한다
   (차압계 x 298,260~308,726 / 방 x 296,937~335,208 — 겹친다 ✔).
"""
from __future__ import annotations

from .base import BaseExtractor, Record


class GaugeExtractor(BaseExtractor):
    """`gauge.layers` 에 놓인 INSERT/CIRCLE 을 차압계 위치로 뽑는다."""

    kind = "gauge"

    def extract(self, doc, profile) -> list[Record]:
        cfg = profile.get("gauge") or {}
        layers = {l for l in (cfg.get("layers") or [])}
        if not layers:
            return []

        out: list[Record] = []
        for e in doc.modelspace():
            try:
                lay = e.dxf.layer
            except AttributeError:
                continue
            if lay not in layers:
                continue
            t = e.dxftype()
            try:
                if t == "INSERT":
                    p = e.dxf.insert
                elif t in ("CIRCLE", "ARC"):
                    p = e.dxf.center
                elif t in ("TEXT", "MTEXT"):
                    p = e.dxf.insert
                else:
                    continue
            except Exception:               # noqa: BLE001
                continue
            out.append(Record(kind="gauge", payload={
                "x": round(p.x, 1), "y": round(p.y, 1),
                "layer": lay,
                # 레이어 이름이 곧 종류다: '차압계-아날로그' / '차압계-디지털'
                "gauge_kind": ("디지털" if "디지털" in lay else
                               "아날로그" if "아날로그" in lay else lay),
            }))
        return out
