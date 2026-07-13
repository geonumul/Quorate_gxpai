# -*- coding: utf-8 -*-
"""급기 풍량(CMH) 추출 회귀 시험.

## ★이 파일이 지키는 가장 중요한 것: **환기 횟수(ACH) 규칙을 만들지 않는다**

수치(Class 100(A) **600회/hr** · Class 10,000(B) **20회/hr**)는
「GMP 조사평가 매뉴얼」이 인용한 **구 KGMP 해설서**에만 있다.

**현행 고시(별표1, 2023 개정 · PIC/S Annex 1 기반)에는 환기 횟수 수치가 없다.**
별표1의 '환기' 언급 6건을 전수 확인했는데 전부 **EO 멸균 환기** 등 다른 맥락이었다.
현행은 **오염관리전략(CCS)** 으로 타당성을 입증하게 한다.

수치를 박아 넣으면 **근거 없는 관행을 법인 것처럼** 판정하는 것이다. **하지 않는다.**

→ 풍량은 **데이터로만 적재**한다. 규칙이 켜지려면 두 가지가 더 필요하다:
    ① 발주처 **자사 환기 기준** (몇 회/hr 로 관리하는가)
    ② **천장고** (ACH = 풍량 ÷ (면적 × 천장고))

## 단위 확정 — **근거 둘이 일치했다**

  ① 도면이 명시한다: 천정기구배치도 레이어 `B-ZONE` 의 텍스트 **`풍량(CMH)`**
  ② 물리적으로 말이 된다: 천장고 2.7m 가정 시 **B 63회 · C 53회 · D 28회 · CNC 19회**
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
    """★단위를 짐작한 게 아니라 **도면에서 읽었다**는 것을 근거에 남긴다."""
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


def test_ACH_규칙은_존재하지_않는다():
    """★★설계 결정을 고정한다. **환기 횟수 규칙을 만들지 않는다.**

    수치는 구 KGMP 해설서에만 있고 **현행 고시에는 없다**.
    누군가 나중에 'HVAC-001 환기횟수' 규칙을 추가하려 하면 이 시험이 막는다 —
    막기 전에 **현행 조문 근거부터 가져오라**는 뜻이다.
    """
    rules = pathlib.Path("rules/gmp_osd_v1.yaml").read_text(encoding="utf-8")
    for banned in ("환기횟수", "환기 횟수", "air_change", "ach_min", "HVAC-001"):
        assert banned not in rules, (
            f"'{banned}' 규칙이 생겼다. 현행 고시(별표1)에는 환기 횟수 수치가 없다. "
            f"구 KGMP 해설서를 법으로 착각한 것이 아닌지 조문부터 확인하라.")
