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
from gettext import gettext as _
from typing import Sequence

import click

from . import Choice
from .colorize import default_theme
from .parameters import ExtraOption

LOG_LEVELS = {
    name: value
    for value, name in sorted(logging._levelToName.items(), reverse=True)
    if name != "NOTSET"
}
"""Mapping of canonical log level names to their IDs.

Sorted from lowest to highest verbosity, and ignore ``NOTSET``, as well as ``FATAL`` &
``WARN`` aliases.
"""


class ColorFormatter(logging.Formatter):
    def formatMessage(self, record):
        """Colorize the record's log level name before calling the strandard
        formatter."""
        level = record.levelname.lower()
        level_style = getattr(default_theme, level, None)
        record.levelname = level_style(level)
        return super().formatMessage(record)


class ClickExtraHandler(logging.Handler):
    def emit(self, record):
        """Print the log message to console's ``<stderr>``."""
        try:
            msg = self.format(record)
            click.echo(msg, err=True)

        # If exception occurs format it to the stream.
        except Exception:
            self.handleError(record)


def extra_basic_config(
        logger_name: str | None = None,
        fmt: str = "%(levelname)s: %(message)s",
    ):
    """Emulate ``logging.basicConfig``, but with sane defaults:

    - handler to :py:class:`ClickExtraHandler`
    - formatter to :py:class:`ColorFormatter` with ``%(levelname)s: %(message)s`` as
      default message format
    """
    logger = logging.getLogger(logger_name)

    if logger is logging.root:
        logging.basicConfig(force=True)

    else:
        # Emulates `force=True` parameter of logging.basicConfig:
        # https://github.com/python/cpython/blob/2b5dbd1f237a013defdaf0799e0a1a3cbd0b13cc/Lib/logging/__init__.py#L2028-L2031
        for h in logger.handlers[:]:
            logger.removeHandler(h)
            h.close()

    handlers = [ClickExtraHandler()]

    # Set up the formatter with a default message format.
    formatter = ColorFormatter(fmt=fmt)
    for h in handlers:
        if h.formatter is None:
            h.setFormatter(formatter)
        logger.addHandler(h)

    logger.propagate = False

    return logger


class VerbosityOption(ExtraOption):
    """Adds a ``--verbosity``/``-v`` option.

    Sets the level of the provided logger.
    """

    logger_name: str
    """The name of the logger to use.

    This is used to fetch the logger instance via
    `logging.getLogger <https://docs.python.org/3/library/logging.html?highlight=getlogger#logging.getLogger>`_.
    """

    def set_level(self, ctx, param, value):
        """Set logger level and print its value as a debug message."""
        logger = logging.getLogger(self.logger_name)
        logger.setLevel(LOG_LEVELS[value])

        # Aligns Click Extra's internal logger level with the verbosity option.
        extra_logger = logging.getLogger("click_extra")
        extra_logger.setLevel(LOG_LEVELS[value])

        extra_logger.debug(f"Verbosity set to {value}.")

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        default_logger: logging.Logger | str | None = None,
        default="INFO",
        metavar="LEVEL",
        type=Choice(LOG_LEVELS, case_sensitive=False),  # type: ignore[arg-type]
        expose_value=False,
        help=_("Either {log_levels}.").format(log_levels=", ".join(LOG_LEVELS)),
        is_eager=True,
        **kwargs,
    ):
        """Set up the verbosity option.

        :param default_logger: If an instance of ``logging.Logger`` is provided, that's
            the instance to which we will set the level set via the option. If the
            parameter is a string, we will use it as the name of the logger to fetch via
            `logging.getLogger <https://docs.python.org/3/library/logging.html?highlight=getlogger#logging.getLogger>`_.
            If not provided or `None`, the `default Python root logger
            <https://github.com/python/cpython/blob/2b5dbd1/Lib/logging/__init__.py#L1945>`_
            is used.
        """
        if not param_decls:
            param_decls = ("--verbosity", "-v")

        # Use the provided logger instance as-is. User is responsible for setting it up.
        if isinstance(default_logger, logging.Logger):
            logger = default_logger
        # If a string is provided, use it as the logger name. ``None`` will produce a
        # default root logger.
        else:
            logger = extra_basic_config(default_logger)

        # Store the logger name for later use.
        self.logger_name = logger.name

        kwargs.setdefault("callback", self.set_level)

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
