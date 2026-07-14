# -*- coding: utf-8 -*-
"""HVAC-001 — **환기 횟수는 자사 기준서로 판정한다** 회귀 시험.

## 대표님이 "제일 중요"하다고 하신 것 (1차 미팅 2026-07-09)

> "**제일 중요한 게 환기 횟수**라는 개념이 있어요. 1시간에 몇 번 순환해야 된다는
>  **조건이 꼭 있거든요.** … **풍량을 환기횟수에 맞게 주고**, 차압을 맞추기 위해 빼 나가는 거예요"

## ⚠★그런데 **법정 수치로 판정하지 않는다**

수치(A 600회/hr · B 20회/hr)는 **구 KGMP 해설서**에만 있다.
**현행 고시(별표1)에는 환기 횟수 수치가 없다** — '환기' 언급 6건을 전수 확인했고
전부 EO 멸균 등 다른 맥락이었다.

→ **차압(PRES-002)과 똑같이 간다.** 실사관은 "법정 수치를 지켰나"가 아니라
  **"당신 회사가 정한 기준을 지켰나"** 를 본다.

한때 나는 "그러니 규칙을 아예 만들지 않는다"고 했다. **반만 맞았다.**
법정 수치를 박지 않는 건 옳지만, **자사 기준 기반 규칙은 만들어야 한다.**
"""
from __future__ import annotations

import pathlib

from gxpai.compliance.checks import hvac_001
from gxpai.compliance.checks._model import RoomView

SPEC = {"enabled": True, "ceiling_height_m": 2.7,
        "ach_by_grade": {"A": 600, "B": 40, "C": 25, "D": 15}}


def _room(no, grade, cmh, area):
    return RoomView(room_no=no, name=f"{no}실", grade=grade,
                    airflow_cmh=cmh, area_m2=area)


def test_자사_기준에_못_미치면_위반():
    # 30㎡ × 2.7m = 81㎥. C 등급 기준 25회 → 2,025 CMH 필요. 1,500 밖에 없다
    v = hvac_001.evaluate([_room("R1", "C", 1500.0, 30.0)], SPEC)
    assert len(v) == 1
    assert v[0]["evidence"]["required"] == 25
    assert v[0]["evidence"]["ach"] < 25


def test_자사_기준을_채우면_위반_아님():
    assert hvac_001.evaluate([_room("R1", "C", 2200.0, 30.0)], SPEC) == []


def test_자사_기준이_없으면_판정하지_않는다():
    """★★가장 중요하다. **법정 수치를 대신 쓰지 않는다.**

    기준서가 없다고 'A는 600회/hr' 를 갖다 쓰면, **근거 없는 관행을 법인 것처럼**
    판정하는 것이다. 현행 고시에는 그 수치가 없다.
    """
    없음 = {"enabled": True, "ceiling_height_m": 2.7}          # ach_by_grade 없음
    assert hvac_001.evaluate([_room("R1", "C", 100.0, 30.0)], 없음) == []


def test_천장고가_없으면_판정하지_않는다():
    """환기 횟수 = 풍량 ÷ (면적 × **천장고**). 천장고를 추측해 채우지 않는다."""
    없음 = {"enabled": True, "ach_by_grade": {"C": 25}}        # ceiling_height_m 없음
    assert hvac_001.evaluate([_room("R1", "C", 100.0, 30.0)], 없음) == []


def test_기준에_없는_등급은_건너뛴다():
    assert hvac_001.evaluate([_room("R1", "CNC", 10.0, 30.0)], SPEC) == []


def test_풍량이나_면적이_없으면_건너뛴다():
    assert hvac_001.evaluate([_room("R1", "C", None, 30.0)], SPEC) == []
    assert hvac_001.evaluate([_room("R1", "C", 100.0, None)], SPEC) == []


def test_법정_수치를_규칙_파일에_박아넣지_않았나():
    """★설계 결정을 고정한다.

    누군가 `ach_by_grade: {A: 600, B: 20}` 를 규칙 파일의 **기본값**으로 넣으려 하면
    이 시험이 막는다. 그건 **구 KGMP 해설서**이지 현행 법이 아니다.
    발주처 자사 기준서가 와야 채운다.
    """
    rules = pathlib.Path("rules/gmp_osd_v1.yaml").read_text(encoding="utf-8")
    i = rules.find("id: HVAC-001")
    assert i > 0
    block = rules[i:i + 2500]
    # 주석(#)이 아닌 실제 설정으로 수치가 들어가 있으면 안 된다
    for line in block.splitlines():
        st = line.strip()
        if st.startswith("#"):
            continue
        assert "ach_by_grade:" not in st, (
            "환기 기준을 규칙 파일에 박아 넣었다. 구 KGMP 해설서 수치를 법으로 "
            "착각한 것이 아닌지 확인하라. 발주처 자사 기준서가 와야 채운다.")
        assert "ceiling_height_m:" not in st, "천장고는 발주처가 줘야 한다"
