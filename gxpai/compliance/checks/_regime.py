# -*- coding: utf-8 -*-
"""압력 유형(regime) 판별 - 압력 규칙의 전제.

왜 이게 필요한가 (★엔진을 통째로 잘못 만들 뻔했다)
  "청정도가 높은 방이 고압이어야 한다"는 **한 유형에만 맞는 말**이다.
  실제로는 세 가지가 있고, **우리 기준 시설(내용고형제)은 두 번째**다.

    ① protect (보호)  : 실이 고압. 외부 오염이 못 들어오게.
                        무균제제, 일반 청정실. Cascade 구조.
    ② contain (봉쇄)  : 실이 **저압**, 복도가 고압. 분진이 복도로 못 나가게.
                        칭량·혼합·과립·정립·타정·코팅 등 **분진 발생 공정**.
    ③ hazard  (특수)  : 실이 **음압** + 전용 전실 + 별도 공조 + (페니실린) 배기 종말처리.
                        페니실린·세팔로스포린·카바페넴·모노박탐·성호르몬·세포독성항암제.

근거
  - 2010 「의약품제조소 시설기준(구조·설비) 안내서」 p.24 그림6:
      분진 발생 지역 → **통로 30Pa > 작업실 15Pa** (일반 Cascade 와 정반대)
  - 같은 안내서 p.60 (시행규칙 제5조 해설):
      특수제제는 "공기의 차압을 이용하여 **내부의 분진이 확산되지(외부로 빠져나가지) 않도록**"
  - 1차 미팅(2026-07-09) 대표님:
      "복도가 높고 여기가 낮다… 복도에 있는 공기가 룸 안으로 들어가야 돼"
  - 상세: 법규/조문근거_색인.md A-4·A-5절

한계(정직)
  방 '이름'으로 공정을 추론한다. 이름은 회사마다 다르다(타정실=타블렛실=정제실).
  → 프로파일(profiles/*.yaml)로 덮어쓸 수 있게 하고, 추론 결과는 regime_source='inferred' 로
    표시해 감사에서 구분한다. **확정이 아니라 추정이다.**
"""
from __future__ import annotations

PROTECT = "protect"
CONTAIN = "contain"
HAZARD = "hazard"
NEUTRAL = "neutral"          # 압력 관리 대상 아님(복도·보관소·기계실 등)

# 분진이 나는 공정 → 봉쇄(실이 저압)
#   근거: 2010 안내서 p.33 "분진이 발생하는 작업실에는 국소집진시설을 설치할 것",
#         p.8 그림2(핵심지역=정립·타정·충전 / 중요지역=혼합·과립·칭량)
#
#   ★'충전/충진' 은 일부러 뺐다 — **시설 종류에 따라 정반대다.**
#     내용고형제의 '캡슐 충전' = 분말 → 분진(봉쇄)
#     무균제제의 '바이알 충진' = 액체 → 분진 없음(보호)
#     이름만으로는 못 가른다. **프로파일(regime_overrides)로 지정할 것.**
#     '건조' 도 같은 이유로 뺐다(동결건조는 무균 공정).
DUST_WORDS = (
    "칭량", "계량", "혼합", "과립", "정립", "타정", "코팅", "분쇄", "선별", "제립",
)

# 특수제제 → 음압 격리
#   근거: 시설기준령 시행규칙 제2조①1호·제5조
HAZARD_WORDS = (
    "페니실린", "세팔로스포린", "카바페넴", "모노박탐",
    "성호르몬", "호르몬", "세포독성", "항암",
)

# 압력 관리 대상이 아닌 공간
#   근거: 2010 안내서 p.5(보관소는 GMP 영역이나 **청정도 관리 불요**)
#         · p.37(청정도 관리가 요구되지 않는 예시) · 새GMP규정 Q&A 문15
#   ※ 복도는 '중립'이 아니라 **기준면**이다. 봉쇄 검사에서 비교 대상이므로 따로 표시한다.
#
#   ★낱말은 **숫자가 끼어도 걸리게** 짧게 잡는다.
#     '기계실'로 뒀더니 실제 도면의 `기계1실`·`기계 2실`을 놓쳤다(보호형으로 오분류).
#     `공조실`·`집진기실`·`외조기실` 같은 설비실도 통째로 빠져 있었다.
NEUTRAL_WORDS = (
    "보관", "창고",
    "기계", "공조", "외조기", "집진", "전기", "설비", "펌프", "보일러",
    "P.S", "PS", "샤프트", "덕트", "계단", "엘리베이터", "승강기", "방풍",
    "사무", "휴게", "식당", "화장실", "예비", "다용도",
)
CORRIDOR_WORDS = ("복도", "통로", "회랑")


def is_corridor(name: str | None) -> bool:
    """복도인가. 봉쇄 검사의 '기준면'이 된다."""
    return bool(name) and any(w in name for w in CORRIDOR_WORDS)


def infer_regime(name: str | None, grade: str | None = None) -> str:
    """방 이름(+등급)으로 압력 유형을 **추정**한다.

    우선순위: **특수제제 > 복도 > 분진공정 > 중립 > 보호(기본)**

    순서가 전부 시행착오로 정해졌다. 두 번 틀렸다:
      ① 분진공정을 복도보다 먼저 봤다 → `정립실복도` 를 봉쇄실로 오판.
         **복도가 먼저**여야 한다. 정립실복도는 복도지 정립실이 아니다.
      ② 중립을 분진공정보다 먼저 봤다 → `선별 3실(예비)` 가 '예비' 때문에 중립으로 빠졌다.
         **분진이 중립보다 먼저**여야 한다. 예비든 뭐든 선별실은 분진이 난다.
    """
    n = (name or "").replace(" ", "")

    if any(w in n for w in HAZARD_WORDS):
        return HAZARD
    if is_corridor(n):
        return NEUTRAL
    if any(w in n for w in DUST_WORDS):
        return CONTAIN
    if any(w in n for w in NEUTRAL_WORDS):
        return NEUTRAL
    return PROTECT


def resolve_regime(name: str | None, grade: str | None,
                   overrides: dict[str, str] | None = None,
                   room_no: str | None = None) -> tuple[str, str]:
    """(regime, source) 를 돌려준다. 프로파일 override 가 추론을 이긴다."""
    if overrides and room_no and room_no in overrides:
        return overrides[room_no], "profile"
    return infer_regime(name, grade), "inferred"
