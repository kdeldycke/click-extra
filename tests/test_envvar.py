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

import os

import click
import cloup
import pytest
from extra_platforms import is_windows

from click_extra import command, echo, option
from click_extra.envvar import clean_envvar_id, env_copy, merge_envvar_ids


@pytest.mark.parametrize(
    ("envvars", "result"),
    (
        (("MY_VAR", "MY_VAR"), ("MY_VAR",)),
        ((None, "MY_VAR"), ("MY_VAR",)),
        (("MY_VAR", None), ("MY_VAR",)),
        ((["MY_VAR"], "MY_VAR"), ("MY_VAR",)),
        ((["MY_VAR"], None), ("MY_VAR",)),
        (("MY_VAR", ["MY_VAR"]), ("MY_VAR",)),
        ((None, ["MY_VAR"]), ("MY_VAR",)),
        ((["MY_VAR"], ["MY_VAR"]), ("MY_VAR",)),
        ((["MY_VAR1"], ["MY_VAR2"]), ("MY_VAR1", "MY_VAR2")),
        ((["MY_VAR1", "MY_VAR2"], ["MY_VAR2"]), ("MY_VAR1", "MY_VAR2")),
        ((["MY_VAR1"], ["MY_VAR1", "MY_VAR2"]), ("MY_VAR1", "MY_VAR2")),
        ((["MY_VAR1"], ["MY_VAR2", "MY_VAR2"]), ("MY_VAR1", "MY_VAR2")),
        ((["MY_VAR1", "MY_VAR1"], ["MY_VAR2"]), ("MY_VAR1", "MY_VAR2")),
        (
            (["MY_VAR1", ["MY_VAR1", None, "MY_VAR1"]], ["MY_VAR2"]),
            ("MY_VAR1", "MY_VAR2"),
        ),
    ),
)
def test_merge_envvar_ids(envvars, result):
    assert merge_envvar_ids(*envvars) == result


@pytest.mark.parametrize(
    ("env_name", "clean_name"),
    (
        ("show-params-cli_VERSION", "SHOW_PARAMS_CLI_VERSION"),
        ("show---params-cli___VERSION", "SHOW_PARAMS_CLI_VERSION"),
        ("__show-__params-_-_-", "SHOW_PARAMS"),
    ),
)
def test_clean_envvar_id(env_name, clean_name):
    assert clean_envvar_id(env_name) == clean_name


@pytest.mark.parametrize(
    ("cmd_decorator", "option_help"),
    (
        # Click and Cloup do not show the auto-generated envvar in the help screen.
        (
            click.command,
            "  --flag / --no-flag  [env var: custom]\n",
        ),
        (
            cloup.command,
            "  --flag / --no-flag  [env var: custom]\n",
        ),
        # Click Extra always adds the auto-generated envvar to the help screen
        # (and show the defaults).
        (
            command,
            "  --flag / --no-flag           [env var: "
            + ("CUSTOM, YO_FLAG" if os.name == "nt" else "custom, yo_FLAG")
            + "; default: no-flag]\n",
        ),
    ),
)
def test_show_auto_envvar_help(invoke, cmd_decorator, option_help):
    """Check that the auto-generated envvar appears in the help screen with the extra
    variants.

    Checks that https://github.com/pallets/click/issues/2483 is addressed.
    """

    @cmd_decorator(context_settings={"auto_envvar_prefix": "yo"})
    @option("--flag/--no-flag", envvar=["custom"], show_envvar=True)
    def envvar_help():
        pass

    # Remove colors to simplify output comparison.
    result = invoke(envvar_help, "--help", color=False)
    assert option_help in result.stdout
    assert not result.stderr
    assert result.exit_code == 0


def envvars_test_cases():
    params = []

    # Which spellings each framework answers to, given `auto_envvar_prefix="yo"`
    # and `envvar=["Magic", "sUper"]` on the option.
    #
    # Two rules explain every row, and neither is a defect:
    #
    # 1. A *user-defined* envvar is matched byte-for-byte, so `Magic` works and
    #    `MAGIC` does not.
    # 2. An *auto-generated* envvar is uppercased by Click: `Context.__init__`
    #    upper-cases `auto_envvar_prefix`, and `Parameter.resolve_envvar_value`
    #    builds `f"{prefix}_{name.upper()}"`. So the generated name is `YO_FLAG`,
    #    whatever case the prefix was declared in, and the literal `yo_FLAG` is
    #    not a name Click ever looks up.
    #
    # Rule 2 was raised upstream as a case-sensitivity bug in
    # https://github.com/pallets/click/issues/2483 and declined: "Environment
    # variables are case sensitive except on Windows. Traditionally, variables
    # are all uppercase... there's nothing to fix regarding case." So the
    # `YO_FLAG` rows below pin Click's intended behavior rather than a bug
    # awaiting a fix, and a Click release that stopped matching it would be a
    # real regression this test is meant to catch.
    #
    # What click-extra adds is the missing half: it registers the literal
    # `yo_FLAG` alongside, so an option answers to the prefix as it was written.
    # Neither framework matches an arbitrary mixed case like `yo_FlAg`.
    matrix = {
        (click.command, "click.command"): {
            "working_envvar": (
                # User-defined envvars are recognized as-is (rule 1).
                "Magic",
                "sUper",
                # The uppercased form is the generated name (rule 2).
                "YO_FLAG",
            ),
            "unknown_envvar": (
                # Uppercased user-defined envvar is not recognized (rule 1).
                "MAGIC",
                # The prefix as declared is never looked up (rule 2); this is
                # the spelling click-extra adds below.
                "yo_FLAG",
                # Mixed-cased auto-generated envvar matches neither form.
                "yo_FlAg",
            ),
        },
        (cloup.command, "cloup.command"): {
            # Cloup inherits Click's resolution untouched, so the two agree.
            "working_envvar": (
                "Magic",
                "sUper",
                "YO_FLAG",
            ),
            "unknown_envvar": (
                "MAGIC",
                "yo_FLAG",
                "yo_FlAg",
            ),
        },
        (command, "click_extra.command"): {
            "working_envvar": (
                # User-defined envvars are recognized as-is (rule 1).
                "Magic",
                "sUper",
                # click-extra's addition: the prefix as declared is registered
                # explicitly, so this spelling resolves where vanilla Click
                # leaves it unmatched.
                "yo_FLAG",
                # Click's generated name still resolves (rule 2).
                "YO_FLAG",
            ),
            "unknown_envvar": (
                # Uppercased user-defined envvar is not recognized (rule 1).
                "MAGIC",
                # Mixed-cased auto-generated envvar matches neither form.
                "yo_FlAg",
            ),
        },
    }

    # Windows automatically normalizes any env var to upper-case, see:
    # https://github.com/python/cpython/blob/e715da6/Lib/os.py#L748-L749
    # https://docs.python.org/3/library/os.html?highlight=environ#os.environ
    # So Windows needs its own test case.
    if is_windows():
        all_envvars = (
            "Magic",
            "MAGIC",
            "sUper",
            "yo_FLAG",
            "YO_FLAG",
            "yo_FlAg",
        )
        matrix = {
            (click.command, "click.command"): {
                "working_envvar": all_envvars,
                "unknown_envvar": (),
            },
            (cloup.command, "cloup.command"): {
                "working_envvar": all_envvars,
                "unknown_envvar": (),
            },
            (command, "click_extra.command"): {
                "working_envvar": all_envvars,
                "unknown_envvar": (),
            },
        }

    # If properly recognized, these envvar values should be passed to the flag.
    working_value_map = {
        "True": True,
        "true": True,
        "tRuE": True,
        "1": True,
        # An empty value never reaches the flag's type: `resolve_envvar_value`
        # guards its lookup with a bare `if rv`, and its docstring states that a
        # variable "present but has an empty string" resolves to `None`. So the
        # option falls back to its default, and `False` here is that default
        # rather than a parse of `""`. Flipping the option's default to `True`
        # flips this expectation with it.
        #
        # This is the one point where click-extra reads a flag differently:
        # `parse_envvar_flag("")` returns `True`, since the variables it serves
        # by hand (`NO_COLOR` and friends) follow the convention that bare
        # presence is the signal. Those never route through a Click option.
        "": False,
        "False": False,
        "false": False,
        "fAlsE": False,
        "0": False,
    }
    # No envvar value will have an effect on the flag if the envvar is not recognized.
    broken_value_map = {k: False for k in working_value_map}

    for (cmd_decorator, decorator_name), envvar_cases in matrix.items():
        for case_name, envvar_names in (
            envvar_cases.items()  # type: ignore[attr-defined]
        ):
            value_map = (
                working_value_map if case_name == "working_envvar" else broken_value_map
            )

            for envvar_name in envvar_names:
                for envar_value, expected_flag in value_map.items():
                    envvar = {envvar_name: envar_value}
                    test_id = (
                        f"{decorator_name}|{case_name}={envvar}"
                        f"|expected_flag={expected_flag}"
                    )
                    params.append(
                        pytest.param(cmd_decorator, envvar, expected_flag, id=test_id)
                    )

    return params


@pytest.mark.parametrize(
    ("cmd_decorator", "envvars", "expected_flag"), envvars_test_cases()
)
def test_auto_envvar_parsing(invoke, cmd_decorator, envvars, expected_flag):
    """This test highlights the way Click recognize and parse envvars.

    It shows that the default behavior is not ideal, and covers how ``command``
    improves the situation by normalizing the envvar name.
    """

    @cmd_decorator(context_settings={"auto_envvar_prefix": "yo"})
    @option("--flag/--no-flag", envvar=["Magic", "sUper"])
    def my_cli(flag):
        echo(f"Flag value: {flag}")

    registered_envvars: list[str] | tuple[str, ...] = ["Magic", "sUper"]
    # Specific behavior of @click_extra.command that is not present in vanilla Click.
    if cmd_decorator == command:
        # @command forces registration of auto-generated envvar.
        registered_envvars = [*registered_envvars, "yo_FLAG"]
        # On Windows, envvars are normalizes to uppercase.
        if os.name == "nt":
            registered_envvars = [envvar.upper() for envvar in registered_envvars]
        # @command parameters returns envvar property as tuple, while vanilla Click
        # returns a list.
        registered_envvars = tuple(registered_envvars)
    assert my_cli.params[0].envvar == registered_envvars

    result = invoke(my_cli, env=envvars)
    assert result.stdout == f"Flag value: {expected_flag}\n"
    assert not result.stderr
    assert result.exit_code == 0


@pytest.mark.parametrize("default", (False, True))
@pytest.mark.parametrize("cmd_decorator", (click.command, cloup.command, command))
def test_empty_envvar_falls_back_to_the_default(invoke, cmd_decorator, default):
    """An empty variable is read as unset, so the flag keeps its own default.

    Pins the rule the ``""`` row of :func:`envvars_test_cases` relies on:
    ``Parameter.resolve_envvar_value`` guards its lookup with a bare ``if rv``,
    so an empty value never reaches the flag's type. The ``False`` that row
    expects is the option's default showing through, which is why flipping the
    default flips the outcome with it.
    """

    # Parenthesized: Cloup rejects the naked form, and the rest of this module
    # calls every decorator anyway.
    @cmd_decorator()
    @option("--flag/--no-flag", default=default, envvar="Magic")
    def my_cli(flag):
        echo(f"Flag value: {flag}")

    for env in (None, {"Magic": ""}):
        result = invoke(my_cli, env=env)
        assert result.stdout == f"Flag value: {default}\n"
        assert result.exit_code == 0

    # A value that does parse still wins over the default, in both directions.
    for value, expected in (("1", True), ("0", False)):
        result = invoke(my_cli, env={"Magic": value})
        assert result.stdout == f"Flag value: {expected}\n"
        assert result.exit_code == 0


def test_env_copy():
    envvar = "MPM_DUMMY_ENVVAR_93725"
    assert envvar not in os.environ

    no_env = env_copy()
    assert no_env is None

    extended_env = env_copy({envvar: "yo"})
    assert extended_env is not None
    assert envvar in extended_env
    assert extended_env[envvar] == "yo"
    assert envvar not in os.environ


def test_env_copy_removes_on_none(monkeypatch):
    """A `None` value drops its variable, the way Click's ``CliRunner`` reads it.

    The only way to hide an inherited variable from a child: assigning the empty
    string leaves it set, which :func:`parse_envvar_flag` counts as activation.
    """
    envvar = "MPM_DUMMY_ENVVAR_93725"
    monkeypatch.setenv(envvar, "inherited")

    assert env_copy({envvar: "override"})[envvar] == "override"  # type: ignore[index]
    assert envvar not in env_copy({envvar: None})  # type: ignore[operator]
    # Removing what is not there is a no-op, not a KeyError.
    assert "MPM_DUMMY_ENVVAR_93726" not in env_copy({"MPM_DUMMY_ENVVAR_93726": None})  # type: ignore[operator]
    # The process environment is never touched.
    assert os.environ[envvar] == "inherited"
