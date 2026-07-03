# -*- coding: utf-8 -*-
"""gxpai - 단일 진입점 CLI (Stage 5 API의 전신).

모든 기능은 CLI로 노출된다. cli.py는 core 함수를 얇게 감싸기만 하며,
그래야 나중에 FastAPI가 껍데기만 추가해 동일 함수를 호출할 수 있다 (docs/API_CONTRACT.md).

명령 계약(B.3):
  gxpai facility add <zip> --name ... --profile ...
  gxpai inventory <facility_id> [--dxf <name>]
  gxpai profile wizard <facility_id>
  gxpai ingest <facility_id>
  gxpai graph build <facility_id>
  gxpai validate <facility_id> --rules gmp_osd_v1
  gxpai report <facility_id>
  gxpai generate --spec spec.yaml --refs <fid1,fid2>
  gxpai export dxf <run_id>
  gxpai run all <facility_id>
"""
from __future__ import annotations

import argparse
import sys

__version__ = "0.1.0"


def _force_utf8_output() -> None:
    """Windows 콘솔 기본 코드페이지(cp949)에서 한글 출력이 깨지는 것을 막는다.

    Python 은 stdout 인코딩을 콘솔 코드페이지로 잡아, UTF-8 터미널에서 한글이 mojibake 로
    보인다(발주처가 CLI 를 쓸 때도 동일). 진입점에서 UTF-8 로 고정해 항상 정상 출력.
    스트림이 reconfigure 를 지원 안 하면(리다이렉트 등) 조용히 넘어간다.
    """
    import io
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError, io.UnsupportedOperation):
            pass


def _todo(name: str) -> int:
    print(f"[gxpai] '{name}' 은 아직 skeleton 입니다. docs/PROGRESS.md 참조.", file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gxpai", description="GXPAI 도면 자동화 엔진")
    p.add_argument("--version", action="version", version=f"gxpai {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    fac = sub.add_parser("facility", help="시설 등록/관리").add_subparsers(dest="sub", required=True)
    add = fac.add_parser("add", help="zip 등록 + 해제 + 매니페스트")
    add.add_argument("zip")
    add.add_argument("--name", required=True)
    add.add_argument("--profile", required=True)

    inv = sub.add_parser("inventory", help="DXF 레이어/텍스트/블록 인벤토리")
    inv.add_argument("facility_id")
    inv.add_argument("--dxf")

    prof = sub.add_parser("profile", help="프로파일 관리").add_subparsers(dest="sub", required=True)
    prof.add_parser("wizard", help="인벤토리 → 프로파일 초안").add_argument("facility_id")

    sub.add_parser("ingest", help="전체 추출 → DB 적재 (run_id 발급)").add_argument("facility_id")
    sub.add_parser("graph", help="온톨로지 → Neo4j").add_subparsers(dest="sub", required=True)\
        .add_parser("build").add_argument("facility_id")

    val = sub.add_parser("validate", help="violations 검증")
    val.add_argument("facility_id")
    val.add_argument("--rules", default="gmp_osd_v1")

    sub.add_parser("report", help="HTML 리포트").add_argument("facility_id")

    gen = sub.add_parser("generate", help="레퍼런스 기반 배치")
    gen.add_argument("--spec", required=True)
    gen.add_argument("--refs", required=True)

    exp = sub.add_parser("export", help="산출물 내보내기").add_subparsers(dest="sub", required=True)
    exp.add_parser("dxf").add_argument("run_id")

    run = sub.add_parser("run", help="파이프라인 묶음 실행").add_subparsers(dest="sub", required=True)
    run.add_parser("all", help="ingest→graph→validate→report").add_argument("facility_id")

    return p


def _cmd_facility_add(args) -> int:
    from pathlib import Path

    from .core import registry
    result = registry.add_facility(Path(args.zip), name=args.name, profile_id=args.profile)
    print(f"[facility add] 시설 등록됨: {result['facility_id']}  ({result['name']})")
    print(f"  프로파일: {result['profile_id']}")
    print(f"  도면 {len(result['drawings'])}건:")
    for d in result["drawings"]:
        print(f"    - {d['kind']:9s} {d['filename']}  (지문 {d['sha256'][:12]}…)")
    return 0


def _cmd_inventory(args) -> int:
    from .core import registry
    from .core.config import raw_dir
    from .ingest.inventory import inventory, print_report
    fac = registry.get_facility(args.facility_id)
    if not fac:
        print(f"시설 없음: {args.facility_id}")
        return 1
    raw = raw_dir() / args.facility_id
    for d in fac["drawings"]:
        if args.dxf and args.dxf not in d["filename"]:
            continue
        path = raw / d["filename"]
        if path.exists():
            print_report(inventory(str(path)))
    return 0


def _cmd_profile_wizard(args) -> int:
    import yaml

    from .core import registry
    from .core.config import raw_dir, repo_root
    from .ingest.profile_wizard import build_draft
    fac = registry.get_facility(args.facility_id)
    if not fac:
        print(f"시설 없음: {args.facility_id}")
        return 1
    raw = raw_dir() / args.facility_id
    fp = next((raw / d["filename"] for d in fac["drawings"] if d["kind"] == "floorplan"), None)
    pr = next((raw / d["filename"] for d in fac["drawings"] if d["kind"] == "pressure"), None)
    if not fp:
        print("평면도 도면이 없어 초안을 만들 수 없습니다.")
        return 1
    draft = build_draft(f"{args.facility_id}_draft", str(fp), str(pr) if pr else None)
    out = repo_root() / "profiles" / f"_draft_{args.facility_id}.yaml"
    out.write_text(yaml.safe_dump(draft, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"[profile wizard] 초안 생성: {out}")
    print(f"  방 레이어 후보: {draft['floorplan']['room_layers']}")
    print(f"  번호 패턴: {draft['floorplan']['room_no_regex']}")
    print(f"  층: {draft['floors']}")
    print(f"  장비 레이어 후보: {draft['equipment']['layers']}")
    print("  ※ 초안입니다. 검토·수정 후 profiles/ 에 정식 배치하세요.")
    return 0


def _cmd_run_all(args) -> int:
    """ingest → graph build → validate → report 순차 실행 (B.3)."""
    from .compliance import engine
    from .core import run
    from .ontology import builder
    from .render import report
    r = run.ingest(args.facility_id)
    print(f"[run all] ingest run_id={r['run_id']} (방 {r['n_merged_rooms']}, 인접 {r['n_adjacency']}, "
          f"화살표↔방 {r['n_pressure_links']})")
    g = builder.build(args.facility_id, run_id=r["run_id"])
    print(f"[run all] graph 노드={g['nodes']} 관계={g['relationships']}")
    v = engine.validate(args.facility_id, ruleset="gmp_osd_v1", run_id=r["run_id"])
    print(f"[run all] violations {v['total']}건 {v['by_rule']}")
    path = report.generate(args.facility_id, run_id=r["run_id"])
    print(f"[run all] report {path}")
    return 0


def _cmd_graph_build(args) -> int:
    from .ontology import builder
    r = builder.build(args.facility_id)
    print(f"[graph build] run_id={r['run_id']}")
    print(f"  노드: {r['nodes']}")
    print(f"  관계: {r['relationships']}")
    return 0


def _cmd_report(args) -> int:
    from .render import report
    path = report.generate(args.facility_id)
    print(f"[report] 생성: {path}")
    return 0


def _cmd_validate(args) -> int:
    from .compliance import engine
    r = engine.validate(args.facility_id, ruleset=args.rules)
    print(f"[validate] run_id={r['run_id']} ruleset={r['ruleset']}")
    print(f"  위반 총 {r['total']}건")
    for rule_id, n in r["by_rule"].items():
        print(f"    {rule_id}: {n}")
    if r["skipped"]:
        print(f"  건너뜀(미구현): {', '.join(r['skipped'])}")
    return 0


def _cmd_ingest(args) -> int:
    from .core import run
    r = run.ingest(args.facility_id)
    print(f"[ingest] run_id={r['run_id']}")
    print(f"  처리 도면: {r['drawings_processed']}")
    print(f"  평면도 방 {r['n_floorplan_rooms']} / 차압도 방 {r['n_pressure_rooms']} "
          f"→ 병합 {r['n_merged_rooms']}개 방을 DB에 적재")
    return 0


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    args = build_parser().parse_args(argv)
    sub = getattr(args, "sub", "") or ""
    if args.command == "facility" and sub == "add":
        return _cmd_facility_add(args)
    if args.command == "inventory":
        return _cmd_inventory(args)
    if args.command == "profile" and sub == "wizard":
        return _cmd_profile_wizard(args)
    if args.command == "ingest":
        return _cmd_ingest(args)
    if args.command == "validate":
        return _cmd_validate(args)
    if args.command == "report":
        return _cmd_report(args)
    if args.command == "graph" and sub == "build":
        return _cmd_graph_build(args)
    if args.command == "run" and sub == "all":
        return _cmd_run_all(args)
    # 나머지는 아직 골격.
    return _todo(f"{args.command} {sub}".strip())


if __name__ == "__main__":
    raise SystemExit(main())
