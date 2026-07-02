# -*- coding: utf-8 -*-
"""합성 미니 시설 DXF 생성기 (T1.3.2 온보딩 리허설용).

실제 시설과 '다른 레이어명 + 5자리 방번호'를 쓴다 - 프로파일만 바꿔서
코드 수정 0줄로 처리되는지 검증하기 위함. 아래 함정을 일부러 심는다:
  - 방이름을 가운데 정렬(MIDDLE_CENTER) 로 배치 → R-F1(정렬점) 검증
  - 두 줄로 쪼갠 방이름 → S-3(여러 줄 병합) 검증
  - 동결(frozen) 레이어의 유령 방번호 → S-10(frozen 제외) 검증
합성 데이터이므로 공개 리포에 포함 가능(고객정보 없음).
"""
from __future__ import annotations

from pathlib import Path

import ezdxf
from ezdxf.enums import TextEntityAlignment

ROOMS = [
    ("10101", "충전실"),
    ("10102", "포장실"),
    ("10103", "복도"),
    ("10104", "탈의실"),
    ("20101", "제조실"),
    ("20102", "세척실"),
]


def build(out_path: Path) -> Path:
    doc = ezdxf.new("R2013", setup=True)
    doc.header["$INSUNITS"] = 4  # mm
    msp = doc.modelspace()
    for name in ("RMNUM", "RMNAME", "EQP", "OLD_GHOST"):
        if name not in doc.layers:
            doc.layers.add(name)
    doc.layers.get("OLD_GHOST").freeze()  # 동결: 여기 글자는 무시되어야 함

    for i, (no, name) in enumerate(ROOMS):
        x = i * 5000.0
        y = 0.0
        # 방번호: 왼쪽 정렬(기본)
        msp.add_text(f"({no})", dxfattribs={"layer": "RMNUM", "height": 300}) \
            .set_placement((x, y))
        # 방이름: 번호 위쪽, 가운데 정렬 (R-F1 함정)
        msp.add_text(name, dxfattribs={"layer": "RMNAME", "height": 300}) \
            .set_placement((x, y + 800), align=TextEntityAlignment.MIDDLE_CENTER)

    # 두 줄로 쪼갠 이름 (S-3): "세척 후" / "기구보관실" → 방 10105 로 합쳐져야 함
    msp.add_text("(10105)", dxfattribs={"layer": "RMNUM", "height": 300}).set_placement((30000, 0))
    msp.add_text("세척 후", dxfattribs={"layer": "RMNAME", "height": 300}) \
        .set_placement((30000, 1100), align=TextEntityAlignment.MIDDLE_CENTER)
    msp.add_text("기구보관실", dxfattribs={"layer": "RMNAME", "height": 300}) \
        .set_placement((30000, 800), align=TextEntityAlignment.MIDDLE_CENTER)

    # 유령 방(S-10): 동결 레이어 - 추출되면 안 됨
    msp.add_text("(19999)", dxfattribs={"layer": "OLD_GHOST", "height": 300}).set_placement((99000, 0))
    msp.add_text("철거된방", dxfattribs={"layer": "OLD_GHOST", "height": 300}).set_placement((99000, 800))

    # 장비 2개
    msp.add_text("타정기", dxfattribs={"layer": "EQP", "height": 200}).set_placement((100, 100))
    msp.add_text("코팅기", dxfattribs={"layer": "EQP", "height": 200}).set_placement((5100, 100))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(out_path)
    return out_path


if __name__ == "__main__":
    p = build(Path(__file__).parent / "synth_facility" / "floorplan.dxf")
    print(f"합성 DXF 생성: {p}  (방 {len(ROOMS)+1}개 + 유령1 + 장비2)")
