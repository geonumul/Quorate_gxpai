# -*- coding: utf-8 -*-
"""급기 풍량(CMH) 추출 회귀 시험.

## 이 파일이 지키는 가장 중요한 것: **환기 횟수(ACH) 규칙을 만들지 않는다**

수치(Class 100(A) **600회/hr**, Class 10,000(B) **20회/hr**)는
「GMP 조사평가 매뉴얼」이 인용한 **구 KGMP 해설서**에만 있다.

**현행 고시(별표1, 2023 개정, PIC/S Annex 1 기반)에는 환기 횟수 수치가 없다.**
별표1의 '환기' 언급 6건을 전수 확인했는데 전부 **EO 멸균 환기** 등 다른 맥락이었다.
현행은 **오염관리전략(CCS)** 으로 타당성을 입증하게 한다.

수치를 박아 넣으면 **근거 없는 관행을 법인 것처럼** 판정하는 것이다. **하지 않는다.**

→ 풍량은 **데이터로만 적재**한다. 규칙이 켜지려면 두 가지가 더 필요하다:
    ① 발주처 **자사 환기 기준** (몇 회/hr 로 관리하는가)
    ② **천장고** (ACH = 풍량 ÷ (면적 × 천장고))

## 단위 확정 — **근거 둘이 일치했다**

  ① 도면이 명시한다: 천정기구배치도 레이어 `B-ZONE` 의 텍스트 **`풍량(CMH)`**
  ② 물리적으로 말이 된다: 천장고 2.7m 가정 시 **B 63회, C 53회, D 28회, CNC 19회**
     — 클린룸 상식과 맞는다. 단위가 Pa 였다면 말이 안 되는 값이 나온다.

TA 단위는 오래 '보류'였는데 **도면 스스로 확정해 줬다**(적어도 이 도면에서는).
기준 시설(내용고형제)의 `TA` 레이어는 도면이 달라 **여전히 추정**이다.
"""
from __future__ import annotations

import pathlib

from gxpai.ingest.extractors.airflow import AirflowExtractor


class FakeText:
    def __init__(self, x, y, t, layer="풍량"):
        self.dxf = type("D", (), {"insert": type("P", (), {"x": x, "y": y})(),
                                  "layer": layer, "text": t})()

    def dxftype(self):
        return "TEXT"


class FakeDoc:
    def __init__(self, ents):
        self._e = ents

    def modelspace(self):
        return self._e


PROFILE = {"airflow": {"layers": ["풍량"], "unit": "CMH",
                       "unit_source": "도면 표기 (B-ZONE: '풍량(CMH)')"}}


def test_풍량_숫자를_읽는다():
    recs = AirflowExtractor().extract(
        FakeDoc([FakeText(100, 200, "1376"), FakeText(300, 400, "680")]), PROFILE)
    assert [r.payload["cmh"] for r in recs] == [1376.0, 680.0]
    assert all(r.payload["unit"] == "CMH" for r in recs)


def test_단위_출처를_남긴다():
    """단위를 짐작한 게 아니라 **도면에서 읽었다**는 것을 근거에 남긴다."""
    recs = AirflowExtractor().extract(FakeDoc([FakeText(0, 0, "290")]), PROFILE)
    assert "도면" in recs[0].payload["unit_source"]


def test_범례_텍스트는_풍량이_아니다():
    """`풍량(CMH)` 같은 범례 텍스트를 숫자로 읽으면 안 된다."""
    recs = AirflowExtractor().extract(
        FakeDoc([FakeText(0, 0, "풍량(CMH)"), FakeText(1, 1, "HEPA FILTER BOX 수량"),
                 FakeText(2, 2, "1376")]), PROFILE)
    assert len(recs) == 1 and recs[0].payload["cmh"] == 1376.0


def test_다른_레이어는_안_읽는다():
    recs = AirflowExtractor().extract(
        FakeDoc([FakeText(0, 0, "1376", layer="차압")]), PROFILE)
    assert recs == []


def test_프로파일에_레이어가_없으면_0건():
    assert AirflowExtractor().extract(FakeDoc([FakeText(0, 0, "1376")]), {}) == []


def test_법정_환기수치를_규칙에_박아넣지_않았다():
    """설계 결정을 고정한다 — 그리고 **이 시험 자체가 한 번 바뀌었다.**

    처음엔 "**환기 횟수 규칙을 아예 만들지 않는다**"고 못 박았다. 수치가 현행 고시에
    없으니 규칙도 없다는 논리였다.

    **반만 맞았다.** 1차 미팅 대표님:
      "**제일 중요한 게 환기 횟수**라는 개념이 있어요. 1시간에 몇 번 순환해야 된다는
       **조건이 꼭 있거든요.**"

    법정 수치로 판정하지 않는 건 옳다. 하지만 **자사 기준서로 판정하는 규칙은 만들어야**
    한다 — 차압(PRES-002)과 똑같이. → HVAC-001 을 만들었다.

    **이 시험이 계속 지키는 것**: 규칙 파일에 **법정 수치를 기본값으로 박지 않는 것.**
    `A: 600`, `B: 20` 은 **구 KGMP 해설서**다. 발주처 자사 기준서가 와야 채운다.
    (상세 시험은 tests/test_hvac_ach.py)
    """
    rules = pathlib.Path("rules/gmp_osd_v1.yaml").read_text(encoding="utf-8")
    for line in rules.splitlines():
        st = line.strip()
        if st.startswith("#"):
            continue                      # 주석의 예시는 괜찮다
        assert "ach_by_grade:" not in st, (
            "환기 기준을 규칙 파일에 박아 넣었다. 구 KGMP 해설서 수치를 법으로 "
            "착각한 것이 아닌지 확인하라. 발주처 자사 기준서가 와야 채운다.")
        assert "ceiling_height_m:" not in st, "천장고는 발주처가 줘야 한다"
