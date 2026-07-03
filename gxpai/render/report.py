# -*- coding: utf-8 -*-
"""단일 파일 HTML 리포트 - 중간보고 겸 포트폴리오 1호 산출물.

로드맵: T2.4.2
내용: 파이프라인 버전 스탬프 + 품질 지표(매칭률/귀속률 등) + violations 표(심각도 정렬)
      + 층별 SVG(방 점 + 위반 마커) + 데이터 정합성 경고 배너(미확정 규칙 명시).
CDN 금지, 단일 파일(스타일 인라인). ACC 논문(N2): 리포트에 근거·추론을 담는다.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

from ..core.config import repo_root
from ..core.db import connect
from .svg import render_floor

PIPELINE_VERSION = "0.1.0"

_CSS = """
:root{color-scheme:dark}
body{font-family:system-ui,'Malgun Gothic',sans-serif;background:#0b0d10;color:#e6e9ef;margin:0;padding:24px;line-height:1.5}
h1{font-size:20px;margin:0 0 4px} h2{font-size:15px;margin:24px 0 8px;color:#c7d0dd}
.sub{color:#8b95a5;font-size:13px}
.banner{background:#3a2a12;border:1px solid #7a5a1e;color:#f0c674;padding:10px 12px;border-radius:6px;margin:16px 0;font-size:13px}
table{border-collapse:collapse;width:100%;font-size:13px;margin:6px 0}
th,td{border:1px solid #232833;padding:5px 8px;text-align:left}
th{background:#151a22;color:#9aa4b2}
.metrics{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;margin:8px 0}
.metric{background:#12161d;border:1px solid #232833;border-radius:6px;padding:8px 10px}
.metric .v{font-size:18px;font-weight:600} .metric .k{font-size:11px;color:#8b95a5}
.sev-critical{color:#ff6b6b;font-weight:600}.sev-major{color:#f0a850}.sev-minor{color:#7bb0ff}
.svgwrap{overflow-x:auto;background:#0f1115;border:1px solid #232833;border-radius:6px;padding:8px;margin:6px 0}
.foot{color:#5f6875;font-size:11px;margin-top:24px}
"""


def _gated_rules(ruleset: str) -> list[dict]:
    """검수 대기(review=unreviewed)라 실행하지 않은 규칙 목록(근거·요구 포함)."""
    from ..compliance.engine import _load_ruleset
    try:
        rs = _load_ruleset(ruleset)
    except Exception:
        return []
    out = []
    for r in rs.get("rules", []):
        if r.get("review") == "unreviewed":
            rase = r.get("rase") or {}
            out.append({"id": r.get("id"), "title": r.get("title"),
                        "clause": r.get("clause"), "requirement": rase.get("requirement")})
    return out


def _metrics(cur, run_id, facility_id) -> dict:
    def one(sql, *a):
        cur.execute(sql, a)
        return cur.fetchone()[0]

    numbered = one("SELECT count(*) FROM room WHERE run_id=%s AND room_no IS NOT NULL", run_id)
    both = one("""SELECT count(*) FROM room WHERE run_id=%s AND room_no IS NOT NULL
                  AND plan_x IS NOT NULL AND pressure_name IS NOT NULL""", run_id)
    unnum = one("SELECT count(*) FROM room WHERE run_id=%s AND room_no IS NULL", run_id)
    eq_tot = one("SELECT count(*) FROM equipment WHERE run_id=%s", run_id)
    eq_att = one("SELECT count(*) FROM equipment WHERE run_id=%s AND room_id IS NOT NULL", run_id)
    ahu = one("SELECT count(*) FROM ahu WHERE run_id=%s", run_id)
    adj = one("SELECT count(*) FROM room_adjacency WHERE run_id=%s", run_id)
    arrows = one("SELECT count(*) FROM pressure_relation WHERE run_id=%s", run_id)
    ov = one("SELECT count(*) FROM facility_meta WHERE run_id=%s", run_id)
    return {
        "번호방": numbered, "양쪽도면 매칭": both, "무번호 공간": unnum,
        "장비(귀속/전체)": f"{eq_att}/{eq_tot}", "공조기(AHU)": ahu,
        "인접 간선": adj, "차압 화살표": arrows, "설계개요 항목": ov,
    }


def generate(facility_id: str, run_id: str | None = None) -> Path:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, name, profile_id FROM facility WHERE id=%s", (facility_id,))
        frow = cur.fetchone()
        fac_name = frow[1] if frow else facility_id
        if run_id is None:
            cur.execute("SELECT id FROM run WHERE facility_id=%s ORDER BY started_at DESC LIMIT 1",
                        (facility_id,))
            r = cur.fetchone()
            run_id = r[0] if r else None
        if not run_id:
            raise ValueError("실행(run) 없음. 먼저 ingest 하세요.")

        metrics = _metrics(cur, run_id, facility_id)

        cur.execute("""SELECT rule_id, severity, message, rooms, evidence FROM violation
                       WHERE run_id=%s ORDER BY
                         CASE severity WHEN 'critical' THEN 0 WHEN 'major' THEN 1 ELSE 2 END,
                         rule_id, id""", (run_id,))
        violations = cur.fetchall()

        cur.execute("""SELECT room_no, name, floor, plan_x, plan_y FROM room
                       WHERE run_id=%s AND plan_x IS NOT NULL ORDER BY floor, room_no""", (run_id,))
        rooms = [{"room_no": a, "name": b, "floor": c, "x": d, "y": e}
                 for a, b, c, d, e in cur.fetchall()]

        # 발주처 확인 대기: (a) 게이트로 잠긴 규칙(미검수), (b) DB 미결 질문
        cur.execute("SELECT topic, body FROM question WHERE facility_id=%s AND status='open' ORDER BY id",
                    (facility_id,))
        open_questions = cur.fetchall()
    gated_rules = _gated_rules("gmp_osd_v1")

    viol_room_nos = set()
    for _rid, _sev, _msg, rooms_json, _ev in violations:
        for rn in (rooms_json or []):
            viol_room_nos.add(str(rn))

    # 조립
    esc = html.escape
    out = [f"<h1>GXPAI 규정 검증 리포트 - {esc(fac_name)}</h1>"]
    out.append(f'<div class="sub">facility={esc(facility_id)} · run={esc(run_id)} · '
               f'pipeline v{PIPELINE_VERSION}</div>')

    out.append('<div class="banner">데이터 정합성 경고: 방 경계 폴리곤(XREF 벽체 미수령)과 '
               '청정등급(Grade) 도면 미확보, 차압 화살표 방향 의미 미확정 상태입니다. '
               '이로 인해 압력(PRES)·인접등급(ADJ) 규칙은 아직 실행하지 않았습니다. '
               '현재 리포트는 라벨 정합성(LBL) 검증과 추출 품질 지표에 한정됩니다.</div>')

    out.append("<h2>품질 지표</h2><div class='metrics'>")
    for k, v in metrics.items():
        out.append(f"<div class='metric'><div class='v'>{esc(str(v))}</div>"
                   f"<div class='k'>{esc(k)}</div></div>")
    out.append("</div>")

    out.append(f"<h2>Violations ({len(violations)}건)</h2>")
    if violations:
        out.append("<table><tr><th>규칙</th><th>심각도</th><th>내용</th><th>근거(조항)</th></tr>")
        for rid, sev, msg, _rj, evidence in violations:
            prov = (evidence or {}).get("_rule", {}) if isinstance(evidence, dict) else {}
            clause = prov.get("clause") or "-"
            out.append(f"<tr><td>{esc(rid)}</td>"
                       f"<td class='sev-{esc(sev)}'>{esc(sev)}</td>"
                       f"<td>{esc(msg)}</td>"
                       f"<td class='sub'>{esc(str(clause))}</td></tr>")
        out.append("</table>")
    else:
        out.append("<p>검출된 위반 없음.</p>")

    # 발주처 확인 대기 (감사 상태 모델: 실행됨 / 미검수-잠금 / 확인질문)
    out.append("<h2>발주처 확인 대기 (미검수·미확정)</h2>")
    out.append('<p class="sub">아래는 우리 측 잠정 상태로, 발주처 확인 전까지 규칙을 실행하지 않거나 '
               '해석을 확정하지 않은 항목입니다. 확인되면 규칙을 활성화합니다.</p>')
    if gated_rules:
        out.append("<table><tr><th>규칙</th><th>제목</th><th>요구(무엇을)</th><th>근거(조항)</th><th>상태</th></tr>")
        for g in gated_rules:
            out.append(f"<tr><td>{esc(str(g['id']))}</td><td>{esc(str(g['title']))}</td>"
                       f"<td>{esc(str(g.get('requirement') or '-'))}</td>"
                       f"<td class='sub'>{esc(str(g.get('clause') or '-'))}</td>"
                       f"<td class='sev-major'>검수대기·잠금</td></tr>")
        out.append("</table>")
    if open_questions:
        out.append("<table><tr><th>확인 항목</th><th>내용</th></tr>")
        for topic, qbody in open_questions:
            out.append(f"<tr><td>{esc(str(topic))}</td><td>{esc(str(qbody))}</td></tr>")
        out.append("</table>")
    if not gated_rules and not open_questions:
        out.append("<p>확인 대기 항목 없음.</p>")

    # 층별 SVG
    out.append("<h2>층별 배치 (방 위치 · 위반 마커)</h2>")
    floors = sorted({r["floor"] for r in rooms if r["floor"]})
    for fl in floors:
        fr = [r for r in rooms if r["floor"] == fl]
        out.append(f"<h3 style='font-size:13px;color:#9aa4b2'>{esc(fl)} ({len(fr)}방)</h3>")
        out.append(f"<div class='svgwrap'>{render_floor(fl, fr, viol_room_nos)}</div>")

    out.append('<div class="foot">GXPAI Engine · 자동 생성 · 고객 식별 정보 포함(비공개). '
               '포트폴리오용은 익명화 버전 별도 생성.</div>')

    body = f"<!doctype html><html lang='ko'><head><meta charset='utf-8'>" \
           f"<meta name='viewport' content='width=device-width,initial-scale=1'>" \
           f"<title>GXPAI 리포트 {esc(fac_name)}</title><style>{_CSS}</style></head>" \
           f"<body>{''.join(out)}</body></html>"

    out_dir = repo_root() / "artifacts" / facility_id / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "report.html"
    out_path.write_text(body, encoding="utf-8")
    # 지표를 JSON 으로도 (기계 가독)
    (out_dir / "metrics.json").write_text(
        json.dumps({"facility": facility_id, "run_id": run_id, "metrics": metrics,
                    "violations": len(violations)}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    return out_path
