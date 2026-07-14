# -*- coding: utf-8 -*-
"""압력 유형(regime) 판별 - 압력 규칙의 전제.

왜 이게 필요한가 (엔진을 통째로 잘못 만들 뻔했다)
  "청정도가 높은 방이 고압이어야 한다"는 **한 유형에만 맞는 말**이다.
  실제로는 세 가지가 있고, **우리 기준 시설(내용고형제)은 두 번째**다.

    ① protect (보호)  : 실이 고압. 외부 오염이 못 들어오게.
                        무균제제, 일반 청정실. Cascade 구조.
    ② contain (봉쇄)  : 실이 **저압**, 복도가 고압. 분진이 복도로 못 나가게.
                        칭량, 혼합, 과립, 정립, 타정, 코팅 등 **분진 발생 공정**.
    ③ hazard  (특수)  : 실이 **음압** + 전용 전실 + 별도 공조 + (페니실린) 배기 종말처리.
                        페니실린, 세팔로스포린, 카바페넴, 모노박탐, 성호르몬, 세포독성항암제.

근거
  - 2010 「의약품제조소 시설기준(구조, 설비) 안내서」 p.24 그림6:
      분진 발생 지역 → **통로 30Pa > 작업실 15Pa** (일반 Cascade 와 정반대)
  - 같은 안내서 p.60 (시행규칙 제5조 해설):
      특수제제는 "공기의 차압을 이용하여 **내부의 분진이 확산되지(외부로 빠져나가지) 않도록**"
  - 1차 미팅(2026-07-09) 대표님:
      "복도가 높고 여기가 낮다… 복도에 있는 공기가 룸 안으로 들어가야 돼"
  - 상세: 법규/조문근거_색인.md A-4, A-5절

한계(정직)
  방 '이름'으로 공정을 추론한다. 이름은 회사마다 다르다(타정실=타블렛실=정제실).
  → 프로파일(profiles/*.yaml)로 덮어쓸 수 있게 하고, 추론 결과는 regime_source='inferred' 로
    표시해 감사에서 구분한다. **확정이 아니라 추정이다.**
"""
from __future__ import annotations

import re

PROTECT = "protect"
CONTAIN = "contain"
HAZARD = "hazard"
NEUTRAL = "neutral"          # 압력 관리 대상 아님(복도, 보관소, 기계실 등)

# 분진이 나는 공정 → 봉쇄(실이 저압)
#   근거: 2010 안내서 p.33 "분진이 발생하는 작업실에는 국소집진시설을 설치할 것",
#         p.8 그림2(핵심지역=정립, 타정, 충전 / 중요지역=혼합, 과립, 칭량)
#
#   '충전/충진' 은 일부러 뺐다 — **시설 종류에 따라 정반대다.**
#     내용고형제의 '캡슐 충전' = 분말 → 분진(봉쇄)
#     무균제제의 '바이알 충진' = 액체 → 분진 없음(보호)
#     이름만으로는 못 가른다. **프로파일(regime_overrides)로 지정할 것.**
#     '건조' 도 같은 이유로 뺐다(동결건조는 무균 공정).
#   회사마다 **이름이 다르다.** 1차 미팅(2026-07-09) 대표님:
#     "이게 우리나라 말로 **타정실**이고, **어떤 회사는 그냥 '타블렛 4' 이렇게도 써놓거든요.**
#      정제를 뜻하는 거라서 **회사마다 그런 명칭이 다 틀려요.**"
#   → 한글만 보면 대량 데이터에서 바로 깨진다. **동의어를 넣는다.**
#     프로파일의 `name_synonyms` 로 더 넣을 수 있다(코드 수정 없이).
DUST_WORDS = (
    # 칭량, 계량 (weighing / dispensing)
    "칭량", "계량", "평량", "WEIGH", "DISPENS",
    # 혼합, 배합 (mixing / blending)
    "혼합", "배합", "MIX", "BLEND",
    # 과립, 조립 (granulation)
    "과립", "조립", "GRANUL",
    # 정립, 분쇄 (sizing / milling)
    "정립", "분쇄", "파쇄", "MILL", "SIZING",
    # 타정, 정제, 타블렛 (tableting)  ← 대표님이 직접 든 예
    "타정", "정제", "타블렛", "타블렛팅", "압축", "TABLET", "COMPRESS", "TABLETING",
    # 코팅 (coating)
    "코팅", "COAT",
    # 선별 (sorting / inspection)
    "선별", "SORT",
    # 제립
    "제립",
    # 캡슐 충전은 분진이지만 '충전'은 시설에 따라 정반대라 여기 안 넣는다(아래 주석 참조)
)

# 특수제제 → 음압 격리
#   근거: 시설기준령 시행규칙 제2조①1호, 제5조
HAZARD_WORDS = (
    "페니실린", "PENICILLIN", "세팔로스포린", "CEPHALOSPORIN",
    "카바페넴", "CARBAPENEM", "모노박탐", "MONOBACTAM",
    "성호르몬", "호르몬", "HORMONE",
    "세포독성", "CYTOTOX", "항암", "ONCOLOG",
    "베타락탐", "BETA-LACTAM", "BETALACTAM",
)

# 압력 관리 대상이 아닌 공간
#   근거: 2010 안내서 p.5(보관소는 GMP 영역이나 **청정도 관리 불요**)
#         - p.37(청정도 관리가 요구되지 않는 예시), 새GMP규정 Q&A 문15
#   ※ 복도는 '중립'이 아니라 **기준면**이다. 봉쇄 검사에서 비교 대상이므로 따로 표시한다.
#
#   낱말은 **숫자가 끼어도 걸리게** 짧게 잡는다.
#     '기계실'로 뒀더니 실제 도면의 `기계1실`, `기계 2실`을 놓쳤다(보호형으로 오분류).
#     `공조실`, `집진기실`, `외조기실` 같은 설비실도 통째로 빠져 있었다.
NEUTRAL_WORDS = (
    "보관", "창고",
    "기계", "공조", "외조기", "집진", "전기", "설비", "펌프", "보일러",
    "P.S", "PS", "샤프트", "덕트", "계단", "엘리베이터", "승강기", "방풍",
    "사무", "휴게", "식당", "화장실", "예비", "다용도",
    # '대기': `칭량 전 원료대기실` 처럼 원료, 반제품이 **밀봉된 채 머무는** 방.
    #         공정을 하는 방이 아니다 → 압력 관리 대상이 아니다.
    "대기",
)
CORRIDOR_WORDS = ("복도", "통로", "회랑", "CORRIDOR", "HALLWAY", "PASSAGE")

# 분진 낱말이 들어 있어도 **그 공정을 하는 방이 아닌** 경우 (2026-07-14 추가)
#
# 기준 시설에서 실제로 오탐이 무더기로 났다:
#     `(N)칭량 전 원료대기실`   원료가 아직 봉지에 밀봉돼 있다. 분진이 날 리 없다
#     `(N)칭량 후 원료대기실`   칭량이 끝난 원료가 대기하는 방
#     `(N)반제품 보관실(선별전)` 보관실이지 선별실이 아니다
#     `(N)타정1실 전실`          에어락이지 타정실이 아니다 (전실만 6개)
#     `(N)코팅기계1실`           설비가 놓인 방
#
# 공통점: **한국어 합성명사는 마지막 명사가 머리말(head)** 이다.
#   `칭량 전 원료대기실` 의 머리말은 '대기실' 이지 '칭량' 이 아니다.
#   그러니 "낱말이 어디든 들어 있으면"이 아니라 **머리말을 봐야** 한다.
#
# 부정은 **분진 판정만 취소**한다. 그 뒤 판별은 계속 흘러간다.
#   → `타정1실 전실` 은 중립이 아니라 **보호(protect)** 로 간다.
#     에어락은 압력 관리 대상이다(오히려 압력 단계의 핵심). 중립으로 빼면
#     '분진이 에어락으로 새는' 진짜 위반을 놓친다.
#   → `칭량 전 원료대기실` 은 '대기' 가 중립 낱말이라 중립으로 간다.
NEGATION_HEADS = (
    "전실", "에어락", "에어록",
    "대기실", "보관실", "보관소", "저장실", "창고", "기계실",
)

# '액(液)' — 분진 낱말 바로 뒤에 붙으면 **액체**다. 분말이 아니다.
#     `과립액 조제1실` = 결합액을 만드는 방, `코팅액 조제2실` = 코팅 용액을 만드는 방
#   [주의] **보류, 발주처 확인 필요**: 용액을 만들 때도 고분자 분말을 붓는 순간이 있다.
#     설계사가 이 방을 어떻게 관리하는지 물어야 한다. 지금은 '분진 아님'으로 둔다.
LIQUID_SUFFIX = "액"

# 괄호 안은 **꾸밈말**이지 머리말이 아니다: `(N)` `(예비)` `(선별전)` `(Bin/DRUM 포함)`
_PAREN = re.compile(r"[（(\[][^）)\]]*[）)\]]")
# 숫자는 방 번호일 뿐이다: `코팅기계1실` → `코팅기계실`, `타정 3실` → `타정실`
_DIGIT = re.compile(r"\d+")


def head_form(name: str | None) -> str:
    """머리말 비교용 정규형: 괄호, 공백, 숫자를 턴다.

        '(N)반제품 보관실(선별전)' → '반제품보관실'
        '(N)코팅 기계 2실'         → '코팅기계실'
        '(N)선별 3실(예비)'        → '선별실'
    """
    n = _PAREN.sub("", name or "")
    n = _DIGIT.sub("", n)
    # 대소문자를 무시한다. `Tablet Room`, `TABLETTING`, `tablet` 이 다 같은 말이다.
    #   (영문 동의어를 넣고도 대소문자 때문에 안 잡혀서 한 번 당했다)
    return n.replace(" ", "").upper()


def is_corridor(name: str | None) -> bool:
    """복도인가. 봉쇄 검사의 '기준면'이 된다."""
    if not name:
        return False
    n = name.replace(" ", "").upper()
    return any(w.replace(" ", "").upper() in n for w in CORRIDOR_WORDS)


def is_dust_process(name: str | None) -> bool:
    """분진이 나는 **공정을 하는 방**인가. 이름에 낱말이 들었는지가 아니다."""
    h = head_form(name)                   # 대문자로 정규화돼 돌아온다
    if not h:
        return False
    if any(h.endswith(w.upper()) for w in NEGATION_HEADS):
        return False                      # 대기실, 보관실, 전실, 기계실 = 공정실이 아니다
    for w in DUST_WORDS:
        i = h.find(w.upper())
        if i < 0:
            continue
        # '과립액' '코팅액' = 액체다. 분말 공정이 아니다.
        if h[i + len(w):].startswith(LIQUID_SUFFIX.upper()):
            continue
        return True
    return False


def infer_regime(name: str | None, grade: str | None = None) -> str:
    """방 이름(+등급)으로 압력 유형을 **추정**한다.

    우선순위: **특수제제 > 복도 > 분진공정 > 중립 > 보호(기본)**

    순서가 전부 시행착오로 정해졌다. 세 번 틀렸다:
      ① 분진공정을 복도보다 먼저 봤다 → `정립실복도` 를 봉쇄실로 오판.
         **복도가 먼저**여야 한다. 정립실복도는 복도지 정립실이 아니다.
      ② 중립을 분진공정보다 먼저 봤다 → `선별 3실(예비)` 가 '예비' 때문에 중립으로 빠졌다.
         **분진이 중립보다 먼저**여야 한다. 예비든 뭐든 선별실은 분진이 난다.
      ③ 낱말이 들어 있기만 하면 분진이라 봤다 → `칭량 전 원료대기실`, `타정1실 전실`, `반제품 보관실(선별전)`, `코팅기계1실` 을 전부 봉쇄실로 오판(기준 시설에서 10방).
         **머리말을 봐야 한다** (is_dust_process). 한국어는 마지막 명사가 머리말이다.
    """
    n = (name or "").replace(" ", "").upper()   # 대소문자 무시

    if any(w.upper() in n for w in HAZARD_WORDS):
        return HAZARD
    if is_corridor(name):
        return NEUTRAL
    if is_dust_process(name):
        return CONTAIN
    if any(w.upper() in n for w in NEUTRAL_WORDS):
        return NEUTRAL
    return PROTECT


def resolve_regime(name: str | None, grade: str | None,
                   overrides: dict[str, str] | None = None,
                   room_no: str | None = None) -> tuple[str, str]:
    """(regime, source) 를 돌려준다. 프로파일 override 가 추론을 이긴다."""
    if overrides and room_no and room_no in overrides:
        return overrides[room_no], "profile"
    return infer_regime(name, grade), "inferred"


# ── 에어락(전실) 판별 — 여러 규칙이 함께 쓴다 ──────────────────────
AIRLOCK_WORDS = ("전실", "에어락", "에어록", "air lock", "airlock", "AIRLOCK",
                 "패스박스", "pass box", "PASSBOX", "PASS-BOX",
                 "해치", "hatch", "ANTEROOM", "AIR SHOWER", "에어샤워")

# `전실` 은 **다른 낱말에 끼어 있다.**
#     `무균 **충전실**`, `캡슐 **충전실**`, `**변전실**`, `**발전실**`
#   전부 '전실'을 품고 있지만 **에어락이 아니다.**
#
#   시험이 잡았다. 이걸 놓치면 **에어락으로 오인해 그 방을 검사에서 빼버린다** —
#   ADJ-001(등급 급변)은 예외 처리하고, ADJ-002(갱의실 우회)는 관문으로 취급해
#   **진짜 위반을 숨긴다.** 거짓 위반보다 더 나쁘다(놓치는 쪽이니까).
NOT_AIRLOCK = ("충전실", "충진실", "변전실", "발전실", "수전실", "배전실")


def is_airlock(name: str | None, words=AIRLOCK_WORDS,
               not_words=NOT_AIRLOCK) -> bool:
    """에어락, 전실, 패스박스인가.

    부정 낱말(`충전실`, `변전실`)은 **머리말로만** 걸러야 한다. 무차별 부분문자열로
      걸렀다가 **진짜 에어락을 부정하는 새 버그**를 만들었다:

          `캡슐충전실 전실`  = 충전실의 **에어락**인데 → '충전실'이 들어 있다고 부정
          (기준 시설에 `타정1실 전실` 같은 이름이 6개나 있다. `캡슐충전실 전실`도 나올 수 있다)

      그러면 무슨 일이 나나 — **셋 다 나쁘다**:
          ADJ-001  예외 처리가 안 돼 **거짓 위반**(등급 급변)
          ADJ-002  관문으로 안 끊어 **거짓 위반**(갱의실 우회)
          ADJ-005  에어락이 아니라며 인터락 검사에서 빼 **진짜 위반을 놓침**

      → 한국어는 **마지막 명사가 머리말**이다. `캡슐충전실 전실` 의 머리말은 '전실'이고,
        `무균 충전실` 의 머리말은 '충전실'이다. **머리말로 가른다.**
    """
    if not name:
        return False
    h = head_form(name)                   # 괄호, 숫자, 공백 제거 + 대문자
    if not h:
        return False
    # 부정: **머리말이** 충전실, 변전실 …이면 에어락이 아니다
    if any(h.endswith(w.upper()) for w in not_words):
        return False
    return any(w.replace(" ", "").upper() in h for w in words)


def extend_from_profile(profile: dict) -> None:
    """프로파일의 `name_synonyms` 로 낱말 목록을 **넓힌다**. 코드 수정 없이.

    회사마다 이름이 다르다(대표님: "타정실 = 어떤 회사는 타블렛"). 대량 데이터가 오면
    우리가 모르는 이름이 반드시 나온다. 그때 **프로파일만 고쳐서** 받는다.

        name_synonyms:
          dust:    [압출, 건식과립]      # 분진 공정에 추가
          hazard:  [스테로이드]
          neutral: [린넨실, 폐기물실]
          airlock: [버퍼존]              # 대표님이 쓴 말이다
          corridor: [진입로]

    [주의] 목록은 **모듈 전역**이라 한 번 넓히면 그 프로세스 내내 유지된다.
      시설마다 다른 낱말을 쓰면 서로 섞인다 — 지금은 시설을 한 번에 하나씩만
      처리하므로 문제없다. 동시에 여러 시설을 돌리게 되면 이 설계를 바꿔야 한다.
    """
    global DUST_WORDS, HAZARD_WORDS, NEUTRAL_WORDS, CORRIDOR_WORDS, AIRLOCK_WORDS
    syn = profile.get("name_synonyms") or {}
    if not syn:
        return
    def add(cur, key):
        extra = tuple(str(w) for w in (syn.get(key) or []))
        return cur + tuple(w for w in extra if w not in cur)
    DUST_WORDS = add(DUST_WORDS, "dust")
    HAZARD_WORDS = add(HAZARD_WORDS, "hazard")
    NEUTRAL_WORDS = add(NEUTRAL_WORDS, "neutral")
    CORRIDOR_WORDS = add(CORRIDOR_WORDS, "corridor")
    AIRLOCK_WORDS = add(AIRLOCK_WORDS, "airlock")
