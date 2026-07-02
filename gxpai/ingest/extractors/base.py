# -*- coding: utf-8 -*-
"""BaseExtractor - 도면종류별 추출기 플러그인 인터페이스.

로드맵: T1.1.2
계약: extract(doc, profile) -> list[Record]
  - doc: ezdxf.Document (원본 불변 - 절대 수정 금지, 원칙 A.2#2)
  - profile: dict (레이어명·거리상수 등 모든 시설별 파라미터. 하드코딩 금지)
새 도면종류 지원 = 이 클래스를 상속한 파일 1개 추가. 코드 배포 없이 profile YAML로 시설 확장.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Record:
    """추출기가 반환하는 정규화 레코드 1건 (kind별로 payload 구조가 다름)."""

    kind: str                       # room | pressure | equipment | ahu | ...
    payload: dict[str, Any]
    source_drawing: str | None = None
    confidence: float | None = None   # Stage 4 학습 루프 대비
    meta: dict[str, Any] = field(default_factory=dict)


class BaseExtractor(ABC):
    """모든 추출기의 부모. 하위 클래스는 `kind`와 `extract`만 구현하면 된다."""

    #: 이 추출기가 담당하는 도면 종류 (registry/CLI에서 dispatch 키로 사용)
    kind: str = ""

    @abstractmethod
    def extract(self, doc: "Any", profile: dict) -> list[Record]:
        """DXF 문서와 프로파일을 받아 정규화 레코드 리스트를 반환한다."""
        raise NotImplementedError
