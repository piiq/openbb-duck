from pathlib import Path

from openbb_duck.cli import build_parser


def test_cli_defaults_data_dir_to_current_working_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    args = build_parser().parse_args([])

    assert args.data_dir == Path.cwd()


def test_cli_accepts_data_dir_host_and_port(tmp_path):
    args = build_parser().parse_args(
        ["--data-dir", str(tmp_path), "--host", "0.0.0.0", "--port", "7788"]
    )

    assert args.data_dir == tmp_path
    assert args.host == "0.0.0.0"
    assert args.port == 7788
