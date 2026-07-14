# -*- coding: utf-8 -*-
"""**기준 시설 잠금 시험** - 실도면에서 나와야 하는 숫자를 못 박는다. 신규 (2026-07-14).

## 왜 이 파일이 있나

전수 감사에서 가장 큰 구멍으로 나왔다:

    기준값(번호방 111, LBL 3/17)이 **주석에만** 있었다.
    이 숫자들이 이미 **진짜 버그를 두 번** 잡았는데 - 자동 시험은 **0개**였다.

        ① 기둥 블록 오염     방이 111 → 163 으로 부풀었다
        ② 3F 도면 유실       방이 111 → 60 으로 줄었다

    사람이 눈으로 대조해서 잡았다. 다음에 못 잡으면? 조용히 틀린 채로 간다.

## 이 시험이 지키는 것

    번호방 111개  = 3F 51 + 4F 60
    LBL-001 위반   3건   (평면도 ↔ 차압도 이름 불일치)
    LBL-002 위반  17건   (한쪽 도면에만 있는 방)

이 숫자가 바뀌면 **둘 중 하나**다 - 추출기가 깨졌거나, 우리가 의도해서 고쳤거나.
어느 쪽이든 **사람이 봐야 한다.** 그래서 시험이 실패해야 한다.

숫자를 고칠 땐 **왜 바뀌었는지 여기 적고** 바꿔라. 그냥 맞추지 마라.

## 조용한 skip 을 금지한다

DB 나 도면이 없으면 `pytest.skip` 한다 - 여기까진 정상이다.
그러나 **CI 에서 전부 skip 되면 초록불인데 아무것도 안 지켜진다.**

    → `GXPAI_REQUIRE_BASELINE=1` 을 켜면 skip 이 **실패**가 된다.
      개발 기계에선 skip, CI 에선 반드시 돌게 한다.
"""
from __future__ import annotations

import os

import pytest

FACILITY = "f_1ae3a266"        # 기준 시설 (내용고형제, 3, 4층)

# ── 못 박는 숫자 ──────────────────────────────────────────────────
ROOMS_TOTAL = 111             # 번호가 붙은 방
ROOMS_BY_FLOOR = {"3F": 51, "4F": 60}
LBL_001_COUNT = 3             # 평면도 ↔ 차압도 이름 불일치
LBL_002_COUNT = 17            # 한쪽 도면에만 있는 방


def _required() -> bool:
    return os.environ.get("GXPAI_REQUIRE_BASELINE") == "1"


def _skip_or_fail(why: str):
    """개발 기계에선 건너뛰고, CI(GXPAI_REQUIRE_BASELINE=1)에선 **실패**시킨다.

    `except Exception: pytest.skip()` 으로 뭉뚱그리면 **fixture 가 고장나도 초록불**이다.
      실제로 다른 시험 파일에서 그러고 있었다. 여기선 이유를 남기고 CI 에선 터뜨린다.
    """
    if _required():
        pytest.fail(f"기준값 시험이 돌지 못했다 (GXPAI_REQUIRE_BASELINE=1): {why}")
    pytest.skip(why)


@pytest.fixture(scope="module")
def baseline_run():
    """기준 시설의 **가장 최근 run** 에서 방, 위반을 읽는다."""
    try:
        from gxpai.core.db import connect
    except ImportError as exc:
        _skip_or_fail(f"gxpai.core.db 를 import 할 수 없다: {exc}")

    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM run WHERE facility_id=%s "
                "ORDER BY started_at DESC LIMIT 1", (FACILITY,))
            row = cur.fetchone()
            if not row:
                _skip_or_fail(f"기준 시설의 run 이 DB 에 없다: {FACILITY} "
                              f"(먼저 `python -m gxpai.cli ingest` 를 돌려라)")
            run_id = row[0]

            cur.execute(
                "SELECT room_no, floor FROM room "
                "WHERE run_id=%s AND room_no IS NOT NULL", (run_id,))
            rooms = cur.fetchall()

            cur.execute(
                "SELECT rule_id, COUNT(*) FROM violation "
                "WHERE run_id=%s GROUP BY rule_id", (run_id,))
            viol = dict(cur.fetchall())
    except pytest.skip.Exception:
        raise
    except Exception as exc:                       # noqa: BLE001
        _skip_or_fail(f"DB 에 연결할 수 없다: {exc}")

    return {"run_id": run_id, "rooms": rooms, "violations": viol}


# ── 방 개수 ──────────────────────────────────────────────────────
def test_번호방이_111개다(baseline_run):
    """기둥 블록이 섞여 들어와 163 개가 된 적이 있다(블록 재귀를 켰을 때).
    3F 도면을 통째로 놓쳐 60 개가 된 적도 있다(시트 x 원점 오프셋 처리 누락)."""
    n = len(baseline_run["rooms"])
    assert n == ROOMS_TOTAL, (
        f"번호방이 {n}개다 (기대 {ROOMS_TOTAL}). "
        f"더 많으면 → 방이 아닌 것(기둥, 설비 블록)이 섞였다. "
        f"더 적으면 → 시트나 층을 통째로 놓쳤다. "
        f"의도한 변경이면 이 파일의 ROOMS_TOTAL 을 **이유와 함께** 고쳐라")


def test_층별_방_개수가_3F_51_4F_60이다(baseline_run):
    """총합만 맞고 층 배분이 틀릴 수 있다 - 층 판정(시트 타이틀 x좌표)이 깨지면 그렇게 된다."""
    got: dict[str, int] = {}
    for _no, floor in baseline_run["rooms"]:
        got[floor or "?"] = got.get(floor or "?", 0) + 1
    assert got == ROOMS_BY_FLOOR, (
        f"층별 방 개수가 {got} 다 (기대 {ROOMS_BY_FLOOR}). "
        f"'?' 가 있으면 층 판정(시트 타이틀 매칭)이 실패한 것이다")


def test_방번호가_중복되지_않는다(baseline_run):
    """`_merge` 가 방번호 중복 시 **조용히 덮어썼다.** 같은 번호가 두 층에 있으면
    한쪽이 사라진다. 총 개수만 보면 안 보이는 버그다."""
    nos = [no for no, _f in baseline_run["rooms"]]
    dup = {n for n in nos if nos.count(n) > 1}
    assert not dup, f"방번호가 중복됐다: {sorted(dup)} - 병합 때 한쪽이 덮어써진다"


# ── 위반 개수 ────────────────────────────────────────────────────
def test_LBL_001_위반이_3건이다(baseline_run):
    """평면도 ↔ 차압도 **이름 불일치**. 정규화를 건드리면 이 숫자가 움직인다.

    실제로 정규화를 고칠 때(맨 N 삭제 → 괄호 N 만 삭제) 이 숫자를 손으로 재확인했다.
      이제 자동으로 지킨다."""
    n = baseline_run["violations"].get("LBL-001", 0)
    assert n == LBL_001_COUNT, (
        f"LBL-001 이 {n}건이다 (기대 {LBL_001_COUNT}). "
        f"이름 정규화(_norm)를 건드렸는가? 늘었으면 **거짓 위반**, "
        f"줄었으면 **놓친 위반**일 수 있다")


def test_LBL_002_위반이_17건이다(baseline_run):
    """한쪽 도면에만 있는 방.

    이 숫자가 **51 건**이 된 적이 있다 - 차압도 추출기가 방번호 정규식을 하드코딩해서
      참고도면(방번호가 `F2I01` 꼴)의 차압도 방을 **0개**로 읽었다.
      그 거짓 위반 51건이 **실제로 DB 에 적재됐다**(LBL-002 는 게이트가 열려 있다).
      미리보기만 돌리고 validate 를 안 돌려봐서 놓쳤다."""
    n = baseline_run["violations"].get("LBL-002", 0)
    assert n == LBL_002_COUNT, (
        f"LBL-002 가 {n}건이다 (기대 {LBL_002_COUNT}). "
        f"차압도 방이 0개로 읽히면 이 숫자가 폭증한다 - 방번호 정규식을 확인하라")


# ── 게이트 ───────────────────────────────────────────────────────
def test_미검수_규칙은_DB에_위반을_쓰지_않는다(baseline_run):
    """**동결 게이트.** `review: unreviewed` 규칙은 컨설턴트 검수 전이다.
    돌리면 틀린 규칙이 위반 이력을 오염시킨다. 미리보기(preview_rules.py)로만 본다.

    LBL-002 가 51건의 거짓 위반을 DB 에 적재한 사고가 바로 이 게이트의 존재 이유다
      (그건 review: internal 이라 게이트가 열려 있었다)."""
    from pathlib import Path

    import yaml

    rules_path = Path(__file__).resolve().parents[1] / "rules" / "gmp_osd_v1.yaml"
    if not rules_path.exists():
        _skip_or_fail(f"규칙 파일이 없다: {rules_path}")

    rules = yaml.safe_load(rules_path.read_text(encoding="utf-8"))["rules"]
    unreviewed = {
        r["id"] for r in rules
        if r.get("review") == "unreviewed" and not (r.get("config") or {}).get("enabled")
    }
    wrote = unreviewed & set(baseline_run["violations"])
    assert not wrote, (
        f"미검수 규칙이 DB 에 위반을 적재했다: {sorted(wrote)}. "
        f"게이트가 열렸는지, 엔진의 게이트 검사가 깨졌는지 확인하라")


# ── 방번호 충돌 ──────────────────────────────────────────────────
def test_방번호_충돌을_조용히_덮어쓰지_않는다():
    """`_merge` 가 같은 방번호를 **말없이 덮어썼다.**

    기준 시설은 번호에 층이 들어간다(3101=3층, 4101=4층) → 충돌이 없다.
    **우리 번호 체계가 마침 안전했을 뿐이다.**

    층마다 101, 102 로 매기는 사무소가 오면 3층 101 과 4층 101 이 같은 키가 되어
    **한쪽이 통째로 사라진다.** 예외도 로그도 0건도 아니다 - 방 개수가 조용히 줄 뿐이다.
    """
    from gxpai.core.run import _merge

    floor_rooms = [
        {"room_no": "101", "name": "타정실", "floor": "3F", "sheet": None,
         "plan_x": 0.0, "plan_y": 0.0},
        {"room_no": "101", "name": "포장실", "floor": "4F", "sheet": None,
         "plan_x": 9.0, "plan_y": 9.0},        # ← 같은 번호, 다른 층
    ]
    collisions: list[dict] = []
    merged = _merge(floor_rooms, [], collisions)

    assert len(merged) == 1                     # 여전히 한쪽이 덮어써진다(현 동작)
    assert len(collisions) == 1, \
        "충돌을 감지하지 못하면 방이 사라져도 아무도 모른다"
    c = collisions[0]
    assert c["room_no"] == "101"
    assert c["lost_name"] == "타정실"            # 먼저 온 쪽이 사라진다
    assert c["kept_name"] == "포장실"
    # 거리로 **서로 다른 방**인지 가른다. LBL-003 이 이 값을 쓴다.
    assert c["dist_mm"] is not None and c["dist_mm"] > 12


def test_기준시설은_방번호_충돌이_없다(baseline_run):
    """기준 시설에서는 충돌이 없어야 한다 - 있으면 방이 이미 사라진 것이다."""
    nos = [no for no, _f in baseline_run["rooms"]]
    assert len(nos) == len(set(nos))
