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

Sorted from lowest to highest verbosity.

Are ignored:

- ``NOTSET``, which is considered internal
- ``WARN``, which `is obsolete
  <https://docs.python.org/3/library/logging.html?highlight=warn#logging.Logger.warning>`_
- ``FATAL``, which `has been deprecated
  <https://github.com/python/cpython/blob/0df7c3a/Lib/logging/__init__.py#L1538-L1541>`_
  in favor of ``CRITICAL``
"""


DEFAULT_LEVEL = logging.WARNING
"""``WARNING`` is the default level we expect any loggers to starts their lives at.

``WARNING`` has been chosen as it is `the level at which the default Python's global
root logger is set up
<https://github.com/python/cpython/blob/0df7c3a/Lib/logging/__init__.py#L1945>`_.

This value is also used as the default level of the ``--verbosity`` option below.
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
    """A pre-configured ``--verbosity``/``-v`` option.

    Sets the level of the provided logger.

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
    def all_loggers(self) -> tuple[str, ...]:
        """Returns the list of logger IDs affected by the verbosity option.

        Will returns the option's logger and Click Extra's internal logger, so we'll
        have the level of these two aligned.
        """
        return (self.logger_name, "click_extra")

    def reset_loggers(self):
        """Forces all loggers managed by the option to be reset to the default level.

        .. danger::
            Resseting loggers is extremely important for unittests. Because they're
            global, loggers have tendency to leak and pollute their state between
            multiple test calls.
        """
        for name in self.all_loggers:
            logger = logging.getLogger(name)
            logger.setLevel(DEFAULT_LEVEL)

    def set_levels(self, ctx, param, value):
        """Set level of all loggers configured on the option.

        Also prints the chosen value as a debug message via the internal
        ``click_extra`` logger.
        """
        for name in self.all_loggers:
            logger = logging.getLogger(name)
            logger.setLevel(LOG_LEVELS[value])
            if name == "click_extra":
                logger.debug(f"Verbosity set to {value}.")

        ctx.call_on_close(self.reset_loggers)

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
