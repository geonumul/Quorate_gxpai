# -*- coding: utf-8 -*-
"""벽 선분 추출의 **블록 재귀** 회귀 시험.

같은 함정을 두 번 밟았다. 이 시험이 세 번째를 막는다.

  텍스트(dxftext)는 이미 블록 재귀로 고쳐 뒀는데, **벽(boundaries)은 안 고쳐 둔 채였다.**
  그 바람에 기준 시설 3층이 37방 중 **32방이 하나의 41,227㎡ 덩어리**로 뭉쳤다.

  나는 이걸 한참 동안 "벽이 안 그려져 있다"고 오진했다.
  문 블록으로 구멍을 막아 보고(+3방), 놓친 벽 레이어 `B-WAL` 을 찾아 넣어 보고(+3방)
  겨우 39/94 였다. **벽이 없어서가 아니라 벽을 못 보고 있었다.**
  블록 재귀 한 줄로 39 → **79/94** (3F 5→27, 4F 34→52).

교훈: CAD 도면에서 무언가 "없다"고 결론 내리기 전에, **블록 안을 봤는지** 먼저 확인하라.
"""
from __future__ import annotations

import ezdxf

from gxpai.geometry.boundaries import _iter_wall_segments


def test_모델스페이스_벽은_그대로_읽는다():
    doc = ezdxf.new()
    doc.layers.add("WALL")
    doc.modelspace().add_line((0, 0), (1000, 0), dxfattribs={"layer": "WALL"})

    segs = list(_iter_wall_segments(doc, ["WALL"]))
    assert segs == [(0.0, 0.0, 1000.0, 0.0)]


def test_블록_안의_벽을_읽는다():
    """핵심 회귀. 이걸 못 봐서 3층이 통째로 뭉쳤다."""
    doc = ezdxf.new()
    doc.layers.add("하니컴패널")
    blk = doc.blocks.new("3층평면")
    blk.add_line((0, 0), (1000, 0), dxfattribs={"layer": "하니컴패널"})
    doc.modelspace().add_blockref("3층평면", (5000, 7000))

    segs = list(_iter_wall_segments(doc, ["하니컴패널"]))
    assert len(segs) == 1
    # 좌표가 **세계좌표로 변환**되어야 한다
    assert segs[0] == (5000.0, 7000.0, 6000.0, 7000.0)


def test_블록_중첩도_따라간다():
    doc = ezdxf.new()
    doc.layers.add("WALL")
    inner = doc.blocks.new("INNER")
    inner.add_line((0, 0), (100, 0), dxfattribs={"layer": "WALL"})
    outer = doc.blocks.new("OUTER")
    outer.add_blockref("INNER", (1000, 0))
    doc.modelspace().add_blockref("OUTER", (10000, 0))

    segs = list(_iter_wall_segments(doc, ["WALL"]))
    assert segs == [(11000.0, 0.0, 11100.0, 0.0)]


def test_블록_안_레이어0은_INSERT_레이어를_상속한다():
    """CAD 규칙. 실제 도면의 선분 상당수가 레이어 '0' 이다."""
    doc = ezdxf.new()
    doc.layers.add("하니컴패널")
    blk = doc.blocks.new("B")
    blk.add_line((0, 0), (100, 0), dxfattribs={"layer": "0"})
    doc.modelspace().add_blockref("B", (0, 0), dxfattribs={"layer": "하니컴패널"})

    assert len(list(_iter_wall_segments(doc, ["하니컴패널"]))) == 1
    assert list(_iter_wall_segments(doc, ["0"])) == []      # 상속됐으므로 '0' 으론 안 잡힌다


def test_skip_blocks_로_특정_블록을_건너뛴다():
    """방 라벨 상자처럼 **벽이 아닌 것**이 벽 레이어에 얹혀 있으면 fill 이 라벨 안에 갇힌다.

    참고도면에서 실제로 당했다 - 51개 방이 전부 실패했다.
    """
    doc = ezdxf.new()
    doc.layers.add("ARCH")
    box = doc.blocks.new("라벨상자")
    box.add_line((0, 0), (100, 0), dxfattribs={"layer": "ARCH"})
    wall = doc.blocks.new("진짜벽")
    wall.add_line((0, 0), (500, 0), dxfattribs={"layer": "ARCH"})
    doc.modelspace().add_blockref("라벨상자", (0, 0))
    doc.modelspace().add_blockref("진짜벽", (0, 0))

    assert len(list(_iter_wall_segments(doc, ["ARCH"]))) == 2
    segs = list(_iter_wall_segments(doc, ["ARCH"], skip_blocks=["라벨상자"]))
    assert segs == [(0.0, 0.0, 500.0, 0.0)]


def test_회전한_블록의_벽도_바르게_변환된다():
    doc = ezdxf.new()
    doc.layers.add("WALL")
    blk = doc.blocks.new("B")
    blk.add_line((0, 0), (1000, 0), dxfattribs={"layer": "WALL"})
    doc.modelspace().add_blockref("B", (0, 0), dxfattribs={"rotation": 90})

    (x0, y0, x1, y1), = _iter_wall_segments(doc, ["WALL"])
    assert (round(x0), round(y0)) == (0, 0)
    assert (round(x1), round(y1)) == (0, 1000)      # +x 가 +y 로 돌았다
