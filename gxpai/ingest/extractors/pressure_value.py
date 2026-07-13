# -*- coding: utf-8 -*-
"""절대압력(Pa) 추출기 — **신규 (2026-07-13).**

무엇을 뽑나
  방마다 도면에 표기된 **절대 정압**(`25Pa`, `0Pa` …). 새 참고도면 DXF 의 레이어 `차압` 에
  TEXT 로 들어 있다(45개). 라벨 블록의 맨 아래 단이다.

      (등급)  → grades.py
      방 이름  → floorplan.py
      방 번호  → floorplan.py
      **(압력)** → 여기

왜 필요한가
  PRES-002(차압 기준 이탈)와 PRES-003(봉쇄 실패)이 이 값을 쓴다.
  ★특히 PRES-003 은 "분진실 Pa > 복도 Pa 이면 봉쇄 실패"를 절대압력으로 직접 판정한다.

★귀속 규칙 (PDF 작업에서 크게 당한 부분)
  압력은 **자기 방번호 바로 아래**에 붙는다. 등급 태그를 기준으로 거리 매칭하면
  **옆방 압력을 훔쳐온다**(실제로 탈의실 5Pa 과 갱의실 15Pa 이 서로 뒤바뀌었다).
  그래서 여기서는 **방번호를 축**으로 삼고, **아래쪽을 우선**한다.
  자리가 좁으면 라벨 위로 밀리는 변형도 있으므로(F2I08), 위쪽도 허용하되 벌점을 준다.

한계(정직)
  - 기준 시설(내용고형제) 차압도에 Pa 표기가 있는지는 **미확인**. 없으면 0건이 나오고,
    PRES-002/003 의 절대압력 경로는 조용히 건너뛴다(화살표 경로는 그대로 동작).
  - TA(풍량, CMH)와 헷갈리면 안 된다. TA 는 90~450 범위의 **단위 없는 숫자**이고,
    압력은 `Pa` 접미가 붙는다. 정규식으로 명확히 가른다.
"""
from __future__ import annotations

import math
import re

from ..dxftext import iter_label_texts
from .base import BaseExtractor, Record

# "25Pa", "0 Pa", "-5pa" — 반드시 Pa 접미가 있어야 한다(TA 풍량과 구분)
PA_RE = re.compile(r"^(-?\d+(?:\.\d+)?)\s*(?:Pa|㎩)$", re.I)

DEFAULT_MAX_D = 5000.0        # mm
DEFAULT_ABOVE_PENALTY = 2.0   # 압력이 방번호 '위'에 있으면 변형 배치 → 벌점


class PressureValueExtractor(BaseExtractor):
    kind = "pressure_value"

    def extract(self, doc, profile) -> list[Record]:
        cfg = profile.get("pressure_value", {}) or {}
        fp = profile.get("floorplan", {}) or {}
        pr = profile.get("pressure", {}) or {}

        # 압력 텍스트가 있는 레이어. 새 도면은 `차압`. 없으면 차압도/평면도 라벨 레이어를 훑는다.
        layers = cfg.get("layers") or pr.get("room_layers") or fp.get("room_layers")
        if not layers:
            return []

        entity_types = profile.get("label_entity_types", ["TEXT", "MTEXT"])
        num_re = re.compile(fp["room_no_regex"]) if fp.get("room_no_regex") else None
        bare_re = re.compile(fp["bare_no_regex"]) if fp.get("bare_no_regex") else None
        max_d = float(cfg.get("max_match_dist_mm", DEFAULT_MAX_D))
        above_penalty = float(cfg.get("above_penalty", DEFAULT_ABOVE_PENALTY))

        # 압력 텍스트는 전용 레이어, 방번호는 라벨 레이어에 있을 수 있다 → 둘 다 훑는다
        num_layers = fp.get("room_layers") or layers
        _skip = profile.get("label_exclude_blocks")
        pa_texts = list(iter_label_texts(doc, layers, entity_types, exclude_blocks=_skip))
        no_texts = list(iter_label_texts(doc, num_layers, entity_types, exclude_blocks=_skip))

        pas: list[tuple[float, float, float]] = []
        for x, y, t, _h in pa_texts:
            m = PA_RE.match(t.strip().replace(" ", ""))
            if m:
                pas.append((x, y, float(m.group(1))))

        numbers: list[tuple[float, float, str]] = []
        for x, y, t, _h in no_texts:
            if num_re:
                m = num_re.match(t)
                if m:
                    numbers.append((x, y, m.group(1)))
                    continue
            if bare_re and bare_re.match(t):
                numbers.append((x, y, t))

        if not pas or not numbers:
            return []

        # 방번호를 축으로 배타 매칭. 압력은 방번호 '아래'가 기본.
        pairs = []
        for pi, (px, py, pa) in enumerate(pas):
            for ni, (nx, ny, no) in enumerate(numbers):
                d = math.hypot(px - nx, py - ny)
                if d > max_d:
                    continue
                if py > ny:                       # 압력이 방번호보다 위 = 변형 배치
                    d *= above_penalty
                pairs.append((d, pi, ni))
        pairs.sort()

        used_p: set[int] = set()
        used_n: set[int] = set()
        out: list[Record] = []
        for d, pi, ni in pairs:
            if pi in used_p or ni in used_n:
                continue
            used_p.add(pi)
            used_n.add(ni)
            px, py, pa = pas[pi]
            nx, ny, no = numbers[ni]
            out.append(Record(kind="room_pressure", payload={
                "room_no": no, "pressure_pa": pa,
                "pa_x": round(px, 1), "pa_y": round(py, 1),
                "match_dist_mm": round(d, 1),
                "source": "pressure_text",
            }))

        unmatched = len(pas) - len(used_p)
        if unmatched:
            # 조용히 버리지 않는다. 등급 표기가 없는 방(기존 구역)의 압력일 수 있다.
            out.append(Record(kind="pressure_unmatched", payload={
                "count": unmatched,
                "note": "방번호에 못 붙인 압력 라벨. 등급/번호 없는 구역의 값일 수 있음 — 확인 필요",
            }))
        return out
