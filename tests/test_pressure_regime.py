# -*- coding: utf-8 -*-
"""압력 규칙 재설계(PRES-001/002/003) + ADJ-001 재설계 회귀 시험.

무엇을 지키려는 시험인가
  ★가장 중요한 것: **거짓 위반을 내지 않는 것.**
    분진 발생실(내용고형제 타정·과립)은 복도보다 저압인 게 **정상**이다.
    예전 규칙("깨끗한 방이 고압")을 그대로 뒀으면 우리 기준 시설 전체가 위반으로 찍혔다.
"""
from __future__ import annotations

from gxpai.compliance.checks import adj_001, pres_001, pres_002, pres_003
from gxpai.compliance.checks._model import AdjPair, PressureRel, RoomView
from gxpai.compliance.checks._regime import CONTAIN, HAZARD, NEUTRAL, PROTECT, infer_regime


# ── 압력 유형 판별 ──────────────────────────────────────────────
def test_regime_분진공정은_봉쇄():
    for n in ["타정실", "제1타정실", "혼합실", "과립실", "정립실", "칭량실", "코팅실 4"]:
        assert infer_regime(n) == CONTAIN, n


def test_regime_특수제제는_음압():
    for n in ["페니실린 조제실", "세포독성 항암제 충전실", "성호르몬제제 작업실"]:
        assert infer_regime(n) == HAZARD, n


def test_regime_복도_보관소는_중립():
    for n in ["복도", "정립실복도", "원료 보관소", "기계실", "화장실"]:
        assert infer_regime(n) == NEUTRAL, n


def test_regime_무균실은_보호():
    for n in ["무균 조제실", "바이알 충진실", "갱의실(남)"]:
        assert infer_regime(n) == PROTECT, n


def test_regime_특수제제가_분진공정보다_우선():
    # '세포독성 항암제 타정실' 은 분진도 나지만 hazard 로 봐야 한다(더 강한 격리)
    assert infer_regime("세포독성 항암제 타정실") == HAZARD


def test_regime_설비실은_중립_숫자가_끼어도():
    """★실제 도면에서 잡은 오분류.

    중립 낱말을 '기계실'로 뒀더니 `기계1실`·`기계 2실` 을 놓쳐 **보호형으로 오분류**했다.
    `공조실`·`집진기실`·`외조기실` 같은 설비실은 목록에 아예 없었다.
    → 낱말을 짧게(숫자가 끼어도 걸리게) 잡는다.
    """
    for n in ["기계1실", "기계 2실", "공조실", "집진기실", "집진실",
              "외조기실-2", "전기실", "예비실", "다용도실", "방풍실"]:
        assert infer_regime(n) == NEUTRAL, n


def test_regime_분진공정이_중립낱말보다_우선():
    """★실제 도면에서 잡은 오분류.

    `선별 3실(예비)` 가 '예비'(중립 낱말) 때문에 중립으로 빠졌다.
    예비든 뭐든 **선별실은 분진이 난다.** 분진 판별이 중립보다 먼저여야 한다.
    """
    assert infer_regime("선별 3실(예비)") == CONTAIN
    assert infer_regime("예비 칭량실") == CONTAIN


def test_regime_복도가_분진공정보다_우선():
    """★'정립실복도' 는 복도지 정립실이 아니다.

    처음엔 분진공정을 먼저 봤다가 복도를 봉쇄실로 오판했다. 시험이 잡았다.
    """
    assert infer_regime("정립실복도") == NEUTRAL
    assert infer_regime("타정실 복도") == NEUTRAL


def test_regime_충전은_이름만으로_못_가른다():
    """★'충전/충진' 은 시설 종류에 따라 정반대다 — 그래서 DUST_WORDS 에서 뺐다.

      내용고형제 '캡슐 충전' = 분말 → 분진(봉쇄)
      무균제제  '바이알 충진' = 액체 → 분진 없음(보호)

    이름만으로는 못 가르므로 **기본은 보호(protect)** 로 두고,
    분진이 나는 충전실은 **프로파일 regime_overrides 로 지정**해야 한다.
    이 시험은 그 설계 결정을 고정한다.
    """
    assert infer_regime("바이알 충진실") == PROTECT
    assert infer_regime("캡슐 충전실") == PROTECT          # 기본값. 프로파일로 덮어써야 한다

    # 프로파일로 덮어쓰면 봉쇄가 된다
    from gxpai.compliance.checks._regime import resolve_regime
    reg, src = resolve_regime("캡슐 충전실", "D", {"3117": CONTAIN}, "3117")
    assert (reg, src) == (CONTAIN, "profile")


# ── PRES-001: 보호형 실끼리만 판정 ──────────────────────────────
CFG1 = {"enabled": True, "cleaner_should_be": "higher",
        "grade_rank": {"A": 5, "B": 4, "C": 3, "D": 2, "CNC": 1, "NC": 0}}


def test_pres001_보호형_역전을_잡는다():
    rooms = [RoomView(room_no="R1", name="무균 조제실", grade="B", regime=PROTECT),
             RoomView(room_no="R2", name="바이알 충진실", grade="C", regime=PROTECT)]
    # R2(C, 덜 깨끗)가 고압, R1(B, 더 깨끗)이 저압 → 역전
    rels = [PressureRel(room_high_no="R2", room_low_no="R1")]
    v = pres_001.evaluate(rels, rooms, CFG1)
    assert len(v) == 1 and v[0]["severity"] == "critical"


def test_pres001_봉쇄실이_끼면_판정하지_않는다():
    """★핵심 회귀: 분진 발생실은 복도보다 저압인 게 정상이다.

    예전 규칙이면 '복도(등급 D)가 고압, 타정실(등급 D)이 저압' 을 놓고
    등급이 같아 위반은 안 났겠지만, 등급이 다른 조합에서는 거짓 위반이 났다.
    지금은 **봉쇄실이 끼면 아예 PRES-001 을 적용하지 않는다.**
    """
    rooms = [RoomView(room_no="C1", name="복도", grade="CNC", regime=NEUTRAL),
             RoomView(room_no="T1", name="타정실", grade="D", regime=CONTAIN)]
    # 복도가 고압, 타정실이 저압 = 봉쇄형에선 정상
    rels = [PressureRel(room_high_no="C1", room_low_no="T1")]
    assert pres_001.evaluate(rels, rooms, CFG1) == []


def test_pres001_regime_미지정이면_이름으로_추론():
    rooms = [RoomView(room_no="C1", name="복도", grade="CNC"),
             RoomView(room_no="T1", name="타정실", grade="D")]
    rels = [PressureRel(room_high_no="C1", room_low_no="T1")]
    assert pres_001.evaluate(rels, rooms, CFG1) == []      # 추론으로도 걸러진다


def test_pres001_게이트_잠기면_0건():
    rooms = [RoomView(room_no="R1", name="무균실", grade="B", regime=PROTECT),
             RoomView(room_no="R2", name="충진실", grade="C", regime=PROTECT)]
    rels = [PressureRel(room_high_no="R2", room_low_no="R1")]
    assert pres_001.run(None, "r", "f", {"config": {"enabled": False}}) == []
    assert len(pres_001.evaluate(rels, rooms, CFG1)) == 1   # 순수 로직은 살아 있다


# ── PRES-003: 봉쇄 실패 ────────────────────────────────────────
CFG3 = {"enabled": True}


def test_pres003_분진실이_복도보다_고압이면_위반_화살표근거():
    rooms = [RoomView(room_no="T1", name="타정실", grade="D", regime=CONTAIN),
             RoomView(room_no="C1", name="복도", grade="CNC", regime=NEUTRAL)]
    rels = [PressureRel(room_high_no="T1", room_low_no="C1")]   # 타정실 → 복도
    v = pres_003.evaluate(rels, [], rooms, CFG3)
    assert len(v) == 1 and "봉쇄 실패" in v[0]["message"]
    assert v[0]["evidence"]["근거"] == "arrow"


def test_pres003_분진실이_복도보다_고압이면_위반_압력근거():
    rooms = [RoomView(room_no="T1", name="과립실", grade="D", regime=CONTAIN, pressure_pa=30),
             RoomView(room_no="C1", name="복도", grade="CNC", regime=NEUTRAL, pressure_pa=15)]
    v = pres_003.evaluate([], [AdjPair("T1", "C1")], rooms, CFG3)
    assert len(v) == 1 and v[0]["evidence"]["근거"] == "pressure_pa"


def test_pres003_상대가_복도가_아니어도_잡는다():
    """★실제 도면에서 3건을 놓쳤다.

    처음엔 저압쪽이 '복도'일 때만 봤다. 그런데 실제로는:
        contain → neutral (보관실·기계실) 2건
        contain → protect (청정실)      1건  ← 이게 제일 나쁘다
    분진이 나가는 곳이 복도든 보관실이든 청정실이든 **봉쇄 실패**다.
    """
    rooms = [RoomView(room_no="T1", name="타정실", grade="D", regime=CONTAIN),
             RoomView(room_no="S1", name="반제품 보관실", grade="D", regime=NEUTRAL),
             RoomView(room_no="C1", name="무균 조제실", grade="C", regime=PROTECT)]
    rels = [PressureRel(room_high_no="T1", room_low_no="S1"),   # 분진 → 보관실
            PressureRel(room_high_no="T1", room_low_no="C1")]   # 분진 → 청정실
    v = pres_003.evaluate(rels, [], rooms, CFG3)
    assert len(v) == 2
    assert all("봉쇄 실패" in x["message"] for x in v)


def test_pres003_분진구역끼리는_문제_아님():
    """contain → contain 은 둘 다 분진 구역이라 정상이다(실제 도면에 14건 있었다)."""
    rooms = [RoomView(room_no="T1", name="타정실", grade="D", regime=CONTAIN),
             RoomView(room_no="T2", name="혼합실", grade="D", regime=CONTAIN)]
    rels = [PressureRel(room_high_no="T1", room_low_no="T2")]
    assert pres_003.evaluate(rels, [], rooms, CFG3) == []


def test_pres003_정상_봉쇄는_위반_아님():
    """복도 30Pa > 타정실 15Pa = 2010 안내서 그림6 그대로. 위반이면 안 된다."""
    rooms = [RoomView(room_no="T1", name="타정실", grade="D", regime=CONTAIN, pressure_pa=15),
             RoomView(room_no="C1", name="복도", grade="CNC", regime=NEUTRAL, pressure_pa=30)]
    rels = [PressureRel(room_high_no="C1", room_low_no="T1")]
    assert pres_003.evaluate(rels, [AdjPair("T1", "C1")], rooms, CFG3) == []


def test_pres003_압력_없으면_조용히_건너뛴다():
    rooms = [RoomView(room_no="T1", name="타정실", grade="D", regime=CONTAIN),
             RoomView(room_no="C1", name="복도", grade="CNC", regime=NEUTRAL)]
    assert pres_003.evaluate([], [AdjPair("T1", "C1")], rooms, CFG3) == []


def test_pres003_중복보고_안함():
    """화살표와 압력 둘 다 걸려도 한 건만."""
    rooms = [RoomView(room_no="T1", name="타정실", grade="D", regime=CONTAIN, pressure_pa=30),
             RoomView(room_no="C1", name="복도", grade="CNC", regime=NEUTRAL, pressure_pa=15)]
    rels = [PressureRel(room_high_no="T1", room_low_no="C1")]
    assert len(pres_003.evaluate(rels, [AdjPair("T1", "C1")], rooms, CFG3)) == 1


# ── PRES-002: 자사 기준서 기반 ─────────────────────────────────
CFG2 = {"enabled": True, "diff_grade_pa": [10, 15], "same_grade_pa": [5, 10],
        "statutory_min_pa": 10}


def test_pres002_동일등급_기준초과를_잡는다():
    """새 참고도면 실제 사례: (D)25Pa → (D)10Pa = Δ15Pa. 사내 기준 '동일 등급 5~10Pa' 위반."""
    rooms = [RoomView(room_no="A", name="세척 및 멸균실", grade="D", pressure_pa=25),
             RoomView(room_no="B", name="물류 전실 1", grade="D", pressure_pa=10)]
    v = pres_002.evaluate([AdjPair("A", "B")], rooms, CFG2)
    assert len(v) == 1 and "동일 등급" in v[0]["message"]
    assert v[0]["evidence"]["delta_pa"] == 15


def test_pres002_등급상이_정상범위는_통과():
    rooms = [RoomView(room_no="A", name="조제실", grade="C", pressure_pa=25),
             RoomView(room_no="B", name="갱의실", grade="D", pressure_pa=15)]
    assert pres_002.evaluate([AdjPair("A", "B")], rooms, CFG2) == []   # Δ10 ∈ [10,15]


def test_pres002_기준서_없으면_미설정이_위반():
    rooms = [RoomView(room_no="A", name="조제실", grade="C", pressure_pa=25)]
    v = pres_002.evaluate([], rooms, {"enabled": True})
    assert len(v) == 1 and "미설정" in v[0]["message"]


def test_pres002_압력데이터_없으면_침묵():
    rooms = [RoomView(room_no="A", name="조제실", grade="C")]
    assert pres_002.evaluate([], rooms, {"enabled": True}) == []


# ── ADJ-001: 등급 점프 ─────────────────────────────────────────
CFGA = {"enabled": True, "max_jump": 1,
        "grade_rank": {"A": 5, "B": 4, "C": 3, "D": 2, "CNC": 1, "NC": 0}}


def test_adj001_2단계_점프를_잡는다():
    rooms = [RoomView(room_no="R1", name="무균 충진실", grade="B"),
             RoomView(room_no="R2", name="일반 복도", grade="CNC")]
    v = adj_001.evaluate([AdjPair("R1", "R2")], rooms, CFGA)
    assert len(v) == 1 and v[0]["evidence"]["jump"] == 3


def test_adj001_한단계는_정상():
    rooms = [RoomView(room_no="R1", name="조제실", grade="C"),
             RoomView(room_no="R2", name="갱의실", grade="D")]
    assert adj_001.evaluate([AdjPair("R1", "R2")], rooms, CFGA) == []


def test_adj001_전실을_끼면_예외():
    """★전실은 등급 완충 장치다. 전실이 끼면 '직접 인접'이 아니다."""
    rooms = [RoomView(room_no="R1", name="무균 충진실", grade="B"),
             RoomView(room_no="R2", name="무균 전실", grade="CNC")]
    assert adj_001.evaluate([AdjPair("R1", "R2")], rooms, CFGA) == []


def test_adj001_양방향_중복제거():
    rooms = [RoomView(room_no="R1", name="충진실", grade="B"),
             RoomView(room_no="R2", name="복도", grade="CNC")]
    v = adj_001.evaluate([AdjPair("R1", "R2"), AdjPair("R2", "R1")], rooms, CFGA)
    assert len(v) == 1


def test_adj001_등급_미상은_건너뛴다():
    rooms = [RoomView(room_no="R1", name="충진실", grade=None),
             RoomView(room_no="R2", name="복도", grade="CNC")]
    assert adj_001.evaluate([AdjPair("R1", "R2")], rooms, CFGA) == []
