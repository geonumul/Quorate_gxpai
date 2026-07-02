# -*- coding: utf-8 -*-
"""합성 시설 온보딩 회귀 테스트 (T1.3.2).

DB 없이 추출기만 검증한다(빠름, CI 친화). 코드 수정 0줄로 다른 레이어명/번호체계를
처리하는지 + 리스크 보완(R-F1 정렬점, S-3 여러줄, S-10 frozen)이 유효한지 지킨다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from gxpai.core.config import load_profile
from gxpai.ingest.extractors.floorplan import FloorplanExtractor

try:
    import ezdxf  # noqa: F401
    from tests.fixtures.synthetic.make_synth import build
    HAVE_EZDXF = True
except Exception:
    HAVE_EZDXF = False


@pytest.mark.skipif(not HAVE_EZDXF, reason="ezdxf 미설치")
def test_synthetic_onboarding(tmp_path):
    import ezdxf as _ezdxf
    dxf = build(tmp_path / "synth" / "floorplan.dxf")
    profile = load_profile("synth_demo")
    doc = _ezdxf.readfile(str(dxf))

    recs = FloorplanExtractor().extract(doc, profile)
    numbered = {r.payload["room_no"]: r.payload["name"]
                for r in recs if r.payload["room_no"]}

    # 7개 방, 5자리 번호
    assert set(numbered) == {"10101", "10102", "10103", "10104", "10105", "20101", "20102"}
    # R-F1: 가운데정렬 이름이 올바르게 매칭됨
    assert numbered["10101"] == "충전실"
    # S-3: 두 줄 이름 병합
    assert numbered["10105"] == "세척 후 기구보관실"
    # S-10: 동결 레이어의 유령 방번호는 없어야 함
    assert "19999" not in numbered
    # 층 자동판정
    floors = {r.payload["room_no"]: r.payload["floor"]
              for r in recs if r.payload["room_no"]}
    assert floors["10101"] == "1F" and floors["20101"] == "2F"
