# -*- coding: utf-8 -*-
"""Grade / 절대압력(Pa) 추출기 회귀 시험.

★가장 중요한 회귀: **옆방 라벨을 훔쳐오지 않는 것.**
  PDF 작업에서 실제로 당했다 — 탈의실(5Pa)과 갱의실(15Pa)의 압력이 서로 뒤바뀌었다.
  라벨 블록은 [등급 / 이름 / 방번호 / 압력] 세로 4단이므로,
    - 등급은 방번호 **위**
    - 압력은 방번호 **아래**
  이 좌표 규칙을 지키는지 고정한다.
"""
from __future__ import annotations

from gxpai.ingest.extractors.grades import GradeExtractor
from gxpai.ingest.extractors.pressure_value import PressureValueExtractor


class FakeText:
    """iter_label_texts 가 도는 최소 DXF 흉내."""

    def __init__(self, x, y, t, layer="라벨"):
        self.x, self.y, self.t, self.layer = x, y, t, layer


class FakeDoc:
    def __init__(self, texts):
        self._texts = texts

    def modelspace(self):
        return []


def _patch(monkeypatch, module, texts):
    # **kwargs: 추출기가 exclude_blocks 같은 인자를 넘겨도 시험이 깨지지 않게.
    # (블록 재귀가 기둥 블록의 철골 규격을 방 이름으로 빨아들여 exclude_blocks 가 생겼다)
    def fake_iter(doc, layers, entity_types=None, **_kw):
        for t in texts:
            if t.layer in layers:
                yield (t.x, t.y, t.t, 100.0)
    monkeypatch.setattr(module, "iter_label_texts", fake_iter)


PROFILE = {
    "floorplan": {"room_layers": ["라벨"],
                  "room_no_regex": r"^(F\d[A-Z]\d{2})$",
                  "bare_no_regex": r"^\d{4}$"},
    "grades": {"layers": ["라벨"]},
    "pressure_value": {"layers": ["차압"]},
    "label_entity_types": ["TEXT"],
}


# ── Grade ─────────────────────────────────────────────────────
def test_grade_방번호_위의_등급을_가져온다(monkeypatch):
    import gxpai.ingest.extractors.grades as G
    texts = [
        FakeText(0, 300, "(CNC)"),      # 위
        FakeText(0, 200, "탈의실(남)"),
        FakeText(0, 100, "F2I01"),      # 방번호(축)
    ]
    _patch(monkeypatch, G, texts)
    recs = GradeExtractor().extract(FakeDoc(texts), PROFILE)
    assert len(recs) == 1
    assert recs[0].payload["room_no"] == "F2I01"
    assert recs[0].payload["grade"] == "CNC"


def test_grade_옆방_등급을_훔쳐오지_않는다(monkeypatch):
    """★핵심 회귀. 두 방이 세로로 붙어 있어도 각자 자기 위의 등급을 가져야 한다."""
    import gxpai.ingest.extractors.grades as G
    texts = [
        FakeText(0, 400, "(CNC)"),     # 방1 등급
        FakeText(0, 300, "F2I01"),     # 방1 번호
        FakeText(0, 200, "(D)"),       # 방2 등급
        FakeText(0, 100, "F2I03"),     # 방2 번호
    ]
    _patch(monkeypatch, G, texts)
    got = {r.payload["room_no"]: r.payload["grade"]
           for r in GradeExtractor().extract(FakeDoc(texts), PROFILE)}
    assert got == {"F2I01": "CNC", "F2I03": "D"}


def test_grade_등급표기_없으면_0건(monkeypatch):
    """기준 시설(내용고형제)처럼 등급 표기가 없으면 0건. 그게 정상이다."""
    import gxpai.ingest.extractors.grades as G
    texts = [FakeText(0, 200, "타정실"), FakeText(0, 100, "F2I01")]
    _patch(monkeypatch, G, texts)
    assert GradeExtractor().extract(FakeDoc(texts), PROFILE) == []


def test_grade_등급과_방번호가_다른_레이어에_있어도_붙는다(monkeypatch):
    """★실제 도면에서 등급 0건이 나온 버그.

    새 참고도면은 등급이 `Grade` 레이어, 방번호가 `ROOMNUMBER` 레이어에 있다.
    처음엔 **등급 레이어 하나에서 둘 다** 찾았다 → 방번호가 0개라 등급도 0건.
    (압력 추출기는 처음부터 레이어를 나눠 읽어 44건이 잘 나왔다. 같은 실수를 등급에서 했다.)
    """
    import gxpai.ingest.extractors.grades as G
    texts = [
        FakeText(0, 300, "(D)", layer="Grade"),          # 등급은 Grade 레이어
        FakeText(0, 100, "F2I03", layer="ROOMNUMBER"),   # 방번호는 다른 레이어
    ]
    _patch(monkeypatch, G, texts)
    prof = {
        "floorplan": {"room_layers": ["ROOMNUMBER"],
                      "room_no_regex": r"^(F\d[A-Z]\d{2})$",
                      "bare_no_regex": r"^\d{4}$"},
        "grades": {"layers": ["Grade"]},
        "label_entity_types": ["TEXT"],
    }
    recs = GradeExtractor().extract(FakeDoc(texts), prof)
    assert len(recs) == 1
    assert recs[0].payload == {**recs[0].payload,
                               "room_no": "F2I03", "grade": "D"}


def test_grade_전각괄호도_읽는다(monkeypatch):
    import gxpai.ingest.extractors.grades as G
    texts = [FakeText(0, 200, "（B）"), FakeText(0, 100, "F2I22")]
    _patch(monkeypatch, G, texts)
    recs = GradeExtractor().extract(FakeDoc(texts), PROFILE)
    assert recs[0].payload["grade"] == "B"


# ── 절대압력(Pa) ───────────────────────────────────────────────
def test_pa_방번호_아래의_압력을_가져온다(monkeypatch):
    import gxpai.ingest.extractors.pressure_value as P
    texts = [
        FakeText(0, 200, "F2I01"),
        FakeText(0, 100, "5Pa", layer="차압"),
    ]
    _patch(monkeypatch, P, texts)
    recs = [r for r in PressureValueExtractor().extract(FakeDoc(texts), PROFILE)
            if r.kind == "room_pressure"]
    assert len(recs) == 1
    assert recs[0].payload["room_no"] == "F2I01"
    assert recs[0].payload["pressure_pa"] == 5.0


def test_pa_옆방_압력을_훔쳐오지_않는다(monkeypatch):
    """★PDF 작업에서 실제로 당한 그 버그. 탈의실 5Pa 과 갱의실 15Pa 이 뒤바뀌었다."""
    import gxpai.ingest.extractors.pressure_value as P
    texts = [
        FakeText(0, 400, "F2I01"),                  # 탈의실
        FakeText(0, 300, "5Pa", layer="차압"),      # ← 탈의실 것
        FakeText(0, 200, "F2I03"),                  # 갱의실
        FakeText(0, 100, "15Pa", layer="차압"),     # ← 갱의실 것
    ]
    _patch(monkeypatch, P, texts)
    got = {r.payload["room_no"]: r.payload["pressure_pa"]
           for r in PressureValueExtractor().extract(FakeDoc(texts), PROFILE)
           if r.kind == "room_pressure"}
    assert got == {"F2I01": 5.0, "F2I03": 15.0}


def test_pa_풍량_숫자를_압력으로_오인하지_않는다(monkeypatch):
    """TA(풍량, CMH)는 단위 없는 숫자다. 'Pa' 접미가 없으면 압력이 아니다."""
    import gxpai.ingest.extractors.pressure_value as P
    texts = [
        FakeText(0, 200, "F2I01"),
        FakeText(0, 100, "270", layer="차압"),      # TA 풍량 — 압력 아님
    ]
    _patch(monkeypatch, P, texts)
    assert [r for r in PressureValueExtractor().extract(FakeDoc(texts), PROFILE)
            if r.kind == "room_pressure"] == []


def test_pa_음수도_읽는다(monkeypatch):
    """특수제제는 음압이다."""
    import gxpai.ingest.extractors.pressure_value as P
    texts = [FakeText(0, 200, "F3A01"), FakeText(0, 100, "-15Pa", layer="차압")]
    prof = dict(PROFILE)
    prof["floorplan"] = dict(PROFILE["floorplan"], room_no_regex=r"^(F\d[A-Z]\d{2})$")
    _patch(monkeypatch, P, texts)
    recs = [r for r in PressureValueExtractor().extract(FakeDoc(texts), prof)
            if r.kind == "room_pressure"]
    assert recs[0].payload["pressure_pa"] == -15.0


def test_pa_귀속못한_압력은_조용히_버리지_않는다(monkeypatch):
    """등급/번호 없는 구역의 압력일 수 있다 → 개수를 보고한다."""
    import gxpai.ingest.extractors.pressure_value as P
    texts = [
        FakeText(0, 200, "F2I01"),
        FakeText(0, 100, "5Pa", layer="차압"),
        FakeText(90000, 90000, "25Pa", layer="차압"),   # 멀리 떨어진 고아 라벨
    ]
    _patch(monkeypatch, P, texts)
    recs = PressureValueExtractor().extract(FakeDoc(texts), PROFILE)
    orphan = [r for r in recs if r.kind == "pressure_unmatched"]
    assert len(orphan) == 1 and orphan[0].payload["count"] == 1
