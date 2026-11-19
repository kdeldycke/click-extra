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
"""Bug reports for the errors a command has no rule for.

A command given a `report_url` ends the run on such an error with a report that its
user can paste into an issue. The report gives the version and platform of the run,
its options, and the traceback of the error, between two `8<` markers. A link opens
the issue form of the project with a title filled in. See
{meth}`~click_extra.commands.Command.invoke`.

A CLI can also log a report of its own with {func}`log_report`, for a failure that
does not stop the run.

```{caution}
Issues are often public, so a report holds no file path. The traceback keeps module
names and line numbers, which say as much about the code as file paths, and nothing
about where it is installed. The options line masks the values of paths, patterns
and positional arguments. The message of the error stays as the code wrote it: the
report asks the user to read it before they paste it.
```
"""

from __future__ import annotations

import inspect
import logging
import os
import re
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, NoReturn
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import click
from click.core import ParameterSource

from . import context
from ._utils import CLI_ECOSYSTEM_PACKAGES
from .carapace import get_cache_dir
from .jobs import JobsOption
from .version import VersionOption
from .version_facts import env_summary

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from types import TracebackType
    from typing import Any

MAX_FRAMES: Final = 12
"""Innermost frames of a traceback that a report keeps.

The frames past them give way to a line that counts them: the innermost ones hold
the code that raised the error.
"""

MAX_MESSAGE_LENGTH: Final = 200
"""Characters of an error message that a report keeps."""

REPORT_START: Final = "----- 8< ----- bug report ----- 8< -----"
"""First line of the block that a user pastes into an issue."""

REPORT_END: Final = "----- 8< ----- end of bug report ----- 8< -----"
"""Last line of the block that a user pastes into an issue."""

REPORTS_FOLDER: Final = "reports"
"""Folder of the cache directory of a CLI that holds its saved reports."""


def describe_error(expt: BaseException) -> str:
    """The class and message of an exception, on one line of capped length.

    The class shows with its module, unless it is built in. The message keeps its
    first {data}`~click_extra.bug_report.MAX_MESSAGE_LENGTH` characters.
    """
    name = type(expt).__qualname__
    module = type(expt).__module__
    if module != "builtins":
        name = f"{module}.{name}"
    message = " ".join(str(expt).split())
    if len(message) > MAX_MESSAGE_LENGTH:
        message = f"{message[:MAX_MESSAGE_LENGTH]}..."
    return f"{name}: {message}" if message else name


def compact_frames(tb: TracebackType | None) -> tuple[str, ...]:
    """A traceback as `module:line in function` entries, outermost first.

    Module names say as much as file paths about the code, and nothing about where
    it is installed, so they are what a report shows. A method shows with its
    class, like `Path.open`.
    """
    frames = [
        f"{frame.f_globals.get('__name__', '?')}:{lineno} in {frame.f_code.co_qualname}"
        for frame, lineno in traceback.walk_tb(tb)
    ]
    if len(frames) > MAX_FRAMES:
        outer = len(frames) - MAX_FRAMES
        frames = [f"... {outer} outer frames", *frames[-MAX_FRAMES:]]
    return tuple(frames)


def cli_traceback(
    tb: TracebackType | None, callback: Callable[..., Any] | None = None
) -> TracebackType | None:
    """The traceback from its first frame outside the Click ecosystem.

    An error reaches {meth}`~click_extra.commands.Command.invoke` through the frames
    that Click and Click Extra run the command with, which are the same in every
    report. A traceback with no other frame is kept whole.

    The code of a CLI built in the Click ecosystem, like the `click-extra` CLI, is in
    it too. So the frame of `callback`, the function of the command, also starts the
    traceback.
    """
    code = getattr(inspect.unwrap(callback), "__code__", None) if callback else None
    current = tb
    while current is not None:
        module = current.tb_frame.f_globals.get("__name__", "")
        if (
            module.partition(".")[0] not in CLI_ECOSYSTEM_PACKAGES
            or current.tb_frame.f_code is code
        ):
            return current
        current = current.tb_next
    return tb


def culprit_function(tb: TracebackType | None, package: str) -> str:
    """The name of the innermost function of `package` in a traceback, or nothing.

    It names the code to fix, even for an error that Python or a library raised
    from a call of the package. A generator expression, a comprehension or a lambda
    has no name of its own, so the named function nearest to it in the traceback
    stands for it.
    """
    name = ""
    for frame, _lineno in traceback.walk_tb(tb):
        module = frame.f_globals.get("__name__", "")
        code_name = frame.f_code.co_name
        if module.partition(".")[0] == package and not code_name.startswith("<"):
            name = code_name
    return name


def masked_value(param: click.Parameter, value: Any) -> str:
    """One value of a parameter as a report shows it.

    A path or a pattern can name the files and the data of the user, so it shows as
    a placeholder, like the value of a positional argument, which is often the data
    the command works on. Other values show as typed.
    """
    if isinstance(param.type, (click.Path, click.File)) or isinstance(
        value, os.PathLike
    ):
        return "<path>"
    if isinstance(value, re.Pattern):
        return "<regexp>"
    if param.param_type_name == "argument":
        return f"<{param.name}>"
    return str(value)


def option_words(param: click.Parameter, value: Any) -> list[str]:
    """Render one parameter as typed on the command line, with its values masked.

    A flag shows alone, or as its secondary name when it is off, like `--no-color`.
    A counting option shows once per count. See {func}`masked_value` for the values.
    """
    if param.param_type_name == "argument":
        items = value if isinstance(value, tuple) else (value,)
        return [masked_value(param, item) for item in items]
    flag = max(param.opts, key=len)
    if getattr(param, "count", False):
        return [flag] * int(value or 0)
    if getattr(param, "is_flag", False):
        if value:
            return [flag]
        secondary = getattr(param, "secondary_opts", ())
        return [max(secondary, key=len)] if secondary else []
    groups = value if getattr(param, "multiple", False) else (value,)
    words: list[str] = []
    for group in groups:
        items = group if param.nargs != 1 and isinstance(group, tuple) else (group,)
        words.append(flag)
        words.extend(masked_value(param, item) for item in items)
    return words


def options_summary(ctx: click.Context) -> str:
    """The parameters of the run that do not come from their default, masked.

    Walks from the root command to the command of `ctx`, and names each subcommand
    on the way. A value from a configuration file or an environment variable counts,
    as it changes the run as much as one typed on the command line.

    The options of Click Extra keep no value of their own in the context, and none
    of them changes what a command does, except `--jobs`. It shows with the number
    of jobs it resolved to.
    """
    chain: list[click.Context] = []
    current: click.Context | None = ctx
    while current is not None:
        chain.insert(0, current)
        current = current.parent

    words: list[str] = []
    for level in chain:
        if level.parent is not None and level.info_name:
            words.append(level.info_name)
        for param in level.command.get_params(level):
            if param.name is None or level.get_parameter_source(param.name) in (
                None,
                ParameterSource.DEFAULT,
            ):
                continue
            if isinstance(param, JobsOption):
                jobs = context.get(level, context.JOBS, 1)
                words.extend((max(param.opts, key=len), str(jobs)))
            elif param.name in level.params:
                words.extend(option_words(param, level.params[param.name]))
    return " ".join(words) or "none"


def cli_version(ctx: click.Context) -> str | None:
    """The version of the root command, as its `--version` option prints it.

    The report reads it from a new {class}`~click_extra.version.VersionOption`,
    which takes the fields the command pinned on its own. The module of the root
    command's callback is pinned too, unless the command pinned one: the walk of
    the stack that finds it otherwise stops on the caller of the CLI, as the
    callback has returned when the error reaches the command.

    Returns `None` when the version cannot be found.
    """
    option = VersionOption()
    for param in ctx.find_root().command.params:
        if isinstance(param, VersionOption):
            for field_id in param._field_overrides:
                option.pin_field(field_id, getattr(param, field_id))
            break
    if "module" not in option._field_overrides:
        module = VersionOption.command_module(ctx)
        if module is not None:
            option.pin_field("module", module)
    # A report must not fail on a fact it cannot find. The walk raises on a frame
    # with no module, like that of a callback run by `exec()`.
    try:
        return option.version
    except Exception as expt:  # noqa: BLE001
        logging.getLogger(__name__).debug(f"Cannot find the version: {expt!r}")
        return None


def report_form_url(url: str, title: str) -> str:
    """The URL of the issue form, with `title` filled in.

    The query of `url` is kept, like the `template` that picks the form of a GitHub
    repository.
    """
    parts = urlsplit(url)
    query = [*parse_qsl(parts.query, keep_blank_values=True), ("title", title)]
    return urlunsplit(parts._replace(query=urlencode(query)))


def render_report(
    headline: str, title: str, details: Iterable[str], ctx: click.Context
) -> str:
    """The message inviting the user to file a bug report, with the block to paste.

    It links to the issue form of the `report_url` of the root command, with `title`
    filled in. The block opens with the version of the CLI, the platform and the
    options of the run, then gives the `details` of the error.

    An AI agent running the CLI gets a line of its own: it is to show the report to
    its user, who decides to file it.
    """
    # Deferred import: keeps extra_platforms off the startup path of every CLI.
    from extra_platforms import is_any_agent

    root = ctx.find_root()
    lines = [headline]
    url = getattr(root.command, "report_url", None)
    if url:
        lines.extend(("Please report it with this form:", report_form_url(url, title)))
    lines.append(
        "Paste the lines between the two 8< markers into the issue. They hold no "
        "file path, and mask the values of paths and arguments. Read the error "
        "lines first: an error message can quote your data."
    )
    if is_any_agent():
        lines.append(
            "AI agent: show this report to your user, and ask before you file it. "
            "Issues are often public."
        )
    name = root.info_name or root.command.name or "?"
    version = cli_version(ctx)
    lines.extend((
        REPORT_START,
        f"{name} {version}, {env_summary()}" if version else f"{name}, {env_summary()}",
        f"Options: {options_summary(ctx)}",
        *details,
        REPORT_END,
    ))
    return "\n".join(lines)


def save_report(report: str, ctx: click.Context) -> Path | None:
    """Write a bug report to a new file in the {data}`REPORTS_FOLDER` of the cache.

    The cache is that of the root command, as
    {func}`~click_extra.carapace.get_cache_dir` locates it. A user who loses the
    output of a long run, to a closed terminal or a short scrollback, still finds the
    report there. The file holds the report as it is printed, so it can be attached
    to an issue whole.

    Each report gets a new file, named after the time it was saved. `mkstemp()` adds
    random characters to the name and never reuses one, so two reports of the same
    second keep a file each.

    Returns `None` if the file cannot be written: the printed report then stands
    alone.
    """
    # Deferred import: keeps tempfile off the startup path of every CLI.
    import tempfile

    root = ctx.find_root()
    app_name = root.command.name or root.info_name
    if not app_name:
        return None
    folder = get_cache_dir(app_name) / REPORTS_FOLDER
    try:
        folder.mkdir(parents=True, exist_ok=True)
        handle, name = tempfile.mkstemp(
            prefix=f"bug-report-{datetime.now(UTC):%Y-%m-%dT%H-%M-%S}-",
            suffix=".txt",
            dir=folder,
        )
        with open(handle, "w", encoding="UTF-8") as report_file:
            report_file.write(f"{report}\n")
    except OSError as expt:
        logging.getLogger(__name__).debug(f"Cannot save the bug report: {expt!r}")
        return None
    return Path(name)


def log_report(
    level: int,
    headline: str,
    title: str,
    details: Iterable[str],
    ctx: click.Context | None = None,
) -> None:
    """Log the report that `render_report()` builds, and save it with `save_report()`.

    The report goes to the root logger, which the CLI prints. The path of the saved
    file comes last, alone on its line, so it is the last thing a user sees of the
    run, and easy to copy. It stays out of the file.

    `ctx` defaults to the context of the running command.
    """
    if ctx is None:
        ctx = click.get_current_context()
    report = render_report(headline, title, details, ctx)
    path = save_report(report, ctx)
    if path is not None:
        report += f"\nThis report is also saved in this file:\n{path}"
    logging.getLogger().log(level, report)


def report_unexpected_error(ctx: click.Context, expt: Exception) -> NoReturn:
    """End the run on an error that its command has no rule for.

    An `OSError` comes from the system, like a missing permission or a full disk,
    so the user can fix it: it ends the run with a one-line error, and its traceback
    goes to the debug log. Any other error is a bug. Its traceback is logged with the
    report inviting the user to file it, and the run exits with code 1. The report
    shows the frames from {func}`cli_traceback` on.

    The title of the issue names the class of the error and the innermost function
    of the package of the root command, which {func}`culprit_function` finds. Reports
    of the same bug then get the same title, so the issue form lists the one already
    open. Unlike a line number, a function name does not change between releases.
    """
    if isinstance(expt, OSError):
        logging.getLogger().debug("Traceback of the error:", exc_info=expt)
        raise click.ClickException(str(expt)) from expt

    tb = cli_traceback(expt.__traceback__, ctx.command.callback)
    root = ctx.find_root()
    # Code run by `exec()` has no module name, like a CLI that a documentation
    # page defines: its frames have none either, and match the empty package.
    module = getattr(root.command.callback, "__module__", None) or ""
    function = culprit_function(tb, module.partition(".")[0])
    where = f" in {function}" if function else ""
    error = describe_error(expt)
    logging.getLogger().critical(f"Unexpected error{where}:", exc_info=expt)
    log_report(
        logging.CRITICAL,
        f"{root.info_name or root.command.name} stopped on this error, which is a bug.",
        f"{error.partition(':')[0]}{where}",
        ("", error, *(f"  {frame}" for frame in compact_frames(tb))),
        ctx,
    )
    ctx.exit(1)
