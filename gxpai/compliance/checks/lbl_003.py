# -*- coding: utf-8 -*-
"""LBL-003 - 같은 방번호가 서로 다른 두 방에 붙어 있다 (minor). 신규 (2026-07-14).

## 어떻게 찾았나

방번호 충돌 감지기를 붙이자마자 기준 시설에서 2건이 나왔다.
그 전까지 `_merge` 가 한쪽을 조용히 덮어썼다. 예외도, 로그도, 0건도 아니었다.
방이 하나 사라지는데 아무도 몰랐다.

    3203   '샤워실(남)A'    ↔  '샤워실(남)A'         8,896mm 떨어짐
    4504   '(N)타정4실'     ↔  '(N)타정2실 전실'     6,025mm 떨어짐

두 라벨 모두 각자의 방 이름에서 250mm 거리다. 둘 다 정상적인 방 라벨이라는 뜻이다.
같은 방에 번호를 두 번 쓴 게 아니라, 서로 다른 두 방이 같은 번호를 달고 있다.

## 4504 는 차압도가 정답을 갖고 있었다

처음엔 "45xx 번호대에 4507 이 비어 있으니 번호 오기로 보인다"까지만 말하려 했다.
그런데 차압도를 대조해 보니 훨씬 강한 근거가 나왔다.

    평면도:  '(N)타정4실' -> 4504     (틀림)
    차압도:  '(N)타정4실' -> 4507     (맞음)

4507 은 평면도에 아예 없다(plan_x 가 NULL). 평면도가 그 방에 4504 를 붙여 버렸기 때문이다.
LBL-002 가 "4507 은 차압도에만 있다"고 따로 보고하던 것도 같은 뿌리였다.
두 규칙이 한 결함을 각자 반쪽씩 말하고 있었다.

이건 추측이 아니라 두 번째 근거와의 교차검증이다. 그래도 확정은 발주처가 한다.
우리는 두 도면이 어긋난다는 사실과 그 근거만 보고한다.

## 3203 은 다르다

32xx 번호대(3201~3206)에는 빈 번호가 없다. 차압도도 3203 을 하나만 안다.
그래서 어느 쪽이 잘못됐는지 도면만으로는 알 수 없다. 그렇게 보고한다.
근거가 없으면 없다고 말한다. 지어내지 않는다.

## 왜 중요한가

방번호는 우리 데이터의 키다. 덮어써진 방은 DB 에 없다. 그러면

    - 그 방의 차압, 인접, 등급을 아무도 검사하지 않는다
    - 그런데 리포트에는 "위반 없음"으로 보인다. 검사를 안 한 건데.

'없다'와 '검사 안 했다'를 혼동하는, 우리가 가장 경계하는 실수의 한 형태다.

## 무해한 경우와 구분한다

같은 방에 번호를 두 번 쓴 도면도 있다. 그건 결함이 아니다.
두 라벨 사이 거리로 가른다. 기본 3,000mm 이상이면 서로 다른 방으로 본다.
"""
from __future__ import annotations

import re

DEFAULT_MIN_DIST_MM = 3000.0

_NORM = re.compile(r"[\s()（）\-_]")


def _norm(s: str | None) -> str:
    return _NORM.sub("", (s or "").strip()).upper()


def _number_from_other_drawing(name, rooms, dup_no):
    """차압도가 이 방을 다른 번호로 부르고 있는지 본다.

    평면도가 번호를 잘못 붙였어도 차압도는 제대로 붙였을 수 있다.
    같은 이름의 방을 차압도가 다른 번호로 부르고, 그 번호가 평면도에는 없다면
    (plan_x 가 NULL), 그게 원래 번호일 가능성이 높다.

    기준 시설에서 실제로 그랬다. '(N)타정4실' 은 평면도에서 4504, 차압도에서 4507 이다.
    """
    target = _norm(name)
    if not target:
        return None
    for r in rooms:
        if not r.room_no or r.room_no == dup_no:
            continue
        if _norm(r.pressure_name) == target and r.plan_x is None:
            return r.room_no
    return None


def _gaps_in_band(dup_no: str, rooms) -> list[str]:
    """같은 번호대(예: 45xx)에서 비어 있는 번호. 사람에게 근거로 보여준다."""
    if not dup_no.isdigit():
        return []
    band = dup_no[:2]
    nos = sorted(r.room_no for r in rooms
                 if r.room_no and r.room_no.isdigit()
                 and len(r.room_no) == len(dup_no) and r.room_no.startswith(band))
    if len(nos) < 2:
        return []
    have = set(nos)
    return [str(i) for i in range(int(nos[0]), int(nos[-1]) + 1) if str(i) not in have]


def evaluate(conflicts: list[dict], rooms: list, cfg: dict) -> list[dict]:
    """conflicts: room_no_conflict 행. rooms: RoomView 목록(교차검증용). 순수 함수."""
    min_dist = float(cfg.get("different_room_min_dist_mm", DEFAULT_MIN_DIST_MM))
    rooms = rooms or []

    out: list[dict] = []
    for c in conflicts:
        dist = c.get("dist_mm")

        # 거리를 모르면 판정하지 않는다. 같은 방의 중복 표기일 수도 있다.
        # '정보가 없다'를 '결함이다'로 바꾸지 않는다. 반복해서 밟은 함정이다.
        if dist is None or dist < min_dist:
            continue

        no = c["room_no"]
        kept, lost = c.get("kept_name"), c.get("lost_name")

        # 두 방 중 어느 쪽이 번호를 잘못 받았는지 차압도에 물어본다
        suggest = None
        for cand in (lost, kept):
            hit = _number_from_other_drawing(cand, rooms, no)
            if hit:
                suggest = (cand, hit)
                break
        gaps = _gaps_in_band(no, rooms)

        head = (f"방번호 중복: {no} 이 서로 다른 두 방에 붙어 있다. "
                f"'{lost}' 와 '{kept}' 가 {dist:,.0f}mm 떨어져 있다")

        if suggest:
            nm, right = suggest
            why = (f". 차압도는 같은 방('{nm}')을 {right} 이라고 적고 있고, "
                   f"{right} 은 평면도에 아예 없다. "
                   f"즉 평면도가 '{nm}' 에 {right} 대신 {no} 를 잘못 적은 것으로 보인다")
            judgement = (f"차압도와 교차검증됨. 평면도의 '{nm}' 은 {no} 가 아니라 {right} "
                         f"이어야 할 것으로 보인다. 확정은 발주처가 한다. "
                         f"우리는 두 도면이 어긋난다는 사실과 근거만 보고한다")
        elif gaps:
            why = (f". 같은 번호대에서 {', '.join(gaps)} 이(가) 비어 있다. "
                   f"둘 중 하나가 그 번호여야 하는 것으로 보인다")
            judgement = ("보류, 발주처 확인 필요. 번호대에 빈자리가 있어 번호 오기로 보이나 "
                         "어느 방이 어느 번호인지는 도면만으로 확정할 수 없다")
        else:
            why = (". 같은 번호대에 빈 번호가 없고 차압도도 다른 번호를 말하지 않는다. "
                   "어느 쪽이 잘못됐는지 도면만으로는 알 수 없다")
            judgement = ("보류, 발주처 확인 필요. 번호 오기인지 두 방을 실제로 같은 번호로 "
                         "운영하는지 우리는 알 수 없다. 사실만 보고한다")

        tail = (f". 우리 병합은 '{lost}' 를 버리므로 그 방은 "
                f"차압, 인접, 등급 검사를 아예 받지 못한다")

        out.append({
            "severity": "minor",
            "rooms": [no],
            "message": head + why + tail,
            "evidence": {
                "room_no": no,
                "버려진_방": {"name": lost, "floor": c.get("lost_floor"),
                          "x": c.get("lost_x"), "y": c.get("lost_y")},
                "남은_방": {"name": kept, "floor": c.get("kept_floor"),
                         "x": c.get("kept_x"), "y": c.get("kept_y")},
                "거리_mm": round(dist),
                "이름도_같은가": _norm(kept) == _norm(lost),
                "번호대_빈자리": gaps,
                "차압도가_말하는_번호": (
                    {"방이름": suggest[0], "차압도_번호": suggest[1]} if suggest else None),
                "clause": "내부 정합성(도면 자체 모순). GMP 조항 아님",
                "판단": judgement,
            },
        })
    return out


def load_conflicts(cur, run_id: str) -> list[dict]:
    cur.execute(
        """SELECT room_no, kept_name, kept_floor, kept_x, kept_y,
                  lost_name, lost_floor, lost_x, lost_y, dist_mm
             FROM room_no_conflict WHERE run_id=%s""",
        (run_id,),
    )
    return [
        {"room_no": r[0], "kept_name": r[1], "kept_floor": r[2],
         "kept_x": r[3], "kept_y": r[4], "lost_name": r[5], "lost_floor": r[6],
         "lost_x": r[7], "lost_y": r[8], "dist_mm": r[9]}
        for r in cur.fetchall()
    ]


def run(cur, run_id, facility_id, rule) -> list[dict]:
    cfg = rule.get("config", {}) or {}
    if not cfg.get("enabled"):
        return []
    from ._model import load_rooms
    return evaluate(load_conflicts(cur, run_id), load_rooms(cur, run_id), cfg)
