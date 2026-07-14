# -*- coding: utf-8 -*-
"""LBL-003 — **같은 방번호가 서로 다른 두 방에 붙어 있다** (minor). 신규 (2026-07-14).

## 어떻게 찾았나

방번호 충돌 감지기를 만들자마자 **기준 시설에서 2건**이 나왔다.
그 전까지 `_merge` 가 한쪽을 **조용히 덮어썼다** — 예외도, 로그도, 0건도 아니었다.
**방이 하나 사라지는데 아무도 몰랐다.**

    3203   '샤워실(남)A'    ↔  '샤워실(남)A'         8,896mm 떨어짐
    4504   '(N)타정4실'     ↔  '(N)타정2실 전실'     6,025mm 떨어짐

두 라벨 모두 각자의 방 이름에서 **250mm** 거리다 — 둘 다 정상적인 방 라벨이다.
같은 방에 번호를 두 번 쓴 게 아니라, **서로 다른 두 방이 같은 번호를 달고 있다.**

## 번호 순서가 말해 준다 (★그러나 이건 **추정**이다)

    45xx:  4501 4502 4503 [4504 4504] 4505 4506 ____ 4508 4509 4510
                          ↑↑ 중복                    ↑ 4507 이 없다

4504 가 둘, 4507 이 없다. 설계사가 번호를 잘못 매긴 것으로 **보인다**.

**그러나 우리가 단정하지 않는다.** 특별한 표기 관례일 수도 있다.
→ evidence 에 **'보류 · 발주처 확인 필요'** 로 남긴다. 우리는 사실만 말한다:
   *"이 번호가 두 방에 붙어 있다. 그리고 이 번호가 비어 있다."*

## 왜 이게 중요한가 (사라진 방은 **검사조차 안 된다**)

방번호는 우리 데이터의 **키**다. 덮어써진 방은 DB 에 없다 →

    · 그 방의 차압·인접·등급을 **아무도 검사하지 않는다**
    · 그런데 리포트에는 "위반 없음"으로 보인다 — **검사를 안 한 건데**

'없다'와 '검사 안 했다'를 혼동하는, 우리가 가장 경계하는 실수의 한 형태다.

## 무해한 경우와 구분한다

같은 방에 번호를 두 번 쓴 도면도 있다(라벨 중복 표기). 그건 결함이 아니다.
→ 두 라벨 사이 **거리**로 가른다. 기본 3,000mm 이상이면 서로 다른 방으로 본다.
"""
from __future__ import annotations

DEFAULT_MIN_DIST_MM = 3000.0


def evaluate(conflicts: list[dict], cfg: dict) -> list[dict]:
    """conflicts: room_no_conflict 행들. 순수 함수(DB 무관)."""
    min_dist = float(cfg.get("different_room_min_dist_mm", DEFAULT_MIN_DIST_MM))

    out: list[dict] = []
    for c in conflicts:
        dist = c.get("dist_mm")

        # ★거리를 모르면 **판정하지 않는다.** 같은 방의 중복 표기일 수도 있다.
        #   ('정보가 없다' 를 '결함이다' 로 바꾸지 않는다 — 반복해서 밟은 함정이다)
        if dist is None:
            continue
        if dist < min_dist:
            continue                       # 같은 방에 라벨이 두 번 — 무해하다

        kept, lost = c.get("kept_name"), c.get("lost_name")
        same_name = (kept or "").strip() == (lost or "").strip()

        out.append({
            "severity": "minor",
            "rooms": [c["room_no"]],
            "message": (
                f"방번호 중복: **{c['room_no']}** 이 서로 다른 두 방에 붙어 있다 — "
                f"'{lost}' 와 '{kept}' ({dist:,.0f}mm 떨어져 있다). "
                f"우리 병합은 **'{lost}' 를 버린다** → 그 방은 "
                f"차압·인접·등급 검사를 **아예 받지 못한다**"),
            "evidence": {
                "room_no": c["room_no"],
                "버려진_방": {"name": lost, "floor": c.get("lost_floor"),
                          "x": c.get("lost_x"), "y": c.get("lost_y")},
                "남은_방": {"name": kept, "floor": c.get("kept_floor"),
                         "x": c.get("kept_x"), "y": c.get("kept_y")},
                "거리_mm": round(dist),
                "이름도_같은가": same_name,
                "clause": "내부 정합성(도면 자체 모순) — GMP 조항 아님",
                "판단": ("보류 · **발주처 확인 필요**. 설계사의 번호 오기로 보이나 "
                       "특별한 표기 관례일 수도 있다. 우리는 사실만 보고한다"),
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
    return evaluate(load_conflicts(cur, run_id), cfg)
