# -*- coding: utf-8 -*-
"""LBL-002 — **'차압도에 있는가'는 이름이 아니라 좌표로 판단한다** 회귀 시험.

## 전수 재검증에서 잡은 버그. 하마터면 거짓 위반 51건이 DB에 남을 뻔했다.

LBL-002 는 "평면도, 차압도 **한쪽에만** 있는 방"을 찾는다. 그런데 존재 여부를
**`pressure_name` 유무**로 판단하고 있었다.

참고도면 2층의 차압도에는 **방번호는 51개 있는데 이름이 없다**(RM 레이어에 번호만).
→ 51개 방을 전부 "차압도에 없음"으로 찍었다. **거짓 위반 51건.**

게다가 LBL 은 `review: internal` 이라 **게이트가 열려 있어 DB에 실제로 적재됐다.**
(PRES/ADJ 는 잠겨 있어 안전했지만 LBL 은 아니었다)

**이름이 없는 것과 방이 없는 것은 다르다.** 이름 불일치는 LBL-001 이 따로 본다.

## 왜 못 잡았나 — **미리보기만 돌리고 validate 를 안 돌렸다**

`scripts/preview_rules.py` 는 PRES/ADJ 만 본다. LBL 은 안 본다.
참고도면에 **실제 파이프라인(validate)을 한 번도 안 돌려봤다.**
→ 규칙을 미리보기로만 검증하지 말 것. **실제 파이프라인도 돌려볼 것.**
"""
from __future__ import annotations

from gxpai.compliance.checks import lbl_002
from gxpai.compliance.checks._model import RoomView


def test_차압도에_이름이_없어도_방이_있으면_위반이_아니다():
    """핵심. 차압도에 방번호만 있고 이름이 없는 도면(참고도면 2층)."""
    rooms = [RoomView(room_no="F2I01", name="탈의실(남)",
                      plan_x=100.0, pres_x=100.0, pressure_name=None)]
    assert lbl_002.evaluate(rooms) == []


def test_차압도에_진짜_없으면_위반():
    rooms = [RoomView(room_no="3117", name="방", plan_x=100.0,
                      pres_x=None, pressure_name=None)]
    v = lbl_002.evaluate(rooms)
    assert len(v) == 1 and v[0]["evidence"]["in"] == "floorplan_only"


def test_평면도에_없고_차압도에만_있으면_위반():
    rooms = [RoomView(room_no="4901", pressure_name="공조실", plan_x=None, pres_x=50.0)]
    v = lbl_002.evaluate(rooms)
    assert len(v) == 1 and v[0]["evidence"]["in"] == "pressure_only"


def test_옛_데이터는_이름으로_폴백한다():
    """pres_x 가 없는 옛 run 은 예전대로 pressure_name 으로 판단한다(하위호환)."""
    있음 = [RoomView(room_no="3117", plan_x=1.0, pres_x=None, pressure_name="타정실")]
    assert lbl_002.evaluate(있음) == []
    없음 = [RoomView(room_no="3117", plan_x=1.0, pres_x=None, pressure_name=None)]
    assert len(lbl_002.evaluate(없음)) == 1


# ── 평면도와 차압도가 같은 파일이면 대조 자체가 무의미하다 ────────────
def test_같은_파일이면_경고한다():
    """참고도면은 평면도와 차압도가 **바이트 단위로 같은 파일**이다(sha256 일치).

    차압 화살표가 평면도 **위에 겹쳐진** 구성이라 시트가 하나다.
    그런데도 LBL 이 "0건"을 내면 읽는 사람은 **"대조했더니 깨끗하다"** 로 오해한다.
    0건의 뜻은 "위반 없음"이 아니라 **"대조할 게 없음"** 이다.
    """
    from gxpai.core.run import _same_source_warning

    같음 = [{"kind": "floorplan", "sha256": "abc"}, {"kind": "pressure", "sha256": "abc"}]
    w = _same_source_warning(같음)
    assert w and "같은 파일" in w and "판정 불가" in w

    다름 = [{"kind": "floorplan", "sha256": "abc"}, {"kind": "pressure", "sha256": "xyz"}]
    assert _same_source_warning(다름) is None

    # 도면이 하나뿐이면 경고할 게 없다
    assert _same_source_warning([{"kind": "floorplan", "sha256": "abc"}]) is None
