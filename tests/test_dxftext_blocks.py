# -*- coding: utf-8 -*-
"""iter_label_texts 의 **블록 재귀** 회귀 시험.

★왜 이 기능이 필요했나 (실제로 당했다)
  새 참고도면은 방 라벨이 전부 **블록 안**에 있다
  (`2층평면도(260320)` 안에 TEXT: Grade 49 · RoomName 56 · ROOMNUMBER 51).
  모델스페이스만 훑던 예전 코드는 **아무것도 못 봤다** — 추출기 전체가 0건.
  CAD 도면은 블록 중첩이 기본이다(이 도면은 3단 중첩).

★깨뜨리면 안 되는 것
  기준 시설(내용고형제)의 라벨은 모델스페이스에 있다. 그 동작이 그대로여야 한다
  (기준값 111방 불변).
"""
from __future__ import annotations

import ezdxf

from gxpai.ingest.dxftext import iter_label_texts


def test_모델스페이스_텍스트는_그대로_읽는다():
    """기준 시설 방식. 회귀 방지."""
    doc = ezdxf.new()
    msp = doc.modelspace()
    doc.layers.add("RM")
    msp.add_text("3117", dxfattribs={"layer": "RM", "insert": (100, 200)})

    got = list(iter_label_texts(doc, ["RM"]))
    assert len(got) == 1
    x, y, t, _h = got[0]
    assert (round(x), round(y), t) == (100, 200, "3117")


def test_블록_안의_텍스트를_읽는다():
    """★새 참고도면 방식. 예전엔 0건이었다."""
    doc = ezdxf.new()
    doc.layers.add("ROOMNUMBER")
    blk = doc.blocks.new("ROOMLABEL")
    blk.add_text("F2I01", dxfattribs={"layer": "ROOMNUMBER", "insert": (10, 20)})

    doc.modelspace().add_blockref("ROOMLABEL", (1000, 2000))

    got = list(iter_label_texts(doc, ["ROOMNUMBER"]))
    assert len(got) == 1
    x, y, t, _h = got[0]
    assert t == "F2I01"
    # ★좌표가 **세계좌표로 변환**되어야 한다 (블록 로컬 10,20 + 삽입 1000,2000)
    assert (round(x), round(y)) == (1010, 2020)


def test_블록_중첩_3단도_읽는다():
    """실제 도면이 3단이었다: 2층평면도 → zw$F5F8 → 2층 평면 변경후."""
    doc = ezdxf.new()
    doc.layers.add("Grade")

    inner = doc.blocks.new("INNER")
    inner.add_text("(D)", dxfattribs={"layer": "Grade", "insert": (5, 5)})

    mid = doc.blocks.new("MID")
    mid.add_blockref("INNER", (100, 100))

    outer = doc.blocks.new("OUTER")
    outer.add_blockref("MID", (1000, 1000))

    doc.modelspace().add_blockref("OUTER", (10000, 10000))

    got = list(iter_label_texts(doc, ["Grade"]))
    assert len(got) == 1
    x, y, t, _h = got[0]
    assert t == "(D)"
    assert (round(x), round(y)) == (11105, 11105)      # 10000+1000+100+5


def test_블록_안_레이어0은_INSERT_레이어를_상속한다():
    """CAD 규칙. 실제 도면의 벽(97k LINE)이 전부 레이어 '0' 이었다."""
    doc = ezdxf.new()
    doc.layers.add("ARCH")
    blk = doc.blocks.new("B")
    blk.add_text("타정실", dxfattribs={"layer": "0", "insert": (0, 0)})   # 레이어 0
    doc.modelspace().add_blockref("B", (500, 500), dxfattribs={"layer": "ARCH"})

    # INSERT 의 레이어(ARCH)로 잡혀야 한다
    assert len(list(iter_label_texts(doc, ["ARCH"]))) == 1
    # 레이어 '0' 으로는 안 잡힌다(상속됐으므로)
    assert list(iter_label_texts(doc, ["0"])) == []


def test_블록_안_자기레이어가_있으면_그것을_쓴다():
    doc = ezdxf.new()
    doc.layers.add("ARCH")
    doc.layers.add("Grade")
    blk = doc.blocks.new("B2")
    blk.add_text("(C)", dxfattribs={"layer": "Grade", "insert": (0, 0)})
    doc.modelspace().add_blockref("B2", (0, 0), dxfattribs={"layer": "ARCH"})

    assert len(list(iter_label_texts(doc, ["Grade"]))) == 1
    assert list(iter_label_texts(doc, ["ARCH"])) == []


def test_꺼진_레이어의_블록은_건너뛴다():
    """S-10: 꺼진/동결 레이어의 '유령 방'이 살아나면 안 된다."""
    doc = ezdxf.new()
    lay = doc.layers.add("OLD")
    lay.off()
    blk = doc.blocks.new("B3")
    blk.add_text("유령방", dxfattribs={"layer": "OLD", "insert": (0, 0)})
    doc.modelspace().add_blockref("B3", (0, 0), dxfattribs={"layer": "OLD"})

    assert list(iter_label_texts(doc, ["OLD"])) == []


def test_스케일_회전된_블록도_좌표가_맞는다():
    doc = ezdxf.new()
    doc.layers.add("RM")
    blk = doc.blocks.new("B4")
    blk.add_text("A", dxfattribs={"layer": "RM", "insert": (10, 0)})
    doc.modelspace().add_blockref(
        "B4", (100, 100), dxfattribs={"xscale": 2, "yscale": 2, "rotation": 90})

    (x, y, t, _h) = list(iter_label_texts(doc, ["RM"]))[0]
    # (10,0) → 2배 → (20,0) → 90도 회전 → (0,20) → 이동 → (100,120)
    assert t == "A"
    assert (round(x), round(y)) == (100, 120)
