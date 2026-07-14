# -*- coding: utf-8 -*-
"""Grade(청정등급) 추출기 — **텍스트 라벨 기반. 2026-07-13 재작성.**

무엇이 바뀌었나
  예전 스켈레톤은 **해치(HATCH) 색상 → 등급** 매핑을 가정했다. 실제 도면은 그렇지 않았다.
  등급은 **방 라벨 블록 안의 텍스트 `(D)` `(C)` `(B)` `(CNC)` `(NC)`** 로 적힌다.
  (새 참고도면 DXF 확인: 블록 `2층평면도(260320)` 안의 TEXT, 등급 49개)

라벨 블록의 구조 (세로 4단)
      (등급)        ← (CNC) (D) (C) (B) (NC)
      방 이름        ← 탈의실(남)
      방 번호        ← F2I01
      (절대압력)     ← 5Pa   ※ 이건 pressure_pa 추출기가 담당(레이어 `차압`)

방법
  등급 텍스트를 찾아 **가장 가까운 방번호**에 귀속시킨다.
  방번호를 축으로 삼는다(등급이 아니라). 등급 라벨은 방번호 **위쪽**에 붙으므로
    '위쪽 우선' 가중치를 준다. 이 좌표 규칙을 안 쓰면 옆방 등급을 훔쳐온다(PDF 작업에서 실제로 당했다).

한계(정직)
  - 등급 표기가 없는 도면(기준 시설 내용고형제)에서는 **0건**이 나온다. 그게 정상이다.
    "비무균이라 등급이 없다"가 아니라 "이 도면에 표기가 없다"는 뜻이다.
    총리령 별표1 제2.3호는 **제형 불문** 청정등급 설정을 요구하므로, 표기 부재는
    **발주처 확인 대상**이다(법규/조문근거_색인.md B절).
  - 해치 색상 매핑도 남겨 둔다(프로파일에 있으면 병행). 시설마다 다를 수 있다.
"""
from __future__ import annotations

import math
import re

from ..dxftext import iter_label_texts
from .base import BaseExtractor, Record

# (D) (C) (B) (A) (CNC) (NC) — 공백, 전각 괄호 허용
# 등급 표기. 사무소마다 다르다(`(D)`, `D급`, `Grade D` …)
# → 프로파일 `grades.grade_regex` 로 덮어쓸 수 있다. 하드코딩하면 다음 사무소에서 0건이 된다.
GRADE_RE = re.compile(r"^[\(（]\s*(A|B|C|D|CNC|NC)\s*[\)）]$", re.I)

DEFAULT_MAX_D = 4000.0      # mm. 등급 라벨 ↔ 방번호 최대 거리
DEFAULT_BELOW_PENALTY = 2.0  # 방번호보다 '아래'에 있는 등급은 옆방 것일 가능성이 높다


class GradeExtractor(BaseExtractor):
    kind = "grade"

    def extract(self, doc, profile) -> list[Record]:
        records: list[Record] = []
        records += self._from_text(doc, profile)
        records += self._from_hatch(doc, profile)
        return records

    # ── 텍스트 라벨 `(D)` → 방번호 귀속 (주 경로) ────────────────
    def _from_text(self, doc, profile) -> list[Record]:
        gcfg = profile.get("grades", {}) or {}
        fp = profile.get("floorplan", {}) or {}
        layers = gcfg.get("layers") or fp.get("room_layers")
        if not layers:
            return []

        entity_types = profile.get("label_entity_types", ["TEXT", "MTEXT"])
        num_re = re.compile(fp["room_no_regex"]) if fp.get("room_no_regex") else None
        bare_re = re.compile(fp["bare_no_regex"]) if fp.get("bare_no_regex") else None
        grade_re = (re.compile(gcfg["grade_regex"], re.I)
                    if gcfg.get("grade_regex") else GRADE_RE)
        max_d = float(gcfg.get("max_match_dist_mm", DEFAULT_MAX_D))
        below_penalty = float(gcfg.get("below_penalty", DEFAULT_BELOW_PENALTY))

        # 등급과 방번호는 **다른 레이어**에 있다 (Grade / ROOMNUMBER).
        #   처음엔 등급 레이어 하나에서 둘 다 찾았다 → 방번호가 0개라 등급도 0건이 나왔다.
        #   (압력 추출기는 처음부터 레이어를 나눠 읽어서 44건이 잘 나왔다. 같은 실수를 여기서 했다.)
        num_layers = fp.get("room_layers") or layers

        grades: list[tuple[float, float, str]] = []
        _skip = profile.get("label_exclude_blocks")
        for x, y, t, _h in iter_label_texts(doc, layers, entity_types, exclude_blocks=_skip):
            m = grade_re.match(t.strip())
            if m:
                # 캡처 그룹이 없는 정규식도 받는다(전체 문자열을 등급으로 본다)
                grades.append((x, y, (m.group(1) if m.groups() else t).strip().upper()))

        numbers: list[tuple[float, float, str]] = []
        for x, y, t, _h in iter_label_texts(doc, num_layers, entity_types,
                                            exclude_blocks=_skip):
            if num_re:
                mm = num_re.match(t)
                if mm:
                    numbers.append((x, y, mm.group(1) if mm.groups() else t))
                    continue
            if bare_re and bare_re.match(t):
                numbers.append((x, y, t))

        if not grades or not numbers:
            return []

        # 방번호를 축으로, 가장 가까운 등급 라벨 하나를 배타적으로 가져간다.
        # 등급은 방번호 '위'에 있으므로, 아래쪽 등급에는 벌점을 준다.
        pairs = []
        for gi, (gx, gy, g) in enumerate(grades):
            for ni, (nx, ny, no) in enumerate(numbers):
                d = math.hypot(gx - nx, gy - ny)
                if d > max_d:
                    continue
                if gy < ny:                      # 등급이 방번호보다 아래 = 의심
                    d *= below_penalty
                pairs.append((d, gi, ni))
        pairs.sort()

        used_g: set[int] = set()
        used_n: set[int] = set()
        out: list[Record] = []
        for d, gi, ni in pairs:
            if gi in used_g or ni in used_n:
                continue
            used_g.add(gi)
            used_n.add(ni)
            gx, gy, g = grades[gi]
            nx, ny, no = numbers[ni]
            out.append(Record(kind="room_grade", payload={
                "room_no": no, "grade": g,
                "grade_x": round(gx, 1), "grade_y": round(gy, 1),
                "match_dist_mm": round(d, 1),
                "source": "grade_text",
            }))
        return out

    # ── 해치 색상 → 등급 (보조 경로. 프로파일에 매핑이 있을 때만) ──
    def _from_hatch(self, doc, profile) -> list[Record]:
        mapping = (profile.get("grades", {}) or {}).get("hatch_color_to_grade")
        if not mapping:
            return []
        out: list[Record] = []
        for e in doc.modelspace():
            if e.dxftype() != "HATCH":
                continue
            color = e.dxf.color
            grade = mapping.get(str(color)) or mapping.get(color)
            if not grade:
                continue
            out.append(Record(kind="grade_zone", payload={
                "grade": grade, "color": color, "layer": e.dxf.layer,
                "source": "grade_hatch",
            }))
        return out
