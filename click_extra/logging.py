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

""" Logging utilities. """

import logging

import click
import click_log
from cloup import GroupedOption

# Initialize global logger.
logger = logging.getLogger(__name__)
click_log.basic_config(logger)


LOG_LEVELS = {
    name: value
    for value, name in sorted(logging._levelToName.items(), reverse=True)
    if name != "NOTSET"
}
"""Index levels by their ID. Sorted from lowest to highest verbosity."""


def reset_logger():
    """Forces the logger level to reset at the end of each CLI execution, as it
    might pollute the logger state between multiple test calls.
    """
    logger.setLevel(logging.NOTSET)


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
    if not default_logger:
        default_logger = logger
    else:
        assert isinstance(default_logger, logging.Logger)

    if not names:
        names = ("--verbosity", "-v")

    def set_level(ctx, param, value):
        """Set logger level and print its value as a debug message."""
        nonlocal default_logger
        default_logger.setLevel(LOG_LEVELS[value])
        logger.debug(f"Verbosity set to {value}.")
        # Forces logger level reset at the end of each CLI execution, as it pollutes the logger
        # state between multiple test calls.
        ctx.call_on_close(reset_logger)

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
