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
    """활성 규칙을 실행해 violation 테이블에 적재하고 요약을 반환."""
    rs = _load_ruleset(ruleset)
    summary = {"ruleset": ruleset, "run_id": run_id, "by_rule": {}, "total": 0, "skipped": []}

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
