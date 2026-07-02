# -*- coding: utf-8 -*-
"""설계개요 추출기 - 표에서 키-값 항목을 복원해 facility 메타로.

로드맵: T1.2.2
방법: 행 그룹핑(같은 y 밴드) + 키워드 사전 앵커. 각 키워드 텍스트의 같은 행 오른쪽에서
가장 가까운 값 텍스트를 짝짓는다("공    사    명" 처럼 자간 있는 키는 공백 제거 후 매칭).
키워드는 profile['overview']['keywords'] 로 주입(하드코딩 금지).
"""
from __future__ import annotations

import re

from ..dxftext import iter_label_texts_any_layer
from .base import BaseExtractor, Record

_WS = re.compile(r"\s+")


def _norm(t: str) -> str:
    return _WS.sub("", t)


class OverviewExtractor(BaseExtractor):
    kind = "overview"

    def extract(self, doc, profile) -> list[Record]:
        ov = profile.get("overview", {})
        keywords = ov.get("keywords")
        if not keywords:
            return []
        norm_keywords = {_norm(k): k for k in keywords}
        row_dy = ov.get("row_dy_mm", 300)
        max_dx = ov.get("value_max_dx_mm", 12000)

        texts = list(iter_label_texts_any_layer(doc))
        records: list[Record] = []
        seen_keys = set()
        for kx, ky, kt, _kl in texts:
            canon = norm_keywords.get(_norm(kt))
            if not canon or canon in seen_keys:
                continue
            # 같은 행(y 밴드) 오른쪽에서 가장 가까운 값 (키워드 칸이 아닌 텍스트)
            best, best_dx = None, None
            for vx, vy, vt, _vl in texts:
                if abs(vy - ky) > row_dy:
                    continue
                dx = vx - kx
                if dx <= 0 or dx > max_dx:
                    continue
                if _norm(vt) in norm_keywords:  # 다른 키 칸이면 값 아님
                    continue
                if not vt.strip():
                    continue
                if best_dx is None or dx < best_dx:
                    best, best_dx = vt.strip(), dx
            if best is not None:
                seen_keys.add(canon)
                records.append(Record(kind="overview_item", payload={
                    "key": canon, "value": best,
                }))
        return records
