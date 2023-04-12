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

import pytest
from pytest_cases import parametrize

from .. import echo, option, extra_command, command
from ..parameters import normalize_envvar, extend_envvars
from ..platforms import is_windows


@pytest.mark.parametrize(
    "envvars_1, envvars_2, result",
    (
        ("MY_VAR", "MY_VAR", ("MY_VAR",)),
        (None, "MY_VAR", ("MY_VAR",)),
        ("MY_VAR", None, ("MY_VAR",)),
        (["MY_VAR"], "MY_VAR", ("MY_VAR",)),
        (["MY_VAR"], None, ("MY_VAR",)),
        ("MY_VAR", ["MY_VAR"], ("MY_VAR",)),
        (None, ["MY_VAR"], ("MY_VAR",)),
        (["MY_VAR"], ["MY_VAR"], ("MY_VAR",)),
        (["MY_VAR1"], ["MY_VAR2"], ("MY_VAR1", "MY_VAR2")),
        (["MY_VAR1", "MY_VAR2"], ["MY_VAR2"], ("MY_VAR1", "MY_VAR2")),
        (["MY_VAR1"], ["MY_VAR1", "MY_VAR2"], ("MY_VAR1", "MY_VAR2")),
        (["MY_VAR1"], ["MY_VAR2", "MY_VAR2"], ("MY_VAR1", "MY_VAR2")),
        (["MY_VAR1", "MY_VAR1"], ["MY_VAR2"], ("MY_VAR1", "MY_VAR2")),
    ),
)
def test_extend_envvars(envvars_1, envvars_2, result):
    assert extend_envvars(envvars_1, envvars_2) == result


@pytest.mark.parametrize(
    "env_name, normalized_env",
    (
        ("show-params-cli_VERSION", "SHOW_PARAMS_CLI_VERSION"),
        ("show---params-cli___VERSION", "SHOW_PARAMS_CLI_VERSION"),
    ),
)
def test_normalize_envvar(env_name, normalized_env):
    assert normalize_envvar(env_name) == normalized_env


def envvars_test_cases():
    params = []

    matrix = {
        (command, "command"): {
            "working_envvar": (
                # User-defined envvars are recognized as-is.
                "Magic",
                "sUper",
                # XXX Uppercased auto-generated envvar is recognized be should not.
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
                # XXX Uppercased auto-generated envvar is recognized be should not.
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
        "1": True,
        "": False,  # XXX: Should be True?
        "False": False,
        "false": False,
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
                    params.append(
                        pytest.param(
                            cmd_decorator,
                            envvar,
                            expected_flag,
                            id=f"{decorator_name}|{case_name}={envvar}|expected_flag={expected_flag}",
                        )
                    )

    return params


@parametrize("cmd_decorator, envvars, expected_flag", envvars_test_cases())
def test_default_auto_envvar(invoke, cmd_decorator, envvars, expected_flag):
    @cmd_decorator(context_settings={"auto_envvar_prefix": "yo"})
    @option("--flag/--no-flag", envvar=["Magic", "sUper"])
    def my_cli(flag):
        echo(f"Flag value: {flag}")

    registered_envvars = ["Magic", "sUper"]
    # @extra_command forces registration of auto-generated envvar.
    if cmd_decorator == extra_command:
        registered_envvars = tuple(registered_envvars + ["yo_FLAG"])
    assert my_cli.params[0].envvar == registered_envvars

    result = invoke(my_cli, env=envvars)
    assert result.exit_code == 0
    assert not result.stderr
    assert result.output == f"Flag value: {expected_flag}\n"
