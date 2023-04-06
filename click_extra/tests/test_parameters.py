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

from .. import command, echo, option
from ..parameters import normalize_envvar, extend_envvars


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


@pytest.mark.parametrize(
    "env, flag_value",
    (
        # User-defined Magic envvar is recognized.
        ({"Magic": "True"}, True),
        ({"Magic": "true"}, True),
        ({"Magic": "1"}, True),
        ({"Magic": ""}, False),  # XXX: Should be True?
        ({"Magic": "False"}, False),
        ({"Magic": "false"}, False),
        ({"Magic": "0"}, False),
        # Uppercased user-defined envvar is not recognized.
        ({"MAGIC": "True"}, False),
        ({"MAGIC": "true"}, False),
        ({"MAGIC": "1"}, False),
        ({"MAGIC": ""}, False),
        ({"MAGIC": "False"}, False),
        ({"MAGIC": "false"}, False),
        ({"MAGIC": "0"}, False),
        # Second user-defined envvar is recognized too.
        ({"sUper": "True"}, True),
        ({"sUper": "true"}, True),
        ({"sUper": "1"}, True),
        ({"sUper": ""}, False),  # XXX: Should be True?
        ({"sUper": "False"}, False),
        ({"sUper": "false"}, False),
        ({"sUper": "0"}, False),
        # Literal auto-generated yo_FLAG is not recognized.
        ({"yo_FLAG": "True"}, False),
        ({"yo_FLAG": "true"}, False),
        ({"yo_FLAG": "1"}, False),
        ({"yo_FLAG": ""}, False),
        ({"yo_FLAG": "False"}, False),
        ({"yo_FLAG": "false"}, False),
        ({"yo_FLAG": "0"}, False),
        # YO_FLAG is recognized.
        ({"YO_FLAG": "True"}, True),
        ({"YO_FLAG": "true"}, True),
        ({"YO_FLAG": "1"}, True),
        ({"YO_FLAG": ""}, False),  # XXX: Should be True?
        ({"YO_FLAG": "False"}, False),
        ({"YO_FLAG": "false"}, False),
        ({"YO_FLAG": "0"}, False),
        # yo_FlAg is not recognized because of its mixed case.
        ({"yo_FlAg": "True"}, False),
        ({"yo_FlAg": "true"}, False),
        ({"yo_FlAg": "1"}, False),
        ({"yo_FlAg": ""}, False),
        ({"yo_FlAg": "False"}, False),
        ({"yo_FlAg": "false"}, False),
        ({"yo_FlAg": "0"}, False),
        (None, False),
    ),
)
def test_default_auto_envvar(invoke, env, flag_value):
    @command(context_settings={"auto_envvar_prefix": "yo"})
    @option("--flag/--no-flag", envvar=["Magic", "sUper"])
    def my_cli(flag):
        echo(f"Flag value: {flag}")

    assert my_cli.params[0].envvar == ["Magic", "sUper"]

    result = invoke(my_cli, env=env)
    assert result.exit_code == 0
    assert not result.stderr
    assert result.output == f"Flag value: {flag_value}\n"
