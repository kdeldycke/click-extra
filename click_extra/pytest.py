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
"""Pytest fixtures and marks to help testing Click CLIs."""

from __future__ import annotations

try:
    import pytest  # noqa: F401
except ImportError:
    raise ImportError(
        "You need to install click_extra[pytest] extra dependencies to use this "
        "module."
    )

from typing import TYPE_CHECKING, Any

import click
import click.testing
import cloup
import pytest

from click_extra.decorators import command, extra_command, extra_group, group
from click_extra.testing import ExtraCliRunner

if TYPE_CHECKING:
    from pathlib import Path

    from _pytest.mark import MarkDecorator
    from _pytest.mark.structures import ParameterSet


@pytest.fixture
def extra_runner():
    """Runner fixture for ``click.testing.ExtraCliRunner``."""
    runner = ExtraCliRunner()
    with runner.isolated_filesystem():
        yield runner


@pytest.fixture
def invoke(extra_runner):
    """Invoke fixture shorthand for ``click.testing.ExtraCliRunner.invoke``."""
    return extra_runner.invoke


skip_naked = pytest.mark.skip(reason="Naked decorator not supported yet.")
"""Mark to skip Cloup decorators without parenthesis.

.. warning::
    `Cloup does not yet support decorators without parenthesis
    <https://github.com/janluke/cloup/issues/127>`_.
"""


def command_decorators(
    no_commands: bool = False,
    no_groups: bool = False,
    no_click: bool = False,
    no_cloup: bool = False,
    no_redefined: bool = False,
    no_extra: bool = False,
    with_parenthesis: bool = True,
    with_types: bool = False,
) -> tuple[ParameterSet, ...]:
    """Returns collection of Pytest parameters to test all forms of click/cloup/click-
    extra command-like decorators."""
    params: list[tuple[Any, set[str], str, tuple | MarkDecorator]] = []

    if no_commands is False:
        if not no_click:
            params.append((click.command, {"click", "command"}, "click.command", ()))
            if with_parenthesis:
                params.append(
                    (click.command(), {"click", "command"}, "click.command()", ()),
                )

        if not no_cloup:
            params.append(
                (cloup.command, {"cloup", "command"}, "cloup.command", skip_naked),
            )
            if with_parenthesis:
                params.append(
                    (cloup.command(), {"cloup", "command"}, "cloup.command()", ()),
                )

        if not no_redefined:
            params.append(
                (command, {"redefined", "command"}, "click_extra.command", ()),
            )
            if with_parenthesis:
                params.append(
                    (command(), {"redefined", "command"}, "click_extra.command()", ()),
                )

        if not no_extra:
            params.append(
                (
                    extra_command,
                    {"extra", "command"},
                    "click_extra.extra_command",
                    (),
                ),
            )
            if with_parenthesis:
                params.append(
                    (
                        extra_command(),
                        {"extra", "command"},
                        "click_extra.extra_command()",
                        (),
                    ),
                )

    if not no_groups:
        if not no_click:
            params.append((click.group, {"click", "group"}, "click.group", ()))
            if with_parenthesis:
                params.append((click.group(), {"click", "group"}, "click.group()", ()))

        if not no_cloup:
            params.append((cloup.group, {"cloup", "group"}, "cloup.group", skip_naked))
            if with_parenthesis:
                params.append((cloup.group(), {"cloup", "group"}, "cloup.group()", ()))

        if not no_redefined:
            params.append((group, {"redefined", "group"}, "click_extra.group", ()))
            if with_parenthesis:
                params.append(
                    (group(), {"redefined", "group"}, "click_extra.group()", ()),
                )

        if not no_extra:
            params.append(
                (
                    extra_group,
                    {"extra", "group"},
                    "click_extra.extra_group",
                    (),
                ),
            )
            if with_parenthesis:
                params.append(
                    (
                        extra_group(),
                        {"extra", "group"},
                        "click_extra.extra_group()",
                        (),
                    ),
                )

    decorator_params = []
    for deco, deco_type, label, marks in params:
        args = [deco]
        if with_types:
            args.append(deco_type)
        decorator_params.append(pytest.param(*args, id=label, marks=marks))

    return tuple(decorator_params)


@pytest.fixture
def create_config(tmp_path):
    """A generic fixture to produce a temporary configuration file."""

    def _create_config(filename: str | Path, content: str) -> Path:
        """Create a fake configuration file."""
        config_path: Path
        if isinstance(filename, str):
            config_path = tmp_path.joinpath(filename)
        else:
            config_path = filename.resolve()

        # Create the missing folder structure, like "mkdir -p" does.
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(content)

        return config_path

    return _create_config


default_options_uncolored_help = (
    r"  --time / --no-time        Measure and print elapsed execution time."
    r"  \[default:\n"
    r"                            no-time\]\n"
    r"  --color, --ansi / --no-color, --no-ansi\n"
    r"                            Strip out all colors and all ANSI codes from"
    r" output.\n"
    r"                            \[default: color\]\n"
    r"  -C, --config CONFIG_PATH  Location of the configuration file. Supports glob\n"
    r"                            pattern of local path and remote URL."
    r"  \[default:( \S+)?\n"
    r"(                            .+\n)*"
    r"                            \S+\.{toml,yaml,yml,json,ini,xml}\]\n"
    r"  --show-params             Show all CLI parameters, their provenance, defaults\n"
    r"                            and value, then exit.\n"
    r"  -v, --verbosity LEVEL     Either CRITICAL, ERROR, WARNING, INFO, DEBUG.\n"
    r"                            \[default: WARNING\]\n"
    r"  --version                 Show the version and exit.\n"
    r"  -h, --help                Show this message and exit.\n"
)


default_options_colored_help = (
    r"  \x1b\[36m--time\x1b\[0m / \x1b\[36m--no-time\x1b\[0m"
    r"        Measure and print elapsed execution time."
    r"  \x1b\[2m\[\x1b\[0m\x1b\[2mdefault:\n"
    r"                            "
    r"\x1b\[0m\x1b\[32m\x1b\[2m\x1b\[3mno-time\x1b\[0m\x1b\[2m\]\x1b\[0m\n"
    r"  \x1b\[36m--color\x1b\[0m, \x1b\[36m--ansi\x1b\[0m /"
    r" \x1b\[36m--no-color\x1b\[0m, \x1b\[36m--no-ansi\x1b\[0m\n"
    r"                            Strip out all colors and all ANSI codes from"
    r" output.\n"
    r"                            \x1b\[2m\[\x1b\[0m\x1b\[2mdefault:"
    r" \x1b\[0m\x1b\[32m\x1b\[2m\x1b\[3mcolor\x1b\[0m\x1b\[2m\]\x1b\[0m\n"
    r"  \x1b\[36m-C\x1b\[0m, \x1b\[36m--config\x1b\[0m"
    r" \x1b\[36m\x1b\[2mCONFIG_PATH\x1b\[0m"
    r"  Location of the configuration file. Supports glob\n"
    r"                            pattern of local path and remote URL."
    r"  \x1b\[2m\[\x1b\[0m\x1b\[2mdefault:( \S+)?\n"
    r"(                            .+\n)*"
    r"                            "
    r"\S+\.{toml,yaml,yml,json,ini,xml}\x1b\[0m\x1b\[2m\]\x1b\[0m\n"
    r"  \x1b\[36m--show-params\x1b\[0m"
    r"             Show all CLI parameters, their provenance, defaults\n"
    r"                            and value, then exit.\n"
    r"  \x1b\[36m-v\x1b\[0m, \x1b\[36m--verbosity\x1b\[0m"
    r" \x1b\[36m\x1b\[2mLEVEL\x1b\[0m"
    r"     Either \x1b\[35mCRITICAL\x1b\[0m, \x1b\[35mERROR\x1b\[0m, "
    r"\x1b\[35mWARNING\x1b\[0m, \x1b\[35mINFO\x1b\[0m, \x1b\[35mDEBUG\x1b\[0m.\n"
    r"                            \x1b\[2m\[\x1b\[0m\x1b\[2mdefault: "
    r"\x1b\[0m\x1b\[32m\x1b\[2m\x1b\[3mWARNING\x1b\[0m\x1b\[2m\]\x1b\[0m\n"
    r"  \x1b\[36m--version\x1b\[0m                 Show the version and exit.\n"
    r"  \x1b\[36m-h\x1b\[0m, \x1b\[36m--help\x1b\[0m"
    r"                Show this message and exit.\n"
)


default_debug_uncolored_logging = (
    r"debug: Set <Logger click_extra \(DEBUG\)> to DEBUG.\n"
    r"debug: Set <RootLogger root \(DEBUG\)> to DEBUG.\n"
)
default_debug_colored_logging = (
    r"\x1b\[34mdebug\x1b\[0m: Set <Logger click_extra \(DEBUG\)> to DEBUG.\n"
    r"\x1b\[34mdebug\x1b\[0m: Set <RootLogger root \(DEBUG\)> to DEBUG.\n"
)


default_debug_uncolored_config = (
    r"debug: Load configuration matching .+\*\.{toml,yaml,yml,json,ini,xml}\n"
    r"debug: Pattern is not an URL: search local file system.\n"
    r"debug: No configuration file found.\n"
)
default_debug_colored_config = (
    r"\x1b\[34mdebug\x1b\[0m: Load configuration"
    r" matching .+\*\.{toml,yaml,yml,json,ini,xml}\n"
    r"\x1b\[34mdebug\x1b\[0m: Pattern is not an URL: search local file system.\n"
    r"\x1b\[34mdebug\x1b\[0m: No configuration file found.\n"
)


default_debug_uncolored_version_details = (
    "debug: Version string template variables:\n"
    r"debug: {module}         : <module '\S+' from '.+'>\n"
    r"debug: {module_name}    : \S+\n"
    r"debug: {module_file}    : .+\n"
    r"debug: {module_version} : \S+\n"
    r"debug: {package_name}   : \S+\n"
    r"debug: {package_version}: \S+\n"
    r"debug: {exec_name}      : \S+\n"
    r"debug: {version}        : \S+\n"
    r"debug: {prog_name}      : \S+\n"
    r"debug: {env_info}       : {.*}\n"
)
default_debug_colored_version_details = (
    r"\x1b\[34mdebug\x1b\[0m: Version string template variables:\n"
    r"\x1b\[34mdebug\x1b\[0m: {module}         : <module '\S+' from '.+'>\n"
    r"\x1b\[34mdebug\x1b\[0m: {module_name}    : \x1b\[97m\S+\x1b\[0m\n"
    r"\x1b\[34mdebug\x1b\[0m: {module_file}    : .+\n"
    r"\x1b\[34mdebug\x1b\[0m: {module_version} : \x1b\[32m\S+\x1b\[0m\n"
    r"\x1b\[34mdebug\x1b\[0m: {package_name}   : \x1b\[97m\S+\x1b\[0m\n"
    r"\x1b\[34mdebug\x1b\[0m: {package_version}: \x1b\[32m\S+\x1b\[0m\n"
    r"\x1b\[34mdebug\x1b\[0m: {exec_name}      : \x1b\[97m\S+\x1b\[0m\n"
    r"\x1b\[34mdebug\x1b\[0m: {version}        : \x1b\[32m\S+\x1b\[0m\n"
    r"\x1b\[34mdebug\x1b\[0m: {prog_name}      : \x1b\[97m\S+\x1b\[0m\n"
    r"\x1b\[34mdebug\x1b\[0m: {env_info}       : \x1b\[90m{.*}\x1b\[0m\n"
)


default_debug_uncolored_log_start = (
    default_debug_uncolored_logging
    + default_debug_uncolored_config
    + default_debug_uncolored_version_details
)
default_debug_colored_log_start = (
    default_debug_colored_logging
    + default_debug_colored_config
    + default_debug_colored_version_details
)


default_debug_uncolored_log_end = (
    r"debug: Reset <RootLogger root \(DEBUG\)> to WARNING.\n"
    r"debug: Reset <Logger click_extra \(DEBUG\)> to WARNING.\n"
)
default_debug_colored_log_end = (
    r"\x1b\[34mdebug\x1b\[0m: Reset <RootLogger root \(DEBUG\)> to WARNING.\n"
    r"\x1b\[34mdebug\x1b\[0m: Reset <Logger click_extra \(DEBUG\)> to WARNING.\n"
)
