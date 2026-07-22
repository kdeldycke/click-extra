# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.

"""Tests for typed configuration schemas, validation, and extension points."""

from __future__ import annotations

from dataclasses import dataclass, field
from textwrap import dedent
from types import SimpleNamespace

import click
import pytest

from click_extra import (
    config_option,
    echo,
    group,
    make_schema_callable,
    option,
    pass_context,
    validate_config_option,
)
from click_extra.config import (
    CONFIG_PATH_METADATA_KEY,
    field_docstrings,
    flatten_config_keys,
    get_tool_config,
    normalize_config_keys,
    schema_field_infos,
)
from click_extra.config.schema import _collect_opaque_paths_from_schema

# --- config_schema and fallback_sections tests ---


def test_normalize_config_keys():
    assert normalize_config_keys({}) == {}
    assert normalize_config_keys({"foo-bar": 1}) == {"foo_bar": 1}
    assert normalize_config_keys({"a-b": {"c-d": 2}}) == {"a_b": {"c_d": 2}}
    # Keys without hyphens are unchanged.
    assert normalize_config_keys({"snake_case": 3}) == {"snake_case": 3}


def test_config_schema_dataclass(invoke, create_config):
    """Dataclass schemas are auto-detected and instantiated with normalized keys."""

    @dataclass
    class AppConfig:
        extra_stuff: str = "default_value"
        my_list: list[str] = field(default_factory=list)

    @group(config_schema=AppConfig)
    @option("--dummy-flag/--no-flag")
    @pass_context
    def schema_cli(ctx, dummy_flag):
        config = get_tool_config(ctx)
        echo(f"dummy_flag   is {dummy_flag!r}")
        echo(f"extra_stuff  is {config.extra_stuff!r}")
        echo(f"my_list      is {config.my_list!r}")

    @schema_cli.command()
    @option("--int-param", type=int, default=10)
    def subcommand(int_param):
        echo(f"int_param    is {int_param!r}")

    conf_path = create_config(
        "schema.toml",
        dedent("""\
            [schema-cli]
            dummy_flag = true
            extra-stuff = "from_config"
            my-list = ["a", "b"]

            [schema-cli.subcommand]
            int_param = 42
            """),
    )

    result = invoke(schema_cli, "--config", str(conf_path), "subcommand", color=False)
    assert result.exit_code == 0
    # CLI options use underscores in the default_map.
    assert "dummy_flag   is True" in result.stdout
    # Schema normalizes hyphens to underscores.
    assert "extra_stuff  is 'from_config'" in result.stdout
    assert "my_list      is ['a', 'b']" in result.stdout
    assert "int_param    is 42" in result.stdout


def test_config_schema_callable(invoke, create_config):
    """A plain callable can be used as config_schema."""

    def my_schema(raw):
        return SimpleNamespace(**normalize_config_keys(raw))

    @group(config_schema=my_schema)
    @option("--dummy-flag/--no-flag")
    @pass_context
    def callable_cli(ctx, dummy_flag):
        config = get_tool_config(ctx)
        echo(f"extra is {config.extra_value!r}")

    @callable_cli.command()
    def subcommand():
        echo("ok")

    conf_path = create_config(
        "callable.toml",
        dedent("""\
            [callable-cli]
            extra-value = "hello"
            """),
    )

    result = invoke(callable_cli, "--config", str(conf_path), "subcommand", color=False)
    assert result.exit_code == 0
    assert "extra is 'hello'" in result.stdout


def test_config_schema_no_config_file(invoke):
    """When no config file is found, schema defaults are used."""

    @dataclass
    class AppConfig:
        value: str = "default"

    @group(config_schema=AppConfig)
    @pass_context
    def no_file_cli(ctx):
        config = get_tool_config(ctx)
        echo(f"value is {config.value!r}")

    @no_file_cli.command()
    def subcommand():
        echo("ok")

    result = invoke(no_file_cli, "subcommand", color=False)
    assert result.exit_code == 0
    assert "value is 'default'" in result.stdout


def test_config_schema_dataclass_defaults(invoke, create_config):
    """Dataclass defaults are used for fields not present in the config file."""

    @dataclass
    class AppConfig:
        present: str = "default_present"
        missing: str = "default_missing"

    @group(config_schema=AppConfig)
    @pass_context
    def defaults_cli(ctx):
        config = get_tool_config(ctx)
        echo(f"present is {config.present!r}")
        echo(f"missing is {config.missing!r}")

    @defaults_cli.command()
    def subcommand():
        echo("ok")

    conf_path = create_config(
        "defaults.toml",
        dedent("""\
            [defaults-cli]
            present = "from_file"
            """),
    )

    result = invoke(defaults_cli, "--config", str(conf_path), "subcommand", color=False)
    assert result.exit_code == 0
    assert "present is 'from_file'" in result.stdout
    assert "missing is 'default_missing'" in result.stdout


def test_fallback_sections(invoke, create_config):
    """Legacy section names are recognized with a deprecation warning."""

    @dataclass
    class AppConfig:
        value: str = "default"

    @group(config_schema=AppConfig, fallback_sections=("old-name", "older-name"))
    @pass_context
    def fallback_cli(ctx):
        config = get_tool_config(ctx)
        echo(f"value is {config.value!r}")

    @fallback_cli.command()
    def subcommand():
        echo("ok")

    # Config uses the old section name.
    conf_path = create_config(
        "fallback.toml",
        dedent("""\
            [old-name]
            value = "from_legacy"
            """),
    )

    result = invoke(fallback_cli, "--config", str(conf_path), "subcommand", color=False)
    assert result.exit_code == 0
    assert "value is 'from_legacy'" in result.stdout
    assert "deprecated" in result.stderr.lower()


def test_fallback_sections_prefers_current(invoke, create_config):
    """When both current and legacy sections exist, current wins."""

    @dataclass
    class AppConfig:
        value: str = "default"

    @group(config_schema=AppConfig, fallback_sections=("old-name",))
    @pass_context
    def current_cli(ctx):
        config = get_tool_config(ctx)
        echo(f"value is {config.value!r}")

    @current_cli.command()
    def subcommand():
        echo("ok")

    conf_path = create_config(
        "both.toml",
        dedent("""\
            [current-cli]
            value = "current"

            [old-name]
            value = "legacy"
            """),
    )

    result = invoke(current_cli, "--config", str(conf_path), "subcommand", color=False)
    assert result.exit_code == 0
    assert "value is 'current'" in result.stdout
    # Should still warn about leftover legacy section.
    assert "deprecated" in result.stderr.lower()


@pytest.mark.parametrize(
    ("conf_name", "conf_text"),
    [
        (
            "schema.yaml",
            dedent("""\
                yaml-cli:
                  extra-stuff: from_yaml
                  my-flag: true
                """),
        ),
        (
            "schema.json",
            dedent("""\
                {
                    "yaml-cli": {
                        "extra-stuff": "from_json",
                        "my-flag": true
                    }
                }
                """),
        ),
    ],
    ids=["yaml", "json"],
)
def test_config_schema_multiple_formats(invoke, create_config, conf_name, conf_text):
    """Config schema works with YAML and JSON, not just TOML."""

    @dataclass
    class AppConfig:
        extra_stuff: str = "default"
        my_flag: bool = False

    @group(config_schema=AppConfig)
    @option("--my-flag/--no-flag")
    @pass_context
    def yaml_cli(ctx, my_flag):
        config = get_tool_config(ctx)
        echo(f"extra_stuff is {config.extra_stuff!r}")

    @yaml_cli.command()
    def subcommand():
        echo("ok")

    conf_path = create_config(conf_name, conf_text)

    result = invoke(yaml_cli, "--config", str(conf_path), "subcommand", color=False)
    assert result.exit_code == 0
    expected = "from_yaml" if conf_name.endswith(".yaml") else "from_json"
    assert f"extra_stuff is '{expected}'" in result.stdout


def test_config_schema_on_config_option_directly(invoke, create_config):
    """Config schema can be set directly on ConfigOption via the decorator."""

    from click import group as click_group

    @dataclass
    class AppConfig:
        extra: str = "default"

    @click_group(context_settings={"show_default": True})
    @config_option(config_schema=AppConfig)
    @pass_context
    def direct_cli(ctx):
        config = get_tool_config(ctx)
        echo(f"extra is {config.extra!r}")

    @direct_cli.command()
    def subcommand():
        echo("ok")

    conf_path = create_config(
        "direct.toml",
        dedent("""\
            [direct-cli]
            extra = "works"
            """),
    )

    result = invoke(direct_cli, "--config", str(conf_path), "subcommand", color=False)
    assert result.exit_code == 0
    assert "extra is 'works'" in result.stdout


def test_get_tool_config_defaults_to_current_context(invoke, create_config):
    """get_tool_config() works without passing ctx explicitly."""

    @dataclass
    class AppConfig:
        value: str = "default"

    @group(config_schema=AppConfig)
    def auto_ctx_cli():
        # Call without explicit ctx.
        config = get_tool_config()
        echo(f"value is {config.value!r}")

    @auto_ctx_cli.command()
    def subcommand():
        echo("ok")

    conf_path = create_config(
        "auto.toml",
        dedent("""\
            [auto-ctx-cli]
            value = "auto"
            """),
    )

    result = invoke(auto_ctx_cli, "--config", str(conf_path), "subcommand", color=False)
    assert result.exit_code == 0
    assert "value is 'auto'" in result.stdout


def test_flatten_config_keys():
    # Empty dict.
    assert flatten_config_keys({}) == {}

    # Flat dict is unchanged.
    assert flatten_config_keys({"a": 1, "b": 2}) == {"a": 1, "b": 2}

    # One level of nesting.
    assert flatten_config_keys({"sub": {"key": "val"}}) == {"sub_key": "val"}

    # Multiple keys in a nested dict.
    assert flatten_config_keys({"dep": {"output": "x", "all": True}}) == {
        "dep_output": "x",
        "dep_all": True,
    }

    # Mixed flat and nested.
    assert flatten_config_keys({"top": 1, "sub": {"inner": 2}}) == {
        "top": 1,
        "sub_inner": 2,
    }

    # Deeply nested.
    assert flatten_config_keys({"a": {"b": {"c": 3}}}) == {"a_b_c": 3}

    # Custom separator.
    assert flatten_config_keys({"a": {"b": 1}}, sep=".") == {"a.b": 1}


def test_flatten_config_keys_with_normalize():
    """flatten + normalize maps nested kebab-case config to flat snake_case fields."""

    raw = {
        "dependency-graph": {"all-groups": True, "output": "deps.mmd"},
        "pypi-package-history": ["old-name"],
    }
    result = flatten_config_keys(normalize_config_keys(raw))
    assert result == {
        "dependency_graph_all_groups": True,
        "dependency_graph_output": "deps.mmd",
        "pypi_package_history": ["old-name"],
    }


def test_config_schema_nested_toml(invoke, create_config):
    """Nested TOML sub-tables map to flat dataclass fields via flattening."""

    @dataclass
    class AppConfig:
        dependency_graph_output: str = "default.mmd"
        dependency_graph_all_groups: bool = True
        gitignore_sync: bool = True
        top_level_list: list[str] = field(default_factory=list)

    @group(config_schema=AppConfig)
    @pass_context
    def nested_cli(ctx):
        config = get_tool_config(ctx)
        echo(f"output     is {config.dependency_graph_output!r}")
        echo(f"all_groups is {config.dependency_graph_all_groups!r}")
        echo(f"git_sync   is {config.gitignore_sync!r}")
        echo(f"top_list   is {config.top_level_list!r}")

    @nested_cli.command()
    def subcommand():
        echo("ok")

    conf_path = create_config(
        "nested.toml",
        dedent("""\
            [nested-cli]
            top-level-list = ["x", "y"]

            [nested-cli.dependency-graph]
            output = "custom.mmd"
            all-groups = false

            [nested-cli.gitignore]
            sync = false
            """),
    )

    result = invoke(nested_cli, "--config", str(conf_path), "subcommand", color=False)
    assert result.exit_code == 0
    assert "output     is 'custom.mmd'" in result.stdout
    assert "all_groups is False" in result.stdout
    assert "git_sync   is False" in result.stdout
    assert "top_list   is ['x', 'y']" in result.stdout


def test_config_schema_strict_rejects_unknown(invoke, create_config):
    """schema_strict=True raises ValueError on unrecognized config keys."""

    @dataclass
    class AppConfig:
        known_field: str = "default"

    @group(config_schema=AppConfig, schema_strict=True)
    @pass_context
    def strict_cli(ctx):
        config = get_tool_config(ctx)
        echo(f"known_field is {config.known_field!r}")

    @strict_cli.command()
    def subcommand():
        echo("ok")

    conf_path = create_config(
        "strict.toml",
        dedent("""\
            [strict-cli]
            known-field = "ok"
            typo-field = "oops"
            """),
    )

    result = invoke(strict_cli, "--config", str(conf_path), "subcommand", color=False)
    # The dataclass adapter's unknown-key error reaches the user as a clean
    # critical-level log and exit 1, unified with the other validation paths.
    assert result.exit_code == 1
    assert "typo_field" in result.stderr


def test_config_schema_strict_passes_when_valid(invoke, create_config):
    """schema_strict=True does not raise when all config keys are known."""

    @dataclass
    class AppConfig:
        known_field: str = "default"

    @group(config_schema=AppConfig, schema_strict=True)
    @pass_context
    def strict_ok_cli(ctx):
        config = get_tool_config(ctx)
        echo(f"known_field is {config.known_field!r}")

    @strict_ok_cli.command()
    def subcommand():
        echo("ok")

    conf_path = create_config(
        "strict_ok.toml",
        dedent("""\
            [strict-ok-cli]
            known-field = "good"
            """),
    )

    result = invoke(
        strict_ok_cli,
        "--config",
        str(conf_path),
        "subcommand",
        color=False,
    )
    assert result.exit_code == 0
    assert "known_field is 'good'" in result.stdout


def test_config_schema_strict_with_nested(invoke, create_config):
    """schema_strict=True validates flattened keys from nested sub-tables."""

    @dataclass
    class AppConfig:
        section_known: str = "default"

    @group(config_schema=AppConfig, schema_strict=True)
    @pass_context
    def strict_nested_cli(ctx):
        config = get_tool_config(ctx)
        echo(f"section_known is {config.section_known!r}")

    @strict_nested_cli.command()
    def subcommand():
        echo("ok")

    conf_path = create_config(
        "strict_nested.toml",
        dedent("""\
            [strict-nested-cli.section]
            known = "found"
            unknown = "oops"
            """),
    )

    result = invoke(
        strict_nested_cli,
        "--config",
        str(conf_path),
        "subcommand",
        color=False,
    )
    assert result.exit_code == 1
    assert "section_unknown" in result.stderr


def test_config_schema_lax_warns_unknown_when_schema_only(invoke, create_config):
    """A schema-only section warns on unknown keys instead of dropping them silently.

    ``included_params=()`` means no CLI parameter is merged from the app's
    section, so any key the schema does not know can only be a typo: lax mode
    then logs a warning while still loading the known fields.
    """

    @dataclass
    class AppConfig:
        known_field: str = "default"

    @group(config_schema=AppConfig, included_params=())
    @pass_context
    def lax_cli(ctx):
        config = get_tool_config(ctx)
        echo(f"known_field is {config.known_field!r}")

    @lax_cli.command()
    def subcommand():
        echo("ok")

    conf_path = create_config(
        "lax.toml",
        dedent("""\
            [lax-cli]
            known-field = "good"
            typo-field = "oops"
            """),
    )

    result = invoke(lax_cli, "--config", str(conf_path), "subcommand", color=False)
    assert result.exit_code == 0
    assert "typo_field" in result.stderr
    assert "known_field is 'good'" in result.stdout


def test_config_schema_lax_silent_when_params_merged(invoke, create_config):
    """Without ``included_params=()``, lax mode stays silent on unknown keys.

    The section may legitimately mix CLI parameter keys with schema fields,
    so a key unknown to the schema is not necessarily a typo.
    """

    @dataclass
    class AppConfig:
        known_field: str = "default"

    @group(config_schema=AppConfig)
    @pass_context
    def mixed_cli(ctx):
        config = get_tool_config(ctx)
        echo(f"known_field is {config.known_field!r}")

    @mixed_cli.command()
    def subcommand():
        echo("ok")

    conf_path = create_config(
        "mixed.toml",
        dedent("""\
            [mixed-cli]
            known-field = "good"
            typo-field = "oops"
            """),
    )

    result = invoke(mixed_cli, "--config", str(conf_path), "subcommand", color=False)
    assert result.exit_code == 0
    assert "typo_field" not in result.stderr
    assert "known_field is 'good'" in result.stdout


def test_make_schema_callable_warn_unknown(caplog):
    """``warn_unknown=True`` logs unknown keys, recursing into nested dataclasses."""

    @dataclass
    class SubConfig:
        depth: int = 0

    @dataclass
    class AppConfig:
        known_field: str = "default"
        sub: SubConfig = field(default_factory=SubConfig)

    schema_callable = make_schema_callable(AppConfig, warn_unknown=True)
    assert schema_callable is not None
    config = schema_callable({
        "known-field": "x",
        "typo-field": 1,
        "sub": {"depth": 2, "sub-typo": 3},
    })
    assert config.known_field == "x"
    assert config.sub.depth == 2
    assert "typo_field" in caplog.text
    assert "sub_typo" in caplog.text


def test_make_schema_callable_lax_default_is_silent(caplog):
    """Without ``warn_unknown``, lax mode keeps dropping unknown keys silently."""

    @dataclass
    class AppConfig:
        known_field: str = "default"

    schema_callable = make_schema_callable(AppConfig)
    assert schema_callable is not None
    config = schema_callable({"known-field": "x", "typo-field": 1})
    assert config.known_field == "x"
    assert "typo_field" not in caplog.text


def test_pyproject_toml_cwd_discovery(invoke, tmp_path, monkeypatch):
    """pyproject.toml in CWD is discovered automatically without --config."""

    @dataclass
    class AppConfig:
        extra_stuff: str = "default_value"

    @group(config_schema=AppConfig)
    @pass_context
    def cwd_cli(ctx):
        config = get_tool_config(ctx)
        if config is not None:
            echo(f"extra_stuff is {config.extra_stuff!r}")
        else:
            echo("config is None")

    @cwd_cli.command()
    def subcommand():
        echo("ok")

    # Write a pyproject.toml in the tmp directory.
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        dedent("""\
            [tool.cwd-cli]
            extra-stuff = "from_cwd"
            """),
    )

    # Run from that directory so CWD discovery finds it.
    monkeypatch.chdir(tmp_path)

    result = invoke(cwd_cli, "subcommand", color=False)
    assert result.exit_code == 0
    assert "extra_stuff is 'from_cwd'" in result.stdout


def test_pyproject_toml_cwd_discovery_walks_up(invoke, tmp_path, monkeypatch):
    """pyproject.toml discovery walks up from CWD to parent directories."""

    @dataclass
    class AppConfig:
        value: str = "default"

    @group(config_schema=AppConfig)
    @pass_context
    def walk_cli(ctx):
        config = get_tool_config(ctx)
        if config is not None:
            echo(f"value is {config.value!r}")
        else:
            echo("config is None")

    @walk_cli.command()
    def subcommand():
        echo("ok")

    # Write pyproject.toml in parent, run from a subdirectory.
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        dedent("""\
            [tool.walk-cli]
            value = "from_parent"
            """),
    )
    subdir = tmp_path / "src" / "pkg"
    subdir.mkdir(parents=True)
    monkeypatch.chdir(subdir)

    result = invoke(walk_cli, "subcommand", color=False)
    assert result.exit_code == 0
    assert "value is 'from_parent'" in result.stdout


def test_pyproject_toml_explicit_config_skips_cwd(
    invoke, create_config, tmp_path, monkeypatch
):
    """Explicit --config skips CWD pyproject.toml discovery."""

    @dataclass
    class AppConfig:
        value: str = "default"

    @group(config_schema=AppConfig)
    @pass_context
    def explicit_cli(ctx):
        config = get_tool_config(ctx)
        if config is not None:
            echo(f"value is {config.value!r}")
        else:
            echo("config is None")

    @explicit_cli.command()
    def subcommand():
        echo("ok")

    # CWD pyproject.toml with one value.
    cwd_pyproject = tmp_path / "pyproject.toml"
    cwd_pyproject.write_text(
        dedent("""\
            [tool.explicit-cli]
            value = "from_cwd"
            """),
    )
    monkeypatch.chdir(tmp_path)

    # Explicit config with a different value.
    conf_path = create_config(
        "explicit.toml",
        dedent("""\
            [explicit-cli]
            value = "from_explicit"
            """),
    )

    result = invoke(
        explicit_cli,
        "--config",
        str(conf_path),
        "subcommand",
        color=False,
    )
    assert result.exit_code == 0
    # Explicit --config wins over CWD pyproject.toml.
    assert "value is 'from_explicit'" in result.stdout


def test_pyproject_toml_cwd_skips_unrelated_tool_section(invoke, tmp_path, monkeypatch):
    """A pyproject.toml without [tool.<cli_name>] is skipped.

    Regression: a pyproject.toml carrying only unrelated [tool.X] sections
    (like a dotfiles repo's [tool.ruff]) used to shadow the user's app-dir
    config. It must now be ignored so the CLI falls back to its defaults
    instead of inheriting an unrelated project's settings.
    """

    @dataclass
    class AppConfig:
        fruit: str = "apple"

    @group(config_schema=AppConfig)
    @pass_context
    def unrelated_cli(ctx):
        config = get_tool_config(ctx)
        echo(f"fruit is {config.fruit!r}")

    @unrelated_cli.command()
    def subcommand():
        echo("ok")

    # pyproject.toml with only an unrelated [tool.X] section.
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        dedent("""\
            [tool.ruff]
            line-length = 100

            [tool.unrelated]
            fruit = "banana"
            """),
    )
    monkeypatch.chdir(tmp_path)

    result = invoke(unrelated_cli, "subcommand", color=False)
    assert result.exit_code == 0
    # The unrelated config must not leak into the CLI; defaults apply.
    assert "fruit is 'apple'" in result.stdout


def test_pyproject_toml_cwd_walks_past_unrelated_tool_section(
    invoke, tmp_path, monkeypatch
):
    """CWD walk continues past a pyproject.toml lacking [tool.<cli_name>].

    A nearer pyproject.toml that only carries unrelated [tool.X] sections
    must not stop the upward walk: a parent pyproject.toml with a matching
    [tool.<cli_name>] section should still be discovered.
    """

    @dataclass
    class AppConfig:
        city: str = "default"

    @group(config_schema=AppConfig)
    @pass_context
    def walk_past_cli(ctx):
        config = get_tool_config(ctx)
        echo(f"city is {config.city!r}")

    @walk_past_cli.command()
    def subcommand():
        echo("ok")

    # Parent pyproject.toml has the matching [tool.<cli_name>] section.
    parent_pyproject = tmp_path / "pyproject.toml"
    parent_pyproject.write_text(
        dedent("""\
            [tool.walk-past-cli]
            city = "Paris"
            """),
    )

    # Closer pyproject.toml only carries unrelated [tool.X] sections.
    subdir = tmp_path / "nested" / "sub"
    subdir.mkdir(parents=True)
    nested_pyproject = subdir / "pyproject.toml"
    nested_pyproject.write_text(
        dedent("""\
            [tool.ruff]
            line-length = 100
            """),
    )
    monkeypatch.chdir(subdir)

    result = invoke(walk_past_cli, "subcommand", color=False)
    assert result.exit_code == 0
    assert "city is 'Paris'" in result.stdout


def test_pyproject_toml_cwd_mixed_tool_sections(invoke, tmp_path, monkeypatch):
    """[tool.<cli_name>] is picked from a pyproject.toml that also has others."""

    @dataclass
    class AppConfig:
        weather: str = "default"

    @group(config_schema=AppConfig)
    @pass_context
    def mixed_cli(ctx):
        config = get_tool_config(ctx)
        echo(f"weather is {config.weather!r}")

    @mixed_cli.command()
    def subcommand():
        echo("ok")

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        dedent("""\
            [tool.ruff]
            line-length = 100

            [tool.mixed-cli]
            weather = "sunny"

            [tool.unrelated]
            ignored = true
            """),
    )
    monkeypatch.chdir(tmp_path)

    result = invoke(mixed_cli, "subcommand", color=False)
    assert result.exit_code == 0
    assert "weather is 'sunny'" in result.stdout


def test_pyproject_toml_cwd_unrelated_does_not_shadow_app_dir(
    invoke, tmp_path, monkeypatch
):
    """An unrelated pyproject.toml falls through to the app-dir config.

    Directly exercises the documented intent of the fix: when CWD contains a
    pyproject.toml whose only [tool.X] sections are unrelated to the CLI, the
    walk must give up so the standard app-dir search can find the user's
    actual config and apply it.
    """

    import click_extra.config.option as config_module

    @dataclass
    class AppConfig:
        animal: str = "default"

    @group(config_schema=AppConfig)
    @pass_context
    def fallback_cli(ctx):
        config = get_tool_config(ctx)
        echo(f"animal is {config.animal!r}")

    @fallback_cli.command()
    def subcommand():
        echo("ok")

    # Redirect the app-dir lookup to a tmp location and seed it with a
    # legitimate config for the CLI.
    app_dir = tmp_path / "app-dir"
    app_dir.mkdir()
    monkeypatch.setattr(
        config_module,
        "get_app_dir",
        lambda name, **kwargs: str(app_dir),
    )
    (app_dir / "config.toml").write_text(
        dedent("""\
            [fallback-cli]
            animal = "otter"
            """),
    )

    # CWD pyproject.toml carries an unrelated [tool.X] section only.
    cwd_dir = tmp_path / "project"
    cwd_dir.mkdir()
    (cwd_dir / "pyproject.toml").write_text(
        dedent("""\
            [tool.ruff]
            line-length = 100
            """),
    )
    monkeypatch.chdir(cwd_dir)

    result = invoke(fallback_cli, "subcommand", color=False)
    assert result.exit_code == 0
    # The app-dir config should win, not the unrelated pyproject.toml.
    assert "animal is 'otter'" in result.stdout


def test_flatten_config_keys_opaque():
    """opaque_keys stops flattening at matching key boundaries."""

    conf = {
        "test_matrix": {
            "exclude": [{"os": "windows"}],
            "replace": {"os": {"old": "new"}, "python-ver": {"3.12": "3.13"}},
        },
        "other": {"nested": "val"},
    }

    # Without opaque_keys: everything flattened recursively.
    flat = flatten_config_keys(conf)
    assert "test_matrix_replace_os_old" in flat
    assert "test_matrix_replace_python-ver_3.12" in flat

    # With opaque_keys: replace kept intact.
    flat = flatten_config_keys(
        conf,
        opaque_keys=frozenset({"test_matrix_replace"}),
    )
    assert flat["test_matrix_replace"] == {
        "os": {"old": "new"},
        "python-ver": {"3.12": "3.13"},
    }
    # Non-opaque siblings still flattened.
    assert flat["test_matrix_exclude"] == [{"os": "windows"}]
    assert flat["other_nested"] == "val"


def test_flatten_config_keys_opaque_nested():
    """opaque_keys works at deeper nesting levels."""

    conf = {"a": {"b": {"c": 1, "d": 2}, "e": 3}}

    flat = flatten_config_keys(conf, opaque_keys=frozenset({"a_b"}))
    assert flat == {"a_b": {"c": 1, "d": 2}, "a_e": 3}


def test_schema_type_aware_flattening(invoke, create_config):
    """dict-typed dataclass fields stop flattening automatically."""

    @dataclass
    class AppConfig:
        simple_value: str = ""
        opaque_map: dict[str, list[str]] = field(default_factory=dict)

    @group(config_schema=AppConfig)
    @pass_context
    def type_aware_cli(ctx):
        config = get_tool_config(ctx)
        echo(f"simple is {config.simple_value!r}")
        echo(f"opaque is {config.opaque_map!r}")

    @type_aware_cli.command()
    def subcommand():
        echo("ok")

    conf_path = create_config(
        "type_aware.toml",
        dedent("""\
            [type-aware-cli]
            simple-value = "hello"

            [type-aware-cli.opaque-map]
            python-version = ["3.12", "3.13"]
            os = ["ubuntu", "macos"]
            """),
    )

    result = invoke(
        type_aware_cli,
        "--config",
        str(conf_path),
        "subcommand",
        color=False,
    )
    assert result.exit_code == 0
    assert "simple is 'hello'" in result.stdout
    # Dict keys preserved as-is (not flattened into opaque_map_python_version).
    assert "python-version" in result.stdout
    assert "os" in result.stdout


def test_schema_field_metadata_config_path(invoke, create_config):
    """click_extra.config_path extracts a value at a dotted TOML path."""

    @dataclass
    class AppConfig:
        normal: str = ""
        special: dict[str, str] = field(
            default_factory=dict,
            metadata={
                "click_extra.config_path": "deep.section",
                "click_extra.normalize_keys": False,
            },
        )

    @group(config_schema=AppConfig)
    @pass_context
    def meta_cli(ctx):
        config = get_tool_config(ctx)
        echo(f"normal is {config.normal!r}")
        echo(f"special is {config.special!r}")

    @meta_cli.command()
    def subcommand():
        echo("ok")

    conf_path = create_config(
        "meta.toml",
        dedent("""\
            [meta-cli]
            normal = "top"

            [meta-cli.deep.section]
            kebab-key = "preserved"
            another = "value"
            """),
    )

    result = invoke(
        meta_cli,
        "--config",
        str(conf_path),
        "subcommand",
        color=False,
    )
    assert result.exit_code == 0
    assert "normal is 'top'" in result.stdout
    # normalize_keys=False: kebab-key stays as-is.
    assert "kebab-key" in result.stdout
    assert "preserved" in result.stdout


def test_schema_field_metadata_normalize_keys_true(invoke, create_config):
    """click_extra.normalize_keys defaults to True: keys are normalized."""

    @dataclass
    class AppConfig:
        extracted: dict[str, str] = field(
            default_factory=dict,
            metadata={"click_extra.config_path": "my-section"},
        )

    @group(config_schema=AppConfig)
    @pass_context
    def norm_cli(ctx):
        config = get_tool_config(ctx)
        echo(f"extracted is {config.extracted!r}")

    @norm_cli.command()
    def subcommand():
        echo("ok")

    conf_path = create_config(
        "norm.toml",
        dedent("""\
            [norm-cli.my-section]
            kebab-key = "val"
            """),
    )

    result = invoke(
        norm_cli,
        "--config",
        str(conf_path),
        "subcommand",
        color=False,
    )
    assert result.exit_code == 0
    # Default normalize_keys=True: kebab-key becomes kebab_key.
    assert "kebab_key" in result.stdout


def test_schema_nested_dataclass(invoke, create_config):
    """Nested dataclass fields are recursively instantiated."""

    @dataclass
    class SubConfig:
        enabled: bool = False
        items: list[str] = field(default_factory=list)

    @dataclass
    class AppConfig:
        name: str = ""
        sub: SubConfig = field(default_factory=SubConfig)

    @group(config_schema=AppConfig)
    @pass_context
    def nested_dc_cli(ctx):
        config = get_tool_config(ctx)
        echo(f"name is {config.name!r}")
        echo(f"sub type is {type(config.sub).__name__}")
        echo(f"sub.enabled is {config.sub.enabled!r}")
        echo(f"sub.items is {config.sub.items!r}")

    @nested_dc_cli.command()
    def subcommand():
        echo("ok")

    conf_path = create_config(
        "nested_dc.toml",
        dedent("""\
            [nested-dc-cli]
            name = "hello"

            [nested-dc-cli.sub]
            enabled = true
            items = ["a", "b"]
            """),
    )

    result = invoke(
        nested_dc_cli,
        "--config",
        str(conf_path),
        "subcommand",
        color=False,
    )
    assert result.exit_code == 0
    assert "name is 'hello'" in result.stdout
    assert "sub type is SubConfig" in result.stdout
    assert "sub.enabled is True" in result.stdout
    assert "sub.items is ['a', 'b']" in result.stdout


def test_schema_nested_dataclass_with_opaque_fields(invoke, create_config):
    """Nested dataclass with dict-typed fields preserves opaque keys."""

    @dataclass
    class MatrixConfig:
        exclude: list[dict[str, str]] = field(default_factory=list)
        replace: dict[str, dict[str, str]] = field(default_factory=dict)
        variations: dict[str, list[str]] = field(default_factory=dict)

    @dataclass
    class AppConfig:
        matrix: MatrixConfig = field(
            default_factory=MatrixConfig,
            metadata={
                "click_extra.config_path": "test-matrix",
                "click_extra.normalize_keys": False,
            },
        )

    @group(config_schema=AppConfig)
    @pass_context
    def matrix_cli(ctx):
        config = get_tool_config(ctx)
        echo(f"exclude is {config.matrix.exclude!r}")
        echo(f"replace is {config.matrix.replace!r}")
        echo(f"variations is {config.matrix.variations!r}")

    @matrix_cli.command()
    def subcommand():
        echo("ok")

    conf_path = create_config(
        "matrix.toml",
        dedent("""\
            [matrix-cli.test-matrix]
            exclude = [{os = "windows-11-arm"}]

            [matrix-cli.test-matrix.replace]
            os = {"ubuntu-slim" = "ubuntu-24.04"}

            [matrix-cli.test-matrix.variations]
            python-version = ["3.14"]
            os = ["custom-runner"]
            """),
    )

    result = invoke(
        matrix_cli,
        "--config",
        str(conf_path),
        "subcommand",
        color=False,
    )
    assert result.exit_code == 0
    # Exclude list preserved with original keys.
    assert "windows-11-arm" in result.stdout
    # Replace dict keys not normalized (os stays, ubuntu-slim stays).
    assert "ubuntu-slim" in result.stdout
    assert "ubuntu-24.04" in result.stdout
    # Variations keys not normalized (python-version stays as-is).
    assert "python-version" in result.stdout
    assert "custom-runner" in result.stdout


def test_schema_nested_dataclass_defaults(invoke, create_config):
    """Nested dataclass uses defaults when config section is absent."""

    @dataclass
    class SubConfig:
        enabled: bool = True
        count: int = 42

    @dataclass
    class AppConfig:
        name: str = "default_name"
        sub: SubConfig = field(default_factory=SubConfig)

    @group(config_schema=AppConfig)
    @pass_context
    def default_dc_cli(ctx):
        config = get_tool_config(ctx)
        echo(f"name is {config.name!r}")
        echo(f"sub.enabled is {config.sub.enabled!r}")
        echo(f"sub.count is {config.sub.count!r}")

    @default_dc_cli.command()
    def subcommand():
        echo("ok")

    conf_path = create_config(
        "default_dc.toml",
        dedent("""\
            [default-dc-cli]
            name = "custom"
            """),
    )

    result = invoke(
        default_dc_cli,
        "--config",
        str(conf_path),
        "subcommand",
        color=False,
    )
    assert result.exit_code == 0
    assert "name is 'custom'" in result.stdout
    # Sub-config uses defaults since [default-dc-cli.sub] is absent.
    assert "sub.enabled is True" in result.stdout
    assert "sub.count is 42" in result.stdout


# Opaque-aware strict check: schema-declared extension sub-trees pass through
# both runtime strict mode and --validate-config without tripping unknown-key
# detection.


def test_strict_skips_opaque_dict_field(invoke, create_config):
    """Strict mode does not reject keys inside a ``dict[str, X]`` schema field.

    A field typed as ``dict[str, dict]`` is user-controlled: the keys are data,
    not CLI flag names. Click-extra strips that sub-tree before running its
    unknown-key check so app extensions don't trip strict mode.
    """

    @dataclass
    class AppConfig:
        extensions: dict[str, dict] = field(default_factory=dict)

    @click.group
    @option("--dummy-flag/--no-flag")
    @config_option(config_schema=AppConfig, strict=True)
    def opaque_cli(dummy_flag):
        echo("ok")

    @opaque_cli.command
    def sub():
        echo("sub")

    conf_path = create_config(
        "opaque_dict.toml",
        dedent("""\
            [opaque-cli]
            dummy_flag = true

            [opaque-cli.extensions.plugin-a]
            anything = "goes"
            and_so_does = ["this", "list"]
            """),
    )

    result = invoke(opaque_cli, "--config", str(conf_path), "sub", color=False)
    assert result.exit_code == 0


def test_strict_skips_opaque_metadata_field(invoke, create_config):
    """Strict mode also honors the ``EXTENSION_METADATA_KEY`` marker on a field
    whose Python type is not a mapping."""

    from click_extra import EXTENSION_METADATA_KEY

    @dataclass
    class AppConfig:
        # Typed as a list but the metadata flag tells click-extra to treat the
        # backing dict in the config file as opaque content.
        plugins: list = field(
            default_factory=list,
            metadata={EXTENSION_METADATA_KEY: True},
        )

    @click.group
    @option("--dummy-flag/--no-flag")
    @config_option(config_schema=AppConfig, strict=True)
    def metadata_opaque_cli(dummy_flag):
        echo("ok")

    @metadata_opaque_cli.command
    def sub():
        echo("sub")

    conf_path = create_config(
        "opaque_metadata.toml",
        dedent("""\
            [metadata-opaque-cli]
            dummy_flag = true

            [metadata-opaque-cli.plugins]
            arbitrary = "content"
            """),
    )

    result = invoke(
        metadata_opaque_cli,
        "--config",
        str(conf_path),
        "sub",
        color=False,
    )
    assert result.exit_code == 0


def test_validate_config_skips_opaque_field(invoke, create_config):
    """--validate-config also skips opaque sub-trees, so a config that the
    runtime accepts also passes validation."""

    @dataclass
    class AppConfig:
        extensions: dict[str, dict] = field(default_factory=dict)

    @click.group
    @option("--dummy-flag/--no-flag")
    @config_option(config_schema=AppConfig, strict=True)
    @validate_config_option
    def validate_opaque_cli(dummy_flag):
        echo("ok")

    @validate_opaque_cli.command
    def sub():
        echo("sub")

    conf_path = create_config(
        "validate_opaque.toml",
        dedent("""\
            [validate-opaque-cli]
            dummy_flag = true

            [validate-opaque-cli.extensions.plugin-a]
            anything = "goes"
            """),
    )

    result = invoke(
        validate_opaque_cli,
        "--validate-config",
        str(conf_path),
        color=False,
    )
    assert result.exit_code == 0
    assert "is valid" in result.stderr


# ConfigValidator: app-registered validators run against opaque sub-trees
# during both --validate-config and normal --config loading.


def test_config_validator_runs_and_fails_under_validate_config(invoke, create_config):
    """A registered ``ConfigValidator`` runs during ``--validate-config`` and
    surfaces its ``ValidationError`` with a path rooted at the config file."""

    from click_extra import ConfigValidator, ValidationError

    @dataclass
    class AppConfig:
        managers: dict[str, dict] = field(default_factory=dict)

    def validate_managers(section: dict) -> None:
        for manager_id, fields in section.items():
            for key in fields:
                if key not in {"timeout", "search_path"}:
                    raise ValidationError(
                        f"{manager_id}.{key}",
                        f"unknown field {key!r}",
                        code="unknown_field",
                    )

    @click.group
    @option("--dummy-flag/--no-flag")
    @config_option(
        config_schema=AppConfig,
        strict=True,
        config_validators=(
            ConfigValidator(
                extension_path="managers",
                validator=validate_managers,
                description="Validates [<app>.managers.<id>] sub-tables.",
            ),
        ),
    )
    @validate_config_option
    def validator_cli(dummy_flag):
        echo("ok")

    @validator_cli.command
    def sub():
        echo("sub")

    # Valid config first: validator passes.
    valid_path = create_config(
        "validator_valid.toml",
        dedent("""\
            [validator-cli]
            dummy_flag = true

            [validator-cli.managers.winget]
            timeout = 30
            """),
    )
    result = invoke(validator_cli, "--validate-config", str(valid_path), color=False)
    assert result.exit_code == 0
    assert "is valid" in result.stderr

    # Invalid config: validator fails with rooted path.
    invalid_path = create_config(
        "validator_invalid.toml",
        dedent("""\
            [validator-cli]
            dummy_flag = true

            [validator-cli.managers.winget]
            timeout = 30
            badkey = "oops"
            """),
    )
    result = invoke(validator_cli, "--validate-config", str(invalid_path), color=False)
    assert result.exit_code == 1
    assert "validator-cli.managers.winget.badkey: unknown field 'badkey'" in (
        result.stderr
    )


def test_config_validator_runs_during_normal_load(invoke, create_config):
    """A misconfigured opaque sub-tree fails fast during normal config loading,
    not only under ``--validate-config``."""

    from click_extra import ConfigValidator, ValidationError

    @dataclass
    class AppConfig:
        managers: dict[str, dict] = field(default_factory=dict)

    def reject_all(section: dict) -> None:
        if section:
            raise ValidationError("", "no entries allowed")

    @click.group
    @config_option(
        config_schema=AppConfig,
        config_validators=(
            ConfigValidator(extension_path="managers", validator=reject_all),
        ),
    )
    def runtime_cli():
        echo("ok")

    @runtime_cli.command
    def sub():
        echo("sub")

    conf_path = create_config(
        "runtime_invalid.toml",
        dedent("""\
            [runtime-cli.managers.x]
            anything = 1
            """),
    )

    result = invoke(runtime_cli, "--config", str(conf_path), "sub", color=False)
    # The validator's failure produces a clean exit-1 with the rooted path in
    # the critical-level log, rather than a raw ValidationError traceback.
    assert result.exit_code == 1
    assert "runtime-cli.managers: no entries allowed" in result.stderr


def test_config_validator_extension_path_strips_strict_check(invoke, create_config):
    """A ConfigValidator(extension_path=...) registration alone is enough to skip
    strict-check on that path, even when the schema doesn't have the field."""
    from click_extra import ConfigValidator

    def noop_validator(section: dict) -> None:
        pass

    @click.group
    @config_option(
        strict=True,
        config_validators=(
            ConfigValidator(extension_path="extras", validator=noop_validator),
        ),
    )
    def strip_only_cli():
        echo("ok")

    @strip_only_cli.command
    def sub():
        echo("sub")

    conf_path = create_config(
        "strip_only.toml",
        dedent("""\
            [strip-only-cli.extras.foo]
            arbitrary = "data"
            """),
    )

    result = invoke(strip_only_cli, "--config", str(conf_path), "sub", color=False)
    assert result.exit_code == 0


def test_config_validator_collects_all_errors(invoke, create_config):
    """``--validate-config`` reports every detected error in one pass.

    A config with both an unknown CLI flag key and a validator-flagged field
    should surface both messages before the run exits non-zero, so the user
    sees the full punch list.
    """

    from click_extra import ConfigValidator, ValidationError

    @dataclass
    class AppConfig:
        managers: dict[str, dict] = field(default_factory=dict)

    def reject_badkey(section: dict) -> None:
        for manager_id, fields in section.items():
            if "badkey" in fields:
                raise ValidationError(
                    manager_id, "badkey is not allowed", code="unknown_field"
                )

    @click.group
    @option("--dummy-flag/--no-flag")
    @config_option(
        config_schema=AppConfig,
        strict=True,
        config_validators=(
            ConfigValidator(extension_path="managers", validator=reject_badkey),
        ),
    )
    @validate_config_option
    def both_errors_cli(dummy_flag):
        echo("ok")

    @both_errors_cli.command
    def sub():
        echo("sub")

    conf_path = create_config(
        "both_errors.toml",
        dedent("""\
            [both-errors-cli]
            dummy_flag = true
            unknown_flag = true

            [both-errors-cli.managers.x]
            badkey = "oops"
            """),
    )

    result = invoke(both_errors_cli, "--validate-config", str(conf_path), color=False)
    assert result.exit_code == 1
    # Both errors appear in the same run.
    assert "unknown_flag" in result.stderr
    assert "badkey is not allowed" in result.stderr


def test_collect_opaque_paths_from_schema():
    """Schema introspection picks up dict-typed fields, metadata-marked
    fields, and nested-dataclass opaque fields with dotted prefixes."""

    from click_extra import EXTENSION_METADATA_KEY

    # Use ``dict`` (the builtin) instead of typing.Any inside ``dict[str, X]``
    # so type-hint resolution doesn't depend on a module-level Any import.
    @dataclass
    class Nested:
        extras: dict[str, dict] = field(default_factory=dict)
        flat: int = 0

    @dataclass
    class AppConfig:
        timeout: int = 0
        managers: dict[str, dict] = field(default_factory=dict)
        nested: Nested = field(default_factory=Nested)
        marked: list = field(
            default_factory=list,
            metadata={EXTENSION_METADATA_KEY: True},
        )

    assert _collect_opaque_paths_from_schema(AppConfig) == frozenset({
        "managers",
        "nested.extras",
        "marked",
    })
    # Empty result for non-dataclass schemas.
    assert _collect_opaque_paths_from_schema(None) == frozenset()
    assert _collect_opaque_paths_from_schema(int) == frozenset()


def test_schema_strict_honors_extension_metadata_on_non_mapping_field(
    invoke, create_config
):
    """schema_strict must not descend into an EXTENSION_METADATA_KEY-marked field
    whose Python type is not a mapping.

    Before the opaque-path unification, the outer strip honored the marker but
    the dataclass adapter's own flatten boundary inspected only the type hint, so
    the marked sub-tree was flattened into dotted keys and rejected as unknown.
    """

    from click_extra import EXTENSION_METADATA_KEY

    @dataclass
    class AppConfig:
        # Typed as a list, but the marker tells click-extra the backing dict in
        # the config file is user-controlled extension content.
        plugins: list = field(
            default_factory=list,
            metadata={EXTENSION_METADATA_KEY: True},
        )

    @group(config_schema=AppConfig, schema_strict=True)
    @pass_context
    def marked_strict_cli(ctx):
        config = get_tool_config(ctx)
        echo(f"plugins is {config.plugins!r}")

    @marked_strict_cli.command()
    def subcommand():
        echo("ok")

    conf_path = create_config(
        "marked_strict.toml",
        dedent("""\
            [marked-strict-cli.plugins.alpha]
            anything = "goes"

            [marked-strict-cli.plugins.beta]
            nested = { deeper = 1 }
            """),
    )

    result = invoke(
        marked_strict_cli, "--config", str(conf_path), "subcommand", color=False
    )
    assert result.exit_code == 0
    assert not result.exception
    # The marked sub-tree reaches the schema instance intact, not flattened.
    assert "plugins is {'alpha': {'anything': 'goes'}" in result.stdout


# run_config_validation: the unified pipeline primitive, exercised directly.


def test_run_config_validation_valid_document():
    """A clean document yields an ok report with the schema instance built and
    every opaque sub-tree extracted."""

    from click_extra import ConfigValidator, run_config_validation

    @dataclass
    class AppConfig:
        verbose: bool = False
        managers: dict[str, dict] = field(default_factory=dict)

    def accept(section: dict) -> None:
        pass

    conf = {"my-cli": {"verbose": True, "managers": {"brew": {"timeout": 1}}}}
    report = run_config_validation(
        conf,
        app_name="my-cli",
        params_template=None,
        config_schema=AppConfig,
        config_validators=(
            ConfigValidator(extension_path="managers", validator=accept),
        ),
    )
    assert report.ok
    assert report.errors == ()
    assert report.schema_instance == AppConfig(
        verbose=True, managers={"brew": {"timeout": 1}}
    )
    assert report.opaque_subtrees == {"managers": {"brew": {"timeout": 1}}}
    # No template was supplied, so there is no default_map payload to carry.
    assert report.merged_conf is None


def test_run_config_validation_exposes_merged_conf():
    """A passing strict check carries the template-filtered config as merged_conf,
    with recognized values merged in and unknown keys dropped."""

    from click_extra import run_config_validation

    report = run_config_validation(
        {"my-cli": {"verbose": True, "unknown": "dropped"}},
        app_name="my-cli",
        params_template={"my-cli": {"verbose": None, "count": None}},
        config_schema=None,
    )
    assert report.ok
    assert report.merged_conf is not None
    assert report.merged_conf["my-cli"]["verbose"] is True
    assert "unknown" not in report.merged_conf["my-cli"]


def test_run_config_validation_collects_all_then_short_circuits():
    """collect_all=True gathers errors from every stage in order; collect_all=False
    stops after the first."""

    from click_extra import ConfigValidator, run_config_validation

    @dataclass
    class AppConfig:
        managers: dict[str, dict] = field(default_factory=dict)

    def reject(section: dict) -> None:
        from click_extra import ValidationError

        if section:
            raise ValidationError("x", "no entries allowed")

    conf = {
        "my-cli": {
            "bogus_flag": True,
            "managers": {"x": {"badkey": "oops"}},
        }
    }
    params_template = {"my-cli": {"verbose": None}}

    full = run_config_validation(
        conf,
        app_name="my-cli",
        params_template=params_template,
        config_schema=AppConfig,
        config_validators=(
            ConfigValidator(extension_path="managers", validator=reject),
        ),
        strict=True,
        collect_all=True,
    )
    assert not full.ok
    # Stage order: CLI-flag strict check first, validator failure last.
    assert [e.code for e in full.errors] == ["unknown_parameter", None]
    assert "bogus_flag" in full.errors[0].message
    assert full.errors[1].path == "my-cli.managers.x"
    # The strict check raised, so no default_map payload is carried.
    assert full.merged_conf is None

    first_only = run_config_validation(
        conf,
        app_name="my-cli",
        params_template=params_template,
        config_schema=AppConfig,
        config_validators=(
            ConfigValidator(extension_path="managers", validator=reject),
        ),
        strict=True,
        collect_all=False,
    )
    assert len(first_only.errors) == 1
    assert first_only.errors[0].code == "unknown_parameter"


def test_run_config_validation_wraps_schema_errors():
    """A schema_strict failure is recorded as a ValidationError with the
    schema_error code, and the message is preserved verbatim."""

    from click_extra import run_config_validation

    @dataclass
    class AppConfig:
        known: str = "default"

    conf = {"my-cli": {"known": "ok", "typo": "oops"}}
    report = run_config_validation(
        conf,
        app_name="my-cli",
        params_template=None,
        config_schema=AppConfig,
        schema_strict=True,
    )
    assert not report.ok
    assert len(report.errors) == 1
    assert report.errors[0].code == "schema_error"
    assert report.errors[0].path == ""
    assert "typo" in report.errors[0].message
    # Empty path keeps the rendered string identical to the raw message.
    assert str(report.errors[0]) == report.errors[0].message


def test_run_config_validation_no_schema_no_template():
    """With neither a template nor a schema, the report is ok and carries no
    schema instance."""
    from click_extra import run_config_validation

    report = run_config_validation(
        {"my-cli": {"anything": 1}},
        app_name="my-cli",
        params_template=None,
        config_schema=None,
    )
    assert report.ok
    assert report.schema_instance is None
    assert report.opaque_subtrees == {}


def test_make_schema_callable_coerces_dict_to_dataclass():
    """The public make_schema_callable turns a raw config dict into a dataclass."""

    from click_extra import make_schema_callable

    @dataclass
    class Forecast:
        city: str = "paris"
        high_c: int = 0

    load = make_schema_callable(Forecast)
    assert load is not None
    # Hyphenated keys are normalized to field names.
    assert load({"city": "lyon", "high-c": 21}) == Forecast(city="lyon", high_c=21)
    # A non-dataclass callable is returned as-is; None passes through.
    assert make_schema_callable(str) is str
    assert make_schema_callable(None) is None


# --- schema introspection tests ---


def test_field_docstrings_returns_full_text():
    """Attribute docstrings are recovered whole, paragraph breaks preserved."""

    @dataclass
    class Orchard:
        rows: int = 4
        """Number of tree rows.

        Rows are planted north to south so every tree gets morning sun.
        """

        undocumented: str = "bare"

    docs = field_docstrings(Orchard)
    assert docs["rows"] == (
        "Number of tree rows.\n\n"
        "Rows are planted north to south so every tree gets morning sun."
    )
    # A field without an attribute docstring produces no entry at all.
    assert "undocumented" not in docs


def test_field_docstrings_degrades_without_source():
    """A class defined through exec has no source: the mapping is empty."""
    namespace: dict = {}
    exec(  # noqa: S102
        dedent("""
            from dataclasses import dataclass

            @dataclass
            class Ghost:
                size: int = 1
                \"\"\"Docstring lost to exec.\"\"\"
        """),
        namespace,
    )
    assert field_docstrings(namespace["Ghost"]) == {}


def test_schema_field_infos_flat_schema():
    """Keys are kebab-cased and sorted; defaults, types, and summaries surface."""

    @dataclass
    class Stand:
        opening_hour: int = 8
        """Hour the stand opens.

        Deliveries start one hour earlier.
        """

        city: str = "Lisbon"
        """City where the stand operates."""

    infos = schema_field_infos(Stand)
    assert [info.key for info in infos] == ["city", "opening-hour"]

    by_key = {info.key: info for info in infos}
    assert by_key["opening-hour"].type_hint == "int"
    assert by_key["opening-hour"].default == 8
    assert by_key["opening-hour"].summary == "Hour the stand opens."
    assert by_key["opening-hour"].description == (
        "Hour the stand opens.\n\nDeliveries start one hour earlier."
    )
    assert by_key["city"].default == "Lisbon"


def test_schema_field_infos_nested_and_config_path():
    """Nested dataclasses expand to dotted keys; config_path metadata wins."""

    @dataclass
    class Basket:
        apples: int = 3
        """How many apples fit in the basket."""

    @dataclass
    class Market:
        basket: Basket = field(
            default_factory=Basket,
            metadata={CONFIG_PATH_METADATA_KEY: "hand-basket"},
        )
        """Parent docstring: nested tables document their leaves only."""

        city: str = "Porto"

    infos = schema_field_infos(Market)
    assert [info.key for info in infos] == ["city", "hand-basket.apples"]
    # Only leaf fields produce records: the parent table has no row of its own.
    nested = infos[1]
    assert nested.default == 3
    assert nested.summary == "How many apples fit in the basket."


def test_schema_field_infos_sorts_segment_wise():
    """A sub-table's options stay contiguous when a sibling shares their prefix.

    Plain string sort would interleave `pear-cellar` between `pear.crates`
    and `pear.pickers` (in ASCII `-` sorts before `.`); segment-wise sort
    keeps the `pear` table's options together.
    """

    @dataclass
    class Pear:
        crates: int = 2
        pickers: int = 5

    @dataclass
    class Harvest:
        pear: Pear = field(default_factory=Pear)
        pear_cellar: bool = False

    infos = schema_field_infos(Harvest)
    assert [info.key for info in infos] == [
        "pear.crates",
        "pear.pickers",
        "pear-cellar",
    ]


def test_schema_field_infos_rejects_non_dataclass():
    """A non-dataclass schema is refused with a clear error."""
    with pytest.raises(TypeError, match="must be a dataclass type"):
        schema_field_infos(str)
    with pytest.raises(TypeError, match="must be a dataclass type"):
        schema_field_infos(42)  # type: ignore[arg-type]
