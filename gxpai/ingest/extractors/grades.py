# -*- coding: utf-8 -*-
"""Grade(청정등급) 추출기 — 해치 색상 → 등급 매핑.

로드맵: T1.2.4 (데이터 수령 전 스켈레톤)
현 시설엔 청정등급 도면이 없다(발주처 수령 대기). 매핑 스키마와 진입점만 준비해 두고,
프로파일 grades.status == pending_data 이면 빈 결과 + 사유를 반환한다.
등급 도면 수령 시 profile['grades']['hatch_color_to_grade'] 만 채우면 동작한다.
"""
from __future__ import annotations

from .base import BaseExtractor, Record


class GradeExtractor(BaseExtractor):
    kind = "grade"

    def extract(self, doc, profile) -> list[Record]:
        grades = profile.get("grades", {})
        mapping = grades.get("hatch_color_to_grade")
        if not mapping:
            # 데이터 미수령: 조용히 빈 결과 (사유는 run 요약/question 에서 노출)
            return []

        records: list[Record] = []
        for e in doc.modelspace():
            if e.dxftype() != "HATCH":
                continue
            color = e.dxf.color
            grade = mapping.get(str(color)) or mapping.get(color)
            if not grade:
                continue
            # 대표점: 첫 경계 경로의 정점 평균 (승격은 point-in-polygon 으로 Stage 2)
            records.append(Record(kind="grade_zone", payload={
                "grade": grade, "color": color, "layer": e.dxf.layer,
            }))
        return records
