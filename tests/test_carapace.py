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

from __future__ import annotations

import json
import os
import platform
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

import click
import cloup
import pytest
import requests
import yaml
from click.shell_completion import CompletionItem, get_completion_class
from cloup.constraints import mutually_exclusive

# jsonschema only gates the Carapace completion-spec validation tests; skip the
# whole module instead of failing collection when it is absent (hermetic
# builders such as Guix and Nixpkgs do not ship it by default).
jsonschema = pytest.importorskip("jsonschema")

import click_extra
from click_extra import carapace as carapace_module
from click_extra.carapace import (
    CARAPACE_DOCS_URL,
    CarapaceComplete,
    _flag_key,
    _flag_name,
    dump_carapace_spec,
    to_carapace_spec,
)
from click_extra.cli import demo
from click_extra.testing import CliRunner

CARAPACE_SCHEMA = json.loads(
    (Path(__file__).parent / "carapace-spec.schema.json").read_text(encoding="utf-8")
)


# -- Sample CLIs (domain-neutral) ---------------------------------------------


class FruitType(click.ParamType):
    """A param type with a custom, dynamic ``shell_complete`` override."""

    name = "fruit"

    def shell_complete(self, ctx, param, incomplete):
        return [CompletionItem("apple"), CompletionItem("banana")]


def complete_city(ctx, param, incomplete):
    """A param-level ``shell_complete`` callback."""
    return [CompletionItem("paris", help="France"), CompletionItem("oslo")]


@cloup.group()
def weather():
    """Weather tools."""


@weather.command(aliases=["fc"])
@click.option("-v", "--verbose", count=True, help="Increase `verbosity`.")
@click.option("--include", multiple=True, help="Patterns to include.")
@click.option("--unit", type=click.Choice(["celsius", "fahrenheit"]), help="Scale.")
@click.option("--out", type=click.Path(dir_okay=False), help="Output file.")
@click.option("--into", type=click.Path(file_okay=False, dir_okay=True))
@click.option("--loud/--quiet", "loud", help="Loud mode.")
@click.option("--fruit", type=FruitType(), help="Dynamic fruit.")
@click.option("--city", shell_complete=complete_city, help="Dynamic city.")
@click.argument("season", type=click.Choice(["spring", "summer"]))
@click.argument("days", nargs=-1, type=click.Path())
def forecast(verbose, include, unit, out, into, loud, fruit, city, season, days):
    """Forecast for a SEASON."""


@weather.command(hidden=True)
def secret():
    """A hidden command."""


@cloup.command()
@cloup.option_group(
    "Sources",
    cloup.option("--local"),
    cloup.option("--remote"),
    constraint=mutually_exclusive,
)
def sync(local, remote):
    """Sync from a source."""


@click_extra.group()
def xtool():
    """A Click Extra group with the full default option set."""


@xtool.command()
@click_extra.option("--name", help="A name.")
def hello(name):
    """Greet someone."""


WEATHER_SPEC = to_carapace_spec(weather, prog_name="weather")
FORECAST = next(c for c in WEATHER_SPEC["commands"] if c["name"] == "forecast")
SYNC_SPEC = to_carapace_spec(sync, prog_name="sync")
XTOOL_SPEC = to_carapace_spec(xtool, prog_name="xtool")


# -- Flag-key grammar ---------------------------------------------------------


@pytest.mark.parametrize(
    ("opts", "value", "optarg", "repeatable", "expected"),
    [
        (["--foo"], False, False, False, "--foo"),
        (["--foo"], True, False, False, "--foo="),
        (["--foo"], True, True, False, "--foo?"),
        (["--foo"], False, False, True, "--foo*"),
        (["--foo"], True, False, True, "--foo=*"),
        (["-f", "--foo"], False, False, False, "-f, --foo"),
        (["-f", "--foo"], True, False, False, "-f, --foo="),
        (["-f"], False, False, True, "-f*"),
        (["--verbose", "-v"], False, False, True, "-v, --verbose*"),
    ],
)
def test_flag_key_grammar(opts, value, optarg, repeatable, expected):
    assert (
        _flag_key(opts, value=value, optarg=optarg, repeatable=repeatable) == expected
    )


@pytest.mark.parametrize(
    ("opts", "expected"),
    [
        (["--table-format"], "table-format"),
        (["-v", "--verbose"], "verbose"),
        (["-q"], "q"),
    ],
)
def test_flag_name(opts, expected):
    assert _flag_name(opts) == expected


# -- Static spec encodings ----------------------------------------------------


def test_root_description():
    assert WEATHER_SPEC["name"] == "weather"
    assert WEATHER_SPEC["description"] == "Weather tools."


def test_count_flag_is_repeatable():
    assert "-v, --verbose*" in FORECAST["flags"]


def test_multiple_value_flag():
    assert "--include=*" in FORECAST["flags"]


def test_boolean_pair_splits_into_two_flags():
    assert "--loud" in FORECAST["flags"]
    assert "--quiet" in FORECAST["flags"]
    # Neither half takes a value.
    assert "--loud=" not in FORECAST["flags"]


def test_choice_inlined():
    assert FORECAST["completion"]["flag"]["unit"] == ["celsius", "fahrenheit"]


def test_path_file_vs_directory():
    assert FORECAST["completion"]["flag"]["out"] == ["$files"]
    assert FORECAST["completion"]["flag"]["into"] == ["$directories"]


def test_positional_choice():
    # season is the sole fixed-arity argument; its choices land in positional[0].
    assert FORECAST["completion"]["positional"] == [["spring", "summer"]]


def test_positionalany_variadic_path():
    assert FORECAST["completion"]["positionalany"] == ["$files"]


def test_hidden_command():
    secret_spec = next(c for c in WEATHER_SPEC["commands"] if c["name"] == "secret")
    assert secret_spec["hidden"] is True


def test_aliases():
    assert FORECAST["aliases"] == ["fc"]


def test_exclusive_flags_from_option_group():
    assert SYNC_SPEC["exclusiveflags"] == [["local", "remote"]]


# -- Dynamic completion actions -----------------------------------------------


@pytest.mark.parametrize("flag_name", ["fruit", "city"])
def test_dynamic_action_emitted(flag_name):
    action = FORECAST["completion"]["flag"][flag_name]
    assert len(action) == 1
    macro = action[0]
    assert macro.startswith("$(")
    assert "_WEATHER_COMPLETE=carapace_complete" in macro
    # The macro bakes the full command path (root + subcommand) AND the option
    # spelling. Carapace forwards neither to the macro: it strips parent command
    # names from the words, and routes a flag's value completion to this per-flag
    # action without putting the flag in those words. Both are restored so Click
    # resolves the right option's value under the right subcommand.
    assert f"COMP_WORDS=weather forecast $* --{flag_name}" in macro


# -- persistentflags ----------------------------------------------------------


def test_root_default_options_are_persistent():
    persistent = XTOOL_SPEC["persistentflags"]
    # A sampling across value, optional-value, count and boolean shapes.
    assert "--version" in persistent
    assert "--config=" in persistent
    assert "--color?" in persistent
    assert "-v, --verbose*" in persistent


def test_subcommand_does_not_repeat_persistent_flags():
    hello_spec = next(c for c in XTOOL_SPEC["commands"] if c["name"] == "hello")
    assert hello_spec["flags"] == {"--name=": "A name."}
    assert "persistentflags" not in hello_spec


def test_plain_cli_keeps_own_lookalike_option():
    # weather is a plain cloup group: its only default is --help, so forecast's
    # own -v/--verbose must survive rather than being mistaken for the default.
    assert "-v, --verbose*" in FORECAST["flags"]
    assert WEATHER_SPEC["persistentflags"] == {"--help": "Show this message and exit."}


# -- Schema conformance -------------------------------------------------------


@pytest.mark.parametrize(
    "spec",
    [WEATHER_SPEC, SYNC_SPEC, XTOOL_SPEC],
    ids=["weather", "sync", "xtool"],
)
def test_spec_validates_against_schema(spec):
    jsonschema.validate(spec, CARAPACE_SCHEMA)


# -- YAML serialization -------------------------------------------------------


def test_dump_has_header_and_name():
    out = dump_carapace_spec(weather, prog_name="weather")
    assert out.startswith("# Generated by Click Extra")
    assert f"# Documentation: {CARAPACE_DOCS_URL}\n" in out
    # Without an explicit invocation, the programmatic path omits the "# $" line.
    assert "\n# $ " not in out
    assert "\nname: weather\n" in out


def test_dump_records_invocation():
    out = dump_carapace_spec(
        weather, prog_name="weather", invocation="my-cli --carapace"
    )
    assert "# $ my-cli --carapace\n" in out


def test_dump_requires_pyyaml(monkeypatch):
    monkeypatch.setattr(carapace_module, "yaml", None)
    with pytest.raises(ImportError, match=r"click-extra\[carapace\]"):
        dump_carapace_spec(weather, prog_name="weather")


# -- Dynamic completion backend (CarapaceComplete) ----------------------------


@pytest.mark.once
def test_carapace_complete_registered():
    assert get_completion_class("carapace") is CarapaceComplete


@pytest.mark.parametrize(
    ("value", "help_text", "expected"),
    [
        ("apple", None, "apple"),
        ("apple", "a fruit", "apple\ta fruit"),
    ],
)
def test_format_completion(value, help_text, expected):
    comp = CarapaceComplete(weather, {}, "weather", "_WEATHER_COMPLETE")
    assert comp.format_completion(CompletionItem(value, help=help_text)) == expected


def test_get_completion_args_reads_comp_words(monkeypatch):
    monkeypatch.setenv("COMP_WORDS", "weather forecast --unit")
    comp = CarapaceComplete(weather, {}, "weather", "_WEATHER_COMPLETE")
    args, incomplete = comp.get_completion_args()
    assert args == ["forecast", "--unit"]
    assert incomplete == ""


def test_complete_reuses_click_machinery():
    # The backend resolves the same completions Click would for a custom callback.
    comp = CarapaceComplete(weather, {}, "weather", "_WEATHER_COMPLETE")
    items = comp.get_completions(["forecast", "--city"], "")
    values = {item.value for item in items}
    assert values == {"paris", "oslo"}


def test_subcommand_dynamic_completion_resolves_end_to_end(monkeypatch):
    """The COMP_WORDS a subcommand flag's generated macro builds must let the
    backend resolve that option's value, not the root command.

    When completing a subcommand flag's value, Carapace forwards an empty word
    list to the macro: it strips the parent command names, and keeps the flag
    being completed in its own state rather than passing it through. So the macro
    bakes both the command path and the flag spelling, and ``$*`` expands to
    nothing. This reconstructs the resulting COMP_WORDS from the generated macro
    and confirms the backend resolves the forecast callback. The original
    root-only, flag-less macro would have reconstructed bare ``weather`` and
    completed the subcommand list instead.
    """
    macro = FORECAST["completion"]["flag"]["city"][0]
    # The macro's COMP_WORDS template, with $* expanded to the empty word list
    # Carapace passes for a flag value.
    template = macro.split("COMP_WORDS=", 1)[1].split('"', 1)[0]
    monkeypatch.setenv("COMP_WORDS", template.replace("$*", ""))
    comp = CarapaceComplete(weather, {}, "weather", "_WEATHER_COMPLETE")
    args, incomplete = comp.get_completion_args()
    assert args == ["forecast", "--city"]
    values = {item.value for item in comp.get_completions(args, incomplete)}
    assert values == {"paris", "oslo"}


# -- CLI surface (wrap --carapace) --------------------------------------------


GREET_SCRIPT = """
import click

@click.group()
def cli():
    "Greeter."

@cli.command()
@click.option("--lang", type=click.Choice(["en", "fr"]))
@click.argument("name")
def hi(lang, name):
    "Say hi to NAME."
"""


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def greet_script(tmp_path):
    script = tmp_path / "greet.py"
    script.write_text(GREET_SCRIPT)
    return str(script)


def test_wrap_carapace_emits_valid_spec(runner, greet_script):
    result = runner.invoke(demo, ["wrap", "--carapace", greet_script], color=False)
    assert result.exit_code == 0
    assert result.stdout.startswith("# Generated by Click Extra")
    # The header records the reconstructed wrap command and the docs link.
    assert "\n# $ click-extra wrap --carapace -- " in result.stdout
    assert f"# Documentation: {CARAPACE_DOCS_URL}\n" in result.stdout
    # The emitted YAML round-trips and conforms to the schema.

    spec = yaml.safe_load(result.stdout)
    jsonschema.validate(spec, CARAPACE_SCHEMA)
    assert any(c["name"] == "hi" for c in spec["commands"])


def test_wrap_carapace_install(runner, greet_script, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    result = runner.invoke(
        demo, ["wrap", "--carapace", "--install", greet_script], color=False
    )
    assert result.exit_code == 0
    written = tmp_path / "carapace" / "specs" / "cli.yaml"
    assert written.exists()
    assert str(written) in result.stdout


@pytest.mark.parametrize(
    ("extra_flags", "message"),
    [
        (["--man"], "mutually exclusive"),
        (["--show-params"], "mutually exclusive"),
    ],
)
def test_wrap_carapace_mutually_exclusive(runner, greet_script, extra_flags, message):
    result = runner.invoke(
        demo, ["wrap", "--carapace", *extra_flags, greet_script], color=False
    )
    assert result.exit_code == 2
    assert message in result.output


def test_wrap_install_requires_carapace(runner, greet_script):
    result = runner.invoke(demo, ["wrap", "--install", greet_script], color=False)
    assert result.exit_code == 2
    assert "--install requires --carapace" in result.output


# -- Real carapace-spec engine (integration) ----------------------------------

# Pinned carapace-spec release exercised by the integration test below.
CARAPACE_SPEC_VERSION = "1.7.0"

# platform.machine() (lower-cased) -> carapace-spec release arch token.
CARAPACE_ARCH = {
    "aarch64": "arm64",
    "amd64": "amd64",
    "arm64": "arm64",
    "x86_64": "amd64",
}

# A self-contained weather CLI exercising each dynamic shell_complete shape: a
# root-level option, a subcommand option, and a subcommand argument. Invoked with
# --dump-carapace-spec it prints its own spec; otherwise it answers the completion
# the spec's dynamic macros call back into.
CARAPACE_RUNNER = '''\
import sys

import click
import cloup
from click.shell_completion import CompletionItem

import click_extra  # noqa: F401  Registers the carapace completion backend.


def complete_region(ctx, param, incomplete):
    return [CompletionItem("north"), CompletionItem("south")]


def complete_city(ctx, param, incomplete):
    return [CompletionItem("paris", help="France"), CompletionItem("oslo")]


def complete_zone(ctx, param, incomplete):
    return [CompletionItem("alpha"), CompletionItem("bravo")]


@cloup.group()
@click.option("--region", shell_complete=complete_region, help="Region.")
def weather(region):
    """Weather tools."""


@weather.command()
@click.option("--city", shell_complete=complete_city, help="City.")
@click.argument("zone", shell_complete=complete_zone)
def forecast(city, zone):
    """Forecast for a zone."""


if __name__ == "__main__":
    if "--dump-carapace-spec" in sys.argv:
        from click_extra.carapace import dump_carapace_spec

        sys.stdout.write(dump_carapace_spec(weather, prog_name="weather"))
    else:
        weather(prog_name="weather")
'''


@pytest.mark.network
@pytest.mark.once
def test_spec_drives_real_carapace_engine(tmp_path):
    """Feed a generated spec to the real carapace-spec binary, end-to-end.

    The tests above simulate Carapace at the CarapaceComplete level. This one
    downloads a pinned carapace-spec release and drives it through each dynamic
    shape: a root option, a subcommand option, and a subcommand argument. It
    guards the contract between the emitted macros and Carapace's real
    traverse/exec/parse behavior, which the simulation cannot see: Carapace strips
    parent command names from the words it forwards, and withholds the flag being
    completed entirely, so the macros must bake both back in.

    .. attention::
        Downloads the carapace-spec binary from GitHub and executes it, hence the
        ``network`` mark (and ``once``, to run on a single CI runner). The dynamic
        macro shells out, so the test only runs on POSIX platforms.
    """
    system = platform.system().lower()
    arch = CARAPACE_ARCH.get(platform.machine().lower())
    if system not in ("linux", "darwin"):
        pytest.skip(f"dynamic macro is POSIX-shell only, not {system}")
    if arch is None:
        pytest.skip(f"no carapace-spec asset for {platform.machine()}")

    # Download the pinned release archive from GitHub.
    asset = f"carapace-spec_{CARAPACE_SPEC_VERSION}_{system}_{arch}.tar.gz"
    url = (
        "https://github.com/carapace-sh/carapace-spec/releases/download/"
        f"v{CARAPACE_SPEC_VERSION}/{asset}"
    )
    with requests.get(url, timeout=60) as response:
        assert response.ok, f"failed to download {url}"
        archive_bytes = response.content

    archive = tmp_path / asset
    archive.write_bytes(archive_bytes)

    # Pull just the carapace-spec binary out of the archive by name. Reading the
    # member by hand (rather than extractall) sidesteps path-traversal and symlink
    # members and the cross-version tar extraction-filter churn.
    with tarfile.open(archive, "r:gz") as tar:
        member = next(
            (
                m
                for m in tar.getmembers()
                if m.isfile() and Path(m.name).name == "carapace-spec"
            ),
            None,
        )
        assert member is not None, tar.getnames()
        payload = tar.extractfile(member)
        assert payload is not None
        binary = tmp_path / "carapace-spec"
        binary.write_bytes(payload.read())
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)

    # Write the CLI and generate its spec through the script's own dump mode.
    script = tmp_path / "weather_cli.py"
    script.write_text(CARAPACE_RUNNER)
    spec = subprocess.run(
        [sys.executable, str(script), "--dump-carapace-spec"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    spec_file = tmp_path / "weather.yaml"
    spec_file.write_text(spec)

    # The dynamic macro execs the program by bare name, so a `weather` shim that
    # runs the script under this interpreter must be discoverable on PATH.
    bindir = tmp_path / "bin"
    bindir.mkdir()
    shim = bindir / "weather"
    shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n')
    shim.chmod(0o755)
    env = {**os.environ, "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}"}

    def complete(*words):
        """Ask the real engine to complete `weather <words> <TAB>`."""
        result = subprocess.run(
            [str(binary), str(spec_file), "export", "weather", *words],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, result.stderr
        return {value["value"] for value in json.loads(result.stdout)["values"]}

    # Each dynamic shape resolves through the real engine.
    assert complete("--region", "") == {"north", "south"}
    assert complete("forecast", "--city", "") == {"paris", "oslo"}
    assert complete("forecast", "") == {"alpha", "bravo"}
    # Carapace prefix-filters the full candidate set the callback returns.
    assert complete("forecast", "--city", "p") == {"paris"}
