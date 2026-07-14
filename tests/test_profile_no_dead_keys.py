# -*- coding: utf-8 -*-
"""프로파일에 **아무도 안 읽는 키**가 있으면 실패한다. 신규 (2026-07-14).

## 왜

전수 감사에서 나왔다. `profiles/ref_2f_2026.yaml` 에 이렇게 적혀 있었다:

    hvac:
      ahu_layers: []          # ← **완전히 죽은 키다**

hvac 추출기는 `ahu_layer_prefix` 와 `ahu_tag_regex` 만 읽는다. `ahu_layers` 는
**어디서도 읽지 않는다.** 프로파일 작성자는 이걸로 AHU 추출을 껐다고 **믿고 있지만
아무 일도 일어나지 않는다** — 추출기는 기본 접두사 'AHU' 로 그냥 돈다.

이게 위험한 이유: **틀렸다는 신호가 하나도 없다.** 예외도, 경고도, 0건도 아니다.
프로파일이 거짓말을 하고 코드는 딴짓을 하는데 아무도 모른다.

오타도 같은 문제다. `room_no_regex` 를 `room_num_regex` 라고 쓰면 **조용히 무시**되고
기본값이 쓰인다 — 방번호가 하나도 안 잡히거나, 엉뚱한 게 잡힌다.

`profiles/_schema.yaml` 이 있긴 한데 **아무도 안 쓴다**(주석에 "CI에서 검증용"이라 써
놓고 검증하는 코드가 없다). 장식품이었다.

## 이 시험이 하는 일

프로파일의 모든 키를 모아, 코드 어딘가에서 **실제로 읽는지** 확인한다.
안 읽는 키가 있으면 **실패**한다 — 지우거나, 코드가 읽게 만들어라.
"""
from __future__ import annotations

import pathlib
import re

import pytest

yaml = pytest.importorskip("yaml")

ROOT = pathlib.Path(__file__).resolve().parents[1]
# ★`_schema.yaml` 은 프로파일이 아니라 **스키마 정의**($schema/type/properties)다 → 제외.
#   `_TEMPLATE.yaml` 은 **검사한다** — 템플릿에 죽은 키가 있으면 신규 사무소마다 번진다.
PROFILES = sorted(p for p in (ROOT / "profiles").glob("*.yaml")
                  if p.name != "_schema.yaml")

# 프로파일의 **최상위 구조 키** — 코드가 `profile["floorplan"]` 처럼 통째로 꺼내 쓴다.
# 이 이름들은 섹션 이름이지 설정값이 아니므로 따로 찾지 않는다.
SECTIONS = {
    "profile_id", "profile_version", "description", "floors",
    "floorplan", "pressure", "equipment", "hvac", "overview", "grades",
    "boundaries", "pressure_value", "gauge", "interlock", "airflow",
    "pressure_regime", "grade_zones", "name_synonyms", "sheets",
}

# 키가 아니라 **값**인 것들(등급 이름·방번호 등)은 검사 대상이 아니다.
SKIP_SECTIONS = {"floors", "grade_zones", "name_synonyms", "sheets"}


def _all_source() -> str:
    """gxpai/ 전체 소스를 한 덩어리로. 키를 여기서 찾는다."""
    buf = []
    for p in (ROOT / "gxpai").rglob("*.py"):
        buf.append(p.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(buf)


SOURCE = _all_source()


def _keys(node, path=""):
    """프로파일 dict 를 훑어 (키, 경로) 를 낸다. 값 dict 안으로는 안 들어간다."""
    if not isinstance(node, dict):
        return
    for k, v in node.items():
        here = f"{path}.{k}" if path else k
        yield k, here
        # 섹션 안의 dict 만 더 파고든다(예: pressure_regime.overrides 는 값이라 안 판다)
        if isinstance(v, dict) and here in SECTIONS:
            yield from _keys(v, here)


@pytest.mark.parametrize("path", PROFILES, ids=lambda p: p.name)
def test_프로파일에_죽은_키가_없다(path: pathlib.Path):
    """모든 키는 코드 어딘가에서 **실제로 읽혀야** 한다.

    ★`ahu_layers: []` 가 이 시험에 걸렸다. hvac 추출기는 `ahu_layer_prefix` 만 읽는다.
      프로파일 작성자는 이걸로 AHU 추출을 껐다고 믿었지만 **아무 일도 일어나지 않았다.**
    """
    prof = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    dead: list[str] = []
    for key, where in _keys(prof):
        top = where.split(".")[0]
        if top in SKIP_SECTIONS:
            continue
        if key in SECTIONS:
            continue                      # 섹션 이름은 코드가 통째로 꺼내 쓴다
        # 코드가 이 키를 문자열로 언급하는가 — `get("k")` · `["k"]` · `.get('k')`
        if re.search(rf"""["']{re.escape(key)}["']""", SOURCE):
            continue
        dead.append(where)

    assert not dead, (
        f"{path.name} 에 **아무도 안 읽는 키**가 있다: {dead}\n"
        f"  → 지우거나, 코드가 읽게 만들어라.\n"
        f"  이런 키는 **틀렸다는 신호를 하나도 안 준다** — 예외도 경고도 0건도 아니다.\n"
        f"  프로파일이 거짓말을 하고 코드는 딴짓을 하는데 아무도 모른다.\n"
        f"  (오타도 같다: `room_no_regex` → `room_num_regex` 로 쓰면 조용히 무시된다)")


def test_프로파일이_하나라도_있다():
    """glob 이 빈손이면 위 시험이 **전부 통과**해 버린다(검사할 게 없으니)."""
    real = [p for p in PROFILES if not p.name.startswith("_")]
    assert real, "프로파일이 하나도 없다 — 위 시험이 아무것도 안 지킨다"
