# -*- coding: utf-8 -*-
"""급기 풍량(CMH) 추출기. **신규 (2026-07-14).**

## 단위가 도면 안에 적혀 있었다

천정기구배치도(시트 0)의 레이어 `B-ZONE` 에 **`풍량(CMH)`** 이라는 텍스트가 있다.
TA 단위(CMH 인지 Pa 인지)는 오래 '보류'였는데 **도면 스스로 확정해 줬다.**
(적어도 이 도면에서는. 기준 시설의 `TA` 레이어는 여전히 추정이다 - 도면이 다르다.)

## [주의]그런데 환기 횟수(ACH) 규칙은 **만들지 않는다**

수치(Class 100(A) 600회/hr, Class 10,000(B) 20회/hr)는
「GMP 조사평가 매뉴얼」이 인용한 **구 KGMP 해설서**에만 있다.
**현행 고시(별표1, 2023 개정, PIC/S Annex 1 기반)에는 환기 횟수 수치가 없다.**
(별표1의 '환기' 언급 6건은 전부 EO 멸균 환기 등 다른 맥락이다 - 전수 확인했다)

현행은 오염관리전략(CCS)으로 타당성을 입증하게 한다.
수치를 박아 넣으면 **근거 없는 관행을 법인 것처럼** 판정하는 것이다. 하지 않는다.

→ 풍량은 **데이터로만 적재**한다. 규칙이 켜지려면:
    ① 발주처 **자사 환기 기준** (몇 회/hr 로 관리하는가)
    ② **천장고** (ACH = 풍량 ÷ (면적 × 천장고))
  둘 다 오면 그날 규칙을 만든다.

## 방에 어떻게 붙이나

풍량 숫자는 급기구(디퓨저) 옆에 적혀 있다. 한 방에 여러 개일 수 있다 → **합산**한다.
방 귀속은 좌표로 한다(가장 가까운 방, 반경 제한).
"""
from __future__ import annotations

import re

from .base import BaseExtractor, Record

_NUM = re.compile(r"^\d{2,6}(?:\.\d+)?$")


class AirflowExtractor(BaseExtractor):
    kind = "airflow"

    def extract(self, doc, profile) -> list[Record]:
        cfg = profile.get("airflow") or {}
        layers = {l for l in (cfg.get("layers") or [])}
        if not layers:
            return []

        out: list[Record] = []
        for e in doc.modelspace():
            if e.dxftype() not in ("TEXT", "MTEXT"):
                continue
            try:
                if e.dxf.layer not in layers:
                    continue
            except AttributeError:
                continue
            t = (e.plain_text() if e.dxftype() == "MTEXT" else e.dxf.text).strip()
            if not _NUM.match(t):
                continue                    # 단위 없는 숫자만. 범례 텍스트는 제외
            p = e.dxf.insert
            out.append(Record(kind="airflow", payload={
                "x": round(p.x, 1), "y": round(p.y, 1),
                "cmh": float(t),
                # 단위는 도면이 명시했다: 레이어 B-ZONE 의 '풍량(CMH)'
                "unit": cfg.get("unit", "CMH"),
                "unit_source": cfg.get("unit_source", "도면 표기"),
            }))
        return out
