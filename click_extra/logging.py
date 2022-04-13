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

import click
import click_log
from cloup import GroupedOption

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
        click_log.basic_config(logger)
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


def verbosity_option(
    default_logger=None,
    *names,
    default="INFO",
    metavar="LEVEL",
    type=click.Choice(LOG_LEVELS, case_sensitive=False),
    expose_value=False,
    help=f"Either {', '.join(LOG_LEVELS)}.",
    is_eager=True,
    cls=GroupedOption,
    **kwargs,
):
    """Adds a ``--verbosity``/``-v`` option.

    A re-implementation of ``click_log.simple_verbosity_option`` decorator,
    with sensible defaults and bug fixes (see:
        https://github.com/click-contrib/click-log/issues/28
        https://github.com/click-contrib/click-log/issues/29
        https://github.com/click-contrib/click-log/pull/18
        https://github.com/click-contrib/click-log/pull/24
    ).
    """
    if not names:
        names = ("--verbosity", "-v")

    logger.set_logger(default_logger)

    def set_level(ctx, param, value):
        """Set logger level and print its value as a debug message."""
        logger.setLevel(LOG_LEVELS[value])
        logger.debug(f"Verbosity set to {value}.")
        # Forces logger level reset at the end of each CLI execution, as it pollutes the logger
        # state between multiple test calls.
        ctx.call_on_close(logger.reset)

    return click.option(
        *names,
        default=default,
        metavar=metavar,
        type=type,
        expose_value=expose_value,
        help=help,
        is_eager=is_eager,
        callback=set_level,
        cls=cls,
        **kwargs,
    )
