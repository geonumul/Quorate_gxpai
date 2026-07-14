# -*- coding: utf-8 -*-
"""압력 규칙 재설계(PRES-001/002/003) + ADJ-001 재설계 회귀 시험.

무엇을 지키려는 시험인가
  가장 중요한 것: **거짓 위반을 내지 않는 것.**
    분진 발생실(내용고형제 타정, 과립)은 복도보다 저압인 게 **정상**이다.
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
    """실제 도면에서 잡은 오분류.

    중립 낱말을 '기계실'로 뒀더니 `기계1실`, `기계 2실` 을 놓쳐 **보호형으로 오분류**했다.
    `공조실`, `집진기실`, `외조기실` 같은 설비실은 목록에 아예 없었다.
    → 낱말을 짧게(숫자가 끼어도 걸리게) 잡는다.
    """
    for n in ["기계1실", "기계 2실", "공조실", "집진기실", "집진실",
              "외조기실-2", "전기실", "예비실", "다용도실", "방풍실"]:
        assert infer_regime(n) == NEUTRAL, n


def test_regime_분진공정이_중립낱말보다_우선():
    """실제 도면에서 잡은 오분류.

    `선별 3실(예비)` 가 '예비'(중립 낱말) 때문에 중립으로 빠졌다.
    예비든 뭐든 **선별실은 분진이 난다.** 분진 판별이 중립보다 먼저여야 한다.
    """
    assert infer_regime("선별 3실(예비)") == CONTAIN
    assert infer_regime("예비 칭량실") == CONTAIN


def test_regime_복도가_분진공정보다_우선():
    """'정립실복도' 는 복도지 정립실이 아니다.

    처음엔 분진공정을 먼저 봤다가 복도를 봉쇄실로 오판했다. 시험이 잡았다.
    """
    assert infer_regime("정립실복도") == NEUTRAL
    assert infer_regime("타정실 복도") == NEUTRAL


def test_regime_충전은_이름만으로_못_가른다():
    """'충전/충진' 은 시설 종류에 따라 정반대다 — 그래서 DUST_WORDS 에서 뺐다.

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
    """핵심 회귀: 분진 발생실은 복도보다 저압인 게 정상이다.

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
    """실제 도면에서 3건을 놓쳤다.

    처음엔 저압쪽이 '복도'일 때만 봤다. 그런데 실제로는:
        contain → neutral (보관실, 기계실) 2건
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


def test_pres002_차압_설정_구간만_검사한다():
    """실제 도면에서 과잉 검출한 버그.

    처음엔 **인접한 모든 실 쌍**에 기준을 들이댔다 → Δ0Pa(같은 등급, 같은 압력) 쌍을
    무더기로 위반으로 찍었다(28건 중 상당수).
    도면 범례 3번: *"기류흐름 및 차압계 설치가 요구되지 않는 위치"*.
    **차압이 설정되지 않은 구간에는 기준이 애초에 적용되지 않는다.**
    """
    rooms = [RoomView(room_no="A", name="포장실", grade="CNC", pressure_pa=10),
             RoomView(room_no="B", name="세척실", grade="CNC", pressure_pa=10)]
    adj = [AdjPair("A", "B")]

    # 화살표가 없다 = 차압 설정 구간이 아니다 → 위반 아님
    assert pres_002.evaluate(adj, rooms, CFG2, rels=[]) == []
    assert pres_002.evaluate(adj, rooms, CFG2, rels=None) != []   # 화살표 정보가 없으면 예전 동작

    # 화살표가 있으면 검사한다 → Δ0Pa 는 사내 기준(5~10) 밖
    rels = [PressureRel(room_high_no="A", room_low_no="B")]
    v = pres_002.evaluate(adj, rooms, CFG2, rels=rels)
    assert len(v) == 1 and v[0]["evidence"]["delta_pa"] == 0


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
    """전실은 등급 완충 장치다. 전실이 끼면 '직접 인접'이 아니다."""
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


# ── 머리말(head) 판별: 낱말이 들었다고 그 공정실이 아니다 ──────────
def test_regime_공정실이_아닌_방을_봉쇄실로_보지_않는다():
    """기준 시설에서 무더기로 난 오탐. 10개 방이 잘못 분류돼 있었다.

    한국어 합성명사는 **마지막 명사가 머리말**이다.
        `칭량 전 원료대기실` 의 머리말은 '대기실' 이지 '칭량' 이 아니다.
        `반제품 보관실(선별전)` 의 머리말은 '보관실' 이지 '선별' 이 아니다.
        `타정1실 전실` 의 머리말은 '전실' 이지 '타정' 이 아니다.
    낱말이 이름 어딘가에 들어 있는지가 아니라 **머리말을 봐야** 한다.

    이게 왜 중요한가: 봉쇄실로 잘못 보면 PRES-003(봉쇄 실패)이
    "원료대기실이 복도보다 고압이다 → 분진이 샌다" 는 **거짓 위반**을 낸다.
    원료는 아직 봉지에 밀봉돼 있다. 분진이 날 리가 없다.
    """
    # 원료, 반제품이 밀봉된 채 머무는 방 → 중립
    assert infer_regime("(N)칭량 전 원료대기실") == NEUTRAL
    assert infer_regime("(N)칭량 후 원료대기실") == NEUTRAL
    assert infer_regime("(N)반제품 보관실(선별전)") == NEUTRAL
    assert infer_regime("(N)반제품 보관실(선별후)") == NEUTRAL
    # 설비가 놓인 방 → 중립
    assert infer_regime("(N)코팅기계1실") == NEUTRAL
    assert infer_regime("(N)코팅 기계 2실") == NEUTRAL


def test_regime_전실은_중립이_아니라_보호다():
    """부정은 **분진 판정만 취소**한다. 중립으로 빼버리면 안 된다.

    `타정1실 전실` 은 타정실이 아니다(분진 아님). 하지만 에어락은
    **압력 관리의 핵심 단계**다. 중립으로 빼면 PRES-002/003 이 아예 건너뛰어
    '분진이 에어락으로 새는' 진짜 위반을 놓친다.
    """
    for n in ["(N)타정1실 전실", "(N)과립1실 전실", "무균 전실", "퇴실 전실"]:
        assert infer_regime(n) == PROTECT, n


def test_regime_액체_조제실은_분진이_아니다():
    """`과립액 조제1실` = 결합액을 만드는 방. 분말이 아니라 **액체**다.

    [주의] 보류, 발주처 확인 필요 — 용액을 만들 때 고분자 분말을 붓는 순간은 있다.
      설계사가 이 방을 어떻게 관리하는지 물어야 한다. 지금은 '분진 아님'으로 둔다.
    """
    from gxpai.compliance.checks._regime import is_dust_process
    assert not is_dust_process("(N)과립액 조제1실")
    assert not is_dust_process("(N)코팅액 조제2실")
    # '액' 이 안 붙으면 그대로 분진이다
    assert is_dust_process("(N)과립1실")
    assert is_dust_process("(N)코팅2실")


def test_regime_진짜_공정실은_그대로_봉쇄다():
    """부정 규칙을 넣다가 진짜 공정실까지 놓치면 안 된다. 회귀 방지."""
    for n in ["(N)칭량1실", "(N)타정1실", "(N)과립1실", "(N)혼합 2실",
              "(N)선별 3실(예비)", "(N)코팅1실"]:
        assert infer_regime(n) == CONTAIN, n


def test_regime_괄호와_숫자는_머리말이_아니다():
    from gxpai.compliance.checks._regime import head_form
    assert head_form("(N)반제품 보관실(선별전)") == "반제품보관실"
    assert head_form("(N)코팅 기계 2실") == "코팅기계실"
    assert head_form("(N)선별 3실(예비)") == "선별실"


# ── '전실'이 다른 낱말에 끼어 있다 ────────────────────────────────
def test_충전실은_전실이_아니다():
    """시험이 잡은 교차 버그. 세 규칙에 동시에 퍼져 있었다.

    `무균 **충전실**`, `캡슐 **충전실**`, `**변전실**`, `**발전실**`
    전부 '전실'을 품고 있지만 **에어락이 아니다.**

    에어락으로 오인하면 무슨 일이 나나 — **놓친다**(거짓 위반보다 나쁘다):
      ADJ-001(등급 급변)   그 방을 **예외 처리해 검사에서 빼버린다**
      ADJ-002(갱의실 우회) **관문**으로 취급해 그래프에서 끊어 버린다 → 우회로를 못 찾는다
      ADJ-005(인터락)      **에어락**으로 보고 인터락을 요구한다 → 거짓 위반
    """
    from gxpai.compliance.checks._regime import is_airlock

    # 에어락이다
    for n in ["무균 전실", "타정1실 전실", "물류 전실 2", "에어락", "패스박스", "이송 해치"]:
        assert is_airlock(n), n

    # '전실'을 품고 있지만 에어락이 **아니다**
    for n in ["무균 충전실", "캡슐 충전실", "바이알 충진실", "변전실", "발전실", "수전실"]:
        assert not is_airlock(n), n


def test_충전실_오인이_세_규칙에서_다_막혔나():
    """세 규칙이 **같은 판별 함수**를 쓰는지 고정한다. 한 곳만 고치면 또 샌다."""
    from gxpai.compliance.checks import adj_001, adj_002, adj_005

    assert not adj_005.is_airlock("무균 충전실")
    assert not adj_002.is_gowning("무균 충전실")
    assert not adj_001._is_airlock("무균 충전실", adj_001.DEFAULT_AIRLOCK)
    # 진짜 전실은 셋 다 알아본다
    assert adj_005.is_airlock("무균 전실")
    assert adj_002.is_gowning("무균 전실")
    assert adj_001._is_airlock("무균 전실", adj_001.DEFAULT_AIRLOCK)


# ── 회사마다 이름이 다르다 (대량 데이터 대비) ──────────────────────
def test_회사마다_다른_이름을_다_잡는다():
    """1차 미팅(2026-07-09) 대표님:

    "이게 우리나라 말로 **타정실**이고, **어떤 회사는 그냥 '타블렛 4' 이렇게도 써놓거든요.**
     정제를 뜻하는 거라서 **회사마다 그런 명칭이 다 틀려요.**"

    한글만 보면 대량 데이터에서 바로 깨진다. 영문, 동의어를 넣었다.
    """
    for n in ["타정1실", "타블렛 4", "정제실", "압축실",
              "Tablet Room 2", "TABLETTING", "tablet room",
              "Weighing Room", "Dispensing 1", "계량실", "평량실",
              "Granulation", "조립실", "Blending", "배합실", "Mixing Room 1",
              "Coating 2", "Milling", "파쇄실"]:
        assert infer_regime(n) == CONTAIN, n


def test_대소문자를_무시한다():
    """영문 동의어를 넣고도 **대소문자 때문에 안 잡혀서** 한 번 당했다.

    `Tablet Room`, `TABLETTING`, `tablet` 이 다 같은 말이다.
    """
    for n in ["Tablet", "TABLET", "tablet", "TaBlEt"]:
        assert infer_regime(n) == CONTAIN, n


def test_동의어를_넣어도_기존_함정이_안_깨진다():
    """가장 중요한 회귀. 낱말을 늘리면 오탐이 늘기 쉽다."""
    assert infer_regime("(N)칭량 전 원료대기실") == NEUTRAL      # 대기실 = 공정실 아님
    assert infer_regime("(N)타정1실 전실") == PROTECT           # 전실 = 에어락
    assert infer_regime("무균 충전실") == PROTECT               # '충전실' ≠ '전실'
    assert infer_regime("(N)과립액 조제1실") == PROTECT         # '액' = 액체
    assert infer_regime("정립실복도") == NEUTRAL                # 복도가 먼저
    assert infer_regime("(N)코팅기계1실") == NEUTRAL            # 기계실


def test_프로파일로_동의어를_더_넣을_수_있다():
    """대량 데이터가 오면 **우리가 모르는 이름**이 반드시 나온다.

    그때 **코드를 고치지 않고 프로파일만** 고쳐서 받는다.
    """
    from gxpai.compliance.checks import _regime

    before = _regime.DUST_WORDS
    try:
        assert infer_regime("건식과립실") == CONTAIN            # '과립' 이 이미 있다
        assert infer_regime("압출성형실") == PROTECT            # '압출' 은 모른다
        _regime.extend_from_profile({"name_synonyms": {"dust": ["압출"]}})
        assert infer_regime("압출성형실") == CONTAIN            # 이제 안다
    finally:
        _regime.DUST_WORDS = before
