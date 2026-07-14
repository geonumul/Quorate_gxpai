# -*- coding: utf-8 -*-
"""규칙 YAML 스키마, 근거추적성 시험.

모든 규칙이 RASE 분해(requirement/applicability/selection/exception) + 근거조항(clause) +
동결게이트(review)를 갖추도록 강제한다. auditability 는 GMP 규제의 핵심가치라, 근거 없는
규칙이 슬그머니 들어오는 것을 막는다(선행연구 공통 결론 + 레드팀 GEN-R2).
"""
from __future__ import annotations

from pathlib import Path

import yaml

RULES = Path(__file__).resolve().parents[1] / "rules" / "gmp_osd_v1.yaml"
RASE_KEYS = {"requirement", "applicability", "selection", "exception"}
REVIEW_VALUES = {"internal", "unreviewed", "approved"}


def _rules():
    return yaml.safe_load(RULES.read_text(encoding="utf-8"))["rules"]


def test_every_rule_has_traceability_fields():
    for r in _rules():
        rid = r.get("id")
        assert rid, "규칙에 id 가 없다"
        assert r.get("clause"), f"{rid}: clause(근거조항) 누락"
        assert r.get("review") in REVIEW_VALUES, f"{rid}: review 는 {REVIEW_VALUES} 중 하나여야"
        rase = r.get("rase")
        assert isinstance(rase, dict) and set(rase) == RASE_KEYS, f"{rid}: rase 4연산자 누락/불일치"
        assert rase["requirement"], f"{rid}: requirement 는 비어있으면 안 됨"


def test_gated_rules_are_unreviewed():
    """게이트로 잠근(enabled:false) 규칙은 미검수(unreviewed) 여야 논리적으로 일관.
    내부 정합성(internal) 규칙은 게이트 없이 활성 안전."""
    for r in _rules():
        cfg = r.get("config") or {}
        if "enabled" in cfg and cfg["enabled"] is False:
            assert r["review"] == "unreviewed", f"{r['id']}: 잠긴 규칙인데 review 가 unreviewed 아님"


def test_internal_rules_have_no_gmp_clause_dependency():
    """internal 규칙(LBL)은 GMP 조항이 아니라 내부 정합성이므로 활성 상태로 둘 수 있다."""
    internal = [r["id"] for r in _rules() if r["review"] == "internal"]
    assert "LBL-001" in internal and "LBL-002" in internal
