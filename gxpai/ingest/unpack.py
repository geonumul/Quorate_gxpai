# -*- coding: utf-8 -*-
"""도면 등록 - DXF를 raw/ 로 복사하고 sha256 지문·종류를 산출.

로드맵: T1.1.1 / S1.1
입력은 zip(cp949 파일명) 또는 DXF 폴더 모두 허용. 원본은 절대 수정하지 않는다(A.2#2).
"""
from __future__ import annotations

import hashlib
import shutil
import zipfile
from pathlib import Path

# 파일명 키워드 → 도면 종류 (한/영 모두 인식; 구체적 키워드를 앞에 둔다)
_KIND_KEYWORDS = [
    ("PRESSURIZATION", "pressure"),
    ("차압", "pressure"),
    ("PRESSURE", "pressure"),
    ("HVAC", "hvac"),
    ("PLOT PLAN", "hvac"),
    ("설계개요", "overview"),
    ("OVERVIEW", "overview"),
    ("배치도", "siteplan"),
    ("SITE PLAN", "siteplan"),
    ("입면", "elevation"),
    ("ELEVATION", "elevation"),
    ("단면", "section"),
    ("SECTION", "section"),
    ("평면도", "floorplan"),
    ("FLOOR PLAN", "floorplan"),
    ("FLOORPLAN", "floorplan"),
    ("PLAN", "floorplan"),   # 남은 '*PLAN' 은 평면도로 (구체 키워드가 위에서 이미 걸러짐)
]


def detect_kind(filename: str) -> str:
    up = filename.upper()
    for kw, kind in _KIND_KEYWORDS:
        if kw.upper() in up:
            return kind
    return "unknown"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _collect_dxf(src: Path, workdir: Path) -> list[Path]:
    """zip 이면 해제, 폴더면 그대로 순회해 DXF 경로 목록 반환."""
    if src.is_dir():
        return sorted(src.rglob("*.dxf"))
    if src.suffix.lower() == ".zip":
        workdir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(src) as z:
            z.extractall(workdir)  # cp949 파일명은 zipfile 이 대체로 처리
        return sorted(workdir.rglob("*.dxf"))
    if src.suffix.lower() == ".dxf":
        return [src]
    raise ValueError(f"지원하지 않는 입력: {src}")


def register(src: Path, facility_id: str, raw_root: Path) -> list[dict]:
    """DXF를 raw/{facility_id}/ 로 복사하고 (filename, sha256, kind, path) 목록 반환."""
    dest_dir = raw_root / facility_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp = raw_root / f".unzip_{facility_id}"

    drawings = []
    for dxf in _collect_dxf(src, tmp):
        dest = dest_dir / dxf.name
        if dxf.resolve() != dest.resolve():
            shutil.copy2(dxf, dest)
        drawings.append({
            "filename": dxf.name,
            "sha256": sha256_of(dest),
            "kind": detect_kind(dxf.name),
            "path": str(dest),
        })
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    return drawings
