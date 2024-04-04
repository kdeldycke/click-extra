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
"""Logging utilities."""

from __future__ import annotations

import logging
import sys
from gettext import gettext as _
from logging import (
    WARNING,
    Formatter,
    Handler,
    Logger,
    LogRecord,
    _levelToName,
)
from typing import TYPE_CHECKING, Literal, TypeVar

import click

from . import Choice, Context, Parameter
from .colorize import default_theme
from .parameters import ExtraOption

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable, Sequence

_original_get_logger = logging.getLogger


def _patched_get_logger(name: str | None = None) -> Logger:
    """Patch ``logging.getLogger`` to return the right root logger object.

    .. warning::
        This is a bugfix for Python 3.8 and earlier for which the ``root`` logger
        cannot be fetched with its plain ``root`` name.

        See:
        - `cpython#81923 <https://github.com/python/cpython/issues/81923>`_
        - `cpython@cb65b3a <https://github.com/python/cpython/commit/cb65b3a>`_
    """
    if name == "root":
        name = None
    return _original_get_logger(name)


if sys.version_info < (3, 9):
    logging.getLogger = _patched_get_logger


LOG_LEVELS: dict[str, int] = {
    name: value
    for value, name in sorted(_levelToName.items(), reverse=True)
    if name != "NOTSET"
}
"""Mapping of canonical log level names to their IDs.

Sorted from lowest to highest verbosity.

Are ignored:

- ``NOTSET``, which is considered internal
- ``WARN``, which `is obsolete
  <https://docs.python.org/3/library/logging.html?highlight=warn#logging.Logger.warning>`_
- ``FATAL``, which `shouldn't be used <https://github.com/python/cpython/issues/85013>`_
  and `replaced by CRITICAL
  <https://github.com/python/cpython/blob/0df7c3a/Lib/logging/__init__.py#L1538-L1541>`_
"""


DEFAULT_LEVEL: int = WARNING
DEFAULT_LEVEL_NAME: str = _levelToName[DEFAULT_LEVEL]
"""``WARNING`` is the default level we expect any loggers to starts their lives at.

``WARNING`` has been chosen as it is `the level at which the default Python's global
root logger is set up
<https://github.com/python/cpython/blob/0df7c3a/Lib/logging/__init__.py#L1945>`_.

This value is also used as the default level of the ``--verbosity`` option below.
"""


TFormatter = TypeVar("TFormatter", bound=Formatter)
THandler = TypeVar("THandler", bound=Handler)
"""Custom types to be used in type hints below."""


class ExtraLogHandler(Handler):
    """A handler to output logs to console's ``<stderr>``."""

    def emit(self, record: LogRecord) -> None:
        """Use ``click.echo`` to print to ``<stderr>`` and supports colors."""
        try:
            msg = self.format(record)
            click.echo(msg, err=True)

        # If exception occurs format it to the stream.
        except Exception:
            self.handleError(record)


class ExtraLogFormatter(Formatter):
    def formatMessage(self, record: LogRecord) -> str:
        """Colorize the record's log level name before calling the strandard
        formatter."""
        level = record.levelname.lower()
        level_style = getattr(default_theme, level, None)
        if level_style:
            record.levelname = level_style(level)
        return super().formatMessage(record)


def extra_basic_config(
    logger_name: str | None = None,
    format: str | None = "{levelname}: {message}",
    datefmt: str | None = None,
    style: Literal["%", "{", "$"] = "{",
    level: int | None = None,
    handlers: Iterable[Handler] | None = None,
    force: bool = True,
    handler_class: type[THandler] = ExtraLogHandler,  # type: ignore[assignment]
    formatter_class: type[TFormatter] = ExtraLogFormatter,  # type: ignore[assignment]
) -> Logger:
    """Setup and configure a logger.

    Reimplements `logging.basicConfig
    <https://docs.python.org/3/library/logging.html?highlight=basicconfig#logging.basicConfig>`_,
    but with sane defaults and more parameters.

    :param logger_name: ID of the logger to setup. If ``None``, Python's ``root``
        logger will be used.
    :param format: Use the specified format string for the handler.
        Defaults to ``levelname`` and ``message`` separated by a colon.
    :param datefmt: Use the specified date/time format, as accepted by
        :func:`time.strftime`.
    :param style: If *format* is specified, use this style for the format string. One
        of ``%``, ``{`` or ``$`` for :ref:`printf-style <old-string-formatting>`,
        :meth:`str.format` or :class:`string.Template` respectively. Defaults to ``{``.
    :param level: Set the logger level to the specified :ref:`level <levels>`.
    :param handlers: A list of ``logging.Handler`` instances to attach to the logger.
        If not provided, a new handler of the class set by the ``handler_class``
        parameter will be created. Any handler in the list which does not have a
        formatter assigned will be assigned the formatter created in this function.
    :param force: Remove and close any existing handlers attached to the logger
        before carrying out the configuration as specified by the other arguments.
        Default to ``True`` so we always starts from a clean state each time we
        configure a logger. This is a life-saver in unittests in which loggers pollutes
        output.
    :param handler_class: Handler class to be used to create a new handler if none
        provided. Defaults to :py:class:`ExtraLogHandler`.
    :param formatter_class: Class of the formatter that will be setup on each handler
        if none found. Defaults to :py:class:`ExtraLogFormatter`.

    .. todo::
        Add more parameters for even greater configurability of the logger, by
        re-implementing those supported by ``logging.basicConfig``.
    """
    # Fetch the logger or create a new one.
    logger = logging.getLogger(logger_name)

    # Remove and close any existing handlers. Copy of:
    # https://github.com/python/cpython/blob/2b5dbd1/Lib/logging/__init__.py#L2028-L2031
    if force:
        for h in logger.handlers[:]:
            logger.removeHandler(h)
            h.close()

    # If no handlers provided, create a new one with the default handler class.
    if not handlers:
        handlers = (handler_class(),)

    # Set up the formatter with a default message format.
    formatter = formatter_class(
        fmt=format,
        datefmt=datefmt,
        style=style,
    )

    # Attach handlers to the loggers.
    for h in handlers:
        if h.formatter is None:
            h.setFormatter(formatter)
        logger.addHandler(h)

    if level is not None:
        logger.setLevel(level)

    return logger


class VerbosityOption(ExtraOption):
    """A pre-configured ``--verbosity``/``-v`` option.

    Sets the level of the provided logger.

    The selected verbosity level name is made available in the context in
    ``ctx.meta["click_extra.verbosity"]``.

    .. important::

        The internal ``click_extra`` logger level will be aligned to the value set via
        this option.
    """

    logger_name: str
    """The ID of the logger to set the level to.

    This will be provided to
    `logging.getLogger <https://docs.python.org/3/library/logging.html?highlight=getlogger#logging.getLogger>`_
    method to fetch the logger object, and as such, can be a dot-separated string to
    build hierarchical loggers.
    """

    @property
    def all_loggers(self) -> Generator[Logger, None, None]:
        """Returns the list of logger IDs affected by the verbosity option.

        Will returns Click Extra's internal logger first, then the option's custom
        logger.
        """
        for name in ("click_extra", self.logger_name):
            yield logging.getLogger(name)

    def reset_loggers(self) -> None:
        """Forces all loggers managed by the option to be reset to the default level.

        Reset loggers in reverse order to ensure the internal logger is reset last.

        .. danger::
            Resseting loggers is extremely important for unittests. Because they're
            global, loggers have tendency to leak and pollute their state between
            multiple test calls.
        """
        for logger in list(self.all_loggers)[::-1]:
            logging.getLogger("click_extra").debug(
                f"Reset {logger} to {DEFAULT_LEVEL_NAME}.",
            )
            logger.setLevel(DEFAULT_LEVEL)

    def set_levels(self, ctx: Context, param: Parameter, value: str) -> None:
        """Set level of all loggers configured on the option.

        Save the verbosity level name in the context.

        Also prints the chosen value as a debug message via the internal
        ``click_extra`` logger.
        """
        ctx.meta["click_extra.verbosity"] = value

        for logger in self.all_loggers:
            logger.setLevel(LOG_LEVELS[value])
            logging.getLogger("click_extra").debug(f"Set {logger} to {value}.")

        ctx.call_on_close(self.reset_loggers)

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        default_logger: Logger | str | None = None,
        default: str = DEFAULT_LEVEL_NAME,
        metavar="LEVEL",
        type=Choice(LOG_LEVELS, case_sensitive=False),  # type: ignore[arg-type]
        expose_value=False,
        help=_("Either {log_levels}.").format(log_levels=", ".join(LOG_LEVELS)),
        is_eager=True,
        **kwargs,
    ) -> None:
        """Set up the verbosity option.

        :param default_logger: If an instance of ``logging.Logger`` is provided, that's
            the instance to which we will set the level set via the option. If the
            parameter is a string, we will fetch it with `logging.getLogger
            <https://docs.python.org/3/library/logging.html?highlight=getlogger#logging.getLogger>`_.
            If not provided or ``None``, the `default Python root logger
            <https://github.com/python/cpython/blob/2b5dbd1/Lib/logging/__init__.py#L1945>`_
            is used.

        .. todo::
            Write more documentation to detail in which case the user is responsible
            for setting up the logger, and when ``extra_basic_config`` is used.
        """
        if not param_decls:
            param_decls = ("--verbosity", "-v")

        # Use the provided logger instance as-is.
        if isinstance(default_logger, Logger):
            logger = default_logger
        # If a string is provided, use it as the logger name.
        elif isinstance(default_logger, str):
            logger = logging.getLogger(default_logger)
        # ``None`` will produce a default root logger.
        else:
            logger = extra_basic_config(default_logger)

        # Store the logger name for later use.
        self.logger_name = logger.name

        kwargs.setdefault("callback", self.set_levels)

        super().__init__(
            param_decls=param_decls,
            default=default,
            metavar=metavar,
            type=type,
            expose_value=expose_value,
            help=help,
            is_eager=is_eager,
            **kwargs,
        )
