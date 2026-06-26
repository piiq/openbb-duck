from pathlib import Path

from openbb_duck.cli import build_parser, resolve_config


def test_cli_defaults_to_current_working_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    config = resolve_config(build_parser().parse_args([]), {})

    assert config.data_dir == Path.cwd()
    assert config.host == "127.0.0.1"
    assert config.port == 7779
    assert config.reload is False
    assert config.cors_origins is None


def test_cli_args_override_defaults(tmp_path):
    config = resolve_config(
        build_parser().parse_args(
            [
                "--data-dir",
                str(tmp_path),
                "--host",
                "0.0.0.0",
                "--port",
                "7788",
                "--reload",
            ]
        ),
        {},
    )

    assert config.data_dir == tmp_path
    assert config.host == "0.0.0.0"
    assert config.port == 7788
    assert config.reload is True


def test_env_vars_override_defaults(tmp_path):
    config = resolve_config(
        build_parser().parse_args([]),
        {
            "OPENBB_DUCK_DATA_DIR": str(tmp_path),
            "OPENBB_DUCK_HOST": "0.0.0.0",
            "OPENBB_DUCK_PORT": "7788",
            "OPENBB_DUCK_RELOAD": "true",
            "OPENBB_DUCK_CORS_ORIGINS": (
                "https://workspace.example.com,http://localhost:3000"
            ),
        },
    )

    assert config.data_dir == tmp_path
    assert config.host == "0.0.0.0"
    assert config.port == 7788
    assert config.reload is True
    assert config.cors_origins == [
        "https://workspace.example.com",
        "http://localhost:3000",
    ]


def test_cli_args_override_env_vars(tmp_path):
    cli_data_dir = tmp_path / "cli"
    env_data_dir = tmp_path / "env"
    config = resolve_config(
        build_parser().parse_args(
            [
                "--data-dir",
                str(cli_data_dir),
                "--host",
                "127.0.0.2",
                "--port",
                "8888",
                "--no-reload",
                "--cors-origin",
                "https://cli.example.com",
            ]
        ),
        {
            "OPENBB_DUCK_DATA_DIR": str(env_data_dir),
            "OPENBB_DUCK_HOST": "0.0.0.0",
            "OPENBB_DUCK_PORT": "7777",
            "OPENBB_DUCK_RELOAD": "true",
            "OPENBB_DUCK_CORS_ORIGINS": "https://env.example.com",
        },
    )

    assert config.data_dir == cli_data_dir
    assert config.host == "127.0.0.2"
    assert config.port == 8888
    assert config.reload is False
    assert config.cors_origins == ["https://cli.example.com"]


def test_cli_parser_accepts_data_dir_host_and_port(tmp_path):
    args = build_parser().parse_args(
        ["--data-dir", str(tmp_path), "--host", "0.0.0.0", "--port", "7788"]
    )

    assert args.data_dir == tmp_path
    assert args.host == "0.0.0.0"
    assert args.port == 7788


def test_cli_accepts_custom_cors_origins():
    args = build_parser().parse_args(
        [
            "--cors-origin",
            "https://workspace.example.com",
            "-c",
            "http://localhost:3000",
        ]
    )

    assert args.cors_origins == [
        "https://workspace.example.com",
        "http://localhost:3000",
    ]
