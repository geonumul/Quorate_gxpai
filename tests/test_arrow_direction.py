# -*- coding: utf-8 -*-
"""차압 화살표 **방향 해석** 회귀 시험.

이 파일이 지키는 것: **화살표를 거꾸로 읽지 않는 것.**

  화살표를 거꾸로 읽으면 PRES-001(캐스케이드 역전), PRES-003(봉쇄 실패)이 **정반대**로 나온다.
  정상 시설을 위반이라 하고, 위반 시설을 정상이라 한다. 엔진에서 가장 위험한 오독이다.

실제로 두 번 당했다(둘 다 여기 시험으로 고정한다):
  ① 블록마다 화살촉 방향이 다른데 "화살촉은 -y" 라고 **가정**했다 → 28개 중 9개 반대
  ② 방을 붙일 때 축거리만 보고 **측면거리를 무시**했다 → 축에서 3m 벗어난 방을 골랐다

잡아낸 방법: 도면에는 **독립된 근거가 둘**(화살표 / 절대압력 Pa) 있고, 둘을 대조하면
"공기가 5Pa 방에서 10Pa 방으로 흐른다"는 물리적 불가능이 드러난다.
근거가 둘일 때는 **반드시 교차검증**한다.
"""
from __future__ import annotations

import math

from gxpai.ingest.arrowgeom import block_tip_local, head_deg
from gxpai.geometry.pressure_links import associate_by_head, associate_one


# ── 가짜 DXF (ezdxf 없이 기하 로직만 검증) ────────────────────────
class FakePoly:
    def __init__(self, pts, closed=True):
        self._pts, self.closed = pts, closed

    def dxftype(self):
        return "LWPOLYLINE"

    def get_points(self, _fmt):
        return self._pts


class FakeLine:
    def dxftype(self):
        return "LINE"


# 실제 도면에서 뜯어온 진짜 좌표다(참고도면 2층 차압흐름도).
BLK_15PA = [                       # 뾰족한 끝 (0,0), 꼬리 +x 쪽 → 화살촉 = -x
    FakePoly([(0.0, 0.0), (343.4, -260.2), (343.4, -156.4), (648.3, -156.4),
              (648.3, 0.0), (648.3, 154.5), (343.4, 154.5), (343.4, 258.3)]),
    FakeLine(),
]
BLK_ZW = [                         # 뾰족한 끝 (0,0), 꼬리 -x 쪽 → 화살촉 = +x  ← 정반대!
    FakePoly([(0.0, 0.0), (-429.2, 325.3), (-429.2, 195.5), (-810.3, 195.5),
              (-810.3, 0.0), (-810.3, -193.2), (-429.2, -193.2), (-429.2, -322.9)]),
]
BLK_NO = [                         # 뾰족한 끝이 원점이 아니다 (1338.7, 994.5) → 화살촉 = +x
    FakePoly([(1338.7, 994.5), (909.5, 1319.7), (909.5, 1190.0), (528.4, 1190.0),
              (528.4, 994.5), (528.4, 801.3), (909.5, 801.3), (909.5, 671.5)]),
]


def _unit(v):
    return (round(v[0], 2), round(v[1], 2))


def test_같은_도면_안에서_블록마다_화살촉이_정반대다():
    """핵심. 이 사실을 몰라서 9개를 거꾸로 읽었다.

    'Air Flow 15Pa' 와 'zw$E99B' 는 **같은 도면의 차압 화살표**인데
    로컬 화살촉 방향이 -x 와 +x 로 **정반대**다.
    그러니 "화살촉은 항상 ○○ 방향"이라는 가정은 어떤 값을 넣어도 절반은 틀린다.
    """
    assert _unit(block_tip_local(BLK_15PA)) == (-1.0, 0.0)
    assert _unit(block_tip_local(BLK_ZW)) == (1.0, 0.0)


def test_화살촉이_원점이_아니어도_찾는다():
    """'Air Flow no차압' 블록은 뾰족한 끝이 (1338,994) 다. 원점을 화살촉이라 가정하면 틀린다."""
    assert _unit(block_tip_local(BLK_NO)) == (1.0, 0.0)


def test_화살표가_아니면_None_을_돌려준다():
    """읽을 수 없으면 **추측해서 채우지 않는다.** None 이면 규칙이 그 화살표를 건너뛴다."""
    사각형 = [FakePoly([(0, 0), (10, 0), (10, 10), (0, 10)])]     # 뾰족한 데가 없다
    assert block_tip_local(사각형) is None
    assert block_tip_local([FakeLine()]) is None                   # 외곽선 자체가 없다
    열린선 = [FakePoly([(0, 0), (5, 5), (10, 0)], closed=False)]   # 닫히지 않았다
    assert block_tip_local(열린선) is None


# ── 세계 좌표 변환 (회전 + 거울반사) ──────────────────────────────
class FakeMatrix:
    """INSERT 의 matrix44 흉내: 축척(음수 가능) → 회전 → 이동."""

    def __init__(self, rot_deg, xs, ys, ox=0.0, oy=0.0):
        self.c, self.s = math.cos(math.radians(rot_deg)), math.sin(math.radians(rot_deg))
        self.xs, self.ys, self.ox, self.oy = xs, ys, ox, oy

    def transform(self, p):
        x, y = p[0] * self.xs, p[1] * self.ys
        return type("P", (), {"x": x * self.c - y * self.s + self.ox,
                              "y": x * self.s + y * self.c + self.oy})()


class FakeInsert:
    def __init__(self, rot, xs=1.0, ys=1.0):
        self._m = FakeMatrix(rot, xs, ys)

    def matrix44(self):
        return self._m


def test_회전을_반영한다():
    # 15Pa 블록(로컬 화살촉 -x)을 90° 돌리면 세계 화살촉은 -y = 270°
    assert round(head_deg(FakeInsert(90), BLK_15PA)) == 270
    # zw 블록(로컬 화살촉 +x)을 90° 돌리면 +y = 90°  ← 같은 회전각인데 정반대
    assert round(head_deg(FakeInsert(90), BLK_ZW)) == 90


def test_거울반사를_반영한다():
    """실제 도면의 화살표 일부는 xscale = -1.125 (좌우 뒤집힘)다.

    회전각만 보면 거울반사를 통째로 놓친다. matrix44 를 써야 잡힌다.
    """
    보통 = head_deg(FakeInsert(0, xs=1.125, ys=1.125), BLK_15PA)     # -x → 180°
    거울 = head_deg(FakeInsert(0, xs=-1.125, ys=1.125), BLK_15PA)    # 뒤집혀 +x → 0°
    assert round(보통) == 180
    assert round(거울) == 0
    # 실제 블록의 화살촉은 축에서 0.1° 쯤 기울어 있다(사람이 그린 도면이다).
    # 반대인지만 보면 된다 - 1° 안이면 같은 방향으로 친다.
    assert abs(abs(보통 - 거울) - 180) < 1.0


# ── 방 귀속: 측면거리 가중 ────────────────────────────────────────
def test_축에서_벗어난_방을_고르지_않는다():
    """실제 도면에서 잡은 오귀속.

    화살표 @(304885,47007) 꼬리쪽 후보:
        F2I20 무균 갱의실   축거리 1071, **측면 3040**
        F2I21 무균 전실     축거리 1075, **측면  460**   ← 정답
    축거리 차이는 **4mm** 인데 측면거리는 3m 차이다. 축거리만 보면 갱의실을 고른다.
    그러면 '무균 갱의실(40Pa) → 퇴실 전실(45Pa)' 이라는 **불가능한 관계**가 만들어진다.
    화살표는 문을 지나는 공기를 그린 것이니, 축에서 옆으로 벗어난 방은 상관이 없다.
    """
    # 화살촉이 +x(0°). 꼬리쪽(x<0) 후보 둘의 축거리는 거의 같고 측면거리만 다르다.
    rooms = [
        ("갱의실", -1071.0, 3040.0),    # 축거리 짧음(4mm 차), 측면 멀다
        ("전실",   -1075.0,  460.0),    # 축거리 약간 김, 측면 가깝다  ← 정답
        ("복도",    1681.0,  455.0),    # 화살촉 쪽
    ]
    tail, head = associate_by_head(0.0, 0.0, 0.0, rooms)
    assert tail == "전실"
    assert head == "복도"


def test_화살촉_각도를_그대로_쓴다_회전각_가정을_하지_않는다():
    """associate_by_head 는 세계 각도를 직접 받는다 - 회전각→방향 변환 가정이 없다."""
    rooms = [("아래", 0.0, -2000.0), ("위", 0.0, 2000.0)]
    # 화살촉이 +y(90°) → 위쪽이 head(저압), 아래쪽이 tail(고압)
    assert associate_by_head(0, 0, 90.0, rooms) == ("아래", "위")
    # 화살촉이 -y(270°) → 정확히 반대
    assert associate_by_head(0, 0, 270.0, rooms) == ("위", "아래")


def test_구_경로는_그대로_살아있다():
    """화살촉을 못 읽는 옛 도면(내용고형제)은 여전히 회전각 가정으로 폴백한다."""
    rooms = [("A", 0.0, -2000.0), ("B", 0.0, 2000.0)]
    # 옛 가정: rotation=0 → 화살촉 -y
    assert associate_one(0, 0, 0.0, rooms) == ("B", "A")


def test_한쪽에_방이_없으면_붙이지_않는다():
    """반대편 방을 못 찾으면 (None, None). 억지로 붙이지 않는다."""
    rooms = [("A", 0.0, 2000.0)]      # 화살촉 쪽만 있다
    assert associate_by_head(0, 0, 90.0, rooms) == (None, None)
