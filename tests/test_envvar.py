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
import pytest
from extra_platforms import is_windows

from click_extra import command, echo, option
from click_extra.decorators import extra_command
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
        # Click does not show the auto-generated envvar in the help screen.
        (
            click.command,
            "  --flag / --no-flag  [env var: custom]\n",
        ),
        # Click Extra always adds the auto-generated envvar to the help screen
        # (and show the defaults).
        (
            extra_command,
            "  --flag / --no-flag        "
            "[env var: "
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
    assert result.exit_code == 0
    assert not result.stderr
    assert option_help in result.stdout


def envvars_test_cases():
    params = []

    matrix = {
        (command, "command"): {
            "working_envvar": (
                # User-defined envvars are recognized as-is.
                "Magic",
                "sUper",
                # XXX Uppercased auto-generated envvar is recognized but should not be.
                "YO_FLAG",
            ),
            "unknown_envvar": (
                # Uppercased user-defined envvar is not recognized.
                "MAGIC",
                # XXX Literal auto-generated is not recognized but should be.
                "yo_FLAG",
                # Mixed-cased auto-generated envvat is not recognized.
                "yo_FlAg",
            ),
        },
        (extra_command, "extra_command"): {
            "working_envvar": (
                # User-defined envvars are recognized as-is.
                "Magic",
                "sUper",
                # Literal auto-generated is properly recognized but is not in vanilla
                # Click (see above).
                "yo_FLAG",
                # XXX Uppercased auto-generated envvar is recognized but should not be.
                "YO_FLAG",
            ),
            "unknown_envvar": (
                # Uppercased user-defined envvar is not recognized.
                "MAGIC",
                # Mixed-cased auto-generated envvat is not recognized.
                "yo_FlAg",
            ),
        },
    }

    # Windows is automaticcaly normalizing any env var to upper-case, see:
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
            (command, "command"): {
                "working_envvar": all_envvars,
                "unknown_envvar": (),
            },
            (extra_command, "extra_command"): {
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
        "": False,  # XXX: Should be True?
        "False": False,
        "false": False,
        "fAlsE": False,
        "0": False,
    }
    # No envvar value will have an effect on the flag if the envvar is not recognized.
    broken_value_map = {k: False for k in working_value_map}

    for (cmd_decorator, decorator_name), envvar_cases in matrix.items():
        for case_name, envvar_names in envvar_cases.items():
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


@pytest.mark.parametrize("cmd_decorator, envvars, expected_flag", envvars_test_cases())
def test_auto_envvar_parsing(invoke, cmd_decorator, envvars, expected_flag):
    """This test highlights the way Click recognize and parse envvars.

    It shows that the default behavior is not ideal, and covers how ``extra_command``
    improves the situation by normalizing the envvar name.
    """

    @cmd_decorator(context_settings={"auto_envvar_prefix": "yo"})
    # XXX Explicitly pass bool type to fix 8.2.0 regression:
    # https://github.com/pallets/click/discussions/2863#discussioncomment-12675496
    @option("--flag/--no-flag", type=bool, envvar=["Magic", "sUper"])
    def my_cli(flag):
        echo(f"Flag value: {flag}")

    registered_envvars = ["Magic", "sUper"]
    # Specific behavior of @extra_command that is not present in vanilla Click.
    if cmd_decorator == extra_command:
        # @extra_command forces registration of auto-generated envvar.
        registered_envvars = [*registered_envvars, "yo_FLAG"]
        # On Windows, envvars are normalizes to uppercase.
        if os.name == "nt":
            registered_envvars = [envvar.upper() for envvar in registered_envvars]
        # @extra_command parameters returns envvar property as tuple, while vanilla Click
        # returns a list.
        registered_envvars = tuple(registered_envvars)
    assert my_cli.params[0].envvar == registered_envvars

    result = invoke(my_cli, env=envvars)
    assert result.exit_code == 0
    assert not result.stderr
    assert result.stdout == f"Flag value: {expected_flag}\n"


def test_env_copy():
    env_var = "MPM_DUMMY_ENV_VAR_93725"
    assert env_var not in os.environ

    no_env = env_copy()
    assert no_env is None

    extended_env = env_copy({env_var: "yo"})
    assert env_var in extended_env
    assert extended_env[env_var] == "yo"
    assert env_var not in os.environ
