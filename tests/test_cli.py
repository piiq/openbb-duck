import pytest

from openbb_duck.cli import build_parser, resolve_config


def test_cli_requires_at_least_one_source():
    args = build_parser().parse_args([])

    with pytest.raises(ValueError, match="at least one --source"):
        resolve_config(args, {})


def test_cli_accepts_repeated_sources():
    config = resolve_config(
        build_parser().parse_args(
            [
                "--source",
                "prices=./prices.parquet",
                "-s",
                "duck=duckdb:./warehouse.db",
            ]
        ),
        {},
    )

    assert config.sources == ["prices=./prices.parquet", "duck=duckdb:./warehouse.db"]


def test_env_vars_override_source_defaults():
    config = resolve_config(
        build_parser().parse_args([]),
        {"OPENBB_DUCK_SOURCES": "prices=./prices.parquet,duck=duckdb:./warehouse.db"},
    )

    assert config.sources == ["prices=./prices.parquet", "duck=duckdb:./warehouse.db"]


def test_cli_args_override_source_env_vars():
    config = resolve_config(
        build_parser().parse_args(["--source", "cli=./cli.parquet"]),
        {"OPENBB_DUCK_SOURCES": "env=./env.parquet"},
    )

    assert config.sources == ["cli=./cli.parquet"]


def test_cli_rejects_ambiguous_db_source():
    args = build_parser().parse_args(["--source", "./warehouse.db"])

    with pytest.raises(ValueError, match="ambiguous source"):
        resolve_config(args, {})


def test_cli_rejects_duplicate_source_aliases():
    args = build_parser().parse_args(
        [
            "--source",
            "warehouse=./warehouse.duckdb",
            "--source",
            "warehouse=./other.duckdb",
        ]
    )

    with pytest.raises(ValueError, match="duplicate source alias"):
        resolve_config(args, {})


def test_cli_retains_server_and_cors_config():
    config = resolve_config(
        build_parser().parse_args(
            [
                "--source",
                "./prices.parquet",
                "--host",
                "0.0.0.0",
                "--port",
                "7788",
                "--reload",
                "--cors-origin",
                "https://workspace.example.com",
            ]
        ),
        {},
    )

    assert config.host == "0.0.0.0"
    assert config.port == 7788
    assert config.reload is True
    assert config.cors_origins == ["https://workspace.example.com"]


def test_cli_accepts_quack_token_from_env_and_argument():
    env_config = resolve_config(
        build_parser().parse_args(["--source", "remote=quack:localhost"]),
        {"OPENBB_DUCK_QUACK_TOKEN": "env-secret"},
    )
    cli_config = resolve_config(
        build_parser().parse_args(
            [
                "--source",
                "remote=quack:localhost",
                "--quack-token",
                "cli-secret",
            ]
        ),
        {"OPENBB_DUCK_QUACK_TOKEN": "env-secret"},
    )

    assert env_config.quack_token == "env-secret"
    assert cli_config.quack_token == "cli-secret"


def test_cli_accepts_api_token_from_env():
    config = resolve_config(
        build_parser().parse_args(["--source", "./prices.parquet"]),
        {"OPENBB_DUCK_API_TOKEN": "api-secret"},
    )

    assert config.api_token == "api-secret"


def test_cli_accepts_object_storage_config_from_env():
    config = resolve_config(
        build_parser().parse_args(["--source", "lake=s3://bucket/**/*.parquet"]),
        {
            "OPENBB_DUCK_S3_ENDPOINT": "account.r2.cloudflarestorage.com",
            "OPENBB_DUCK_S3_ACCESS_KEY_ID": "key",
            "OPENBB_DUCK_S3_SECRET_ACCESS_KEY": "secret",
        },
    )

    assert config.object_storage is not None
    assert config.object_storage.endpoint == "account.r2.cloudflarestorage.com"
    assert config.object_storage.access_key_id == "key"
    assert config.object_storage.secret_access_key == "secret"
    assert config.object_storage.region == "auto"
    assert config.object_storage.url_style == "path"


def test_cli_accepts_object_storage_config_from_arguments():
    config = resolve_config(
        build_parser().parse_args(
            [
                "--source",
                "lake=s3://bucket/**/*.parquet",
                "--s3-endpoint",
                "account.r2.cloudflarestorage.com",
                "--s3-access-key-id",
                "cli-key",
                "--s3-secret-access-key",
                "cli-secret",
                "--s3-region",
                "weur",
                "--s3-url-style",
                "vhost",
            ]
        ),
        {
            "OPENBB_DUCK_S3_ENDPOINT": "env.example.com",
            "OPENBB_DUCK_S3_ACCESS_KEY_ID": "env-key",
            "OPENBB_DUCK_S3_SECRET_ACCESS_KEY": "env-secret",
        },
    )

    assert config.object_storage is not None
    assert config.object_storage.endpoint == "account.r2.cloudflarestorage.com"
    assert config.object_storage.access_key_id == "cli-key"
    assert config.object_storage.secret_access_key == "cli-secret"
    assert config.object_storage.region == "weur"
    assert config.object_storage.url_style == "vhost"


def test_cli_help_explains_source_usage():
    help_text = build_parser().format_help()

    assert "--source" in help_text
    assert "alias=source" in help_text
    assert "duckdb:./warehouse.db" in help_text
    assert "s3://bucket/path/**/*.parquet" in help_text
    assert "quack:localhost" in help_text
    assert "--s3-endpoint" in help_text
    assert "--s3-access-key-id" in help_text
    assert "--s3-secret-access-key" in help_text
