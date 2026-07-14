# -*- coding: utf-8 -*-
"""설정 로딩 (.env + 프로파일 YAML).

로드맵: S1.1
외부 의존(python-dotenv) 없이 최소 구현. 모든 시설별 파라미터는 profiles/*.yaml 에서 읽는다.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml


@lru_cache
def repo_root() -> Path:
    """저장소 루트 (이 파일 기준 gxpai/core/ 에서 두 단계 위)."""
    return Path(__file__).resolve().parents[2]


def load_env() -> None:
    """루트의 .env 를 os.environ 에 주입 (기존 값은 덮지 않음)."""
    env = repo_root() / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip())


def load_profile(profile_id: str) -> dict:
    path = repo_root() / "profiles" / f"{profile_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"프로파일 없음: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def raw_dir() -> Path:
    """원본 DXF 폴더. GXPAI_RAW_DIR 이 절대경로면 그대로, 상대경로면 저장소 루트 기준.

    주의: 예전엔 .lstrip("./") 로 접두 제거를 시도했으나 lstrip 은 '문자 집합'을 벗겨
    "/data/raw"→"data/raw", "../x"→"x" 처럼 절대경로, 상위경로를 조용히 망가뜨렸다(수정됨).
    """
    p = Path(os.environ.get("GXPAI_RAW_DIR", "raw"))
    return p if p.is_absolute() else repo_root() / p
