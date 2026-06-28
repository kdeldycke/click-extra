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

import logging
import os
import sys

import click
import pytest

from click_extra import (
    Style,
    color,
    color_option,
    command,
    echo,
    group,
    no_color_option,
    pass_context,
    secho,
    style,
    verbosity_option,
)
from click_extra.color import (
    COLOR_DISABLING_TERMS,
    _is_dark_rgb,
    _parse_osc_rgb,
    color_envvars,
    forced_color,
    query_osc_background,
    resolve_background,
    resolve_color_env,
)
from click_extra.pytest import (
    default_debug_colored_log_end,
    default_debug_colored_log_start,
    default_debug_colored_logging,
    default_debug_uncolored_log_end,
    default_debug_uncolored_log_start,
    default_debug_uncolored_logging,
)
from click_extra.theme import get_default_theme

theme = get_default_theme()

from .conftest import skip_windows_colors


@skip_windows_colors
@pytest.mark.parametrize("option_decorator", (color_option, color_option()))
@pytest.mark.parametrize(
    ("param", "expecting_colors"),
    (
        ("--color", True),
        ("--no-color", False),
        (None, True),
    ),
)
def test_standalone_color_option(
    invoke, option_decorator, param, expecting_colors, assert_output_regex
):
    """Check color option values, defaults and effects on all things colored, including
    verbosity option."""

    @click.command
    @verbosity_option
    @option_decorator
    @no_color_option
    def standalone_color():
        echo(Style(fg="yellow")("It works!"))
        echo("\x1b[0m\x1b[1;36mArt\x1b[46;34m\x1b[0m")
        echo(style("Run command.", fg="magenta"))
        logging.getLogger("click_extra").warning("Processing...")
        print(style("print() bypass Click.", fg="blue"))
        secho("Done.", fg="green")

    result = invoke(standalone_color, param, "--verbosity", "DEBUG", color=True)
    if expecting_colors:
        assert result.stdout == (
            "\x1b[33mIt works!\x1b[0m\n"
            "\x1b[0m\x1b[1;36mArt\x1b[46;34m\x1b[0m\n"
            "\x1b[35mRun command.\x1b[0m\n"
            "\x1b[34mprint() bypass Click.\x1b[0m\n"
            "\x1b[32mDone.\x1b[0m\n"
        )
        assert_output_regex(
            result.stderr,
            (
                rf"{default_debug_colored_logging}"
                r"\x1b\[33mwarning\x1b\[0m: Processing\.\.\.\n"
                rf"{default_debug_colored_log_end}"
            ),
        )
    else:
        assert result.stdout == (
            "It works!\n"
            "Art\n"
            "Run command.\n"
            "\x1b[34mprint() bypass Click.\x1b[0m\n"
            "Done.\n"
        )
        assert_output_regex(
            result.stderr,
            (
                rf"{default_debug_uncolored_logging}"
                r"warning: Processing\.\.\.\n"
                rf"{default_debug_uncolored_log_end}"
            ),
        )
    assert result.exit_code == 0


@pytest.mark.parametrize(
    ("env", "env_expect_colors"),
    (
        ({"COLOR": "True"}, True),
        ({"COLOR": "true"}, True),
        ({"COLOR": "1"}, True),
        ({"COLOR": ""}, True),
        ({"COLOR": "False"}, False),
        ({"COLOR": "false"}, False),
        ({"COLOR": "0"}, False),
        ({"NO_COLOR": "True"}, False),
        ({"NO_COLOR": "true"}, False),
        ({"NO_COLOR": "1"}, False),
        ({"NO_COLOR": ""}, False),
        ({"NO_COLOR": "False"}, True),
        ({"NO_COLOR": "false"}, True),
        ({"NO_COLOR": "0"}, True),
        ({"LLM": "True"}, False),
        ({"LLM": "true"}, False),
        ({"LLM": "1"}, False),
        ({"LLM": ""}, False),
        ({"LLM": "False"}, True),
        ({"LLM": "false"}, True),
        ({"LLM": "0"}, True),
        (None, True),
    ),
)
@pytest.mark.parametrize(
    ("param", "param_expect_colors"),
    (
        ("--color", True),
        ("--no-color", False),
        (None, True),
    ),
)
def test_no_color_env_convention(
    invoke,
    env,
    env_expect_colors,
    param,
    param_expect_colors,
):
    @click.command
    @color_option
    @no_color_option
    def color_cli7():
        echo(Style(fg="yellow")("It works!"))

    # Unset all recognized color env vars so the outer environment (like
    # LLM=1 set by AI agents) doesn't leak into the baseline case.
    if env is None:
        env = {var: None for var in color_envvars if var in os.environ}

    result = invoke(color_cli7, param, color=True, env=env)

    # Params always overrides env's expectations.
    expecting_colors = env_expect_colors
    if param:
        expecting_colors = param_expect_colors
    if expecting_colors:
        assert result.stdout == "\x1b[33mIt works!\x1b[0m\n"
    else:
        assert result.stdout == "It works!\n"

    assert result.exit_code == 0
    assert not result.stderr


@pytest.mark.parametrize(
    ("term", "expected"),
    (
        # A dumb/unknown terminal cannot render ANSI: color-off even on a TTY.
        ("dumb", False),
        ("unknown", False),
        # A capable, empty, or unset TERM expresses no opinion (auto).
        ("xterm-256color", None),
        ("", None),
        (None, None),
    ),
)
def test_resolve_color_env_term(monkeypatch, term, expected):
    """A dumb/unknown TERM votes color-off, while any other value stays neutral."""
    # Clear every recognized color variable so only TERM is under test.
    for var in color_envvars:
        monkeypatch.delenv(var, raising=False)
    if term is None:
        monkeypatch.delenv("TERM", raising=False)
    else:
        monkeypatch.setenv("TERM", term)
    assert resolve_color_env() is expected


@pytest.mark.parametrize("term", sorted(COLOR_DISABLING_TERMS))
def test_resolve_color_env_force_color_beats_dumb_term(monkeypatch, term):
    """An explicit FORCE_COLOR stays authoritative over a dumb/unknown TERM."""
    for var in color_envvars:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("TERM", term)
    monkeypatch.setenv("FORCE_COLOR", "1")
    assert resolve_color_env() is True


# --- GNU --color synonyms, hidden aliases, and forgiving configuration ---
#
# ``--color`` accepts the GNU coreutils synonyms (yes/force, no/none, tty/if-tty)
# as hidden aliases for always/never/auto, case-insensitively. Configuration files
# additionally accept native booleans (true -> always, false -> never), including
# YAML's coercion of yes/no/on/off. See click_extra.color.ColorWhenChoice.


def _no_color_env():
    """Unset every recognized color env var so auto/tty resolve to None and the
    outer environment cannot leak into the synonym resolution."""
    return {var: None for var in color_envvars if var in os.environ}


@skip_windows_colors
@pytest.mark.parametrize(
    ("when", "ctx_color"),
    (
        # Canonical values.
        ("auto", "None"),
        ("always", "True"),
        ("never", "False"),
        # Canonical values are case-insensitive too.
        ("AUTO", "None"),
        ("Always", "True"),
        ("NEVER", "False"),
        # GNU "always" synonyms.
        ("yes", "True"),
        ("force", "True"),
        ("YES", "True"),
        ("Force", "True"),
        # GNU "never" synonyms.
        ("no", "False"),
        ("none", "False"),
        ("NO", "False"),
        ("None", "False"),
        # GNU "auto" synonyms.
        ("tty", "None"),
        ("if-tty", "None"),
        ("TTY", "None"),
        ("IF-TTY", "None"),
    ),
)
def test_color_synonym_cli_resolution(invoke, when, ctx_color):
    """Every canonical value and GNU synonym resolves --color to the right state."""

    @click.command
    @color_option
    @no_color_option
    @pass_context
    def color_synonym_cli(ctx):
        echo(f"ctx.color={ctx.color}")

    result = invoke(color_synonym_cli, f"--color={when}", env=_no_color_env())
    assert result.exit_code == 0
    assert result.stdout == f"ctx.color={ctx_color}\n"


@skip_windows_colors
@pytest.mark.parametrize("when", ("purple", "true", "false", "1", "0", ""))
def test_color_synonym_invalid_value(invoke, when):
    """Unknown values, including the git-style true/false, still error. The message
    lists only the canonical choices, never the hidden synonyms."""

    @click.command
    @color_option
    @no_color_option
    def color_invalid_cli():
        echo("unreached")

    result = invoke(color_invalid_cli, f"--color={when}", env=_no_color_env())
    assert result.exit_code == 2
    assert "'auto', 'always', 'never'" in result.stderr
    # The synonyms stay out of the error message.
    for hidden in ("force", "none", "if-tty"):
        assert hidden not in result.stderr


@skip_windows_colors
def test_color_synonym_hidden_in_help(invoke):
    """The GNU synonyms are accepted but never advertised: --help shows only the
    canonical metavar."""

    @click.command
    @color_option
    @no_color_option
    def color_help_cli():
        echo("unreached")

    result = invoke(color_help_cli, "--help", env=_no_color_env())
    assert result.exit_code == 0
    assert "[auto|always|never]" in result.stdout
    for hidden in ("force", "if-tty"):
        assert hidden not in result.stdout


@skip_windows_colors
@pytest.mark.parametrize(
    ("when", "env_var", "ctx_color"),
    (
        # An explicit CLI synonym outranks the color env vars, like its canonical twin.
        ("yes", "NO_COLOR", "True"),
        ("force", "NO_COLOR", "True"),
        ("no", "FORCE_COLOR", "False"),
        ("none", "FORCE_COLOR", "False"),
    ),
)
def test_color_synonym_cli_beats_env(invoke, when, env_var, ctx_color):
    """A synonym on the command line keeps the same env precedence as its canonical
    twin: a command-line choice outranks the color environment variables."""

    @click.command
    @color_option
    @no_color_option
    @pass_context
    def color_env_cli(ctx):
        echo(f"ctx.color={ctx.color}")

    env = _no_color_env()
    env[env_var] = "1"
    result = invoke(color_env_cli, f"--color={when}", env=env)
    assert result.exit_code == 0
    assert result.stdout == f"ctx.color={ctx_color}\n"


@skip_windows_colors
@pytest.mark.parametrize(
    ("when", "ctx_color"),
    (
        ("always", "True"),
        ("yes", "True"),
        ("force", "True"),
        ("never", "False"),
        ("no", "False"),
        ("none", "False"),
        ("auto", "None"),
        ("tty", "None"),
        ("if-tty", "None"),
        # Case-insensitive in configuration too.
        ("Force", "True"),
    ),
)
def test_color_synonym_config_string(invoke, create_config, when, ctx_color):
    """A configuration file accepts the GNU synonyms as strings, normalized exactly
    like on the command line."""
    conf_path = create_config("color.toml", f'[color-cfg-cli]\ncolor = "{when}"\n')

    @command
    @pass_context
    def color_cfg_cli(ctx):
        echo(f"ctx.color={ctx.color}")

    result = invoke(color_cfg_cli, "--config", str(conf_path), env=_no_color_env())
    assert result.exit_code == 0
    assert f"ctx.color={ctx_color}\n" in result.stdout


@skip_windows_colors
@pytest.mark.parametrize(
    ("filename", "raw", "ctx_color"),
    (
        # Native booleans in TOML and JSON.
        ("color.toml", "true", "True"),
        ("color.toml", "false", "False"),
        ("color.json", "true", "True"),
        ("color.json", "false", "False"),
        # YAML's own true/false booleans.
        ("color.yaml", "true", "True"),
        ("color.yaml", "false", "False"),
        # YAML 1.1 coerces these to booleans; they must agree with the string
        # synonyms (yes == always, no == never).
        ("color.yaml", "yes", "True"),
        ("color.yaml", "no", "False"),
        ("color.yaml", "on", "True"),
        ("color.yaml", "off", "False"),
    ),
)
def test_color_synonym_config_boolean(invoke, create_config, filename, raw, ctx_color):
    """A configuration boolean maps true -> always and false -> never, including
    YAML's coercion of yes/no/on/off, so a value means the same across formats."""
    ext = filename.rsplit(".", 1)[1]
    if ext == "json":
        content = '{"color-cfg-cli": {"color": ' + raw + "}}"
    elif ext == "yaml":
        content = f"color-cfg-cli:\n  color: {raw}\n"
    else:
        content = f"[color-cfg-cli]\ncolor = {raw}\n"
    conf_path = create_config(filename, content)

    @command
    @pass_context
    def color_cfg_cli(ctx):
        echo(f"ctx.color={ctx.color}")

    result = invoke(color_cfg_cli, "--config", str(conf_path), env=_no_color_env())
    assert result.exit_code == 0
    assert f"ctx.color={ctx_color}\n" in result.stdout


@skip_windows_colors
@pytest.mark.parametrize(
    ("rhs", "env_var", "ctx_color"),
    (
        # A config value (string synonym or boolean) inherits the precedence of any
        # DEFAULT_MAP value: it outranks the color environment variables.
        ('"yes"', "NO_COLOR", "True"),
        ("true", "NO_COLOR", "True"),
        ('"no"', "FORCE_COLOR", "False"),
        ("false", "FORCE_COLOR", "False"),
    ),
)
def test_color_synonym_config_beats_env(invoke, create_config, rhs, env_var, ctx_color):
    """A config synonym or boolean beats the color environment variables, matching
    the documented precedence of canonical config values."""
    conf_path = create_config("color.toml", f"[color-cfg-cli]\ncolor = {rhs}\n")

    @command
    @pass_context
    def color_cfg_cli(ctx):
        echo(f"ctx.color={ctx.color}")

    env = _no_color_env()
    env[env_var] = "1"
    result = invoke(color_cfg_cli, "--config", str(conf_path), env=env)
    assert result.exit_code == 0
    assert f"ctx.color={ctx_color}\n" in result.stdout


@pytest.mark.parametrize(
    ("param", "expecting_colors", "ctx_color"),
    (
        ("--color", True, "True"),
        ("--no-color", False, "False"),
        # No flag: the GNU auto default leaves ctx.color at None (TTY detection),
        # yet a forced runner still renders colors.
        (None, True, "None"),
    ),
)
def test_integrated_color_option(
    invoke, param, expecting_colors, ctx_color, assert_output_regex
):
    """Check effect of color option on all things colored, including verbosity option.

    Also checks the color option in subcommands is inherited from parent context.
    """

    @group
    @pass_context
    def color_cli8(ctx):
        echo(f"ctx.color={ctx.color}")
        echo(Style(fg="yellow")("It works!"))
        echo("\x1b[0m\x1b[1;36mArt\x1b[46;34m\x1b[0m")

    @color_cli8.command()
    @pass_context
    def command1(ctx):
        echo(f"ctx.color={ctx.color}")
        echo(style("Run command #1.", fg="magenta"))
        logging.getLogger("click_extra").warning("Processing...")
        print(style("print() bypass Click.", fg="blue"))
        secho("Done.", fg="green")

    result = invoke(color_cli8, param, "--verbosity", "DEBUG", "command1", color=True)
    if expecting_colors:
        assert result.stdout == (
            f"ctx.color={ctx_color}\n"
            "\x1b[33mIt works!\x1b[0m\n"
            "\x1b[0m\x1b[1;36mArt\x1b[46;34m\x1b[0m\n"
            f"ctx.color={ctx_color}\n"
            "\x1b[35mRun command #1.\x1b[0m\n"
            "\x1b[34mprint() bypass Click.\x1b[0m\n"
            "\x1b[32mDone.\x1b[0m\n"
        )
        assert_output_regex(
            result.stderr,
            (
                rf"{default_debug_colored_log_start}"
                r"\x1b\[33mwarning\x1b\[0m: Processing\.\.\.\n"
                rf"{default_debug_colored_log_end}"
            ),
        )

    else:
        assert result.stdout == (
            f"ctx.color={ctx_color}\n"
            "It works!\n"
            "Art\n"
            f"ctx.color={ctx_color}\n"
            "Run command #1.\n"
            "\x1b[34mprint() bypass Click.\x1b[0m\n"
            "Done.\n"
        )
        assert_output_regex(
            result.stderr,
            (
                rf"{default_debug_uncolored_log_start}"
                r"warning: Processing\.\.\.\n"
                rf"{default_debug_uncolored_log_end}"
            ),
        )
    assert result.exit_code == 0


@pytest.mark.parametrize(
    ("args", "expecting_colors"),
    (
        # A --color placed before the eager screen has always worked.
        pytest.param(("--color=always", "--help"), True, id="color-before-help"),
        pytest.param(("--color=always", "--version"), True, id="color-before-version"),
        # ...and now also when placed after it. Click processes eager options in
        # command-line order, so a late --color used to pin ctx.color only after the
        # screen had already rendered and exited.
        pytest.param(("--help", "--color=always"), True, id="color-after-help"),
        pytest.param(("--version", "--color=always"), True, id="color-after-version"),
        # A bare --color (GNU optional value) trailing an eager screen still means
        # always.
        pytest.param(("--help", "--color"), True, id="bare-color-after-help"),
        pytest.param(("--version", "--color"), True, id="bare-color-after-version"),
        # No color request in a piped (non-TTY) run leaves the screens plain.
        pytest.param(("--help",), False, id="help-plain"),
        pytest.param(("--version",), False, id="version-plain"),
        # The negative --no-color wins wherever it sits, even after an eager screen.
        pytest.param(("--help", "--no-color"), False, id="no-color-after-help"),
        pytest.param(("--version", "--no-color"), False, id="no-color-after-version"),
        # The last color choice on the line wins, whatever --help's position.
        pytest.param(
            ("--help", "--color=never", "--color=always"), True, id="last-wins-on"
        ),
        pytest.param(
            ("--help", "--color=always", "--no-color"), False, id="last-wins-off"
        ),
        # GNU synonyms colorize the eager screens exactly like their canonical twin.
        pytest.param(("--color=force", "--help"), True, id="force-synonym-before-help"),
        pytest.param(("--help", "--color=yes"), True, id="yes-synonym-after-help"),
        pytest.param(("--version", "--color=no"), False, id="no-synonym-after-version"),
    ),
)
def test_color_settles_before_eager_help_and_version(invoke, args, expecting_colors):
    """--color / --no-color colorize the eager --help and --version screens whatever
    their position on the command line.

    Click processes eager options in command-line order, so a --color sitting after
    --help or --version would otherwise pin ``ctx.color`` only once the screen had
    already printed and exited. ``Command.parse_args`` settles the color options in a
    pre-pass to close that gap. See ``Command._resolve_color_eagerly``.
    """

    @command
    def color_cli():
        # Never reached: --help / --version short-circuit before invocation.
        echo(style("Unreached.", fg="yellow"))

    # Omitting the runner's color keeps it in piped (non-TTY) mode without stripping
    # ANSI, so only an explicit --color can introduce color codes into the screen.
    result = invoke(color_cli, *args)
    assert result.exit_code == 0
    assert ("\x1b[" in result.output) is expecting_colors


def test_forced_color_sets_and_restores_env(monkeypatch):
    """``forced_color`` forces ``FORCE_COLOR`` and clears Click Extra's disabling vars.

    Inside the context the capture sees ``FORCE_COLOR=1`` with every flag that would
    disable color (``NO_COLOR``, ``LLM``, …) removed; on exit the prior environment,
    including any pre-existing values, is restored untouched.
    """
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("LLM", "1")
    monkeypatch.delenv("FORCE_COLOR", raising=False)

    with forced_color():
        assert os.environ["FORCE_COLOR"] == "1"
        assert "NO_COLOR" not in os.environ
        assert "LLM" not in os.environ

    assert "FORCE_COLOR" not in os.environ
    assert os.environ["NO_COLOR"] == "1"
    assert os.environ["LLM"] == "1"


# --- Terminal background detection -------------------------------------------


@pytest.mark.parametrize(
    ("env", "expected"),
    (
        # CLITHEME explicit override, case- and variant-tolerant.
        ({"CLITHEME": "light"}, "light"),
        ({"CLITHEME": "dark"}, "dark"),
        ({"CLITHEME": "LIGHT"}, "light"),
        ({"CLITHEME": "dark:solarized"}, "dark"),
        # Unrecognized / auto CLITHEME falls through to the next signal.
        ({"CLITHEME": "auto", "COLORFGBG": "0;15"}, "light"),
        ({"CLITHEME": "bogus", "COLORFGBG": "15;0"}, "dark"),
        # COLORFGBG: background is the last field; 0-6 and 8 are dark.
        ({"COLORFGBG": "0;15"}, "light"),
        ({"COLORFGBG": "15;0"}, "dark"),
        ({"COLORFGBG": "0;default;15"}, "light"),
        ({"COLORFGBG": "15;default;0"}, "dark"),
        ({"COLORFGBG": "7;0"}, "dark"),
        ({"COLORFGBG": "15;7"}, "light"),
        ({"COLORFGBG": "garbage"}, None),
        # No signal at all leaves the decision to the caller.
        ({}, None),
        # Precedence: CLITHEME > COLORFGBG.
        ({"CLITHEME": "light", "COLORFGBG": "15;0"}, "light"),
    ),
)
def test_resolve_background(monkeypatch, env, expected):
    """Environment-variable precedence for the dark/light background decision."""
    for var in ("CLITHEME", "COLORFGBG"):
        monkeypatch.delenv(var, raising=False)
    for var, value in env.items():
        monkeypatch.setenv(var, value)
    assert resolve_background() == expected


def test_resolve_background_query_is_opt_in(monkeypatch):
    """The OSC 11 query runs only when ``allow_query`` is set, below the env vars."""
    for var in ("CLITHEME", "COLORFGBG"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(color, "query_osc_background", lambda: (255, 255, 255))

    # With no env signal and the query allowed, the live color decides.
    assert resolve_background(allow_query=True) == "light"
    # The query is never consulted when not explicitly allowed.
    assert resolve_background(allow_query=False) is None


def test_resolve_background_query_below_explicit_env(monkeypatch):
    """An explicit env signal outranks the live query even when querying is allowed."""
    monkeypatch.delenv("COLORFGBG", raising=False)
    monkeypatch.setenv("CLITHEME", "dark")
    monkeypatch.setattr(color, "query_osc_background", lambda: (255, 255, 255))
    assert resolve_background(allow_query=True) == "dark"


@pytest.mark.parametrize(
    ("response", "expected"),
    (
        (b"\x1b]11;rgb:1c1c/1c1c/1c1c\x07", (28, 28, 28)),
        (b"\x1b]11;rgb:ffff/ffff/ffff\x1b\\", (255, 255, 255)),
        (b"\x1b]11;rgb:00/00/00\x07", (0, 0, 0)),
        # 8-bit channels normalize the same as their 16-bit doublings.
        (b"\x1b]11;rgb:ff/ff/ff\x07", (255, 255, 255)),
        # rgba: the alpha channel is ignored.
        (b"\x1b]11;rgba:2e2e/3434/3636/ffff\x07", (46, 52, 54)),
        # A search skips any leading type-ahead before the reply.
        (b"typed-ahead\x1b]11;rgb:ff/ff/ff\x07", (255, 255, 255)),
        # No recognizable color yields None.
        (b"\x1b]11;rgb:nothex\x07", None),
        (b"no match here", None),
        (b"", None),
    ),
)
def test_parse_osc_rgb(response, expected):
    """An OSC 11 reply is parsed into an 8-bit RGB tuple, or None when malformed."""
    assert _parse_osc_rgb(response) == expected


@pytest.mark.parametrize(
    ("rgb", "is_dark"),
    (
        ((0, 0, 0), True),
        ((30, 30, 30), True),  # common dark terminal (#1e1e1e)
        ((40, 42, 54), True),  # Dracula background
        ((255, 255, 255), False),
        ((253, 246, 227), False),  # Solarized light background
        ((136, 136, 136), False),  # mid grey just above the L* 50 midpoint
    ),
)
def test_is_dark_rgb(rgb, is_dark):
    """Perceived-lightness classification of background colors."""
    assert _is_dark_rgb(rgb) is is_dark


class _FakeStream:
    """Minimal stdin/stdout stand-in wrapping a raw file descriptor."""

    def __init__(self, fd: int, *, tty: bool) -> None:
        self._fd = fd
        self._tty = tty

    def fileno(self) -> int:
        return self._fd

    def isatty(self) -> bool:
        return self._tty

    def write(self, text: str) -> None:
        os.write(self._fd, text.encode())

    def flush(self) -> None:
        pass


def test_query_osc_background_without_tty(monkeypatch):
    """The OSC query is a no-op when stdin or stdout is not a terminal."""
    not_a_tty = _FakeStream(0, tty=False)
    monkeypatch.setattr(sys, "__stdin__", not_a_tty)
    monkeypatch.setattr(sys, "__stdout__", not_a_tty)
    assert query_osc_background() is None


def test_query_osc_background_without_streams(monkeypatch):
    """A detached process (no __stdin__/__stdout__) cannot query the terminal."""
    monkeypatch.setattr(sys, "__stdin__", None)
    monkeypatch.setattr(sys, "__stdout__", None)
    assert query_osc_background() is None


@pytest.mark.skipif(os.name != "posix", reason="OSC query needs a POSIX pty")
def test_query_osc_background_pty(monkeypatch):
    """A full OSC 11 round-trip over a pseudo-terminal yields the parsed color."""
    import pty
    import termios
    import tty

    try:
        controller, worker = pty.openpty()
    except OSError as error:  # No pty available (sandboxed or exhausted).
        pytest.skip(f"no pseudo-terminal available: {error}")
    # Put the worker in cbreak before loading the reply so the bytes are
    # readable without waiting for a (never-sent) newline.
    tty.setcbreak(worker, termios.TCSANOW)
    os.write(controller, b"\x1b]11;rgb:1c1c/1c1c/1c1c\x07")

    stream = _FakeStream(worker, tty=True)
    monkeypatch.setattr(sys, "__stdin__", stream)
    monkeypatch.setattr(sys, "__stdout__", stream)
    try:
        assert query_osc_background(timeout=2.0) == (28, 28, 28)
    finally:
        os.close(controller)
        os.close(worker)
