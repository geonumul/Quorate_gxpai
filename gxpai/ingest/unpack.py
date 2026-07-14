# -*- coding: utf-8 -*-
"""도면 등록 - DXF를 raw/ 로 복사하고 sha256 지문, 종류를 산출.

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


def _dxf_paths(root: Path) -> list[Path]:
    """대소문자 무관하게 .dxf 파일 수집(Linux 등 대소문자 구분 FS 대비)."""
    return sorted(p for p in root.rglob("*")
                  if p.is_file() and p.suffix.lower() == ".dxf")


def _extract_zip(src: Path, workdir: Path) -> None:
    """cp949 파일명을 복원하며 해제. (예전 zipfile.extractall 은 UTF-8 플래그 없는
    한국 zip 을 cp437 로 디코드해 한글이 깨지고 → detect_kind 가 'unknown' 이 됐다.)"""
    workdir.mkdir(parents=True, exist_ok=True)
    root = workdir.resolve()
    with zipfile.ZipFile(src) as z:
        for info in z.infolist():
            name = info.filename
            if not (info.flag_bits & 0x800):          # UTF-8 아님 → cp437→cp949 재해석
                try:
                    name = name.encode("cp437").decode("cp949")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass
            target = (workdir / name).resolve()
            if not str(target).startswith(str(root)):  # path traversal 방어
                continue
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as s, open(target, "wb") as d:
                    shutil.copyfileobj(s, d)


def _collect_dxf(src: Path, workdir: Path) -> list[Path]:
    """zip 이면 해제, 폴더면 그대로 순회해 DXF 경로 목록 반환."""
    if src.is_dir():
        return _dxf_paths(src)
    if src.suffix.lower() == ".zip":
        _extract_zip(src, workdir)
        return _dxf_paths(workdir)
    if src.suffix.lower() == ".dxf":
        return [src]
    raise ValueError(f"지원하지 않는 입력: {src}")


def register(src: Path, facility_id: str, raw_root: Path) -> list[dict]:
    """DXF를 raw/{facility_id}/ 로 복사하고 (filename, sha256, kind, path) 목록 반환."""
    dest_dir = raw_root / facility_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp = raw_root / f".unzip_{facility_id}"

    drawings = []
    used: set[str] = set()
    for dxf in _collect_dxf(src, tmp):
        # 다른 하위폴더의 동명 파일(예: 3F/PLAN.dxf, 4F/PLAN.dxf)이 basename 으로 뭉개져
        # 도면이 유실되던 문제 방지 - 충돌 시 상위 폴더명을 붙여 구분한다.
        base = dxf.name
        if base in used:
            base = f"{dxf.parent.name}__{dxf.name}"
            i = 1
            while base in used:
                base = f"{dxf.parent.name}_{i}__{dxf.name}"
                i += 1
        used.add(base)
        dest = dest_dir / base
        if dxf.resolve() != dest.resolve():
            shutil.copy2(dxf, dest)
        drawings.append({
            "filename": base,
            "sha256": sha256_of(dest),
            "kind": detect_kind(base),
            "path": str(dest),
        })
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    return drawings
