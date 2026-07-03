# -*- coding: utf-8 -*-
"""추출기 공통 헬퍼 회귀 시험 (S-3 이름병합 · R-F1 앵커매칭 · 층판정).

이 헬퍼들은 방 추출 정확도의 핵심인데 직접 시험이 없었다. 리스크 문서가 지목한 함정
(여러 줄 이름, 정렬점, 위쪽 이름 관례)을 못박는다.
"""
from __future__ import annotations

from gxpai.ingest.extractors._common import (
    floor_from_number,
    match_name_to_anchor,
    merge_multiline_names,
)


# ---------------------------------------------------------------- S-3 여러 줄 병합
def test_two_line_name_merged_top_to_bottom():
    names = [(0, 800, "세척 후"), (0, 0, "기구보관실")]
    out = merge_multiline_names(names, max_dy=1000, max_dx=1200)
    assert len(out) == 1 and out[0][2] == "세척 후 기구보관실"


def test_three_line_chain_merged_in_order():
    names = [(0, 1600, "제1"), (0, 800, "제조"), (0, 0, "실")]
    out = merge_multiline_names(names, max_dy=1000, max_dx=1200)
    assert out[0][2] == "제1 제조 실"


def test_same_y_names_not_merged():
    # 나란히 있는(같은 y) 두 이름은 붙이면 안 됨 (0 < cy-y2 조건)
    names = [(0, 0, "충전실"), (5000, 0, "포장실")]
    out = merge_multiline_names(names, max_dy=1000, max_dx=100000)
    assert len(out) == 2


def test_far_dx_not_merged():
    names = [(0, 800, "위"), (5000, 0, "아래")]  # dx=5000 > max_dx
    out = merge_multiline_names(names, max_dy=1000, max_dx=1200)
    assert len(out) == 2


# ---------------------------------------------------------------- R-F1 앵커 매칭
def test_nearest_name_chosen():
    names = [(0, 100, "가까움"), (9000, 100, "멀다")]
    _i, name = match_name_to_anchor(0, 0, names, max_dist=6000)
    assert name == "가까움"


def test_name_above_preferred_over_below():
    # 위(관례)와 아래에 같은 거리 후보가 있으면 위를 고른다 (아래는 감점)
    names = [(0, 500, "위이름"), (0, -500, "아래이름")]
    _i, name = match_name_to_anchor(0, 0, names, max_dist=6000,
                                    above_max=2500, above_penalty=1500)
    assert name == "위이름"


def test_beyond_max_dist_returns_none():
    names = [(0, 9000, "너무멈")]
    assert match_name_to_anchor(0, 0, names, max_dist=6000) == (None, None)


# ---------------------------------------------------------------- 층 판정
def test_floor_from_number():
    m = {"1": "1F", "2": "2F", "3": "3F", "4": "4F"}
    assert floor_from_number("3301", m) == "3F"
    assert floor_from_number("4102", m) == "4F"
    assert floor_from_number(None, m) is None
    assert floor_from_number("9999", m) is None  # 매핑에 없는 첫자리
