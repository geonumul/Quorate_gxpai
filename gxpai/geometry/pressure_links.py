# -*- coding: utf-8 -*-
"""차압 화살표 ↔ 방 귀속 + **압력 방향 해석**.

로드맵: T2.1 후속. docs/기존데이터_분석.md 가설 2, 3의 우회로를 파이프라인에 반영.

각 화살표에 대해 차압도 방 라벨(같은 좌표계) 중 화살촉이 향하는 쪽(head)과 꼬리 쪽(tail)을
찾아 pressure_relation.room_head / room_tail 에 저장한다. 이것은 **도면에서 읽은 사실**이다.

## S-1(화살표 의미) — **확정됨 (2026-07-13)**
    **화살촉 = 저압 쪽 = 공기가 흘러가는 방향.**  (공기는 고압에서 저압으로 흐른다)
    → `room_high = room_tail`, `room_low = room_head`

확정 근거 4중:
  ① 1차 미팅(2026-07-09) 대표님: "바람은 높은 데서 낮은 데로"
  ② 새 참고도면 범례: 화살표 종류별 차압 설정값 명시(10~15Pa / 5~10Pa / 불필요)
  ③ 도면의 절대압력(Pa)과 대조: 5Pa 탈의실 → 0Pa 복도 등 일치
  ④ DXF 원본에 **회전각(0/90/180/270)** 으로 존재 — 추측이 아니라 데이터
  ⑤ 2010 시설기준 안내서 p.23 Cascade 구조

**예전에는 이 해석을 일부러 하지 않았다**(room_high/room_low 를 NULL 로 두었다).
그 결과 차압관계 98개가 있어도 **방 귀속 확정 0건**이라 PRES 규칙이 전부 판정 불가였다.
이제 근거가 갖춰졌으므로 채운다. 상세: 법규/조문근거_색인.md A절.

구조: associate() 는 순수 함수(DB 무관, 합성 시험 대상), build() 는 DB 어댑터.
화살표 기하: rotation=0 에서 화살촉 -y, 세계각도 = 270° + rotation.
"""
from __future__ import annotations

import math

from ..core.db import connect

MAX_DIST = 6000.0   # 방 라벨 탐색 반경(mm)
MAX_LAT = 3500.0    # 화살표 축에서 벗어난 측면거리 허용(mm)
# 후보를 고를 때 측면거리에 주는 가중치. 축거리보다 **측면거리가 더 중요하다** —
# 화살표는 문을 지나는 공기를 그린 것이므로, 그 축에서 옆으로 벗어난 방은 관계가 없다.
LAT_WEIGHT = 2.0


def head_vector(rotation_deg: float) -> tuple[float, float]:
    th = math.radians(270.0 + rotation_deg)
    return math.cos(th), math.sin(th)


def associate_by_head(ax: float, ay: float, head_deg: float,
                      rooms: list[tuple], max_dist: float = MAX_DIST,
                      max_lat: float = MAX_LAT):
    """현재 경로. 화살촉 **세계 각도**(블록 기하에서 잰 값)로 방을 붙인다.

    associate_one() 과 달리 회전각→방향 가정을 하지 않는다.
    """
    th = math.radians(head_deg)
    return _associate(ax, ay, math.cos(th), math.sin(th), rooms, max_dist, max_lat)


def associate_one(ax: float, ay: float, rotation_deg: float,
                  rooms: list[tuple], max_dist: float = MAX_DIST,
                  max_lat: float = MAX_LAT):
    """구(舊) 경로 — 회전각으로부터 방향을 **가정**한다. 화살촉을 못 읽었을 때만 쓴다.

    [주의] 이 가정("rotation=0 이면 화살촉 -y")이 참고도면에서 9건을 거꾸로 읽게 했다.
      블록 기하가 읽히는 도면에서는 associate_by_head() 를 써야 한다.
    """
    hx, hy = head_vector(rotation_deg)
    return _associate(ax, ay, hx, hy, rooms, max_dist, max_lat)


def _associate(ax: float, ay: float, hx: float, hy: float,
               rooms: list[tuple], max_dist: float, max_lat: float):
    """화살표 하나에 대해 (tail_key, head_key) 반환. 못 붙이면 (None, None).

    rooms: (key, x, y) 목록. key 는 room_no(테스트) 또는 room id(DB) 무엇이든 됨.
    head = 화살촉이 향하는 쪽(투영 +), tail = 꼬리 쪽(투영 -).
    """
    head_key = tail_key = None
    head_s = tail_s = None
    for key, rx, ry in rooms:
        if rx is None or ry is None:
            continue
        dx, dy = rx - ax, ry - ay
        if math.hypot(dx, dy) > max_dist:
            continue
        if abs(dx * -hy + dy * hx) > max_lat:   # 측면거리(축 수직 성분)
            continue
        proj = dx * hx + dy * hy
        lat = abs(dx * -hy + dy * hx)
        # 후보 점수 = |축거리| + LAT_WEIGHT × 측면거리.
        #
        #   예전엔 |proj| 만 봤다(축 방향으로 가장 가까운 방). 실제 도면에서 이게 깨졌다:
        #     화살표 @(304885,47007) 꼬리쪽 후보
        #       F2I20 무균 갱의실   proj=-1071  측면=3040   ← 이걸 골랐다
        #       F2I21 무균 전실     proj=-1075  측면= 460   ← 정답
        #     축거리 차이가 **4mm** 인데 측면거리는 3m 나 차이 났다.
        #     축에서 3m 벗어난 방은 그 문을 지나는 공기와 상관이 없다.
        #
        #   결과: '무균 갱의실(40Pa) → 퇴실 전실(45Pa)' 이라는 물리적으로 불가능한 관계를
        #   만들어 냈다(공기가 저압에서 고압으로 흐를 수 없다). 절대압력과 대조해 잡았다.
        cost = abs(proj) + LAT_WEIGHT * lat
        if proj > 0 and (head_s is None or cost < head_s):
            head_key, head_s = key, cost
        elif proj < 0 and (tail_s is None or cost < tail_s):
            tail_key, tail_s = key, cost
    if head_key is not None and tail_key is not None and head_key != tail_key:
        return tail_key, head_key
    return None, None


def build(run_id: str) -> int:
    """pressure_relation 각 화살표에 room_head/room_tail 을 채운다. 귀속 성공 수 반환."""
    with connect() as conn, conn.cursor() as cur:
        # 차압도 좌표(pres_x/y)가 없으면 평면도 좌표(plan_x/y)로 폴백한다.
        #   기준 시설은 평면도와 차압도가 **다른 파일**이라 좌표계가 달라 pres_x 를 따로 뒀다.
        #   그런데 새 참고도면은 **평면도와 차압도가 한 장**이다 → pres_x 가 NULL 이라
        #   화살표가 방에 하나도 안 붙었다(귀속 0건). 도면 구성은 시설마다 다르다.
        cur.execute(
            """SELECT id,
                      COALESCE(pres_x, plan_x) AS x,
                      COALESCE(pres_y, plan_y) AS y
                 FROM room
                WHERE run_id=%s AND room_no IS NOT NULL
                      AND COALESCE(pres_x, plan_x) IS NOT NULL
                      AND COALESCE(pres_y, plan_y) IS NOT NULL""",
            (run_id,),
        )
        rooms = [(r[0], r[1], r[2]) for r in cur.fetchall()]

        # head_deg = 블록 기하에서 **잰** 세계 각도. rotation 은 폴백(옛 데이터용).
        #   예전엔 rotation 만 보고 "화살촉 = -y" 라 가정했다가 28개 중 9개를 거꾸로 읽었다.
        #   (블록마다 화살촉 방향이 ±x 로 정반대였고 일부는 xscale 음수로 거울반사)
        cur.execute(
            """SELECT id, evidence_x, evidence_y, rotation, head_deg
                 FROM pressure_relation WHERE run_id=%s""",
            (run_id,),
        )
        arrows = cur.fetchall()  # (id, ex, ey, rot, head_deg)

        n = 0
        for pr_id, ex, ey, rot, hdeg in arrows:
            guessed = False
            if hdeg is not None:
                tail_id, head_id = associate_by_head(ex, ey, hdeg, rooms)
            else:
                # 화살촉을 못 읽었다 → **추측한다. 그러나 확정으로 표시하지 않는다.**
                #
                #   예전엔 옛 가정(`associate_one`)으로 추측해 놓고 `approx=False`(확정)로
                #   기록했다. 그 가정은 **참고도면에서 28개 중 9개를 거꾸로 읽게 한 바로 그것**이다.
                #   PRES 규칙은 approx=false 만 판정하므로, **추측한 방향으로 위반/합격을 냈다.**
                #
                #   arrowgeom 모듈이 스스로 적어 뒀다 — *"그런 화살표는 판정 대상에서 빼야지,
                #   추측해 채우면 안 된다."* 파이프라인이 그 원칙을 어기고 있었다.
                #
                #   → 추측값은 참고용으로만 두고 **approx=true** 로 표시한다. 규칙이 건너뛴다.
                tail_id, head_id = associate_one(ex, ey, rot or 0.0, rooms)
                guessed = True
            # S-1 확정(2026-07-13): 화살촉 = 저압 쪽, 꼬리 = 고압 쪽.
            #   예전엔 이 해석을 미뤄 room_high/room_low 를 NULL 로 뒀고,
            #   그 바람에 차압관계 98개가 있어도 **방 귀속 확정 0건**이라 PRES 규칙이 전부 죽었다.
            #   근거 4중 확인(모듈 docstring 참조). approx=false 로 표시해 규칙이 판정하게 한다.
            linked = head_id is not None and tail_id is not None
            # 추측한 방향(head_deg 를 못 읽음)은 **확정이 아니다.** approx=true.
            approx = (not linked) or guessed
            cur.execute(
                """UPDATE pressure_relation
                      SET room_head=%s, room_tail=%s,
                          room_high=%s, room_low=%s, approx=%s
                    WHERE id=%s""",
                (head_id, tail_id, tail_id, head_id, approx, pr_id),
            )
            if linked and not guessed:
                n += 1
        conn.commit()
        return n
