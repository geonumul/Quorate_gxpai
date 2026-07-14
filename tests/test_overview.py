# -*- coding: utf-8 -*-
"""설계개요 추출기 회귀 테스트 (T1.2.2). DB 없이 합성 표로 검증."""
from __future__ import annotations

import pytest

try:
    import ezdxf
    from ezdxf.enums import TextEntityAlignment
    HAVE_EZDXF = True
except ImportError:      # `except Exception` 이었다 - fixture 가 **고장나도**
    # "ezdxf 미설치"로 둔갑해 시험이 통째로 skip 되고 **초록불**이 떴다.
    # 못 불러오는 것(ImportError)만 건너뛴다. 그 외 오류는 터뜨린다.
    HAVE_EZDXF = False

from gxpai.ingest.extractors.overview import OverviewExtractor

# 자간 있는 키("공  사  명")도 공백 제거 후 매칭되는지 포함
_ROWS = [
    ("공  사  명", "내용고형제 증축", 0.0),
    ("연 면 적", "43,046.49㎡", -500.0),
    ("건폐율", "37.77%", -1000.0),
]
_PROFILE = {
    "overview": {
        "row_dy_mm": 200,
        "value_max_dx_mm": 12000,
        "keywords": ["공사명", "연면적", "건폐율", "대지면적"],
    }
}


@pytest.mark.skipif(not HAVE_EZDXF, reason="ezdxf 미설치")
def test_overview_keyvalue():
    doc = ezdxf.new("R2013", setup=True)
    msp = doc.modelspace()
    for key, val, y in _ROWS:
        msp.add_text(key, dxfattribs={"height": 200}).set_placement((0.0, y))
        msp.add_text(val, dxfattribs={"height": 200}).set_placement((4000.0, y))

    recs = OverviewExtractor().extract(doc, _PROFILE)
    got = {r.payload["key"]: r.payload["value"] for r in recs}

    assert got["공사명"] == "내용고형제 증축"   # 자간 키 정규화 매칭
    assert got["연면적"] == "43,046.49㎡"
    assert got["건폐율"] == "37.77%"
    assert "대지면적" not in got               # 없는 키는 나오면 안 됨
