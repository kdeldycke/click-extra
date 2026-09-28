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

"""Resolution of the reserved subcommand keys a configuration file can declare.

`_default_subcommands` and `_prepend_subcommands` are read from the loaded
configuration and turned into subcommand names, which
{meth}`~click_extra.config.option.ConfigOption.handle_parse_result` splices into
the residual arguments Click dispatches on.

```{note}
The keys are honoured by whichever group carries the `--config` option, not only
by click-extra's own {class}`~click_extra.commands.Group`. Injection happens at
parse time, from the option itself, because a plain `click.Group` offers
click-extra no other hook: a third-party framework building its group on
`click.Group` still gets the feature.
```

```{caution}
A group whose `no_args_is_help` is left on never reaches its parameters when
invoked with no arguments at all, so neither key fires on a bare invocation.
Pass at least one option, or declare the group with `no_args_is_help=False`.
```
"""

from __future__ import annotations

import logging

import click

from .. import context
from .schema import DEFAULT_SUBCOMMANDS_KEY, PREPEND_SUBCOMMANDS_KEY

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Any

logger = logging.getLogger(__name__)


def _descend_to_group_config(ctx: click.Context) -> dict[str, Any] | None:
    """Return the loaded config section for the current group's command path.

    Reads the full configuration document from `ctx.meta`, descends into the
    root command's section, then walks from the root context down to `ctx`
    following each group name. Returns the resolved mapping, or `None` when no
    configuration was loaded or any segment along the path is missing.
    """
    full_config = context.get(ctx, context.CONF_FULL)
    if not full_config:
        return None

    root_ctx = ctx.find_root()
    config_branch = full_config.get(root_ctx.command.name)
    if not isinstance(config_branch, dict):
        return None

    # Walk from root context down to the current group.
    path: list[str] = []
    current: click.Context | None = ctx
    while current is not None and current is not root_ctx:
        if current.command.name is not None:
            path.append(current.command.name)
        current = current.parent
    path.reverse()

    for segment in path:
        config_branch = config_branch.get(segment)
        if not isinstance(config_branch, dict):
            return None

    return config_branch


def _dedupe_subcommands(raw: list[str], key: str) -> list[str]:
    """Drop duplicate subcommand names, keeping the first occurrence.

    Warns when duplicates are dropped, naming the configuration `key` they
    came from.
    """
    seen: set[str] = set()
    deduped: list[str] = []
    for name in raw:
        if name in seen:
            continue
        seen.add(name)
        deduped.append(name)
    if len(deduped) < len(raw):
        logger.warning(
            f"Duplicate entries in {key}: {raw!r}. "
            f"Keeping first occurrences: {deduped!r}."
        )
    return deduped


def _read_subcommand_list(
    ctx: click.Context,
    group: click.Group,
    key: str,
) -> list[str] | None:
    """Read, validate, dedupe, and existence-check a subcommand-list config key.

    Returns the deduplicated list of subcommand names declared under `key`
    in the loaded configuration, or `None` when the key is absent or empty.
    Shared by {func}`resolve_default_subcommands` and
    {func}`resolve_prepend_subcommands`; each caller layers on its own chain-mode
    rule (the only behavior that differs between the two keys).

    :raises click.UsageError: when the value is not a list of strings, or when
        a listed subcommand does not exist in `group`.
    """
    config_branch = _descend_to_group_config(ctx)
    if config_branch is None:
        return None

    raw = config_branch.get(key)
    if raw is None:
        return None

    # Validate type.
    if not isinstance(raw, list) or not all(isinstance(s, str) for s in raw):
        raise click.UsageError(f"{key} must be a list of strings, got {raw!r}.")

    if not raw:
        return None

    raw = _dedupe_subcommands(raw, key)

    # Validate that all subcommands exist.
    for name in raw:
        if group.get_command(ctx, name) is None:
            raise click.UsageError(
                f"Subcommand {name!r} from {key} not found in group {group.name!r}."
            )

    return raw


def resolve_default_subcommands(
    ctx: click.Context,
    group: click.Group,
) -> list[str] | None:
    """Read and validate `_default_subcommands` from the loaded configuration."""
    raw = _read_subcommand_list(ctx, group, DEFAULT_SUBCOMMANDS_KEY)
    if raw is None:
        return None

    # Non-chained groups can only have one default subcommand.
    if not group.chain and len(raw) > 1:
        raise click.UsageError(
            f"Non-chained group {group.name!r} can have at most 1 default "
            f"subcommand, got {len(raw)}: {raw!r}."
        )

    return raw


def resolve_prepend_subcommands(
    ctx: click.Context,
    group: click.Group,
) -> list[str] | None:
    """Read and validate `_prepend_subcommands` from the loaded configuration."""
    raw = _read_subcommand_list(ctx, group, PREPEND_SUBCOMMANDS_KEY)
    if raw is None:
        return None

    # Prepend subcommands only work with chained groups.
    if not group.chain:
        raise click.UsageError(
            f"{PREPEND_SUBCOMMANDS_KEY} requires chain=True on group {group.name!r}."
        )

    return raw


def inject_reserved_subcommands(ctx: click.Context, args: list[str]) -> list[str]:
    """Return `args` with the reserved subcommand keys applied.

    `_default_subcommands` fills in for an invocation that names no subcommand.
    The command line always wins: when `args` already carries one, the
    configured defaults are logged and dropped.

    `_prepend_subcommands` goes in front of whatever remains, whether the
    subcommand came from the command line or from the defaults. It requires a
    `chain=True` group.

    Applies at most once per group, tracked in
    {data}`~click_extra.context.SUBCOMMANDS_APPLIED`. A group can be visited
    twice, by the no-args pre-pass in
    {meth}`click_extra.commands.Group.parse_args` and then by the regular
    parameter loop, and prepending the same subcommand on both passes would run
    it twice.

    :raises click.UsageError: on an invalid value, an unknown subcommand, or a
        chain-mode violation.
    """
    group = ctx.command
    if not isinstance(group, click.Group):
        return args

    applied = context.get(ctx, context.SUBCOMMANDS_APPLIED)
    if applied is None:
        applied = set()
        context.set(ctx, context.SUBCOMMANDS_APPLIED, applied)
    if ctx.command_path in applied:
        return args
    applied.add(ctx.command_path)

    default_subcmds = resolve_default_subcommands(ctx, group)
    if default_subcmds is not None:
        if args:
            logger.debug(
                f"CLI subcommands provided; ignoring {DEFAULT_SUBCOMMANDS_KEY}"
                f" config: {default_subcmds!r}."
            )
        else:
            args = list(default_subcmds)

    prepend_subcmds = resolve_prepend_subcommands(ctx, group)
    if prepend_subcmds is not None:
        logger.info(
            f"Prepending {PREPEND_SUBCOMMANDS_KEY} config: {prepend_subcmds!r}."
        )
        args = list(prepend_subcmds) + args

    return args
