# -*- coding: utf-8 -*-
"""평면도/차압도 방 병합(_merge) 회귀 시험.

_merge 는 번호방 111개(카나리아)를 만들어내는 핵심 로직인데 그동안 단위 시험이 없었다.
여기서 회귀가 나면 전 단계가 무너지므로 병합 규칙을 못박는다(DB 없이).
"""
from __future__ import annotations

from gxpai.core.run import _merge


def _fp(no, name, floor="3F", x=0.0, y=0.0):
    return {"room_no": no, "name": name, "floor": floor, "sheet": None,
            "plan_x": x, "plan_y": y, "source_drawing_id": "d_fp"}


def _pr(no, name, floor="3F", x=0.0, y=0.0):
    return {"room_no": no, "name": name, "floor": floor, "x": x, "y": y,
            "source_drawing_id": "d_pr"}


def _by_no(merged):
    return {m["room_no"]: m for m in merged if m.get("room_no")}


def test_room_in_both_drawings_merges_names_and_positions():
    merged = _by_no(_merge([_fp("3101", "충전실", x=10, y=20)],
                           [_pr("3101", "충전실", x=100, y=200)]))
    r = merged["3101"]
    assert r["name"] == "충전실"          # 이름은 평면도 기준
    assert r["pressure_name"] == "충전실"  # 차압도 이름 보존(LBL 비교용)
    assert (r["plan_x"], r["plan_y"]) == (10, 20)   # 평면도 좌표
    assert (r["pres_x"], r["pres_y"]) == (100, 200)  # 차압도 좌표(화살표 귀속용)


def test_floorplan_only_room_has_no_pressure():
    merged = _by_no(_merge([_fp("3102", "포장실", x=5, y=6)], []))
    r = merged["3102"]
    assert r["plan_x"] == 5 and r["pressure_name"] is None
    assert r.get("pres_x") is None       # 차압도에 없으니 pres 좌표 없음


def test_pressure_only_room_has_no_plan():
    merged = _by_no(_merge([], [_pr("3103", "세척실", x=7, y=8)]))
    r = merged["3103"]
    assert r["plan_x"] is None           # 평면도에 없음
    assert r["pressure_name"] == "세척실" and r["pres_x"] == 7


def test_pressure_fills_missing_name_and_floor():
    # 평면도에 번호는 있으나 이름/층이 비어있고, 차압도가 채운다
    fp = _fp("3104", None, floor=None)
    merged = _by_no(_merge([fp], [_pr("3104", "복도", floor="3F")]))
    r = merged["3104"]
    assert r["name"] == "복도"           # 평면도 이름이 None 이라 차압도로 채움
    assert r["floor"] == "3F"


def test_unnumbered_rooms_kept_by_position_key():
    # room_no None 인 무번호 공간도 (좌표 키로) 보존돼야 함
    merged = _merge([_fp(None, "복도", x=1, y=2), _fp(None, "샤프트", x=3, y=4)], [])
    unnum = [m for m in merged if not m.get("room_no")]
    assert len(unnum) == 2
    assert {m["name"] for m in unnum} == {"복도", "샤프트"}


def test_match_count_mirrors_canary_logic():
    # 평면도 2 ∩ 차압도 2 = 1 매칭 + 각 1개 단독 → 번호방 3개(양쪽매칭 1)
    fp = [_fp("3201", "A"), _fp("3202", "B")]
    pr = [_pr("3201", "A"), _pr("3203", "C")]
    merged = _by_no(_merge(fp, pr))
    both = [r for r in merged.values() if r["plan_x"] is not None and r["pressure_name"] is not None]
    assert set(merged) == {"3201", "3202", "3203"}
    assert [r["room_no"] for r in both] == ["3201"]   # 양쪽 존재 = 1
