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
"""Multicall / `argv[0]` dispatch: one binary answering to many names.

A multicall binary is a single executable whose behavior is selected by the
name it is invoked with: `bzip2`, `bunzip2` and `bzcat` are the same file,
`vim` and `view` differ by default options, and BusyBox multiplexes hundreds
of applets behind symlinks pointing at one binary. {class}`MulticallGroup`
brings the pattern to Click Extra: a group that, when invoked under the name
of one of its subcommands, skips the group and behaves exactly like that
subcommand as a standalone binary.

Declare one with {func}`~click_extra.decorators.multicall_group`:

```{code-block} python
from click_extra import argument, echo, multicall_group, option


@multicall_group()
def kitchen():
    '''A multicall kitchen appliance.'''


@kitchen.command()
@option("--temperature", default="180")
@argument("dishes", nargs=-1)
def bake(temperature, dishes):
    '''Bake dishes in the oven.'''


@kitchen.command()
@option("--hours", default="2")
@argument("bottles", nargs=-1)
def chill(hours, bottles):
    '''Chill bottles in the fridge.'''
```

Invoked as `kitchen`, the CLI is a regular group. Invoked through a symlink
named `bake` (or any other subcommand name), it *is* the `bake` command: one
flat argument parse, its own usage line and help screen, and the full set of
Click Extra options merged in:

```{code-block} console
$ kitchen bake --temperature 200 pie       # regular group dispatch
$ ln -s $(which kitchen) bake
$ bake --temperature 200 pie               # same thing, no subcommand
```

A personality maps to a *sequence of tokens*, not just a subcommand, so a
name can also pre-fill options (`bzcat` is `bzip2 --decompress --stdout`):

```{code-block} python
@multicall_group(personalities={"chill-fast": ("chill", "--hours", "1")})
def kitchen():
    ...
```

```{note}
Behavioral notes for personality mode:

- The group's own callback does not run: the personality is a standalone
  command with no parent context.
- Configuration and environment variable namespaces follow the personality
  name: `bake` reads its configuration from the `bake` app dir and the
  `BAKE_*` environment variables, the way a standalone binary would, and not
  from the group's `kitchen` namespace.
- The invocation name a command was started under is also exposed on its own,
  for custom dispatch logic: see {data}`click_extra.context.INVOCATION_NAME`.
```

```{todo}
Drop `click_extra._utils.memoize_enums()` and both its call sites, here and in
{meth}`click_extra.version.VersionOption.__deepcopy__`, once this package's
Click floor reaches the release carrying
[pallets/click#3805](https://github.com/pallets/click/pull/3805). That pull
request gives `Sentinel` its own `__copy__`, `__deepcopy__` and `__reduce_ex__`,
so a member survives a copy unaided and the memo seeding buys nothing. It is
slated for Click `8.5.1`, against a floor of `8.4.1` here.
```
"""

from __future__ import annotations

import copy
import logging
import os
import sys
from collections.abc import Sequence
from typing import cast

import click
from click._utils import UNSET

from ._utils import memoize_enums
from .commands import ColorizedCommand, Command, Group, HelpCommand
from .context import Context

logger = logging.getLogger(__name__)

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any

WINDOWS_EXE_SUFFIX = ".exe"
"""Suffix of Windows console-script wrappers, stripped from `argv[0]`.

On Windows, entry points are materialized as `.exe` shims, so a symlink named
`bake` lands in `argv[0]` as `bake.exe`.
"""


def normalize_personality(tokens: object) -> tuple[str, ...]:
    """Normalize a personality mapping value into a tuple of CLI tokens.

    Accepts a bare subcommand name (`"chill"`) or a token sequence
    (`("chill", "--hours", "1")`). The first token names the subcommand the
    personality dispatches to; the rest is prepended to the user's arguments.

    :raises TypeError: when the value is neither a string nor a sequence.
    :raises ValueError: on an empty sequence or a non-string token.
    """
    if isinstance(tokens, str):
        tokens = (tokens,)
    if not isinstance(tokens, Sequence):
        msg = (
            f"A personality must be a string or a sequence of tokens, got: {tokens!r}."
        )
        raise TypeError(msg)
    token_list = tuple(tokens)
    if not token_list or not all(isinstance(t, str) and t for t in token_list):
        msg = f"A personality must be a non-empty sequence of tokens, got: {tokens!r}."
        raise ValueError(msg)
    return token_list


class PersonalitiesCommand(ColorizedCommand):
    """Synthetic subcommand listing every name a `MulticallGroup` answers to.

    Auto-injected into every {class}`MulticallGroup`, the way
    {class}`~click_extra.commands.HelpCommand` is injected into every
    {class}`~click_extra.commands.Group`: the group mode needs a place to
    enumerate the symlink names, and a subcommand costs no new top-level
    option on the group's help screen.
    """

    def invoke(self, ctx: click.Context) -> None:
        """List each personality next to the command line it invokes."""
        parent_ctx = ctx.parent
        assert parent_ctx is not None
        group = parent_ctx.command
        assert isinstance(group, MulticallGroup)

        rows: list[tuple[str, str, str]] = []
        for name, tokens in group.list_personalities().items():
            sub = group.commands.get(tokens[0])
            short_help = sub.get_short_help_str() if sub is not None else ""
            rows.append((name, " ".join(tokens), short_help))

        # `ColorizedCommand` contexts are always click-extra's own `Context`,
        # whose `print_table` honors the invocation's table options.
        cast(Context, ctx).print_table(
            rows,
            headers=("Name", "Invokes", "Description"),
            sort_key=lambda row: row[0],
        )
        ctx.exit()


def _make_personalities_command() -> PersonalitiesCommand:
    """Create the synthetic `personalities` subcommand for a `MulticallGroup`."""
    return PersonalitiesCommand(
        name="personalities",
        help="List the invocation names this binary answers to.",
        context_settings={"auto_envvar_prefix": None},
    )


class MulticallGroup(Group):
    """A `Group` dispatching on its invocation name, BusyBox-style.

    When the name the binary was invoked under matches a personality, the
    group steps aside entirely and runs the matching subcommand as a
    standalone command: the personality carries the group's options merged
    into the subcommand's, parses them in one flat pass with no positional
    ordering constraint, and renders its own usage line and help screen. Any
    other invocation name falls through to regular group behavior.

    The invocation name is, in precedence order:

    #. an explicit `prog_name` passed to `main()` (what
       {class}`click_extra.testing.CliRunner` uses to simulate a symlink),
    #. else the unresolved basename of `sys.argv[0]`.

    The basename is used *unresolved*: resolving through `os.path.realpath()`
    would return the symlink's target and destroy the personality. A trailing
    {data}`WINDOWS_EXE_SUFFIX` is stripped for Windows console-script shims.
    Click's own `_detect_program_name()` is deliberately not used: it reads
    `__main__.__package__` and answers `python -m …` in the module case. See
    {func}`click_extra.cli_wrapper.invoke_target` for the full trap. A name
    matching no personality is not an error: it falls through, which is also
    what keeps the feature inert under test runners, where `argv[0]` is the
    runner's own binary.
    """

    def __init__(
        self,
        *args: Any,
        personalities: Mapping[str, str | Sequence[str]] | None = None,
        personalities_command: bool = True,
        **kwargs: Any,
    ) -> None:
        """Like `Group.__init__`, but with multicall dispatch.

        :param personalities: maps an invocation name to the tokens it
            invokes: a bare subcommand name (`"chill"`) or a token sequence
            (`("chill", "--hours", "1")`) whose extra tokens are prepended to
            the user's arguments. Left to `None`, every non-hidden,
            non-synthetic subcommand is its own personality.
        :param personalities_command: when `True` (the default), a
            `personalities` subcommand is auto-registered on the group,
            listing every invocation name the binary answers to. Register your
            own `personalities` subcommand to override it.
        """
        super().__init__(*args, **kwargs)
        self.personalities: dict[str, tuple[str, ...]] = {}
        for name, tokens in (personalities or {}).items():
            self.personalities[name] = normalize_personality(tokens)
        if personalities_command and "personalities" not in self.commands:
            self.add_command(_make_personalities_command())

    def resolve_invocation_name(self, prog_name: str | None = None) -> str | None:
        """The name this binary was invoked under.

        An explicit *prog_name* wins: it is what makes the feature testable
        without symlinks on disk. Otherwise the unresolved basename of
        `sys.argv[0]` is used, with a trailing `.exe` stripped on Windows.
        """
        if prog_name:
            return prog_name
        if not sys.argv or not sys.argv[0]:
            return None
        name = os.path.basename(sys.argv[0])
        if name.lower().endswith(WINDOWS_EXE_SUFFIX):
            name = name[: -len(WINDOWS_EXE_SUFFIX)]
        return name or None

    def list_personalities(self) -> dict[str, tuple[str, ...]]:
        """Every personality name mapped to the tokens it invokes.

        The explicit {attr}`personalities` mapping when one was declared,
        else every non-hidden, non-synthetic subcommand mapped to itself.
        """
        if self.personalities:
            return dict(self.personalities)
        return {
            name: (name,)
            for name, cmd in self.commands.items()
            if not cmd.hidden
            and not isinstance(cmd, (HelpCommand, PersonalitiesCommand))
        }

    def match_personality(self, name: str | None) -> tuple[str, ...] | None:
        """Tokens to invoke when called under *name*, or `None` to fall through."""
        if not name:
            return None
        if self.personalities:
            return self.personalities.get(name)
        cmd = self.commands.get(name)
        if (
            cmd is None
            or cmd.hidden
            or isinstance(cmd, (HelpCommand, PersonalitiesCommand))
        ):
            return None
        return (name,)

    def main(  # type: ignore[override]
        self,
        args: Sequence[str] | None = None,
        prog_name: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Dispatch on the invocation name before any argument parsing.

        A matching personality runs as a standalone command, the group's own
        options merged into it, its extra tokens prepended to the arguments.
        Anything else delegates to the regular group `main()`.
        """
        name = self.resolve_invocation_name(prog_name)
        tokens = self.match_personality(name)
        if tokens is None:
            return super().main(args=args, prog_name=prog_name, **kwargs)

        personality = self.build_personality(name, tokens)
        if args is None:
            args = sys.argv[1:]
        return personality.main(
            args=[*tokens[1:], *list(args)],
            prog_name=name,
            **kwargs,
        )

    def build_personality(
        self,
        name: str | None,
        tokens: tuple[str, ...],
    ) -> click.Command:
        """Synthesize the standalone command the *name* personality runs as.

        The personality is a fresh instance of the subcommand's own class,
        re-instantiated over the group's parameters merged with the
        subcommand's, not a copy whose `params` attribute is patched after
        the fact. Two reasons make the re-instantiation mandatory:

        - Cloup computes its help layout (`arguments`, `option_groups`,
          `ungrouped_options`) from `params` inside `__init__`, so a patched
          copy parses every merged option but only renders the subcommand's
          own on its help screen.
        - Click Extra's own `Command.__init__` does work that must run over
          the merged set: `extra_option_at_end` reordering, option
          priorities, auto envvar population and help-keyword collection.

        Every parameter is deep-copied, because `Command.__init__` re-runs
        `populate_auto_envvars` over the merged set under the personality's
        own `auto_envvar_prefix`: sharing instances would rewrite the group's
        and subcommand's `envvar` attributes and leak that back into group
        mode. This is the same class of leaky state
        {func}`~click_extra.commands.default_params` warns about.
        """
        sub_name = tokens[0]
        sub = self._get_personality_subcommand(sub_name)
        if sub is None:
            msg = f"Personality {name!r} maps to unknown subcommand {sub_name!r}."
            raise RuntimeError(msg)

        group_params = _deepcopy_params(self.params)
        sub_params = _deepcopy_params(sub.params)

        # The subcommand's context settings carry over, minus the ones the
        # personality re-derives from its own name: keeping the subcommand's
        # auto envvar prefix would defeat the personality namespace.
        ctx_settings = dict(sub.context_settings)
        ctx_settings.pop("auto_envvar_prefix", None)

        kwargs: dict[str, Any] = {
            "name": name,
            "context_settings": ctx_settings,
            "callback": sub.callback,
            "params": _merge_params(group_params, sub_params),
            "help": sub.help,
            "epilog": sub.epilog,
            "short_help": sub.short_help,
            "options_metavar": sub.options_metavar,
            "add_help_option": sub.add_help_option,
            "no_args_is_help": sub.no_args_is_help,
            "hidden": sub.hidden,
            "deprecated": sub.deprecated,
        }

        # Cloup extras, present on cloup commands only.
        if hasattr(sub, "aliases"):
            kwargs["aliases"] = list(sub.aliases)
        if hasattr(sub, "formatter_settings"):
            kwargs["formatter_settings"] = dict(sub.formatter_settings)

        # Constraints bound to the subcommand's original parameter instances
        # must be rebound to their copies, else they would check the stale
        # originals, which never see the parsed values.
        kwargs["constraints"] = _rebind_constraints(sub, sub_params)

        if isinstance(sub, Group):
            kwargs.update(
                commands=dict(sub.commands),
                chain=sub.chain,
                invoke_without_command=sub.invoke_without_command,
                subcommand_metavar=sub.subcommand_metavar,
                result_callback=sub.result_callback,
                sort_subcommands=sub.sort_subcommands,
                subcommand_priorities=dict(sub.subcommand_priorities),
            )
            if isinstance(sub, MulticallGroup):
                kwargs["personalities"] = dict(sub.personalities)

        if isinstance(sub, Command):
            kwargs["examples"] = sub.examples
            kwargs["option_priorities"] = {
                **self.option_priorities,
                **sub.option_priorities,
            }
            if getattr(sub, "extra_keywords", None):
                kwargs["extra_keywords"] = sub.extra_keywords
            if getattr(sub, "excluded_keywords", None):
                kwargs["excluded_keywords"] = sub.excluded_keywords

        return type(sub)(**kwargs)

    def _get_personality_subcommand(self, name: str) -> click.Command | None:
        """Resolve *name* to a command object, importing lazy ones on the way.

        Personality dispatch runs ahead of any context, so lazy groups cannot
        be resolved through `get_command()`. Registration is delegated to
        {meth}`~click_extra.commands.LazyGroup._register_lazy` instead, so the
        subcommand lands in the section it was declared with.
        """
        sub = self.commands.get(name)
        register_lazy = getattr(self, "_register_lazy", None)
        if (
            sub is None
            and register_lazy is not None
            and name in getattr(self, "lazy_subcommands", {})
        ):
            sub = register_lazy(name)
        return sub


def _deepcopy_params(params: list[click.Parameter]) -> list[click.Parameter]:
    """Deep-copy *params*, handing back the enum sentinels they carry untouched.

    See {func}`~click_extra._utils.memoize_enums` for why a parameter cannot be
    deep-copied as it is on Python 3.10.
    """
    memo: dict[int, Any] = {}
    for param in params:
        memoize_enums(param, memo, UNSET)
    return copy.deepcopy(params, memo)


def _merge_params(
    group_params: list[click.Parameter],
    sub_params: list[click.Parameter],
) -> list[click.Parameter]:
    """Merge the group's parameters ahead of the subcommand's.

    A subcommand parameter whose flags or destination collide with a group
    parameter's is dropped, the group's copy winning: subcommands registered
    through click-extra's own `@command` decorator carry a full copy of the
    default options, which would otherwise appear twice.
    """
    reserved: set[str] = set()

    def _record(param: click.Parameter) -> None:
        if param.name:
            reserved.add(param.name)
        if isinstance(param, click.Option):
            reserved.update(param.opts)
            reserved.update(param.secondary_opts)

    for param in group_params:
        _record(param)

    merged = list(group_params)
    for param in sub_params:
        keys: set[str] = {param.name} if param.name else set()
        if isinstance(param, click.Option):
            keys.update(param.opts)
            keys.update(param.secondary_opts)
        if keys & reserved:
            logger.debug(
                f"Dropping subcommand parameter {param.name!r}: "
                f"collides with a group parameter."
            )
            continue
        merged.append(param)
        _record(param)
    return merged


def _rebind_constraints(
    sub: click.Command,
    sub_params_copy: list[click.Parameter],
) -> tuple[Any, ...]:
    """Rebind the subcommand's constraints to its copied parameters.

    Cloup's `BoundConstraint` holds direct references to parameter instances,
    and the personality runs on deep copies of them. A constraint whose
    constrained parameter was dropped by {func}`_merge_params` is skipped,
    since it has nothing left to bind to.
    """
    constraints = getattr(sub, "param_constraints", ())
    if not constraints:
        return ()
    copies = {id(old): new for old, new in zip(sub.params, sub_params_copy)}
    rebound = []
    for bound in constraints:
        new_params = [copies.get(id(param)) for param in bound.params]
        if any(param is None for param in new_params):
            logger.debug(
                f"Skipping constraint {bound.constraint!r}: one of its "
                f"parameters was dropped from the personality."
            )
            continue
        # `BoundConstraint` is a NamedTuple: `_make` rebuilds it with the
        # rebound parameter instances.
        rebound.append(bound._make((bound.constraint, tuple(new_params))))
    return tuple(rebound)
