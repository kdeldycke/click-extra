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

import click
import logging
from gettext import gettext as _
from typing import Sequence

from . import Choice
from .parameters import ExtraOption
from .colorize import default_theme


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
    def __init__(
        self, fmt: str | None = "%(levelname)s: %(message)s", *args, **kwargs
    ) -> None:
        """Set up the formatter with a default message format.

        Default message format is ``levelname: message`` instead of
        ``levelname:name:message`` as defined by `logging.BASIC_FORMAT
        <https://github.com/python/cpython/blob/2b5dbd1/Lib/logging/__init__.py#L523>`_.
        """
        super().__init__(fmt=fmt, *args, **kwargs)

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


class WrappedLogger:
    """A wrapper around the default logger."""

    wrapped_logger = None

    def initialize_logger(self):
        """Generate a default logger.

        Set up the default handler (:py:class:`ClickExtraHandler`) and formatter
        (:py:class:`ColorFormatter`) on the given logger.
        """
        logger = logging.getLogger(__name__)
        _default_handler = ClickExtraHandler()
        _default_handler.formatter = ColorFormatter()
        logger.handlers = [_default_handler]
        logger.propagate = False
        return logger

    def set_logger(self, default_logger=None):
        if not default_logger:
            self.wrapped_logger = self.initialize_logger()
        else:
            self.wrapped_logger = default_logger
        # Double-check we're not fed junk.
        assert isinstance(self.wrapped_logger, logging.Logger)

    def __getattr__(self, name):
        """Passthrought attribute calls to our wrapped logger."""
        if not self.wrapped_logger:
            self.set_logger()
        return getattr(self.wrapped_logger, name)

    def reset(self):
        """Forces the logger level to reset at the end of each CLI execution, as it
        might pollute the logger state between multiple test calls."""
        self.wrapped_logger.setLevel(logging.NOTSET)


# Global application logger.
logger = WrappedLogger()


class VerbosityOption(ExtraOption):
    """Adds a ``--verbosity``/``-v`` option.

    A re-implementation of ``click_log.simple_verbosity_option`` decorator, with
    sensible defaults and bug fixes.

    .. seealso::
        - https://github.com/click-contrib/click-log/issues/28
        - https://github.com/click-contrib/click-log/issues/29
        - https://github.com/click-contrib/click-log/pull/18
        - https://github.com/click-contrib/click-log/pull/24
    """

    @staticmethod
    def set_level(ctx, param, value):
        """Set logger level and print its value as a debug message.

        Also forces logger level reset at the end of each CLI execution, as it pollutes
        the logger state between multiple test calls.
        """
        logger.setLevel(LOG_LEVELS[value])
        logger.debug(f"Verbosity set to {value}.")
        ctx.call_on_close(logger.reset)

    def __init__(
        self,
        default_logger=None,
        param_decls: Sequence[str] | None = None,
        default="INFO",
        metavar="LEVEL",
        type=Choice(LOG_LEVELS, case_sensitive=False),
        expose_value=False,
        help=_("Either {log_levels}.").format(log_levels=", ".join(LOG_LEVELS)),
        is_eager=True,
        **kwargs,
    ):
        if not param_decls:
            param_decls = ("--verbosity", "-v")

        kwargs.setdefault("callback", self.set_level)

        logger.set_logger(default_logger)

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
