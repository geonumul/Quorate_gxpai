# -*- coding: utf-8 -*-
"""규칙 로드 → checks 동적 실행 → violation 적재.

로드맵: T2.3.2 (필수 납품 코어)
설계(ACC 논문 반영): 규칙은 데이터(rules/*.yaml), 실행은 결정론적 코드(checks/<rule_id>.py).
LLM 은 규칙 '해석/초안'에만 쓰고 실행은 코드가 한다(N2/C6: LLM-RAG 단독 수치추론 한계).
각 check 모듈은 run(cur, run_id, facility_id, rule) -> list[dict] 를 제공한다.
반환 dict: {severity, rooms(list), message, evidence(dict)}.
"""
from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import yaml
from psycopg.types.json import Json

from ..core.db import connect


def _load_ruleset(ruleset: str) -> dict:
    root = Path(__file__).resolve().parents[2]
    path = root / "rules" / f"{ruleset}.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _latest_run(cur, facility_id: str) -> str | None:
    cur.execute("SELECT id FROM run WHERE facility_id=%s ORDER BY started_at DESC, id DESC LIMIT 1",
                (facility_id,))
    row = cur.fetchone()
    return row[0] if row else None


def validate(facility_id: str, ruleset: str = "gmp_osd_v1", run_id: str | None = None) -> dict:
    """활성 규칙을 실행해 violation 테이블에 적재하고 요약을 반환.

    ★★게이트가 **두 겹**이다. 예전엔 둘 다 없었다.

    ① **동결 게이트** (`review`)
       규칙 YAML 머리말이 *"unreviewed = 게이트로 잠금"* 이라고 선언해 놓고,
       엔진은 `review` 를 **읽지도 않았다.** 각 체크 모듈이 스스로 `cfg["enabled"]` 를
       확인하는 **관례**에만 의존했다.
       → 새 모듈이 그 확인을 빠뜨리면 **미검수 규칙이 조용히 DB에 위반을 적재**한다.
       → 엔진이 직접 막는다.

    ② **제형 게이트** (`applies_to`)
       ★가장 심각했던 결함. 법규 코퍼스를 검색해 확인했다 —
       **별표17(완제)에 '청정등급'·'차압계'·'인터락' 조문이 0건**인데,
       우리 규칙 5종이 **별표1(무균)** 조문으로 **완제 시설(내용고형제)** 을 판정하고 있었다.
       ADJ-002 의 조문은 아예 "**무균의약품 제조는**…" 으로 시작한다.
       → 시설의 제형과 규칙의 제형이 안 맞으면 **판정하지 않는다.**

    그리고 **"0건"과 "잠김"과 "적용 대상 아님"을 구분해서** 요약에 담는다.
    구분하지 않으면 리포트를 읽는 사람이 **"검사했는데 깨끗하다"** 로 오해한다.
    """
    from ..core import registry
    from .checks._scope import applies, product_scope, why_not

    rs = _load_ruleset(ruleset)
    summary = {"ruleset": ruleset, "run_id": run_id, "by_rule": {}, "total": 0,
               "skipped": [], "gated": [], "not_applicable": []}

    fac = registry.get_facility(facility_id) or {}
    ptype = fac.get("product_type")
    if not ptype:
        # 프로파일에 있을 수도 있다
        try:
            from ..core.config import load_profile
            ptype = (load_profile(fac.get("profile_id") or "") or {}).get("product_type")
        except Exception:      # noqa: BLE001
            ptype = None
    fscope = product_scope(ptype)

    with connect() as conn, conn.cursor() as cur:
        rid = run_id or _latest_run(cur, facility_id)
        if not rid:
            raise ValueError(f"실행(run)이 없습니다: {facility_id}. 먼저 ingest 하세요.")
        summary["run_id"] = rid

        # 멱등: 이 run 의 기존 violation 제거 후 재적재
        cur.execute("DELETE FROM violation WHERE run_id=%s", (rid,))

        for rule in rs.get("rules", []):
            rid_name = rule["id"]
            module_name = rid_name.lower().replace("-", "_")
            full_name = f"gxpai.compliance.checks.{module_name}"
            # 모듈 '존재 여부'만 find_spec 으로 판정한다. 예전엔 import 를 통째로 try/except 해서,
            # 체크 모듈이 존재하지만 내부에서 오타난 의존성을 import 하다 난 ModuleNotFoundError 까지
            # '미구현'으로 삼켜 규칙이 조용히 사라졌다(수정됨). 이제 그런 진짜 오류는 전파된다.
            if importlib.util.find_spec(full_name) is None:
                summary["skipped"].append(f"{rid_name}(미구현)")
                continue
            mod = importlib.import_module(full_name)
            if not hasattr(mod, "run"):
                summary["skipped"].append(f"{rid_name}(run 없음)")
                continue

            cfg = rule.get("config") or {}

            # ① 동결 게이트 — 컨설턴트 미검수 규칙은 **엔진이 막는다**
            if rule.get("review") == "unreviewed" and not cfg.get("enabled"):
                summary["gated"].append(rid_name)
                continue

            # ② 제형 게이트 — 무균 조문으로 완제 시설을 판정하지 않는다
            if not applies(cfg, fscope):
                summary["not_applicable"].append(
                    f"{rid_name}: {why_not(cfg, fscope, ptype)}")
                continue

            found = mod.run(cur, rid, facility_id, rule) or []
            # 근거 추적성(audit trail): 위반이 어느 조항·요구에서 왔는지를 위반 레코드에 함께 새긴다.
            # 규칙 YAML 이 나중에 바뀌어도 판정 당시의 근거가 보존된다.
            prov = {
                "clause": rule.get("clause"),
                "review": rule.get("review"),
                "requirement": (rule.get("rase") or {}).get("requirement"),
            }
            for v in found:
                evidence = dict(v.get("evidence", {}))
                evidence["_rule"] = prov
                cur.execute(
                    """INSERT INTO violation (run_id, rule_id, severity, rooms, message, evidence, status)
                       VALUES (%s,%s,%s,%s,%s,%s,'open')""",
                    (rid, rid_name, v.get("severity", rule.get("severity", "minor")),
                     Json(v.get("rooms", [])), v.get("message", ""),
                     Json(evidence)),
                )
            summary["by_rule"][rid_name] = len(found)
            summary["total"] += len(found)

        conn.commit()
    return summary
