# -*- coding: utf-8 -*-
"""도면 unpack/registry 회귀 시험 (코드리뷰 CRITICAL #1, detect_kind).

DB 없이 파일시스템만으로 검증한다.
"""
from __future__ import annotations

import zipfile

from gxpai.ingest import unpack


def test_detect_kind_keyword_mapping():
    assert unpack.detect_kind("M0-014~015 PRESSURIZATION PLAN.dxf") == "pressure"
    assert unpack.detect_kind("차압도.dxf") == "pressure"
    assert unpack.detect_kind("A-201~207 평면도(증축후).dxf") == "floorplan"
    assert unpack.detect_kind("M0-007 HVAC PLOT PLAN.dxf") == "hvac"
    assert unpack.detect_kind("A-011 설계개요.dxf") == "overview"
    assert unpack.detect_kind("A-014 배치도.dxf") == "siteplan"
    assert unpack.detect_kind("random.dxf") == "unknown"


def test_register_keeps_same_basename_across_folders(tmp_path):
    """다른 하위폴더의 동명 DXF(3F/PLAN.dxf, 4F/PLAN.dxf)가 유실되지 않아야 한다(CRITICAL #1).
    예전엔 basename 으로 뭉개져 3층 도면(111방 중 51방)이 사라졌다."""
    zpath = tmp_path / "fac.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("3F/PLAN.dxf", b"dummy-3F")
        z.writestr("4F/PLAN.dxf", b"dummy-4F")
    raw = tmp_path / "raw"
    drawings = unpack.register(zpath, "f_test", raw)

    assert len(drawings) == 2                       # 둘 다 보존
    names = [d["filename"] for d in drawings]
    assert len(set(names)) == 2                     # 이름 충돌 없음
    dest = list((raw / "f_test").glob("*.dxf"))
    assert len(dest) == 2                            # 실제 파일도 둘 다 존재
    # 두 파일의 내용(지문)이 서로 다름 = 덮어쓰기 안 됨
    assert len({d["sha256"] for d in drawings}) == 2


def test_register_flat_names_unchanged(tmp_path):
    """동명 충돌이 없으면 filename 은 그대로(기존 동작 불변)."""
    zpath = tmp_path / "fac2.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("A-201 평면도.dxf", b"a")
        z.writestr("M0-014 차압도.dxf", b"b")
    drawings = unpack.register(zpath, "f_flat", tmp_path / "raw")
    names = sorted(d["filename"] for d in drawings)
    assert names == ["A-201 평면도.dxf", "M0-014 차압도.dxf"]
