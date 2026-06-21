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
    import pytest
except ImportError:
    raise ImportError(
        "You need to install click_extra[pytest] extra dependencies to use this module."
    )


import click
import cloup
from _pytest.assertion.util import assertrepr_compare
from extra_platforms import is_windows

from click_extra.decorators import argument, command, group, option
from click_extra.testing import (
    CliRunner,
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
def runner():
    """Runner fixture for :class:`click_extra.testing.CliRunner`."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        yield runner


@pytest.fixture
def invoke(runner):
    """Invoke fixture shorthand for :meth:`click_extra.testing.CliRunner.invoke`."""
    return runner.invoke


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

    :return: Pytest parameters covering each command-like decorator variant:

        - ``click.command``
        - ``click.command()``
        - ``cloup.command``
        - ``cloup.command()``
        - ``click_extra.command``
        - ``click_extra.command()``
        - ``click.group``
        - ``click.group()``
        - ``cloup.group``
        - ``cloup.group()``
        - ``click_extra.group``
        - ``click_extra.group()``
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

    :return: Pytest parameters covering each parameter-like decorator variant:

        - ``click.option``
        - ``click.option()``
        - ``cloup.option``
        - ``cloup.option()``
        - ``click_extra.option``
        - ``click_extra.option()``
        - ``click.argument``
        - ``click.argument()``
        - ``cloup.argument``
        - ``cloup.argument()``
        - ``click_extra.argument``
        - ``click_extra.argument()``
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
    r"  --time / --no-time           Measure and print elapsed execution time\.\n"
    r"                               \[default: no-time\]\n"
    r"  --config CONFIG_PATH         Location of the configuration file\. Supports\n"
    r"                               local path with glob patterns or remote URL\.\n"
    r"                               \[default: .*\n"
    r"(?:                               .+\n"
    r")*                               .*\]\n"
    r"  --no-config                  Ignore all configuration files and only use\n"
    r"                               command line parameters and environment\n"
    r"                               variables\.\n"
    r"  --validate-config FILE       Validate the configuration file and exit\.\n"
    r"  --accessible                 Accessibility mode: disable colors and render\n"
    r"                               tables in a plain, screen-reader-friendly format\.\n"
    r"  --color \[auto\|always\|never\]  Colorize the output\. A bare --color is the same\n"
    r"                               as --color=always\.  \[default: auto\]\n"
    r"  --no-color                   Disable colorization \(alias of --color=never\)\.\n"
    r"  --progress / --no-progress   Show progress indicators during long operations\.\n"
    r"                               Disabled for non-interactive output \(pipes, dumb\n"
    r"                               terminals, CI\) and by --accessible\.  \[default:\n"
    r"                               progress\]\n"
    r"  --theme \[dark\|dracula\|light\|manpage\|monokai\|nord\|solarized_dark\]\n"
    r"                               Color theme used for help screens\.  \[default:\n"
    r"                               dark\]\n"
    r"  --show-params                Show all CLI parameters, their provenance,\n"
    r"                               defaults and value, then exit\.\n"
    r"  --table-format \[aligned\|asciidoc\|colon-grid\|csv\|csv-excel\|csv-excel-tab\|csv-unix\|double-grid\|double-outline\|fancy-grid\|fancy-outline\|github\|grid\|heavy-grid\|heavy-outline\|hjson\|html\|jira\|json\|json5\|jsonc\|latex\|latex-booktabs\|latex-longtable\|latex-raw\|mediawiki\|mixed-grid\|mixed-outline\|moinmoin\|orgtbl\|outline\|pipe\|plain\|presto\|pretty\|psql\|rounded-grid\|rounded-outline\|rst\|simple\|simple-grid\|simple-outline\|textile\|toml\|tsv\|unsafehtml\|vertical\|xml\|yaml\|youtrack\]\n"
    r"                               Rendering style of tables\.  \[default: rounded-\n"
    r"                               outline\]\n"
    r"  --verbosity LEVEL            Either CRITICAL, ERROR, WARNING, INFO, DEBUG\.\n"
    r"                               \[default: WARNING\]\n"
    r"  -v, --verbose                Increase the default WARNING verbosity by one\n"
    r"                               level for each additional repetition of the\n"
    r"                               option\.  \[default: 0\]\n"
    r"  -q, --quiet                  Decrease the default WARNING verbosity by one\n"
    r"                               level for each additional repetition of the\n"
    r"                               option\.  \[default: 0\]\n"
    r"  --man                        Show the command's man page \(roff\) and exit\.\n"
    r"  --version                    Show the version and exit\.\n"
    r"  -h, --help                   Show this message and exit\.\n"
)


default_options_colored_help = (
    r"  \x1b\[36m\x1b\[1m--time\x1b\[0m / \x1b\[36m\x1b\[1m--no-time\x1b\[0m           Measure and print elapsed execution time\.\n"
    r"                               \x1b\[2m\[\x1b\[0m\x1b\[2mdefault: \x1b\[0m\x1b\[32m\x1b\[2m\x1b\[3mno-time\x1b\[0m\x1b\[2m\]\x1b\[0m\n"
    r"  \x1b\[36m\x1b\[1m--config\x1b\[0m \x1b\[36m\x1b\[2m\x1b\[3mCONFIG_PATH\x1b\[0m         Location of the configuration file\. Supports\n"
    r"                               local path with glob patterns or remote URL\.\n"
    r"                               \x1b\[2m\[\x1b\[0m\x1b\[2mdefault: \x1b\[0m\x1b\[32m\x1b\[2m\x1b\[3m.*\n"
    r"(?:                               .+\n"
    r")*                               .*\x1b\[0m\x1b\[2m\]\x1b\[0m\n"
    r"  \x1b\[36m\x1b\[1m--no-config\x1b\[0m                  Ignore all configuration files and only use\n"
    r"                               command line parameters and environment\n"
    r"                               variables\.\n"
    r"  \x1b\[36m\x1b\[1m--validate-config\x1b\[0m \x1b\[36m\x1b\[2m\x1b\[3mFILE\x1b\[0m       Validate the configuration file and exit\.\n"
    r"  \x1b\[36m\x1b\[1m--accessible\x1b\[0m                 Accessibility mode: disable colors and render\n"
    r"                               tables in a \x1b\[35m\x1b\[1mplain\x1b\[0m, screen-reader-friendly format\.\n"
    r"  \x1b\[36m\x1b\[1m--color\x1b\[0m \[\x1b\[35m\x1b\[1mauto\x1b\[0m\|\x1b\[35m\x1b\[1malways\x1b\[0m\|\x1b\[35m\x1b\[1mnever\x1b\[0m\]  Colorize the output\. A bare \x1b\[36m\x1b\[1m--color\x1b\[0m is the same\n"
    r"                               as \x1b\[36m\x1b\[1m--color\x1b\[0m=\x1b\[35m\x1b\[1malways\x1b\[0m\.  \x1b\[2m\[\x1b\[0m\x1b\[2mdefault: \x1b\[0m\x1b\[32m\x1b\[2m\x1b\[3mauto\x1b\[0m\x1b\[2m\]\x1b\[0m\n"
    r"  \x1b\[36m\x1b\[1m--no-color\x1b\[0m                   Disable colorization \(alias of \x1b\[36m\x1b\[1m--color\x1b\[0m=\x1b\[35m\x1b\[1mnever\x1b\[0m\)\.\n"
    r"  \x1b\[36m\x1b\[1m--progress\x1b\[0m / \x1b\[36m\x1b\[1m--no-progress\x1b\[0m   Show progress indicators during long operations\.\n"
    r"                               Disabled for non-interactive output \(pipes, dumb\n"
    r"                               terminals, CI\) and by \x1b\[36m\x1b\[1m--accessible\x1b\[0m\.  \x1b\[2m\[\x1b\[0m\x1b\[2mdefault:\n"
    r"                               \x1b\[0m\x1b\[32m\x1b\[2m\x1b\[3mprogress\x1b\[0m\x1b\[2m\]\x1b\[0m\n"
    r"  \x1b\[36m\x1b\[1m--theme\x1b\[0m \[\x1b\[35m\x1b\[1mdark\x1b\[0m\|\x1b\[35m\x1b\[1mdracula\x1b\[0m\|\x1b\[35m\x1b\[1mlight\x1b\[0m\|\x1b\[35m\x1b\[1mmanpage\x1b\[0m\|\x1b\[35m\x1b\[1mmonokai\x1b\[0m\|\x1b\[35m\x1b\[1mnord\x1b\[0m\|\x1b\[35m\x1b\[1msolarized_dark\x1b\[0m\]\n"
    r"                               Color theme used for help screens\.  \x1b\[2m\[\x1b\[0m\x1b\[2mdefault:\n"
    r"                               \x1b\[0m\x1b\[32m\x1b\[2m\x1b\[3mdark\x1b\[0m\x1b\[2m\]\x1b\[0m\n"
    r"  \x1b\[36m\x1b\[1m--show-params\x1b\[0m                Show all CLI parameters, their provenance,\n"
    r"                               defaults and value, then exit\.\n"
    r"  \x1b\[36m\x1b\[1m--table-format\x1b\[0m \[\x1b\[35m\x1b\[1maligned\x1b\[0m\|\x1b\[35m\x1b\[1masciidoc\x1b\[0m\|\x1b\[35m\x1b\[1mcolon-grid\x1b\[0m\|\x1b\[35m\x1b\[1mcsv\x1b\[0m\|\x1b\[35m\x1b\[1mcsv-excel\x1b\[0m\|\x1b\[35m\x1b\[1mcsv-excel-tab\x1b\[0m\|\x1b\[35m\x1b\[1mcsv-unix\x1b\[0m\|\x1b\[35m\x1b\[1mdouble-grid\x1b\[0m\|\x1b\[35m\x1b\[1mdouble-outline\x1b\[0m\|\x1b\[35m\x1b\[1mfancy-grid\x1b\[0m\|\x1b\[35m\x1b\[1mfancy-outline\x1b\[0m\|\x1b\[35m\x1b\[1mgithub\x1b\[0m\|\x1b\[35m\x1b\[1mgrid\x1b\[0m\|\x1b\[35m\x1b\[1mheavy-grid\x1b\[0m\|\x1b\[35m\x1b\[1mheavy-outline\x1b\[0m\|\x1b\[35m\x1b\[1mhjson\x1b\[0m\|\x1b\[35m\x1b\[1mhtml\x1b\[0m\|\x1b\[35m\x1b\[1mjira\x1b\[0m\|\x1b\[35m\x1b\[1mjson\x1b\[0m\|\x1b\[35m\x1b\[1mjson5\x1b\[0m\|\x1b\[35m\x1b\[1mjsonc\x1b\[0m\|\x1b\[35m\x1b\[1mlatex\x1b\[0m\|\x1b\[35m\x1b\[1mlatex-booktabs\x1b\[0m\|\x1b\[35m\x1b\[1mlatex-longtable\x1b\[0m\|\x1b\[35m\x1b\[1mlatex-raw\x1b\[0m\|\x1b\[35m\x1b\[1mmediawiki\x1b\[0m\|\x1b\[35m\x1b\[1mmixed-grid\x1b\[0m\|\x1b\[35m\x1b\[1mmixed-outline\x1b\[0m\|\x1b\[35m\x1b\[1mmoinmoin\x1b\[0m\|\x1b\[35m\x1b\[1morgtbl\x1b\[0m\|\x1b\[35m\x1b\[1moutline\x1b\[0m\|\x1b\[35m\x1b\[1mpipe\x1b\[0m\|\x1b\[35m\x1b\[1mplain\x1b\[0m\|\x1b\[35m\x1b\[1mpresto\x1b\[0m\|\x1b\[35m\x1b\[1mpretty\x1b\[0m\|\x1b\[35m\x1b\[1mpsql\x1b\[0m\|\x1b\[35m\x1b\[1mrounded-grid\x1b\[0m\|\x1b\[35m\x1b\[1mrounded-outline\x1b\[0m\|\x1b\[35m\x1b\[1mrst\x1b\[0m\|\x1b\[35m\x1b\[1msimple\x1b\[0m\|\x1b\[35m\x1b\[1msimple-grid\x1b\[0m\|\x1b\[35m\x1b\[1msimple-outline\x1b\[0m\|\x1b\[35m\x1b\[1mtextile\x1b\[0m\|\x1b\[35m\x1b\[1mtoml\x1b\[0m\|\x1b\[35m\x1b\[1mtsv\x1b\[0m\|\x1b\[35m\x1b\[1munsafehtml\x1b\[0m\|\x1b\[35m\x1b\[1mvertical\x1b\[0m\|\x1b\[35m\x1b\[1mxml\x1b\[0m\|\x1b\[35m\x1b\[1myaml\x1b\[0m\|\x1b\[35m\x1b\[1myoutrack\x1b\[0m\]\n"
    r"                               Rendering style of tables\.  \x1b\[2m\[\x1b\[0m\x1b\[2mdefault: \x1b\[0m\x1b\[32m\x1b\[2m\x1b\[3mrounded-\n"
    r"                               outline\x1b\[0m\x1b\[2m\]\x1b\[0m\n"
    r"  \x1b\[36m\x1b\[1m--verbosity\x1b\[0m \x1b\[36m\x1b\[2m\x1b\[3mLEVEL\x1b\[0m            Either \x1b\[35m\x1b\[1mCRITICAL\x1b\[0m, \x1b\[35m\x1b\[1mERROR\x1b\[0m, \x1b\[35m\x1b\[1mWARNING\x1b\[0m, \x1b\[35m\x1b\[1mINFO\x1b\[0m, \x1b\[35m\x1b\[1mDEBUG\x1b\[0m\.\n"
    r"                               \x1b\[2m\[\x1b\[0m\x1b\[2mdefault: \x1b\[0m\x1b\[32m\x1b\[2m\x1b\[3mWARNING\x1b\[0m\x1b\[2m\]\x1b\[0m\n"
    r"  \x1b\[36m\x1b\[1m-v\x1b\[0m, \x1b\[36m\x1b\[1m--verbose\x1b\[0m                Increase the default \x1b\[35m\x1b\[1mWARNING\x1b\[0m verbosity by one\n"
    r"                               level for each additional repetition of the\n"
    r"                               option\.  \x1b\[2m\[\x1b\[0m\x1b\[2mdefault: \x1b\[0m\x1b\[32m\x1b\[2m\x1b\[3m0\x1b\[0m\x1b\[2m\]\x1b\[0m\n"
    r"  \x1b\[36m\x1b\[1m-q\x1b\[0m, \x1b\[36m\x1b\[1m--quiet\x1b\[0m                  Decrease the default \x1b\[35m\x1b\[1mWARNING\x1b\[0m verbosity by one\n"
    r"                               level for each additional repetition of the\n"
    r"                               option\.  \x1b\[2m\[\x1b\[0m\x1b\[2mdefault: \x1b\[0m\x1b\[32m\x1b\[2m\x1b\[3m0\x1b\[0m\x1b\[2m\]\x1b\[0m\n"
    r"  \x1b\[36m\x1b\[1m--man\x1b\[0m                        Show the command's man page \(roff\) and exit\.\n"
    r"  \x1b\[36m\x1b\[1m--version\x1b\[0m                    Show the version and exit\.\n"
    r"  \x1b\[36m\x1b\[1m-h\x1b\[0m, \x1b\[36m\x1b\[1m--help\x1b\[0m                   Show this message and exit\.\n"
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


default_debug_uncolored_quiet_log = (
    r"debug: Decreased log verbosity by \d+ levels: from WARNING to [A-Z]+.\n"
)
default_debug_colored_quiet_log = (
    r"\x1b\[34mdebug\x1b\[0m: Decreased log verbosity "
    r"by \d+ levels: from WARNING to [A-Z]+.\n"
)


default_config_file_pattern = (
    # ``*.json5`` and ``*.jsonc`` are only emitted by ``ConfigFormat`` when
    # the optional ``json5`` and ``json-with-comments`` packages are
    # importable (see ``click_extra.config``). Make both optional in the
    # regex so the same assertion matches whether or not those extras are
    # installed: full match in upstream CI, gracefully shorter match in
    # hermetic builders (Guix, Nixpkgs) that ship neither extra. Same
    # shape as the ``git_long_hash = (?:hash|None)`` graceful-degradation
    # pattern further down.
    r"\{\*\.toml,\*\.yaml,\*\.yml,\*\.json"
    r"(?:,\*\.json5)?(?:,\*\.jsonc)?"
    r",\*\.hjson,\*\.ini,\*\.xml,pyproject\.toml\}"
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
    r"debug: {author}         : .+\n"
    r"debug: {license}        : .+\n"
    r"debug: {exec_name}      : \S+\n"
    r"debug: {version}        : \S+\n"
    r"debug: {git_repo_path}  : \S+\n"
    r"debug: {git_branch}     : \S+\n"
    r"debug: {git_long_hash}  : (?:[a-f0-9]{40}|None)\n"
    r"debug: {git_short_hash} : (?:[a-f0-9]{4,40}|None)\n"
    r"debug: {git_date}       : (?:\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4}|None)\n"
    r"debug: {git_tag}        : \S+\n"
    r"debug: {git_tag_sha}    : \S+\n"
    r"debug: {git_distance}   : (?:\d+|None)\n"
    r"debug: {git_dirty}      : (?:dirty|clean|None)\n"
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
    r"\x1b\[34mdebug\x1b\[0m: {author}         : .+\n"
    r"\x1b\[34mdebug\x1b\[0m: {license}        : .+\n"
    r"\x1b\[34mdebug\x1b\[0m: {exec_name}      : \x1b\[97m\S+\x1b\[0m\n"
    r"\x1b\[34mdebug\x1b\[0m: {version}        : \x1b\[32m\S+\x1b\[0m\n"
    r"\x1b\[34mdebug\x1b\[0m: {git_repo_path}  : \x1b\[90m\S+\x1b\[0m\n"
    r"\x1b\[34mdebug\x1b\[0m: {git_branch}     : \x1b\[36m\S+\x1b\[0m\n"
    r"\x1b\[34mdebug\x1b\[0m: {git_long_hash}  : \x1b\[33m(?:[a-f0-9]{40}|None)\x1b\[0m\n"
    r"\x1b\[34mdebug\x1b\[0m: {git_short_hash} : \x1b\[33m(?:[a-f0-9]{4,40}|None)\x1b\[0m\n"
    r"\x1b\[34mdebug\x1b\[0m: {git_date}       : \x1b\[90m(?:\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4}|None)\x1b\[0m\n"
    r"\x1b\[34mdebug\x1b\[0m: {git_tag}        : \x1b\[36m\S+\x1b\[0m\n"
    r"\x1b\[34mdebug\x1b\[0m: {git_tag_sha}    : \x1b\[33m\S+\x1b\[0m\n"
    r"\x1b\[34mdebug\x1b\[0m: {git_distance}   : \x1b\[32m(?:\d+|None)\x1b\[0m\n"
    r"\x1b\[34mdebug\x1b\[0m: {git_dirty}      : \x1b\[31m(?:dirty|clean|None)\x1b\[0m\n"
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
