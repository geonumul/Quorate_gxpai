# -*- coding: utf-8 -*-
"""**커버리지 0% 였던 두 모듈**을 시험으로 덮는다. 신규 (2026-07-14).

전수 감사에서 나왔다. 둘 다 중요한데 시험이 **하나도** 없었다:

    gxpai/core/grade_zones.py          → 110개 방의 **등급을 정한다**
    gxpai/compliance/checks/pres_004.py → **도면 내부 모순**을 잡는 자기점검 규칙

## grade_zones - 등급은 도면에 **없는 게 정상이다**

우리는 오랫동안 "등급 0건 = 도면 결함 = 최대 병목"이라고 문서에 써 왔다. **틀렸다.**
1차 미팅(2026-07-09) 대표님:

    "방마다 (등급을) 하지는 않고 **구역**으로 해요. 'a부터 b까지는 그레이드 B'
     이렇게 해 주면 AI가 알아서 하는 거지."
    "내용고형제는 기본이 **D** 예요."
    "일반 사무 공간, 거기는 차압 관리 안 해요. **공조를 안 해요.**"

→ 순서: 도면 표기 → 사람이 지정한 구역 → 제형 기본값.
  **복도, 기계실 등 관리 외 구역은 등급을 주지 않는다**(None 으로 둔다).
  0 이나 'NC' 로 채우면 "등급이 없다"가 "등급이 최하다"로 둔갑한다.

## PRES-004 - 두 근거가 어긋나면 **우리 버그일 수도 있다**

화살표(고압→저압)와 도면에 적힌 절대압력(Pa)은 **서로 독립된 두 근거**다.
어긋나면 셋 중 하나다: 화살표가 틀렸거나, 압력 수치가 틀렸거나, **우리가 잘못 읽었거나.**
그래서 이 규칙은 도면 검사이면서 동시에 **우리 엔진의 자기점검**이다.
"""
from __future__ import annotations

from gxpai.compliance.checks._model import PressureRel, RoomView
from gxpai.compliance.checks import pres_004
from gxpai.core.grade_zones import _expand, apply_grade_zones, grade_from_product


# ══════════════════════════════════════════════ grade_zones
def test_제형이_기본등급을_정한다():
    """대표님: "내용고형제는 기본이 D 예요.\""""
    assert grade_from_product("내용고형제") == "D"
    assert grade_from_product("주사제") == "B"
    assert grade_from_product(None) is None       # 모르면 정하지 않는다


def test_복도와_기계실은_등급을_주지_않는다():
    """**가장 중요한 시험.** 대표님: "일반 사무 공간, 거기는 차압 관리 안 해요."

    복도, 기계실에 D 를 주면 ADJ(등급 급변), PRES(캐스케이드) 규칙이 **거짓 위반을 쏟아낸다**
    - 관리하지도 않는 공간을 청정실 취급하기 때문이다."""
    rooms = [
        {"room_no": "3101", "name": "타정실"},
        {"room_no": "3102", "name": "복도"},
        {"room_no": "3103", "name": "기계실"},
        {"room_no": "3104", "name": "창고"},
    ]
    counts = apply_grade_zones(rooms, {"product_type": "내용고형제"})

    by_no = {r["room_no"]: r for r in rooms}
    assert by_no["3101"]["grade"] == "D"          # 작업소 → 제형 기본값
    assert by_no["3101"]["grade_source"] == "product_default"
    assert by_no["3102"].get("grade") is None, "복도에 등급을 줬다 - 거짓 위반이 쏟아진다"
    assert by_no["3103"].get("grade") is None, "기계실에 등급을 줬다"
    assert counts["none"] >= 2


def test_사람이_지정한_구역이_제형기본값을_이긴다():
    """예외 구역만 사람이 지정한다. 지정한 건 반드시 이겨야 한다."""
    rooms = [{"room_no": "3101", "name": "무균 충전실"},
             {"room_no": "3102", "name": "타정실"}]
    apply_grade_zones(rooms, {
        "product_type": "내용고형제",             # 기본 D
        "grade_zones": {"B": ["3101"]},          # 그런데 3101 만 B
    })
    assert rooms[0]["grade"] == "B" and rooms[0]["grade_source"] == "zone"
    assert rooms[1]["grade"] == "D" and rooms[1]["grade_source"] == "product_default"


def test_도면_표기가_가장_세다():
    """도면에 등급이 적혀 있으면 그게 사실이다. 추정으로 덮어쓰지 않는다."""
    rooms = [{"room_no": "3101", "name": "타정실", "grade": "C"}]
    apply_grade_zones(rooms, {"product_type": "내용고형제",
                              "grade_zones": {"B": ["3101"]}})
    assert rooms[0]["grade"] == "C"               # 구역 지정(B)보다 도면(C)이 세다
    assert rooms[0]["grade_source"] == "drawing"


def test_제형을_모르면_등급을_지어내지_않는다():
    """모르는 걸 채우면 안 된다. 이 프로젝트에서 반복해 밟은 함정이다."""
    rooms = [{"room_no": "3101", "name": "타정실"}]
    apply_grade_zones(rooms, {})                  # product_type 없음
    assert rooms[0].get("grade") is None


def test_구역_범위_표기를_편다():
    assert _expand(["4401", "4402"]) == {"4401", "4402"}
    assert _expand({"from": "4401", "to": "4403"}) == {"4401", "4402", "4403"}
    # 섞어 써도 된다
    got = _expand(["4401", {"from": "4501", "to": "4502"}])
    assert got == {"4401", "4501", "4502"}


# ══════════════════════════════════════════════ PRES-004
def _rooms(pa_hi, pa_lo):
    return [RoomView(room_no="3101", name="타정실", pressure_pa=pa_hi),
            RoomView(room_no="3102", name="복도", pressure_pa=pa_lo)]


def _rel(approx=False):
    return PressureRel(room_high_no="3101", room_low_no="3102", approx=approx)


def test_pres004_화살표와_압력이_어긋나면_잡는다():
    """화살표는 3101 → 3102 로 흐른다는데, 적힌 압력은 3101 이 **더 낮다**.
    공기는 낮은 쪽으로만 흐른다 - 둘 중 하나가 틀렸다."""
    v = pres_004.evaluate([_rel()], _rooms(pa_hi=5.0, pa_lo=15.0), {})
    assert len(v) == 1
    assert v[0]["rooms"] == ["3101", "3102"]
    assert "모순" in v[0]["message"]


def test_pres004_일치하면_위반이_아니다():
    assert pres_004.evaluate([_rel()], _rooms(pa_hi=15.0, pa_lo=5.0), {}) == []


def test_pres004_동압은_위반이_아니다():
    """같은 압력이면 모순이 아니다(문이 열려 있는 등 정상 상황)."""
    assert pres_004.evaluate([_rel()], _rooms(pa_hi=10.0, pa_lo=10.0), {}) == []


def test_pres004_추측한_화살표는_판정하지_않는다():
    """`approx=True` = 화살촉을 못 읽어 **추측한** 방향이다.

    예전엔 추측해 놓고 approx=False(확정)로 기록했다. 그 가정이 참고도면에서
    28개 중 9개를 거꾸로 읽게 한 바로 그것이다. 추측으로 위반을 내면 안 된다."""
    assert pres_004.evaluate([_rel(approx=True)], _rooms(5.0, 15.0), {}) == []


def test_pres004_근거가_하나면_대조할_게_없다():
    """절대압력이 없으면 **판정 불가**다. '위반 없음'이 아니다.

    이 규칙은 **두 근거를 대조**한다. 하나가 없으면 대조 자체가 성립하지 않는다.
    (`[]` vs `None` 함정 - '정보가 없다'를 '문제가 없다'로 바꾸면 안 된다)"""
    assert pres_004.evaluate([_rel()], _rooms(pa_hi=None, pa_lo=15.0), {}) == []
    assert pres_004.evaluate([_rel()], _rooms(pa_hi=5.0, pa_lo=None), {}) == []


def test_pres004_같은_방쌍은_한_번만_보고한다():
    """화살표가 여러 개라도 같은 방 쌍은 한 건이다."""
    v = pres_004.evaluate([_rel(), _rel(), _rel()], _rooms(5.0, 15.0), {})
    assert len(v) == 1
