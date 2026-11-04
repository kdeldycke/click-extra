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
"""Helpers to introspect a CLI: its parameters and its command tree.

Every renderer of a CLI reads it through these helpers: the man pages, the
Markdown and JSON documents, the Carapace completion spec, the `--tree` view and
the `--params` table. One helper per question keeps their answers from drifting
apart: which parameters a command lists and in which order, what each one is
called, what it accepts, and how its help text reads once Click's markers are
taken out.
"""

from __future__ import annotations

import inspect
import logging
import re
from contextlib import nullcontext
from enum import Enum
from functools import cache, cached_property, reduce
from itertools import chain
from operator import getitem
from typing import TypeVar

import click
import cloup
from click import ParamType, get_current_context
from click.core import _format_deprecated_label

from . import context

# Imported under a private name so this module does not offer a second public
# spelling of the helper: its canonical home is click_extra._utils.
from ._utils import patch_attr as _patch_attr, set_nested

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Sequence
    from typing import Any, ClassVar, Literal

logger = logging.getLogger(__name__)

P = TypeVar("P", bound=click.Parameter)
"""Type variable bound to {class}`click.Parameter`, letting {func}`search_params`,
{func}`last_param` and {func}`require_sibling_param` return the exact subclass
they were asked to find."""

#: Separator joining the keys of a parameter's fully-qualified path
#: (`cli.subcommand.param`).
PARAM_PATH_SEP = "."

INLINE_LITERAL_RE = re.compile(r"``([^`]+?)``")
"""Match a reST inline literal, text between two pairs of backticks, in a docstring.

Click stores docstrings verbatim, so any reST markup the author used to
render code-like tokens in HTML docs leaks into `Command.help` /
`Command.short_help`. The roff and HTML man-page paths translate these
matches into the bold/literal markers their renderers understand; the
Sphinx index directive translates them into `nodes.literal`.
"""


def iter_inline_literals(text: str) -> Iterator[tuple[str, bool]]:
    """Walk `text` and yield `(segment, is_literal)` pairs.

    Split on {data}`INLINE_LITERAL_RE` so the consumer can apply
    different rendering to the literal segments (bold for roff, a
    `literal` node for docutils) without re-parsing the regex.
    """
    pos = 0
    for match in INLINE_LITERAL_RE.finditer(text):
        if match.start() > pos:
            yield text[pos : match.start()], False
        yield match.group(1), True
        pos = match.end()
    if pos < len(text):
        yield text[pos:], False


def clean_help(text: str) -> str:
    r"""Normalize Click help prose for the backends that carry newlines natively.

    Runs {func}`inspect.cleandoc` and drops Click's `\b` (`\x08`) no-rewrap
    marker, keeping every line break the marker protected. Markdown, JSON and a
    completion spec all represent those breaks on their own, so none needs an
    equivalent of the roff `.nf` / `.fi` pair: only the control character has to
    go, or it lands in the output as a stray byte.
    """
    return inspect.cleandoc(text).replace("\x08\n", "").replace("\x08", "").strip()


def choice_values(param_type: click.ParamType) -> tuple[str, ...]:
    """The values a `click.Choice`-like type accepts, spelled as Click completes them.

    An {class}`~enum.Enum` member is named by its `name`, as
    {meth}`click.Choice.normalize_choice` does before it folds case, and
    anything else by `str()`. A type carrying no `choices` attribute, or an
    empty one, answers an empty tuple. The one spelling every document of a
    CLI lists a choice under: the help screen, the man page, the completion
    spec.
    """
    choices = getattr(param_type, "choices", None)
    if not choices:
        return ()
    return tuple(
        choice.name if isinstance(choice, Enum) else str(choice) for choice in choices
    )


def search_params(
    params: Iterable[click.Parameter],
    klass: type[P],
    include_subclasses: bool = True,
) -> P | None:
    """Return the one parameter of class `klass` in `params`, or `None`.

    The result is typed as `klass` itself, so a caller needs no `isinstance`
    check to use what it found.

    :param params: list of parameter instances to search in.
    :param klass: the class of the parameter to look for.
    :param include_subclasses: if `True` (the default), a parameter subclassing
        `klass` matches too. If `False`, only a parameter of exactly `klass`
        does.
    :raises RuntimeError: if more than one parameter matches.
    """
    param_list = [
        p
        for p in params
        if isinstance(p, klass) and (include_subclasses or p.__class__ is klass)
    ]
    if not param_list:
        return None
    if len(param_list) != 1:
        raise RuntimeError(
            f"More than one {klass.__name__} parameter found on command: {param_list}"
        )
    return param_list[0]


def last_param(
    params: Iterable[click.Parameter],
    klass: type[P],
) -> P | None:
    """Return the last parameter of exactly `klass` in `params`, or `None`.

    Unlike {func}`search_params`, this matches the exact `klass` (no subclasses)
    and tolerates duplicates: when an option is declared more than once (like an
    explicit `@verbosity_option` stacked on a Click Extra command that already
    ships one), Click keeps the last occurrence, so this mirrors that here instead
    of erroring out on the ambiguity.

    :param params: the command's parameter list to scan.
    :param klass: the exact parameter class to look for.
    """
    options = [p for p in params if isinstance(p, klass) and p.__class__ is klass]
    return options[-1] if options else None


def require_sibling_param(
    params: Iterable[click.Parameter],
    requester: click.Parameter,
    klass: type[P],
) -> P:
    """Return the sibling `klass` parameter declared on the same command, or raise.

    Some options are inert on their own: they drive machinery owned by a sibling
    option. `--no-config` and `--validate-config`, for instance, both depend on
    the `--config` option ({class}`~click_extra.config.option.ConfigOption`). This
    helper centralizes the lookup so every such option raises the same
    `RuntimeError` when its required sibling is missing, naming the offending flag.

    :param params: the command's parameter list to scan.
    :param requester: the parameter requiring the sibling, used to build the error
        message from its flag names and class.
    :param klass: the sibling parameter class to look for.
    """
    sibling = search_params(params, klass)
    if sibling is None:
        raise RuntimeError(
            f"{'/'.join(requester.opts)} {type(requester).__name__} must be used "
            f"alongside {klass.__name__}."
        )
    return sibling


def full_short_help(command: click.Command) -> str:
    """Return the command's canonical one-line short help, untruncated.

    Click's {meth}`click.Command.get_short_help_str` truncates to 45 characters by
    default with a trailing `"..."` so subcommand listings fit a terminal column.
    That bound is wrong for generated documentation and completion specs, where the
    NAME / COMMANDS sections carry the full description and the renderer wraps text
    on its own.

    The lookup mirrors Click's order: an explicit `short_help` wins, otherwise the
    first paragraph of `command.help` is joined into one line. A truthy
    `deprecated` flag appends Click's own label, so a listing reads the same
    marker Click's `get_short_help_str()` produces, reason string included.
    """
    if command.short_help:
        text = command.short_help.strip()
    elif command.help:
        # Click already stores `help` after `inspect.cleandoc`: split on the
        # first blank line to grab the leading paragraph, drop Click's `\b`
        # no-rewrap marker as `get_short_help_str()` does, then squash internal
        # newlines so the result is one line.
        paragraph = command.help.split("\n\n", 1)[0]
        text = clean_help(paragraph).replace("\n", " ")
    else:
        text = ""
    if command.deprecated:
        label = _format_deprecated_label(command.deprecated)
        text = f"{text} {label}".strip()
    return text


def resolve_param_help(param: click.Parameter, ctx: click.Context) -> str | None:
    """Return a parameter's help text, including the dynamically-generated ones.

    Reading `param.help` covers the options that carry a static string, and
    misses the ones that compute their help from the context: Click Extra's own
    `-v` / `-q` derive theirs from the resolved base verbosity, and leave the
    attribute at `None` (see `VerboseOption.get_help_record()`). Falling back to
    the help record picks those up.

    The record also carries Click's bracket fields (`[default: …]`,
    `[required]`, `[env var: …]`), appended to the prose behind two spaces. They
    are stripped here: they are not the author's documentation, and every
    backend of this module renders them (or deliberately does not) from
    structured fields of its own.
    """
    help_text = getattr(param, "help", None)
    if help_text:
        return str(help_text)

    record = param.get_help_record(ctx)
    if not record:
        return None
    text = record[1]
    if isinstance(param, click.Option) and param.get_help_extra(ctx):
        marker = text.rfind("  [")
        if marker != -1:
            text = text[:marker]
    return text.strip() or None


def canonical_param_name(name: str) -> str:
    """Fold a spelling to the parameter name Click would derive from it.

    Applies Click's own derivation, minus the option prefix its callers strip
    first: hyphens become underscores and the result is case-folded, so
    `Foo-Bar` answers `foo_bar`. Use it to resolve an outside spelling (a
    configuration key, an argfile declaration) against the names a CLI
    already has.

    ```{caution}
    The fold is many-to-one, so it identifies a name and never reconstructs a
    spelling. `--foo-bar`, `--Foo-Bar` and `--FOO-BAR` answer the same name,
    as do `--foo--bar` and `--foo__bar`, and `--K` (the Kelvin sign, `U+212A`)
    lands on the same `k` as `--k`. Case folding reaches every script and is
    not length-preserving: `--ẞ` answers `ß`, whose upper case is the two
    letters `SS`, and a composed `café` answers a different name than a
    decomposed one that renders identically.
    ```

    ```{caution}
    A folded spelling is a *candidate*, never an answer on its own. Click
    takes an identifier declaration verbatim, so `@option("--x", "Foo_Bar")`
    names its parameter `Foo_Bar`, which this function would never produce.
    Match the fold against the names a CLI declares and keep the CLI's own
    spelling, rather than storing what this returns.
    ```

    ```{todo}
    Upstream [pallets/click#3827](https://github.com/pallets/click/pull/3827)
    asks whether `Option` should keep the case of an identifier declaration,
    as it does today, or fold it the way `Argument` already does. Should Click
    fold both, no parameter can be named `Foo_Bar` any more: drop the caution
    above, and with it the ambiguity branch of `_merge_into_template` in
    `click_extra.config.schema`, which exists only to tell two such names
    apart.
    ```
    """
    return name.replace("-", "_").lower()


def param_spellings(param: click.Parameter) -> tuple[str, ...]:
    """All literal spellings of a parameter: primary `opts` then `secondary_opts`.

    A boolean flag pair yields both forms (`--foo`, `--no-foo`); a plain option
    yields just its declared names.
    """
    return tuple(param.opts) + tuple(param.secondary_opts)


def short_long_opts(opts: Sequence[str]) -> tuple[str, str]:
    """Split option spellings into the first short (`-x`) and long (`--xy`) form.

    Either element is the empty string when that form is absent.
    """
    short = next((o for o in opts if o.startswith("-") and not o.startswith("--")), "")
    long = next((o for o in opts if o.startswith("--")), "")
    return short, long


def option_value_kind(
    param: click.Parameter,
) -> Literal["flag", "optional", "required"]:
    """Classify how an option consumes a value, the basis for rendering its metavar.

    - `"flag"`: takes no value. A boolean switch (`--foo`, `--foo/--no-foo`), a
      flag with a custom `flag_value` (`--no-config`), or a counter (`-v`).
    - `"optional"`: the value may be omitted. Click models this as
      `is_flag=False` with a `flag_value` set, so a bare `--color` stands for
      the flag value while `--color=never` passes an explicit one.
    - `"required"`: consumes a value (`--config LOCATION`).

    ```{note}
    The discriminator is Click's `is_flag` (plus `count`), not
    `is_bool_flag`: a flag carrying a custom `flag_value` such as
    {class}`~click_extra.config.option.NoConfigOption` reports
    `is_bool_flag=False` yet still takes no value.
    ```
    """
    if (
        getattr(param, "count", False)
        or getattr(param, "is_flag", False)
        or getattr(param, "secondary_opts", None)
    ):
        return "flag"
    if resolve_flag_value(param) is not None:
        return "optional"
    return "required"


def resolve_flag_value(param: click.Parameter) -> Any:
    """The value `param`'s primary declaration stands for.

    `None` for a plain option, a counter or an argument, `True` for a boolean
    flag, and the declared value otherwise (`--color` standing for `always`).

    Read from Click's `Option.flag_activation_value`, not from `flag_value`:
    Click keeps the `UNSET` sentinel there when no value was declared, and the
    sentinel stored anywhere it is read back as a value turns the flag off.
    """
    return getattr(param, "flag_activation_value", None)


def is_repeatable(param: click.Parameter) -> bool:
    """Whether the parameter may be supplied several times (`multiple` or `count`)."""
    return bool(getattr(param, "multiple", False) or getattr(param, "count", False))


class ParamStructure:
    """Utilities to introspect CLI options and commands structure.

    Structures are represented by a tree-like `dict`.

    Access to a node is available using a serialized path string composed of the keys to
    descend to that node, separated by a dot `.`.
    """

    excluded_params: frozenset[str]
    """Fully-qualified IDs of the parameters to block from the structure.

    Set by subclasses: {class}`~click_extra.show_params.ShowParamsOption` freezes an
    empty set, while `ConfigOption` resolves a dynamic default (or the user-provided
    list) within the active context. The two filters are mutually exclusive, a
    constraint each subclass enforces in its own constructor.

    With an allowlist, this holds only the IDs that the walk of
    {meth}`~click_extra.param_tools.ParamStructure.build_param_trees` reaches and
    the allowlist leaves out. Ask
    {meth}`~click_extra.param_tools.ParamStructure.is_excluded` about a parameter of
    another subcommand.
    """

    included_params: frozenset[str] | None
    """Allowlist of parameter IDs, mutually exclusive with `excluded_params`.

    `None` disables the allowlist. Otherwise
    {meth}`~click_extra.param_tools.ParamStructure.build_param_trees` walks only the
    subcommands an allowed ID lies under, and resolves the parameters it reaches
    into `excluded_params`.
    """

    @staticmethod
    def init_tree_dict(*path: str, leaf: Any = None) -> Any:
        """Nest one dict per key of `path`, the deepest one holding `leaf`.

        An empty `path` returns `leaf` itself.
        """
        return reduce(lambda node, key: {key: node}, reversed(path), leaf)

    @staticmethod
    def get_tree_value(tree_dict: dict[str, Any], *path: str) -> Any:
        """Get in the `tree_dict` the value located at the `path`.

        Raises `KeyError` if no item is found at the provided `path`.
        """
        return reduce(getitem, path, tree_dict)

    def walk_params(
        self,
        *,
        descend: Callable[[tuple[str, ...]], bool] | None = None,
    ) -> Iterator[tuple[tuple[str, ...], click.Parameter]]:
        """Yield every parameter of the CLI, unfiltered.

        Everything is included, from top-level groups to subcommands, and from
        options to arguments, unless `descend` skips a subcommand.

        Thin adapter over {func}`~click_extra.param_tools.walk_command_params`: it
        resolves the root CLI from the active context and drops the per-parameter
        context that the free function also yields.

        :param descend: passed on to
            {func}`~click_extra.param_tools.walk_command_params`, to skip the
            subcommands it declines.
        :return: `(keys, param)` pairs: the keys leading to the parameter, then
            the parameter itself.
        """
        ctx = get_current_context()
        cli = ctx.find_root().command
        assert cli.name is not None
        for keys, param, _ctx in walk_command_params(
            cli, ctx, (cli.name,), descend=descend
        ):
            yield keys, param

    TYPE_MAP: ClassVar[dict[type[ParamType], type[str | int | float | bool | list]]] = {
        click.types.StringParamType: str,
        click.types.IntParamType: int,
        click.types.FloatParamType: float,
        click.types.BoolParamType: bool,
        click.types.UUIDParameterType: str,
        click.types.UnprocessedParamType: str,
        click.types.File: str,
        click.types.Path: str,
        click.types.Choice: str,
        click.types.IntRange: int,
        click.types.FloatRange: float,
        click.types.DateTime: str,
        click.types.Tuple: list,
    }
    """Map Click types to their Python equivalent.

    Keys are subclasses of `click.types.ParamType`. Values are expected to be simple
    builtins Python types.

    This mapping can be seen as a reverse of the `click.types.convert_type()` method.
    """

    @staticmethod
    def map_click_type(click_type: ParamType) -> type[str | int | float | bool | list]:
        """Map a Click parameter type instance to its Python equivalent.

        Returns `str` for unrecognised custom types, since command-line
        parameters are strings by default.

        See the list of
        [custom types provided by Click](https://click.palletsprojects.com/en/stable/api/#types).
        """
        return _python_type_of(type(click_type))

    @staticmethod
    def get_param_type(
        param: click.Parameter,
    ) -> type[str | int | float | bool | list]:
        """Get the Python type of a Click parameter.

        Returns `str` for unrecognised custom types, since command-line
        parameters are strings by default.

        A boolean flag is a `bool` even when it is repeatable: it collects
        occurrences of a toggle rather than values, and a configuration file
        spells it as the boolean it is. That is why the check comes before the
        multi-value one, which would otherwise read it as a list and have an
        unset one dump as `[]`, a shape no user writes.

        See the list of
        [custom types provided by Click](https://click.palletsprojects.com/en/stable/api/#types).
        """
        if getattr(param, "is_bool_flag", False):
            return bool

        if param.multiple or param.nargs != 1:
            return list

        return ParamStructure.map_click_type(param.type)

    def is_excluded(self, param_id: str) -> bool:
        """Whether a configuration file cannot set the parameter `param_id`.

        An allowlist answers alone: the parameter is excluded when
        `included_params` does not name it. So the answer holds for a parameter
        of a subcommand that the walk of
        {meth}`~click_extra.param_tools.ParamStructure.build_param_trees` skipped.
        Without an allowlist, the parameter is excluded when `excluded_params`
        lists it.

        :param param_id: the fully-qualified ID of the parameter, its path keys
            joined with {data}`~click_extra.param_tools.PARAM_PATH_SEP`.
        """
        if self.included_params is not None:
            return param_id not in self.included_params
        return param_id in self.excluded_params

    def _leads_to_included(self, keys: tuple[str, ...]) -> bool:
        """Whether an ID of `included_params` lies under the subcommand at `keys`."""
        assert self.included_params is not None
        prefix = f"{PARAM_PATH_SEP.join(keys)}{PARAM_PATH_SEP}"
        return any(param_id.startswith(prefix) for param_id in self.included_params)

    def build_param_trees(self) -> dict[str, Any]:
        """Build and return the parameters tree structure.

        Each leaf is the list of the parameters its path names: one, or several
        when options share a name, like the feature switches of one destination.

        This removes parameters whose fully-qualified IDs are in the `excluded_params`
        blocklist.

        With an allowlist, the tree holds only the parameters `included_params`
        names. The walk then skips each subcommand that no allowed ID lies under,
        so it does not import a lazy subcommand of a
        {class}`~click_extra.commands.LazyGroup` that the allowlist leaves out. An
        empty allowlist walks the root command alone. The parameters the walk
        reaches and the allowlist leaves out become `excluded_params`.
        """
        descend = self._leads_to_included if self.included_params is not None else None

        objects: dict[str, Any] = {}
        reached_ids = set()

        for keys, param in self.walk_params(descend=descend):
            param_id = PARAM_PATH_SEP.join(keys)
            reached_ids.add(param_id)
            if self.is_excluded(param_id):
                continue

            # Parameters sharing a name, like the feature switches of a single
            # destination, gather in one leaf, in declaration order.
            try:
                leaf = self.get_tree_value(objects, *keys)
            except (KeyError, TypeError):
                leaf = None
            set_nested(
                objects, keys, [*leaf, param] if isinstance(leaf, list) else [param]
            )

        if self.included_params is not None:
            self.excluded_params = frozenset(reached_ids) - self.included_params

        return objects

    @staticmethod
    def _nullify_leaves(tree: dict[str, Any]) -> dict[str, Any]:
        """Derive a template shape from a tree by replacing all leaves with `None`."""
        return {
            k: ParamStructure._nullify_leaves(v) if isinstance(v, dict) else None
            for k, v in tree.items()
        }

    @cached_property
    def params_template(self) -> dict[str, Any]:
        """Returns a tree-like dictionary whose keys shadows the CLI options and
        subcommands and values are `None`.

        Perfect to serve as a template for configuration files.
        """
        return self._nullify_leaves(self.params_objects)

    @cached_property
    def params_objects(self) -> dict[str, Any]:
        """Returns a tree-like dictionary whose keys shadows the CLI options and
        subcommands and values are parameter objects.

        Perfect to parse configuration files and user-provided parameters.
        """
        return self.build_param_trees()


@cache
def _python_type_of(
    click_type_class: type[ParamType],
) -> type[str | int | float | bool | list]:
    """The Python type a class of Click parameter type converts to.

    Answers from {attr}`ParamStructure.TYPE_MAP`: the entry of the class itself,
    else the first entry the class inherits, else `str`, which is what the command
    line hands a custom type. Cached by class, since a CLI declares a handful of
    types and the `--params` table asks once per parameter.
    """
    py_type = ParamStructure.TYPE_MAP.get(click_type_class)
    if py_type is not None:
        return py_type
    for param_type, mapped_type in ParamStructure.TYPE_MAP.items():
        if issubclass(click_type_class, param_type):
            return mapped_type
    return str


def get_param_spec(param: click.Parameter, ctx: click.Context) -> str | None:
    """Extract the option-spec string (like `-v, --verbose`) from a parameter.

    Temporarily unhides hidden options so their help record can be produced.

    ```{note}
    The `hidden` property is only supported by `Option`, not `Argument`.
    ```

    ```{todo}
    Upstream [pallets/click#3821](https://github.com/pallets/click/pull/3821)
    splits the spec half of `Option.get_help_record()` into its own
    `get_help_spec()` method, which returns it even for hidden options.
    Once a Click release ships it, drop the monkey-patching below and call
    that method directly.
    ```
    """
    if not hasattr(param, "hidden"):
        return None
    with _patch_attr(param, "hidden", False) if param.hidden else nullcontext():
        help_record = param.get_help_record(ctx)
        return help_record[0] if help_record else None


def make_resilient_context(
    command: click.Command,
    info_name: str | None = None,
    parent: click.Context | None = None,
) -> click.Context:
    """Build an introspection context for a command.

    Parses no arguments and sets `resilient_parsing=True` so required-argument
    errors, prompts and eager-option side effects stay dormant: the canonical way
    to materialize a {class}`click.Context` purely to read a command's structure
    (its parameters, env-var prefix and subcommands), shared by the man-page and
    Carapace exporters.

    :param command: the command to build the context of.
    :param info_name: the name the command goes by in that context. Defaults to
        the command's own name.
    :param parent: the context of the command's parent, if any.
    """
    if info_name is None:
        info_name = command.name
    return command.make_context(info_name, [], parent=parent, resilient_parsing=True)


def child_context(
    command: click.Command,
    parent: click.Context,
    info_name: str,
) -> click.Context:
    """Build the context of a subcommand under `parent`, without parsing anything.

    Built the way {meth}`click.Command.make_context` builds one, from the
    command's own `context_class` and `context_settings`, so the context reads
    like the one a real invocation gets: a subcommand setting its own
    `auto_envvar_prefix` names its environment variables after it, where a bare
    `click.Context` would derive them from the parent's prefix. Unlike
    {func}`make_resilient_context`, no parameter is processed, so a walk over a
    live invocation never re-runs a callback.
    """
    return command.context_class(
        command,
        info_name=info_name,
        parent=parent,
        **command.context_settings,
    )


def iter_subcommands(
    command: click.Command,
    ctx: click.Context,
    *,
    skip_hidden: bool = True,
    listing: bool = False,
) -> Iterator[tuple[str, click.Command]]:
    """Yield a group's direct subcommands as `(name, command)` pairs.

    Subcommands are discovered dynamically through
    {meth}`click.Group.list_commands` / {meth}`~click.Group.get_command`, in
    listing order, so lazily-registered commands are included. A non-group yields
    nothing, a name resolving to `None` is skipped, and hidden subcommands are
    skipped unless `skip_hidden` is `False` (completion specs keep them,
    flagged hidden; documentation drops them).

    :param listing: resolve each name to the command the group's help screen
        describes, through its `listed_command` method when it has one. A
        {class}`~click_extra.commands.LazyGroup` answers there with a stand-in
        for a lazy subcommand declaring its help, so the walk imports nothing.
    """
    if not isinstance(command, click.Group):
        return
    resolve = command.get_command
    if listing:
        resolve = getattr(command, "listed_command", resolve)
    for name in command.list_commands(ctx):
        sub = resolve(ctx, name)
        if sub is None:
            continue
        if skip_hidden and getattr(sub, "hidden", False):
            continue
        yield name, sub


def iter_subcommand_contexts(
    command: click.Command,
    ctx: click.Context,
    *,
    skip_hidden: bool = True,
) -> Iterator[tuple[str, click.Command, click.Context]]:
    """Yield a group's direct subcommands, each with an introspection context.

    Pairs {func}`iter_subcommands` with {func}`make_resilient_context`: every
    renderer walking a command tree (the man pages, the Markdown and JSON
    documents, the Carapace spec, the `--tree` view) descends through here, so a
    lazy subcommand, the order {meth}`click.Group.list_commands` sets and a name
    resolving to `None` are handled the same way in all of them.

    Each context is built under `ctx` and named after the subcommand's
    registration name, so its `command_path` and its environment variable
    prefix are the ones a run reaches.

    :param skip_hidden: passed on to {func}`iter_subcommands`.
    :return: `(name, subcommand, subcontext)` triples, in listing order.
    """
    for name, sub in iter_subcommands(command, ctx, skip_hidden=skip_hidden):
        yield name, sub, make_resilient_context(sub, name, parent=ctx)


def split_option_groups(
    command: cloup.OptionGroupMixin,
) -> tuple[tuple[cloup.OptionGroup, ...], tuple[cloup.OptionGroup, ...]]:
    """A command's explicit option groups, split around its ungrouped section.

    Hands back the groups drawn *before* the ungrouped options, then those drawn
    *after*. A Click Extra command decides that split itself, through
    {meth}`click_extra.commands.Command.split_option_groups`, so its own sections
    land past the ungrouped ones. A plain Cloup command has no such method and
    keeps every group ahead of the ungrouped section, which is Cloup's own rule.

    Every renderer reading a command's sections goes through this, so the split is
    resolved in one place whatever the command class.

    :param command: the command whose groups are read.
    :return: the groups drawn before the ungrouped section, then those after it.
    """
    splitter = getattr(command, "split_option_groups", None)
    if splitter is None:
        return tuple(command.option_groups), ()
    return splitter()  # type: ignore[no-any-return]


def iter_params_for_display(
    command: click.Command,
    ctx: click.Context,
) -> Iterator[click.Parameter]:
    """Yield a command's parameters in the order its help screen lists them.

    A Click Extra command keeps two orders apart: `command.params` is the
    processing order, which decides when each callback fires, while the help screen
    reads the presentation order Cloup caches in `arguments`, `option_groups` and
    `ungrouped_options`, sectioned by
    {meth}`click_extra.commands.Command.split_option_groups` and sorted within a
    section by {meth}`~click_extra.commands.Command.param_priority`. Reading
    `get_params()` therefore renders a man page, a Markdown document or a
    completion spec whose flags no longer match the `--help` its reader just saw.
    This is the accessor every such renderer should go through.

    Falls back to `get_params()` for a command that carries no Cloup option groups,
    where the two orders are the same list. Any parameter attached after
    construction, and so absent from the cached groups, is yielded last rather than
    dropped.
    """
    if not isinstance(command, cloup.Command):
        yield from command.get_params(ctx)
        return

    own_groups, extra_groups = split_option_groups(command)
    seen: set[int] = set()
    for param in chain(
        command.arguments,
        (option for group in own_groups for option in group.options),
        command.get_ungrouped_options(ctx),
        (option for group in extra_groups for option in group.options),
        # A parameter appended to `command.params` after construction never made
        # it into the cached groups: yield it rather than drop it from the render.
        command.get_params(ctx),
    ):
        if id(param) not in seen:
            seen.add(id(param))
            yield param


def walk_command_params(
    cmd: click.Command,
    ctx: click.Context,
    parent_keys: tuple[str, ...] = (),
    *,
    descend: Callable[[tuple[str, ...]], bool] | None = None,
) -> Iterator[tuple[tuple[str, ...], click.Parameter, click.Context]]:
    """Walk the parameter tree of a Click command and all its subcommands.

    Yields `(path_keys, param, owning_ctx)` for every parameter found on
    `cmd` and, recursively, on each subcommand. Each subcommand is walked under
    its own freshly-built child context (see {func}`child_context`), so
    context-sensitive metadata (notably the auto-generated environment variable,
    which derives from `Context.auto_envvar_prefix`) is computed at the correct
    nesting level, with the subcommand's own context settings applied, rather
    than inherited from the root.

    A subcommand whose name collides with a sibling parameter at the same level
    is skipped: a single fully-qualified path cannot address both an option and
    a subcommand at once.

    :param descend: called with the path keys of each subcommand, before the
        group resolves it. The walk skips a subcommand for which it returns
        `False`, so a lazy subcommand it declines is not imported. `None` walks
        every subcommand.
    """
    level_param_names = set()
    for param in cmd.get_params(ctx):
        if param.name is not None:
            level_param_names.add(param.name)
            yield (*parent_keys, param.name), param, ctx

    if isinstance(cmd, click.Group):
        # `list_commands()` is the group's own authority on subcommand order: a
        # stock Click group still answers alphabetically, and one that was told
        # otherwise gets a `--params` tree matching its help screen.
        for subcmd_name in cmd.list_commands(ctx):
            if subcmd_name in level_param_names:
                logger.debug(
                    f"{cmd.name}{PARAM_PATH_SEP}{subcmd_name} subcommand shadows a "
                    f"top-level parameter; excluded from parameter tree.",
                )
                continue
            subcmd_keys = (*parent_keys, subcmd_name)
            if descend is not None and not descend(subcmd_keys):
                continue
            subcmd = cmd.get_command(ctx, subcmd_name)
            if subcmd is None:
                continue
            subcmd_ctx = child_context(subcmd, ctx, subcmd_name)
            yield from walk_command_params(
                subcmd, subcmd_ctx, subcmd_keys, descend=descend
            )


def replay_raw_args(subject_ctx: click.Context) -> dict[str, Any]:
    """Re-parse the captured raw arguments to recover per-parameter values.

    Click discards the pre-parsed arguments once processing is done, so the
    value and provenance of each parameter cannot be read back directly. When
    {data}`~click_extra.context.RAW_ARGS` was captured on the context (by
    `Command`/`Group`), replaying it through a fresh parser rebuilds the
    `opts` mapping that `Parameter.consume_value` consults, without re-firing
    eager callbacks: `handle_parse_result` is never called here, only the
    parser.

    Returns an empty mapping when no raw arguments were captured, so callers can
    fall back to parameter defaults.
    """
    raw_args = context.get(subject_ctx, context.RAW_ARGS)
    if raw_args is None:
        return {}
    parser = subject_ctx.command.make_parser(subject_ctx)
    opts, _, _ = parser.parse_args(args=list(raw_args))
    return opts
