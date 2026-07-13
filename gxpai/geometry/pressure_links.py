# -*- coding: utf-8 -*-
"""차압 화살표 ↔ 방 귀속 + **압력 방향 해석**.

로드맵: T2.1 후속. docs/기존데이터_분석.md 가설 2·3의 우회로를 파이프라인에 반영.

각 화살표에 대해 차압도 방 라벨(같은 좌표계) 중 화살촉이 향하는 쪽(head)과 꼬리 쪽(tail)을
찾아 pressure_relation.room_head / room_tail 에 저장한다. 이것은 **도면에서 읽은 사실**이다.

## S-1(화살표 의미) — **확정됨 (2026-07-13)**
    **화살촉 = 저압 쪽 = 공기가 흘러가는 방향.**  (공기는 고압에서 저압으로 흐른다)
    → `room_high = room_tail` · `room_low = room_head`

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


def head_vector(rotation_deg: float) -> tuple[float, float]:
    th = math.radians(270.0 + rotation_deg)
    return math.cos(th), math.sin(th)


def associate_one(ax: float, ay: float, rotation_deg: float,
                  rooms: list[tuple], max_dist: float = MAX_DIST,
                  max_lat: float = MAX_LAT):
    """화살표 하나에 대해 (tail_key, head_key) 반환. 못 붙이면 (None, None).

    rooms: (key, x, y) 목록. key 는 room_no(테스트) 또는 room id(DB) 무엇이든 됨.
    head = 화살촉이 향하는 쪽(투영 +), tail = 꼬리 쪽(투영 -).
    """
    hx, hy = head_vector(rotation_deg)
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
        # 화살표는 인접한 두 방 사이에 있으므로, 각 방향에서 가장 '가까운'(작은 |proj|) 방을 고른다.
        # (예전엔 가장 먼 방을 골라, 화살표 원뿔 안에 방이 3개 이상일 때 엉뚱한 방을 붙였다.)
        if proj > 0 and (head_s is None or proj < head_s):
            head_key, head_s = key, proj
        elif proj < 0 and (tail_s is None or -proj < tail_s):
            tail_key, tail_s = key, -proj
    if head_key is not None and tail_key is not None and head_key != tail_key:
        return tail_key, head_key
    return None, None


def build(run_id: str) -> int:
    """pressure_relation 각 화살표에 room_head/room_tail 을 채운다. 귀속 성공 수 반환."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT id, pres_x, pres_y FROM room
               WHERE run_id=%s AND room_no IS NOT NULL
                     AND pres_x IS NOT NULL AND pres_y IS NOT NULL""",
            (run_id,),
        )
        rooms = [(r[0], r[1], r[2]) for r in cur.fetchall()]

        cur.execute(
            "SELECT id, evidence_x, evidence_y, rotation FROM pressure_relation WHERE run_id=%s",
            (run_id,),
        )
        arrows = cur.fetchall()  # (id, ex, ey, rot)

        n = 0
        for pr_id, ex, ey, rot in arrows:
            tail_id, head_id = associate_one(ex, ey, rot or 0.0, rooms)
            # ★S-1 확정(2026-07-13): 화살촉 = 저압 쪽, 꼬리 = 고압 쪽.
            #   예전엔 이 해석을 미뤄 room_high/room_low 를 NULL 로 뒀고,
            #   그 바람에 차압관계 98개가 있어도 **방 귀속 확정 0건**이라 PRES 규칙이 전부 죽었다.
            #   근거 4중 확인(모듈 docstring 참조). approx=false 로 표시해 규칙이 판정하게 한다.
            linked = head_id is not None and tail_id is not None
            cur.execute(
                """UPDATE pressure_relation
                      SET room_head=%s, room_tail=%s,
                          room_high=%s, room_low=%s, approx=%s
                    WHERE id=%s""",
                (head_id, tail_id, tail_id, head_id, not linked, pr_id),
            )
            if head_id is not None and tail_id is not None:
                n += 1
        conn.commit()
        return n
