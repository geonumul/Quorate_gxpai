# -*- coding: utf-8 -*-
"""**단위계 검사**와 **장벽 기하 타입** 시험. 신규 (2026-07-14).

전수 감사에서 나온 두 가지 **조용한** 결함을 고정한다.

## ① 단위계($INSUNITS)를 아무도 확인하지 않았다

우리 코드는 **전부 mm 를 가정한다**(격자 50mm · 탐색반경 6,000mm · 면적 ㎡).
미터 단위 도면이 오면 **1000배 어긋난다** — 그런데 예외도 안 나고 0건도 아니다.
**그럴듯하게 틀린 숫자**가 조용히 DB 에 들어간다. 그게 제일 나쁘다.

우리가 가진 도면 3장이 전부 INSUNITS=4(mm) 라 **운이 좋았을 뿐이다.**

## ② 벽 기하 타입 4종을 조용히 버렸다

emit() 이 LINE·LWPOLYLINE·ARC **3종만** 다뤘다. POLYLINE·CIRCLE·SPLINE·ELLIPSE 는
아무 말 없이 사라졌다.

★처음엔 "88,356 개가 버려진다"고 썼다가 **재 보고 정정했다.** 그건 문서 전체 개수다
  (SPLINE 51,883 · CIRCLE 27,954 …). 대부분 가구·조경이라 레이어 필터에서 이미 걸러진다.
  **벽/문 레이어 위**에서 실제로 버려지던 건 **ELLIPSE 32 · POLYLINE 22 = 54개**다.

  작지만 진짜 손실이다. 그리고 이 도면이 마침 그럴 뿐이다 — POLYLINE 은
  **구형 폴리라인**(LWPOLYLINE 이전 표기)이라, 벽을 이걸로 그리는 사무소가 오면
  **벽이 통째로 사라진다.** 그래도 예외 하나 안 난다.
"""
from __future__ import annotations

import pytest

ezdxf = pytest.importorskip("ezdxf")

from gxpai.core.run import check_units                       # noqa: E402
from gxpai.geometry.boundaries import (BARRIER_TYPES_DEFAULT,  # noqa: E402
                                       _GEOM_TYPES, _iter_wall_segments)


def _doc(insunits: int | None):
    d = ezdxf.new("R2010")
    if insunits is not None:
        d.header["$INSUNITS"] = insunits
    return d


# ── 단위계 ───────────────────────────────────────────────────────
def test_밀리미터는_통과한다():
    assert check_units(_doc(4), "a.dxf") is None


@pytest.mark.parametrize("code,말", [(6, "미터"), (1, "인치"), (2, "피트"), (5, "센티미터")])
def test_mm이_아니면_경고한다(code, 말):
    """★미터 도면은 방 경계가 통째로 뭉치거나 면적이 백만 배가 된다.
    예외가 안 나므로 **경고하지 않으면 아무도 모른다.**"""
    w = check_units(_doc(code), "a.dxf")
    assert w is not None, f"$INSUNITS={code}({말}) 인데 경고가 없다 — 조용히 틀린다"
    assert 말 in w


def test_단위_미지정은_막지_않되_알린다():
    """INSUNITS=0('단위 없음')은 드물지 않다. 막으면 멀쩡한 도면을 거부한다.
    → 통과시키되 **경고는 남긴다**(좌표 크기로 상식성을 따로 확인하라)."""
    w = check_units(_doc(0), "a.dxf")
    assert w is not None and "지정되지" in w


def test_실도면_3장은_전부_밀리미터다():
    """기준 시설·참고도면·MAS UNIT. 이게 깨지면 그 도면 처리 결과를 **전부 의심해야** 한다."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    files = [
        root / "raw/f_1ae3a266/A-201~207 평면도(증축후).dxf",
        root / "raw/f_84e33f88/floorplan.dxf",
    ]
    seen = 0
    for f in files:
        if not f.exists():
            continue
        seen += 1
        assert check_units(ezdxf.readfile(str(f)), f) is None, \
            f"{f.name} 이 mm 가 아니다 — 이 도면의 면적·경계·귀속을 전부 의심하라"
    if seen == 0:
        pytest.skip("실도면이 없다(raw/ 미배치)")


# ── 장벽 기하 타입 ───────────────────────────────────────────────
def test_기본_장벽타입에_구형_POLYLINE이_들어있다():
    """★LWPOLYLINE 은 있는데 **POLYLINE 이 빠져 있었다.**
    이름이 비슷해 다 되는 줄 알았다 — 실제로는 완전히 다른 엔티티다."""
    assert "POLYLINE" in BARRIER_TYPES_DEFAULT
    assert "LWPOLYLINE" in BARRIER_TYPES_DEFAULT


def test_못_다룬_타입은_세어서_알린다():
    """★핵심. **조용히 버리지 않는다.**

    CIRCLE·SPLINE 은 기본값에서 꺼져 있다(이 도면에선 벽이 아니라 가구·기호였다).
    끄는 건 괜찮다 — 그러나 **몇 개를 껐는지는 반드시 알아야 한다.**
    다른 사무소 도면에서 벽이 SPLINE 이면 이 카운터가 유일한 단서다."""
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_line((0, 0), (1000, 0))
    msp.add_circle((500, 500), 100)
    msp.add_circle((900, 900), 100)

    dropped: dict[str, int] = {}
    segs = list(_iter_wall_segments(doc, ["*"], barrier_types=("LINE",),
                                    unsupported=dropped))
    assert len(segs) == 1                       # LINE 만 태웠다
    assert dropped == {"CIRCLE": 2}, \
        "끈 타입의 개수를 세지 않으면 벽이 사라져도 아무도 모른다"


def test_켠_타입은_실제로_장벽이_된다():
    """CIRCLE 을 켜면 선분으로 풀려 장벽이 되어야 한다(현 오차 FLATTEN_MM)."""
    doc = ezdxf.new("R2010")
    doc.modelspace().add_circle((0, 0), 1000)

    dropped: dict[str, int] = {}
    segs = list(_iter_wall_segments(doc, ["*"], barrier_types=("CIRCLE",),
                                    unsupported=dropped))
    assert len(segs) > 8, "원이 선분으로 안 풀렸다"
    assert not dropped


def test_구형_POLYLINE도_장벽이_된다():
    """구형 POLYLINE(vertices 방식). LWPOLYLINE 과 코드 경로가 다르다."""
    doc = ezdxf.new("R2010")
    doc.modelspace().add_polyline2d([(0, 0), (1000, 0), (1000, 1000)])

    dropped: dict[str, int] = {}
    segs = list(_iter_wall_segments(doc, ["*"], barrier_types=("POLYLINE",),
                                    unsupported=dropped))
    assert len(segs) == 2, f"구형 폴리라인이 안 풀렸다 (선분 {len(segs)}개)"
    assert not dropped


def test_다룰_수_있는_타입_목록이_기본값을_포함한다():
    """기본값에 오타가 있으면 그 타입이 **영원히 안 켜진다** — 조용히."""
    for t in BARRIER_TYPES_DEFAULT:
        assert t in _GEOM_TYPES, f"{t} 는 emit() 이 못 다루는 타입이다(오타?)"


# ── 블록 제외 문법 통일 ──────────────────────────────────────────
def test_블록제외는_정규식과_부분문자열을_둘다_받는다():
    """★같은 개념인데 **문법이 두 가지**였다:

        label_exclude_blocks: "기둥"          ← 정규식 문자열 (dxftext)
        boundaries.skip_blocks: ["B2026…"]   ← 부분문자열 리스트 (blockwalk)

    `skip_blocks: ["기둥.*"]` 라고 쓰면 정규식으로 안 돌고 **조용히 아무것도 안 걸린다.**
    프로파일 작성자가 반드시 틀리는 함정이다. → 이제 둘 다 받는다."""
    from gxpai.ingest.blockwalk import block_skipper

    assert block_skipper("기둥")(["기둥-A1"][0])           # 정규식 문자열
    assert block_skipper(["기둥"])("기둥-A1")               # 리스트 + 부분문자열
    assert block_skipper(["기둥.*"])("기둥-A1")             # 리스트 + 정규식
    assert block_skipper("^COL")("COL-1")                   # 앵커 정규식
    assert not block_skipper("기둥")("방라벨")
    assert not block_skipper(None)("무엇이든")


def test_AutoCAD_익명블록_이름에_터지지_않는다():
    """★AutoCAD 익명 블록은 `*U12` · `*D5` 꼴이다.
    그대로 `re.compile` 하면 `nothing to repeat` 로 **터진다.**
    예전 dxftext 는 정규식만 받았으므로 이 이름을 제외 목록에 넣으면 죽었다."""
    from gxpai.ingest.blockwalk import block_skipper

    skip = block_skipper(["*U12", "*D5"])       # 컴파일 실패 → 리터럴로 강등
    assert skip("*U12")
    assert not skip("기둥")


# ── 정규식 캡처 그룹 방어 ────────────────────────────────────────
def test_캡처그룹_없는_방번호_정규식에_죽지_않는다():
    """★프로파일에 `room_no_regex: '^\d{4}$'`(그룹 없음)라고 쓰면
    `m.group(1)` 이 **IndexError 로 추출기를 죽였다.**

    pressure.py 는 이걸 방어해 뒀는데 floorplan·grades·pressure_value 는 **뚫려 있었다.**
    같은 방어를 한 곳에만 해 두면 나머지는 반드시 터진다."""
    from gxpai.ingest.extractors.floorplan import FloorplanExtractor

    doc = ezdxf.new("R2010")
    doc.layers.add("RM")
    msp = doc.modelspace()
    msp.add_text("3101", dxfattribs={"layer": "RM"}).set_placement((0, 0))
    msp.add_text("타정실", dxfattribs={"layer": "RM"}).set_placement((0, -300))

    prof = {
        "label_entity_types": ["TEXT", "MTEXT"],
        "floors": {},
        "floorplan": {
            "room_layers": ["RM"],
            "room_no_regex": r"^\d{4}$",       # ← **캡처 그룹이 없다**
            "bare_no_regex": r"^\d{4}$",
            "max_match_dist_mm": 2000,
        },
    }
    recs = FloorplanExtractor().extract(doc, prof)      # 예전엔 여기서 IndexError
    assert any(r.payload.get("room_no") == "3101" for r in recs)


# ── 문 호(arc)의 거울반사 ────────────────────────────────────────
def _door_sweep(doc):
    """door_swing 이 실제로 훑는 각도. `(a1 - a0) % 360` — **늘 반시계**다."""
    import math

    from gxpai.geometry.door_barriers import iter_door_arcs

    out = []
    for c, p0, p1 in iter_door_arcs(doc, ["DOOR"]):
        a0 = math.degrees(math.atan2(p0[1] - c[1], p0[0] - c[0])) % 360
        a1 = math.degrees(math.atan2(p1[1] - c[1], p1[0] - c[0])) % 360
        out.append(round((a1 - a0) % 360.0))
    return out


def _door_doc(xscale: float):
    doc = ezdxf.new("R2010")
    doc.layers.add("DOOR")
    blk = doc.blocks.new("DOOR_90")
    blk.add_arc(center=(0, 0), radius=900, start_angle=0, end_angle=90,
                dxfattribs={"layer": "DOOR"})
    doc.modelspace().add_blockref(
        "DOOR_90", (0, 0),
        dxfattribs={"layer": "DOOR", "xscale": xscale, "yscale": 1.0})
    return doc


def test_거울반사된_문도_90도로_읽힌다():
    """★★**화살촉에서 당한 것과 똑같은 함정.**

    DXF 의 ARC 는 **항상 반시계**로 start→end 다. 그런데 거울반사(xscale<0)된 블록
    안에서는 세계좌표 기준으로 **시계방향**이 된다.

    door_swing 은 `(a1 - a0) % 360` 으로 **늘 반시계**로 훑는다.
    → 거울반사된 90° 문이 **270° 부채꼴**로 뒤집혀 검사된다.
      문이 지나가지도 않는 반대편에서 기둥을 찾아내 **거짓 "못 열림"** 을 낸다.

    (차압 화살표에서 이미 이 함정으로 28개 중 9개를 거꾸로 읽었다)
    """
    assert _door_sweep(_door_doc(1.0)) == [90]
    assert _door_sweep(_door_doc(-1.0)) == [90], \
        "거울반사된 문이 270° 로 뒤집혔다 — 반대편 부채꼴을 검사하게 된다"
