# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
# All Rights Reserved.
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

import logging
from functools import partial
from gettext import gettext as _

from click import echo
from click_log import basic_config
from cloup import Choice, option

from .parameters import ExtraOption

LOG_LEVELS = {
    name: value
    for value, name in sorted(logging._levelToName.items(), reverse=True)
    if name != "NOTSET"
}
"""Index levels by their ID. Sorted from lowest to highest verbosity."""


class WrappedLogger:

    wrapped_logger = None

    def initialize_logger(self):
        """Generate a default logger."""
        logger = logging.getLogger(__name__)
        basic_config(logger)
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

    A re-implementation of ``click_log.simple_verbosity_option`` decorator,
    with sensible defaults and bug fixes (see:
        https://github.com/click-contrib/click-log/issues/28
        https://github.com/click-contrib/click-log/issues/29
        https://github.com/click-contrib/click-log/pull/18
        https://github.com/click-contrib/click-log/pull/24
    ).
    """

    @staticmethod
    def set_level(ctx, param, value):
        """Set logger level and print its value as a debug message."""
        logger.setLevel(LOG_LEVELS[value])
        logger.debug(f"Verbosity set to {value}.")
        # Forces logger level reset at the end of each CLI execution, as it pollutes the logger
        # state between multiple test calls.
        ctx.call_on_close(logger.reset)

    def __init__(
        self,
        default_logger=None,
        param_decls=None,
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


verbosity_option = partial(option, cls=VerbosityOption)
"""Decorator for ``VerbosityOption``."""
