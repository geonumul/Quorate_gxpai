# -*- coding: utf-8 -*-
"""CLI 골격 스모크 테스트 — 파서가 명령을 인식하는지만 확인 (구현 전)."""
import pytest

from gxpai.cli import build_parser


def test_version_flag():
    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--version"])
    assert exc.value.code == 0


@pytest.mark.parametrize("argv", [
    ["facility", "add", "x.zip", "--name", "n", "--profile", "osd_hs_2025"],
    ["inventory", "F1"],
    ["ingest", "F1"],
    ["validate", "F1", "--rules", "gmp_osd_v1"],
    ["run", "all", "F1"],
])
def test_known_commands_parse(argv):
    # 파싱 자체는 성공해야 한다 (핸들러는 아직 미구현).
    args = build_parser().parse_args(argv)
    assert args.command == argv[0]
