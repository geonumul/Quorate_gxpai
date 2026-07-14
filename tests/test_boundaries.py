# -*- coding: utf-8 -*-
"""방 경계 flood-fill 회귀 시험 (합성 도면).

무엇을 지키려는가
  1) 벽으로 닫힌 방의 **면적**이 맞는가
  2) **인접**이 정확한가 (벽을 맞댄 방끼리만)
  3) **문틈으로 새지 않는가** - 이게 flood-fill 의 최대 실패 모드다.
     문 자리는 벽이 끊겨 있어서, 그대로 fill 하면 두 방이 하나로 합쳐진다.
  4) 벽이 안 닫힌 방은 **조용히 이상한 값을 넣지 말고 실패로 기록**하는가
"""
from __future__ import annotations

import ezdxf

from gxpai.geometry import boundaries

PROFILE = {"boundaries": {
    "wall_layers": ["WALL"],
    "door_layers": ["DOOR"],
    "cell_mm": 50,
    "close_gap_mm": 200,
    "max_area_m2": 500,
    "min_area_m2": 0.5,
}}


def _rect(msp, x0, y0, x1, y1, layer="WALL", gap=None):
    """사각 벽. gap=(변, 시작, 끝) 이면 그 구간을 비워 '문'을 만든다."""
    edges = [
        ("s", (x0, y0), (x1, y0)),
        ("e", (x1, y0), (x1, y1)),
        ("n", (x1, y1), (x0, y1)),
        ("w", (x0, y1), (x0, y0)),
    ]
    for side, a, b in edges:
        if gap and gap[0] == side:
            # 한 변을 두 토막으로 나눠 가운데를 비운다
            g0, g1 = gap[1], gap[2]
            if side in ("s", "n"):
                y = a[1]
                msp.add_line((a[0], y), (g0, y), dxfattribs={"layer": layer})
                msp.add_line((g1, y), (b[0], y), dxfattribs={"layer": layer})
            else:
                x = a[0]
                msp.add_line((x, a[1]), (x, g0), dxfattribs={"layer": layer})
                msp.add_line((x, g1), (x, b[1]), dxfattribs={"layer": layer})
        else:
            msp.add_line(a, b, dxfattribs={"layer": layer})


def test_닫힌_방_두개_면적과_인접():
    """벽을 맞댄 방 2개. 각 5m x 4m = 20㎡."""
    doc = ezdxf.new()
    msp = doc.modelspace()
    _rect(msp, 0, 0, 5000, 4000)          # R1
    _rect(msp, 5000, 0, 10000, 4000)      # R2 (벽 공유)
    rooms = [{"room_no": "R1", "plan_x": 2500, "plan_y": 2000},
             {"room_no": "R2", "plan_x": 7500, "plan_y": 2000}]

    res = boundaries.build(doc, rooms, PROFILE)
    got = {r.room_no: r.area_m2 for r in res.rooms}
    assert set(got) == {"R1", "R2"}
    for a in got.values():
        assert 17 <= a <= 20        # 벽 두께, 격자 오차 감안(정확히 20㎡ 는 안 나온다)
    assert sorted(res.adjacency[0]) == ["R1", "R2"]


def test_떨어진_방은_인접이_아니다():
    doc = ezdxf.new()
    msp = doc.modelspace()
    _rect(msp, 0, 0, 4000, 4000)
    _rect(msp, 20000, 0, 24000, 4000)     # 멀리 떨어짐
    rooms = [{"room_no": "R1", "plan_x": 2000, "plan_y": 2000},
             {"room_no": "R2", "plan_x": 22000, "plan_y": 2000}]
    res = boundaries.build(doc, rooms, PROFILE)
    assert len(res.rooms) == 2
    assert res.adjacency == []


def test_문틈으로_새지_않는다():
    """핵심 회귀.

    두 방 사이 벽에 900mm 문 구멍이 뚫려 있다. 문짝 선(DOOR 레이어)을 장벽으로 태우고
    close_gap 으로 나머지를 메워, **두 방이 하나로 합쳐지지 않아야** 한다.
    """
    doc = ezdxf.new()
    msp = doc.modelspace()
    _rect(msp, 0, 0, 5000, 4000, gap=("e", 1500, 2400))       # 오른쪽 벽에 문
    _rect(msp, 5000, 0, 10000, 4000, gap=("w", 1500, 2400))   # 맞은편도 같은 자리
    # 문짝 선 (닫힌 상태)
    msp.add_line((5000, 1500), (5000, 2400), dxfattribs={"layer": "DOOR"})

    rooms = [{"room_no": "R1", "plan_x": 2500, "plan_y": 2000},
             {"room_no": "R2", "plan_x": 7500, "plan_y": 2000}]
    res = boundaries.build(doc, rooms, PROFILE)

    got = {r.room_no: r.area_m2 for r in res.rooms}
    assert set(got) == {"R1", "R2"}, f"두 방이 합쳐졌다: {res.failed}"
    # 합쳐졌다면 면적이 40㎡ 근처가 된다. 각각 20㎡ 근처여야 한다.
    for a in got.values():
        assert a < 25, f"문틈으로 새어 면적이 커졌다: {got}"
    assert sorted(res.adjacency[0]) == ["R1", "R2"]   # 붙어 있으니 인접은 맞다


def test_벽이_안_닫히면_버리고_기록한다():
    """벽 한 변이 통째로 없으면 **도면 전체로 번진다** → 조용히 넣지 말고 failed 에 남긴다.

    ※격자 범위는 도면 요소들의 바운딩 박스로 잡힌다. 그래서 이 시험은
      **실제 도면처럼 넓은 도면**이어야 의미가 있다(멀리 떨어진 방을 하나 더 둔다).
      좁은 합성 도면이면 새어나가도 갈 데가 없어 면적이 안 커진다 - 처음에 그렇게 만들었다가
      시험이 통과해버렸다(가짜 통과).
    """
    doc = ezdxf.new()
    msp = doc.modelspace()
    # 'ㄷ' 자 - 오른쪽 벽 없음 → 바깥 자유공간으로 새어나간다
    msp.add_line((0, 0), (5000, 0), dxfattribs={"layer": "WALL"})
    msp.add_line((0, 4000), (5000, 4000), dxfattribs={"layer": "WALL"})
    msp.add_line((0, 0), (0, 4000), dxfattribs={"layer": "WALL"})
    # 멀리 떨어진 정상 방 - 도면 범위를 넓혀 '바깥'을 크게 만든다
    _rect(msp, 60000, 0, 64000, 4000)

    rooms = [{"room_no": "OPEN", "plan_x": 2500, "plan_y": 2000},
             {"room_no": "OK", "plan_x": 62000, "plan_y": 2000}]

    prof = {"boundaries": dict(PROFILE["boundaries"], max_area_m2=100)}
    res = boundaries.build(doc, rooms, prof)

    got = {r.room_no for r in res.rooms}
    assert "OPEN" not in got, "벽이 안 닫힌 방을 그대로 넣으면 안 된다"
    assert "OK" in got, "정상 방은 그대로 나와야 한다"
    assert any("벽이 안 닫힘" in f for f in res.failed)


def test_틈메우기가_크면_작은방을_삼킨다():
    """실제 도면에서 당한 버그.

    close_gap 을 900mm 로 뒀더니 **무균 전실, 갱의실 6개가 통째로 사라졌다**
    (라벨이 '벽 픽셀' 위에 얹힘 = 방이 벽에 먹혔다).
    전실은 원래 2~4㎡ 로 작다. 900mm 닫기는 벽을 양쪽으로 450mm 씩 두껍게 만들어 방을 지운다.
    → close_gap 은 **작게**(틈만 메울 만큼) 잡아야 한다.
    """
    doc = ezdxf.new()
    msp = doc.modelspace()
    _rect(msp, 0, 0, 1600, 1600)          # 작은 전실 (1.6m x 1.6m = 2.56㎡)
    # ※도면을 넓게 만든다. 좁으면 '바깥 영역'이 작아서, 방이 먹혔을 때
    #   _seed 가 바깥을 방으로 착각해 잡는다(가짜 통과). 실제 도면 조건을 흉내낸다.
    _rect(msp, 40000, 0, 44000, 4000)
    rooms = [{"room_no": "AL", "plan_x": 800, "plan_y": 800}]

    prof = dict(PROFILE["boundaries"], min_area_m2=0.8, max_area_m2=50)

    # 큰 close_gap → 방이 벽에 먹힌다 (바깥은 max_area 초과라 후보가 안 된다)
    big = {"boundaries": dict(prof, close_gap_mm=900)}
    assert boundaries.build(doc, rooms, big).rooms == [], "큰 close_gap 이 작은 방을 삼켜야(=재현)"

    # 작은 close_gap → 살아난다
    small = {"boundaries": dict(prof, close_gap_mm=200)}
    got = boundaries.build(doc, rooms, small).rooms
    assert len(got) == 1 and 1.5 <= got[0].area_m2 <= 2.6


def test_인접반경은_틈메우기와_분리된다():
    """close_gap 을 줄이면(작은 방을 살리려고) 인접까지 같이 줄어들던 문제.

    두 값은 요구가 정반대다:
      close_gap  작아야 좋다 (크면 작은 방을 삼킨다)
      adj_gap    커야 좋다   (벽 두께를 건너뛰어야 인접이 잡힌다)
    실제 도면에서 close_gap=200 으로 방 51개를 다 찾고도 인접이 9쌍뿐이었다.
    """
    doc = ezdxf.new()
    msp = doc.modelspace()
    _rect(msp, 0, 0, 5000, 4000)
    _rect(msp, 5400, 0, 10400, 4000)      # 400mm 두께 벽을 사이에 둔 두 방
    rooms = [{"room_no": "R1", "plan_x": 2500, "plan_y": 2000},
             {"room_no": "R2", "plan_x": 7900, "plan_y": 2000}]

    base = dict(PROFILE["boundaries"], close_gap_mm=200)

    # adj_gap(반경)이 벽 두께(400mm)보다 작으면 못 건너뛴다 → 인접 0
    narrow = boundaries.build(doc, rooms, {"boundaries": dict(base, adj_gap_mm=50)})
    assert len(narrow.rooms) == 2 and narrow.adjacency == []

    # 반경을 벽 두께 이상으로 주면 잡힌다
    wide = boundaries.build(doc, rooms, {"boundaries": dict(base, adj_gap_mm=500)})
    assert len(wide.rooms) == 2
    assert sorted(wide.adjacency[0]) == ["R1", "R2"]


def test_wall_layers_미설정이면_사유를_남긴다():
    doc = ezdxf.new()
    res = boundaries.build(doc, [], {"boundaries": {}})
    assert res.rooms == [] and "wall_layers" in res.failed[0]


def test_라벨_좌표_없으면_사유를_남긴다():
    doc = ezdxf.new()
    doc.modelspace().add_line((0, 0), (1000, 0), dxfattribs={"layer": "WALL"})
    res = boundaries.build(doc, [{"room_no": "R1"}], PROFILE)
    assert res.rooms == [] and res.failed
