# -*- coding: utf-8 -*-
"""검사(check) 입력용 순수 데이터 모델.

설계 의도: 규칙 판정 로직을 DB 커서에서 떼어내 '방 데이터만 받아 위반을 돌려주는'
순수 함수로 만든다. 그래야
  1) 합성 데이터로 DB 없이 빠르게 회귀 시험(T2.3.3),
  2) Stage 3 생성에서 '만든 배치가 규칙을 지키는지' 자기검증에 같은 함수를 재사용,
  3) 실제 도면 검사 결과는 그대로(변경 후에도 기준값 3/17 불변)
할 수 있다.

각 check 모듈은 두 층으로 나뉜다.
  - evaluate(...) : 순수 함수. RoomView 등 평범한 객체만 받는다(DB·psycopg 의존 없음).
  - run(cur, ...) : 얇은 DB 어댑터. 행을 읽어 evaluate 에 넘긴다.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoomView:
    """한 방(번호 기준 병합 엔티티)의 검사에 필요한 최소 뷰.

    모든 필드 선택적: 평면도에만 있는 방은 pressure_name 이 None,
    차압도에만 있는 방은 plan_x/plan_y 가 None 이다(LBL-002 판정 근거).
    grade(청정등급)는 Grade 도면 수령 전까지 None → grade 의존 규칙은 자연히 0건.
    """
    room_no: str | None = None
    name: str | None = None
    pressure_name: str | None = None
    floor: str | None = None
    grade: str | None = None
    plan_x: float | None = None
    plan_y: float | None = None
    # 아래 3개는 migration 007. 압력 규칙 재설계(PRES-001/002/003)에 필요하다.
    #   pressure_pa   : 도면에 표기된 절대 정압(Pa). 없으면 None → 수치 규칙은 조용히 건너뜀
    #   regime        : protect | contain | hazard | neutral (압력 방향 유형)
    #   regime_source : inferred | profile | drawing | manual (감사 추적)
    # regime 이 None 이면 검사 쪽에서 방 이름으로 **추정**한다(_regime.infer_regime).
    pressure_pa: float | None = None
    regime: str | None = None
    regime_source: str | None = None


@dataclass(frozen=True)
class PressureRel:
    """차압 관계 한 건: high 쪽이 low 쪽보다 고압이라는 방향.

    approx=True 는 화살표 기하만 있고 두 방 귀속이 확정되지 않은 원시 상태.
    room_high_no / room_low_no 가 채워져야(=방 귀속 확정) 규칙이 판정한다.

    아래 3개는 migration 008.
      head_deg    : 화살촉의 **세계 각도**(블록 기하에서 잰 값. 회전각 가정이 아니다).
                    None = 화살촉을 못 읽음 → 추측하지 않고 규칙이 건너뛴다.
      layer       : 화살표가 놓인 레이어. 이름이 곧 차압 설정값이다.
                    'Air Flow 10Pa' / 'Air Flow 15Pa' / 'Air Flow no차압'
      setpoint_pa : 레이어에서 읽은 목표 차압. None + layer 에 'no차압' →
                    **차압 기준이 없는 구간**(도면 범례 3번). 기준을 들이대면 거짓 위반이다.
    """
    room_high_no: str | None = None
    room_low_no: str | None = None
    approx: bool = False
    head_deg: float | None = None
    layer: str | None = None
    setpoint_pa: float | None = None
    # migration 010. 이 구간에 **차압계가 설치돼 있는가** (별표1 4-너)
    #   None = 차압계 도면이 없는 시설 → 판정 불가. "차압계가 없다"와 혼동하면 안 된다.
    has_gauge: bool | None = None
    gauge_kind: str | None = None


@dataclass(frozen=True)
class AdjPair:
    """인접한 두 방(번호).

    via_door: **문으로 이어졌는가**(동선). migration 009.
        True  = 문이 있다 → 사람이 오간다. ADJ-001(등급 급변)이 판정한다
        False = 벽만 맞댔다 → 오갈 수 없다. 동선 위반이 아니다
        None  = 문 데이터가 없는 도면 → 판정 불가. 벽 인접으로 폴백하되 근거에 남긴다
    """
    a: str
    b: str
    via_door: bool | None = None


def load_rooms(cur, run_id: str) -> list[RoomView]:
    """room 테이블에서 한 run 의 방들을 RoomView 로 적재."""
    cur.execute(
        """SELECT room_no, name, pressure_name, floor, grade, plan_x, plan_y,
                  pressure_pa, regime, regime_source
             FROM room WHERE run_id=%s""",
        (run_id,),
    )
    return [
        RoomView(room_no=r[0], name=r[1], pressure_name=r[2], floor=r[3],
                 grade=r[4], plan_x=r[5], plan_y=r[6],
                 pressure_pa=r[7], regime=r[8], regime_source=r[9])
        for r in cur.fetchall()
    ]


def load_pressure_rels(cur, run_id: str) -> list[PressureRel]:
    """pressure_relation(방 id) → 방번호로 변환해 적재.

    room_high/room_low 가 NULL 이면(현재 원시 상태) 방번호도 None → 규칙이 건너뛴다.
    """
    cur.execute(
        """SELECT rh.room_no, rl.room_no, pr.approx,
                  pr.head_deg, pr.layer, pr.setpoint_pa,
                  pr.has_gauge, pr.gauge_kind
             FROM pressure_relation pr
             LEFT JOIN room rh ON rh.id = pr.room_high
             LEFT JOIN room rl ON rl.id = pr.room_low
            WHERE pr.run_id=%s""",
        (run_id,),
    )
    return [PressureRel(room_high_no=r[0], room_low_no=r[1], approx=bool(r[2]),
                        head_deg=r[3], layer=r[4], setpoint_pa=r[5],
                        has_gauge=r[6], gauge_kind=r[7])
            for r in cur.fetchall()]


def load_adjacency(cur, run_id: str) -> list[AdjPair]:
    """room_adjacency(방 id 쌍) → 방번호 쌍으로 변환해 적재."""
    cur.execute(
        """SELECT ra.room_no, rb.room_no, adj.via_door
             FROM room_adjacency adj
             JOIN room ra ON ra.id = adj.room_a
             JOIN room rb ON rb.id = adj.room_b
            WHERE adj.run_id=%s""",
        (run_id,),
    )
    return [AdjPair(a=r[0], b=r[1], via_door=r[2]) for r in cur.fetchall()
            if r[0] is not None and r[1] is not None]
