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
        "You need to install click_extra[pytest] extra dependencies to use this module."
    )


import click
import cloup
import pytest
from _pytest.assertion.util import assertrepr_compare
from extra_platforms import is_windows

from click_extra.decorators import argument, command, group, option
from click_extra.testing import (
    ExtraCliRunner,
    RegexLineMismatch,
    regex_fullmatch_line_by_line,
)

TYPE_CHECKING = False
if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any

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


skip_naked = pytest.mark.skip(reason="Naked decorator not supported.")
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
    no_extra: bool = False,
    with_parenthesis: bool = True,
    with_types: bool = False,
) -> tuple[ParameterSet, ...]:
    """Returns collection of Pytest parameters to test all command-like decorators.

    Returns:

    - `click.command`
    - `click.command()`
    - `cloup.command`
    - `cloup.command()`
    - `click_extra.command`
    - `click_extra.command()`
    - `click.group`
    - `click.group()`
    - `cloup.group`
    - `cloup.group()`
    - `click_extra.group`
    - `click_extra.group()`
    """
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

        if not no_extra:
            params.append((command, {"extra", "command"}, "click_extra.command", ()))
            if with_parenthesis:
                params.append(
                    (command(), {"extra", "command"}, "click_extra.command()", ()),
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

        if not no_extra:
            params.append((group, {"extra", "group"}, "click_extra.group", ()))
            if with_parenthesis:
                params.append((group(), {"extra", "group"}, "click_extra.group()", ()))

    decorator_params = []
    for deco, deco_type, label, marks in params:
        args = [deco]
        if with_types:
            args.append(deco_type)
        decorator_params.append(pytest.param(*args, id=label, marks=marks))

    return tuple(decorator_params)


def option_decorators(
    no_options: bool = False,
    no_arguments: bool = False,
    no_click: bool = False,
    no_cloup: bool = False,
    no_extra: bool = False,
    with_parenthesis: bool = True,
    with_types: bool = False,
) -> tuple[ParameterSet, ...]:
    """Returns collection of Pytest parameters to test all parameter-like decorators.

    Returns:

    - `click.option`
    - `click.option()`
    - `cloup.option`
    - `cloup.option()`
    - `click_extra.option`
    - `click_extra.option()`
    - `click.argument`
    - `click.argument()`
    - `cloup.argument`
    - `cloup.argument()`
    - `click_extra.argument`
    - `click_extra.argument()`
    """
    params: list[tuple[Any, set[str], str, tuple | MarkDecorator]] = []

    if no_options is False:
        if not no_click:
            params.append((click.option, {"click", "option"}, "click.option", ()))
            if with_parenthesis:
                params.append(
                    (click.option(), {"click", "option"}, "click.option()", ()),
                )

        if not no_cloup:
            params.append(
                (cloup.option, {"cloup", "option"}, "cloup.option", skip_naked),
            )
            if with_parenthesis:
                params.append(
                    (cloup.option(), {"cloup", "option"}, "cloup.option()", ()),
                )

        if not no_extra:
            params.append((option, {"extra", "option"}, "click_extra.option", ()))
            if with_parenthesis:
                params.append(
                    (option(), {"extra", "option"}, "click_extra.option()", ()),
                )

    if no_arguments is False:
        if not no_click:
            params.append((click.argument, {"click", "argument"}, "click.argument", ()))
            if with_parenthesis:
                params.append(
                    (click.argument(), {"click", "argument"}, "click.argument()", ()),
                )

        if not no_cloup:
            params.append(
                (cloup.argument, {"cloup", "argument"}, "cloup.argument", skip_naked),
            )
            if with_parenthesis:
                params.append(
                    (cloup.argument(), {"cloup", "argument"}, "cloup.argument()", ()),
                )

        if not no_extra:
            params.append((argument, {"extra", "argument"}, "click_extra.argument", ()))
            if with_parenthesis:
                params.append(
                    (argument(), {"extra", "argument"}, "click_extra.argument()", ()),
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
        config_path.write_text(content, encoding="utf-8")

        return config_path

    return _create_config


default_options_uncolored_help = (
    r"  --time / --no-time    Measure and print elapsed execution time.  \[default: no-\n"
    r"                        time\]\n"
    r"  --color, --ansi / --no-color, --no-ansi\n"
    r"                        Strip out all colors and all ANSI codes from output.\n"
    r"                        \[default: color\]\n"
    r"  --config CONFIG_PATH  Location of the configuration file. Supports local path\n"
    r"                        with glob patterns or remote URL.  \[default:( \S+)?\n"
    # XXX We cannot do better than \S+ for the default path because it is OS-specific,
    # and we cannot hard-code the whole glob pattern because the line wrapping would be
    # different on different terminals.
    r"(                        .+\n)*"
    r"                        .*ni\|\*\.xml\]\n"
    r"  --no-config           Ignore all configuration files and only use command line\n"
    r"                        parameters and environment variables.\n"
    r"  --show-params         Show all CLI parameters, their provenance, defaults and\n"
    r"                        value, then exit.\n"
    r"  --table-format \[asciidoc\|csv\|csv-excel\|csv-excel-tab\|csv-unix\|double-grid\|double-outline\|fancy-grid\|fancy-outline\|github\|grid\|heavy-grid\|heavy-outline\|html\|jira\|latex\|latex-booktabs\|latex-longtable\|latex-raw\|mediawiki\|mixed-grid\|mixed-outline\|moinmoin\|orgtbl\|outline\|pipe\|plain\|presto\|pretty\|psql\|rounded-grid\|rounded-outline\|rst\|simple\|simple-grid\|simple-outline\|textile\|tsv\|unsafehtml\|vertical\|youtrack\]\n"
    r"                        Rendering style of tables.  \[default: rounded-outline\]\n"
    r"  --verbosity LEVEL     Either CRITICAL, ERROR, WARNING, INFO, DEBUG.  \[default:\n"
    r"                        WARNING\]\n"
    r"  -v, --verbose         Increase the default WARNING verbosity by one level for\n"
    r"                        each additional repetition of the option.  \[default: 0\]\n"
    r"  --version             Show the version and exit.\n"
    r"  -h, --help            Show this message and exit.\n"
)


default_options_colored_help = (
    r"  \x1b\[36m--time\x1b\[0m / \x1b\[36m--no-time\x1b\[0m    Measure and print elapsed execution time.  \x1b\[2m\[\x1b\[0m\x1b\[2mdefault: \x1b\[0m\x1b\[32m\x1b\[2m\x1b\[3mno-\n"
    r"                        time\x1b\[0m\x1b\[2m\]\x1b\[0m\n"
    r"  \x1b\[36m--color\x1b\[0m, \x1b\[36m--ansi\x1b\[0m / \x1b\[36m--no-color\x1b\[0m, \x1b\[36m--no-ansi\x1b\[0m\n"
    r"                        Strip out all colors and all ANSI codes from output.\n"
    r"                        \x1b\[2m\[\x1b\[0m\x1b\[2mdefault: \x1b\[0m\x1b\[32m\x1b\[2m\x1b\[3mcolor\x1b\[0m\x1b\[2m\]\x1b\[0m\n"
    r"  \x1b\[36m--config\x1b\[0m \x1b\[36m\x1b\[2mCONFIG_PATH\x1b\[0m  Location of the configuration file. Supports local path\n"
    # XXX We cannot do better than \S+ for the default path because it is OS-specific,
    # and we cannot hard-code the whole glob pattern because the line wrapping would be
    # different on different terminals.
    r"                        with glob patterns or remote URL.  \x1b\[2m\[\x1b\[0m\x1b\[2mdefault:( \S+)?\n"
    r"(                        .+\n)*"
    r"                        .*ni\|\*\.xml\x1b\[0m\x1b\[2m\]\x1b\[0m\n"
    r"  \x1b\[36m--no-config\x1b\[0m           Ignore all configuration files and only use command line\n"
    r"                        parameters and environment variables.\n"
    r"  \x1b\[36m--show-params\x1b\[0m         Show all CLI parameters, their provenance, defaults and\n"
    r"                        value, then exit.\n"
    r"  \x1b\[36m--table-format\x1b\[0m \[\x1b\[35masciidoc\x1b\[0m\|\x1b\[35mcsv\x1b\[0m\|\x1b\[35mcsv-excel\x1b\[0m\|\x1b\[35mcsv-excel-tab\x1b\[0m\|\x1b\[35mcsv-unix\x1b\[0m\|\x1b\[35mdouble-grid\x1b\[0m\|\x1b\[35mdouble-outline\x1b\[0m\|\x1b\[35mfancy-grid\x1b\[0m\|\x1b\[35mfancy-outline\x1b\[0m\|\x1b\[35mgithub\x1b\[0m\|\x1b\[35mgrid\x1b\[0m\|\x1b\[35mheavy-grid\x1b\[0m\|\x1b\[35mheavy-outline\x1b\[0m\|\x1b\[35mhtml\x1b\[0m\|\x1b\[35mjira\x1b\[0m\|\x1b\[35mlatex\x1b\[0m\|\x1b\[35mlatex-booktabs\x1b\[0m\|\x1b\[35mlatex-longtable\x1b\[0m\|\x1b\[35mlatex-raw\x1b\[0m\|\x1b\[35mmediawiki\x1b\[0m\|\x1b\[35mmixed-grid\x1b\[0m\|\x1b\[35mmixed-outline\x1b\[0m\|\x1b\[35mmoinmoin\x1b\[0m\|\x1b\[35morgtbl\x1b\[0m\|\x1b\[35moutline\x1b\[0m\|\x1b\[35mpipe\x1b\[0m\|\x1b\[35mplain\x1b\[0m\|\x1b\[35mpresto\x1b\[0m\|\x1b\[35mpretty\x1b\[0m\|\x1b\[35mpsql\x1b\[0m\|\x1b\[35mrounded-grid\x1b\[0m\|\x1b\[35mrounded-outline\x1b\[0m\|\x1b\[35mrst\x1b\[0m\|\x1b\[35msimple\x1b\[0m\|\x1b\[35msimple-grid\x1b\[0m\|\x1b\[35msimple-outline\x1b\[0m\|\x1b\[35mtextile\x1b\[0m\|\x1b\[35mtsv\x1b\[0m\|\x1b\[35munsafehtml\x1b\[0m\|\x1b\[35mvertical\x1b\[0m\|\x1b\[35myoutrack\x1b\[0m\]\n"
    # XXX rounded-outline is double-highlighted because it is both the default
    # and one of the choices.
    r"                        Rendering style of tables.  \x1b\[2m\[\x1b\[0m\x1b\[2mdefault: \x1b\[0m\x1b\[32m\x1b\[2m\x1b\[3mrounded-\x1b\[35moutline\x1b\[0m\x1b\[0m\x1b\[2m\]\x1b\[0m\n"
    r"  \x1b\[36m--verbosity\x1b\[0m \x1b\[36m\x1b\[2mLEVEL\x1b\[0m     Either \x1b\[35mCRITICAL\x1b\[0m, \x1b\[35mERROR\x1b\[0m, \x1b\[35mWARNING\x1b\[0m, \x1b\[35mINFO\x1b\[0m, \x1b\[35mDEBUG\x1b\[0m.  \x1b\[2m\[\x1b\[0m\x1b\[2mdefault:\n"
    r"                        \x1b\[0m\x1b\[32m\x1b\[2m\x1b\[3mWARNING\x1b\[0m\x1b\[2m\]\x1b\[0m\n"
    r"  \x1b\[36m-v\x1b\[0m, \x1b\[36m--verbose\x1b\[0m         Increase the default \x1b\[35mWARNING\x1b\[0m verbosity by one level for\n"
    r"                        each additional repetition of the option.  \x1b\[2m\[\x1b\[0m\x1b\[2mdefault: \x1b\[0m\x1b\[32m\x1b\[2m\x1b\[3m0\x1b\[0m\x1b\[2m\]\x1b\[0m\n"
    r"  \x1b\[36m--version\x1b\[0m             Show the version and exit.\n"
    r"  \x1b\[36m-h\x1b\[0m, \x1b\[36m--help\x1b\[0m            Show this message and exit.\n"
)


default_debug_uncolored_logging = (
    r"debug: Set <Logger click_extra \(DEBUG\)> to DEBUG.\n"
    r"debug: Set <RootLogger root \(DEBUG\)> to DEBUG.\n"
)
default_debug_colored_logging = (
    r"\x1b\[34mdebug\x1b\[0m: Set <Logger click_extra \(DEBUG\)> to DEBUG.\n"
    r"\x1b\[34mdebug\x1b\[0m: Set <RootLogger root \(DEBUG\)> to DEBUG.\n"
)


default_debug_uncolored_verbose_log = (
    r"debug: Increased log verbosity by \d+ levels: from WARNING to [A-Z]+.\n"
)
default_debug_colored_verbose_log = (
    r"\x1b\[34mdebug\x1b\[0m: Increased log verbosity "
    r"by \d+ levels: from WARNING to [A-Z]+.\n"
)


default_config_file_pattern = (
    r"\*\.toml\|\*\.yaml\|\*\.yml\|\*\.json\|\*\.json5\|\*\.jsonc\|\*\.hjson\|\*\.ini\|"
    r"\*\.xml"
)
default_debug_uncolored_config = (
    rf"debug: Load configuration matching .+{default_config_file_pattern}\n"
    rf"debug: Search filesystem for .+{default_config_file_pattern}\n"
    + (
        r"debug: Windows pattern converted from"
        rf" .+{default_config_file_pattern} to .+{default_config_file_pattern}\n"
        if is_windows()
        else ""
    )
    + r"debug: No configuration file found.\n"
)
default_debug_colored_config = (
    rf"\x1b\[34mdebug\x1b\[0m: Load configuration matching .+{default_config_file_pattern}\n"
    rf"\x1b\[34mdebug\x1b\[0m: Search filesystem for .+{default_config_file_pattern}\n"
    + (
        r"\x1b\[34mdebug\x1b\[0m: Windows pattern converted from"
        rf" .+{default_config_file_pattern} to .+{default_config_file_pattern}\n"
        if is_windows()
        else ""
    )
    + r"\x1b\[34mdebug\x1b\[0m: No configuration file found.\n"
)


default_debug_uncolored_version_details = (
    r"debug: Version string template variables:\n"
    r"debug: {module}         : <module '\S+' from '.+'>\n"
    r"debug: {module_name}    : \S+\n"
    r"debug: {module_file}    : .+\n"
    r"debug: {module_version} : \S+\n"
    r"debug: {package_name}   : \S+\n"
    r"debug: {package_version}: \S+\n"
    r"debug: {exec_name}      : \S+\n"
    r"debug: {version}        : \S+\n"
    r"debug: {git_repo_path}  : \S+\n"
    r"debug: {git_branch}     : \S+\n"
    r"debug: {git_long_hash}  : [a-f0-9]{40}\n"
    r"debug: {git_short_hash} : [a-f0-9]{4,40}\n"
    r"debug: {git_date}       : \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4}\n"
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
    r"\x1b\[34mdebug\x1b\[0m: {git_repo_path}  : \x1b\[90m\S+\x1b\[0m\n"
    r"\x1b\[34mdebug\x1b\[0m: {git_branch}     : \x1b\[36m\S+\x1b\[0m\n"
    r"\x1b\[34mdebug\x1b\[0m: {git_long_hash}  : \x1b\[33m[a-f0-9]{40}\x1b\[0m\n"
    r"\x1b\[34mdebug\x1b\[0m: {git_short_hash} : \x1b\[33m[a-f0-9]{4,40}\x1b\[0m\n"
    r"\x1b\[34mdebug\x1b\[0m: {git_date}       : \x1b\[90m\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4}\x1b\[0m\n"
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


@pytest.fixture
def assert_output_regex(request):
    """An assert-like utility for Pytest to compare CLI output against the regex.

    Designed for the regexes defined above.
    """

    def _check_output(output: str, regex: str) -> None:
        """Check that the ``output`` matches the given ``regex``.

        Rely on Pytest's terminal writer to enhance diff highlighting.
        """
        try:
            regex_fullmatch_line_by_line(regex, output)
        except RegexLineMismatch as ex:
            explanation = assertrepr_compare(
                request.config, "==", ex.regex_line, ex.content_line
            )
            diff = "\n".join(explanation)  # type: ignore[arg-type]
            raise AssertionError(
                f"Output line {ex.content_line} does not match:\n{diff}"
            )

    return _check_output
