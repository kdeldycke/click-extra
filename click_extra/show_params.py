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
"""The `--params` option, which prints a table of every parameter of a CLI.

The table shows each parameter's value and where that value comes from: the
command line, an environment variable, a configuration file or a default.
"""

from __future__ import annotations

import logging
from collections import ChainMap
from gettext import gettext as _

import click
from click._utils import UNSET
from click.core import ParameterSource

from . import context

# Imported under a private name so this module does not offer a second public
# spelling of the helper: its canonical home is click_extra._utils.
from ._utils import patch_attr as _patch_attr, shrinkuser
from .columns import (
    ColumnSpec,
    render_columns_markdown_table,
    select_columns,
    select_row,
)
from .config import ConfigOption, ensure_config_loaded
from .envvar import param_envvar_ids
from .highlight import DEPRECATED_RE, highlight
from .param_tools import (
    PARAM_PATH_SEP,
    ParamStructure,
    get_param_spec,
    replay_raw_args,
    resolve_flag_value,
    resolve_param_help,
    search_params,
    walk_command_params,
)
from .parameters import ExtraOption
from .styling import Style
from .table import DEFAULT_FORMAT, SERIALIZATION_FORMATS, print_table
from .table_options import ColumnsOption, TableFormatOption
from .theme import KO_GLYPH, OK_GLYPH, get_current_theme

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path
    from typing import Any, ClassVar

    from .param_tools import P

logger = logging.getLogger(__name__)


def _structured_value(value: Any) -> Any:
    """Coerce a value to a natively serializable form for structured output.

    Scalars and lists (`str`, `int`, `float`, `bool`, `list`, `None`)
    pass through unchanged so JSON, YAML and TOML renderers keep their native
    types. Anything else (a Click `ParamType`, a `Path`, an arbitrary
    object) is rendered with {func}`repr` so it survives serialization as a
    readable string.
    """
    if isinstance(value, (str, int, float, bool, list, type(None))):
        return value
    return repr(value)


def _format_param_row(
    param: click.Parameter,
    ctx: click.Context,
    path: str,
    is_structured: bool,
) -> dict[str, Any]:
    """Compute the *structural* table cells for a Click parameter.

    Returns a `dict[column_id, cell]` covering every column that can be
    derived from the parameter object alone (no runtime invocation state or
    config-file context). Specifically: `id`, `spec`, `class`,
    `param_type`, `python_type`, `hidden`, `exposed`, `envvars`,
    `default`, `is_flag`, `flag_value`, `is_bool_flag`, `multiple`,
    `nargs`, `prompt`, and `confirmation_prompt`.

    Attributes only defined on `click.Option` (`hidden`, `is_flag`,
    `flag_value`, `is_bool_flag`, `prompt`, `confirmation_prompt`)
    yield `None` for `click.Argument` parameters: empty cell in visual
    formats, `null` in structured ones.

    For structured formats (JSON, YAML, etc.), values are native Python types.
    For visual formats, values are themed strings matching help-screen styling.

    The remaining table columns (`allowed_in_conf`, `value`, `source`,
    `config_file`) require live context and are filled in by
    {func}`~click_extra.show_params.render_params_table`.
    """
    param_spec = get_param_spec(param, ctx)
    param_class = param.__class__
    class_str = f"{param_class.__module__}.{param_class.__qualname__}"
    type_str = f"{param.type.__module__}.{param.type.__class__.__name__}"
    python_type_name = ParamStructure.get_param_type(param).__name__

    hidden = getattr(param, "hidden", None)
    is_flag = getattr(param, "is_flag", None)
    flag_value = resolve_flag_value(param)
    is_bool_flag = getattr(param, "is_bool_flag", None)
    prompt = getattr(param, "prompt", None)
    confirmation_prompt = getattr(param, "confirmation_prompt", None)

    # Click returns the UNSET sentinel for a parameter without a default. Present
    # it as None, as click.Command.parse_args does for ctx.params. See the
    # RAW_ARGS notes in click_extra.context.
    default_val = param.get_default(ctx)
    if default_val is UNSET:
        default_val = None

    if is_structured:
        default_val = _structured_value(default_val)
        flag_value = _structured_value(flag_value)
        return {
            "id": path,
            "spec": param_spec,
            "help": resolve_param_help(param, ctx),
            "class": class_str,
            "param_type": type_str,
            "python_type": python_type_name,
            "hidden": hidden,
            "exposed": param.expose_value,
            "envvars": list(param_envvar_ids(param, ctx)),
            "default": default_val,
            "is_flag": is_flag,
            "flag_value": flag_value,
            "is_bool_flag": is_bool_flag,
            "multiple": param.multiple,
            "nargs": param.nargs,
            "prompt": prompt,
            "confirmation_prompt": confirmation_prompt,
        }

    active_theme = get_current_theme()

    def styled_help(text):
        """Paint the deprecation marker, leaving the author's own prose alone.

        The marker is the one part of this column Click Extra puts there itself,
        and the help screen paints it: a table whose every other column is themed
        would otherwise be the one render that draws it flat.
        """
        if text is None:
            return None
        return highlight(text, [DEPRECATED_RE], active_theme.deprecated)

    def styled_bool(value):
        """Render an attribute as a themed glyph by its truth, or `None` if absent.

        Read by truth rather than identity with `True`: Click accepts a string
        for `confirmation_prompt`, which asks for confirmation like `True` does.
        """
        if value is None:
            return None
        return active_theme.success(OK_GLYPH) if value else active_theme.error(KO_GLYPH)

    return {
        "id": active_theme.invoked_command(path),
        "spec": active_theme.option(param_spec) if param_spec else param_spec,
        "help": styled_help(resolve_param_help(param, ctx)),
        "class": class_str,
        "param_type": type_str,
        "python_type": active_theme.metavar(python_type_name),
        "hidden": styled_bool(hidden),
        "exposed": styled_bool(param.expose_value),
        "envvars": ", ".join(map(active_theme.envvar, param_envvar_ids(param, ctx))),
        "default": active_theme.default(repr(default_val)),
        "is_flag": styled_bool(is_flag),
        "flag_value": (
            active_theme.default(repr(flag_value)) if flag_value is not None else None
        ),
        "is_bool_flag": styled_bool(is_bool_flag),
        "multiple": styled_bool(param.multiple),
        "nargs": str(param.nargs),
        "prompt": prompt,
        "confirmation_prompt": styled_bool(confirmation_prompt),
    }


def param_config_source(
    root_ctx: click.Context,
    keys: Sequence[str],
) -> Path | str | None:
    """Return the configuration file supplying a parameter's `default_map` value.

    `keys` is the parameter's fully-qualified path, root command name first
    and parameter name last, as yielded by
    {func}`~click_extra.param_tools.walk_command_params`.
    A local file is returned as a `Path`, a remote one as its URL, a `str`.
    Returns `None` when no configuration file was loaded, when the parameter
    is absent from every loaded layer, or when the context carries no layered
    `default_map` at all.

    The walk mirrors how Click resolves `default_map`, so the attribution
    matches the value Click actually picks. The root context's `default_map`
    is a `~collections.ChainMap` whose first layers are the loaded files, in
    the order of {data}`~click_extra.context.CONF_SOURCES`. A key resolves to
    the first layer holding it, in a subcommand section as at the root: the
    first layer holding the whole path of the parameter names the file.

    ```{note}
    Lazy subcommands receive their section from the merged configuration
    document, injected into the front layer by
    {meth}`~click_extra.commands.LazyGroup._apply_config_to_parent_context`:
    those values are attributed to the highest-precedence file even when
    several files contributed to the merge.
    ```
    """
    sources: tuple[tuple[Path | str, dict[str, Any]], ...] | None = context.get(
        root_ctx, context.CONF_SOURCES
    )
    if not sources:
        return None
    default_map = root_ctx.default_map
    if not isinstance(default_map, ChainMap):
        return None

    for index, layer in enumerate(default_map.maps[: len(sources)]):
        subtree: Any = layer
        for segment in keys[1:-1]:
            subtree = subtree.get(segment) if isinstance(subtree, dict) else None
        if isinstance(subtree, dict) and keys[-1] in subtree:
            return sources[index][0]
    return None


def _replay_sibling_option(
    subject_ctx: click.Context,
    params: Sequence[click.Parameter],
    opts: dict[str, Any],
    option_class: type[P],
    meta_key: str,
    apply: Callable[[P, click.Context, click.Parameter, Any], None],
) -> None:
    """Hand a sibling option's value to its `apply` callback, ahead of Click.

    {func}`render_params_table` runs from an eager callback, possibly before
    Click processes a sibling `--table-format` or `--columns` option. The value
    the option takes is recovered from `opts`, the replayed command line, through
    {meth}`click.Parameter.consume_value`, then converted and passed to `apply`,
    the option's own callback, which stores it on the context.

    Does nothing when the context already holds `meta_key`, or when the command
    carries no `option_class` option.
    """
    if context.get(subject_ctx, meta_key) is not None:
        return
    option = search_params(params, option_class)
    if option is None:
        return
    raw_value, _source = option.consume_value(subject_ctx, opts)
    value = (
        option.type.convert(raw_value, option, subject_ctx)
        if raw_value
        else option.get_default(subject_ctx)
    )
    apply(option, subject_ctx, option, value)


def render_params_table(
    subject_ctx: click.Context,
    *,
    default_columns: Sequence[str] | None = None,
) -> None:
    """Introspect `subject_ctx.command` and print its parameter metadata table.

    Walks the command and any nested subcommands, emitting one row per
    parameter. The table format and column selection are read from
    `subject_ctx.meta` (see {data}`~click_extra.context.TABLE_FORMAT` and
    {data}`~click_extra.context.COLUMNS`); when neither is set, a sibling
    `--table-format` / `--columns` option on the command is consulted, then
    the `default_columns` fallback, then the canonical order.

    When `subject_ctx.meta` carries pre-parsed
    {data}`~click_extra.context.RAW_ARGS`, the `value` and `source` columns
    are resolved by replaying those arguments against the command parser;
    otherwise they fall back to the parameter defaults.

    This is the shared rendering core behind both
    {meth}`~click_extra.show_params.ShowParamsOption.print_params` (introspecting
    the live CLI) and the `click-extra wrap --params` path (introspecting a
    foreign target).
    The caller is responsible for exiting the context afterwards.

    ```{important}
    Click does not keep the raw, pre-parsed arguments around, so values and
    their provenance cannot be read back directly. The workaround replays
    {data}`~click_extra.context.RAW_ARGS` (captured on the context by
    `Command`/`Group`) through the command parser, calling
    `consume_value()` rather than `handle_parse_result()` so eager
    callbacks are not re-triggered.
    ```
    """
    active_theme = get_current_theme()
    ok_styled = active_theme.success(OK_GLYPH)
    ko_styled = active_theme.error(KO_GLYPH)

    cmd = subject_ctx.command

    # Resolve the value getter. When the original arguments are available, they
    # are replayed through the command parser to recover each value and its
    # provenance; otherwise only the parameter defaults are known. Values are
    # resolved against each parameter's owning context, so subcommand
    # parameters read their `default_map` from the subcommand's own section
    # and their environment variables from the correct nesting level.
    opts: dict[str, Any] = {}
    raw_args = context.get(subject_ctx, context.RAW_ARGS)
    if raw_args is not None:
        logger.debug(f"{context.RAW_ARGS}: {raw_args}")
        opts = replay_raw_args(subject_ctx)

        def get_param_value(param, param_ctx):
            # Replayed under resilient parsing, like shell completion: an option
            # declaring a prompt then reports its missing value instead of
            # asking the user for one.
            with _patch_attr(param_ctx, "resilient_parsing", True):
                value, source = param.consume_value(param_ctx, opts)
            # consume_value() can return the UNSET sentinel for a parameter with
            # no user input and no default. Normalize it to None, mirroring the
            # step click.Command.parse_args runs after parsing, which this
            # re-parse bypasses. See the RAW_ARGS notes in click_extra.context.
            return (None if value is UNSET else value), source

    else:

        def get_param_value(param, param_ctx):
            return None, param_ctx.get_parameter_source(param.name)

    params = cmd.get_params(subject_ctx)
    # Locate a --config option to fill the "allowed in conf?" column.
    config_option = search_params(params, ConfigOption)

    _replay_sibling_option(
        subject_ctx,
        params,
        opts,
        TableFormatOption,
        context.TABLE_FORMAT,
        TableFormatOption.init_formatter,
    )
    table_format = context.get(subject_ctx, context.TABLE_FORMAT) or DEFAULT_FORMAT
    is_structured = table_format in SERIALIZATION_FORMATS

    _replay_sibling_option(
        subject_ctx,
        params,
        opts,
        ColumnsOption,
        context.COLUMNS,
        ColumnsOption.init_columns,
    )
    canonical_ids = ShowParamsOption.column_ids()
    selected_ids: tuple[str, ...] = context.get(subject_ctx, context.COLUMNS) or ()
    if not selected_ids:
        # No projection asked for: show the caller's columns, else every column
        # but the opt-in ones, which would otherwise squeeze all the others (see
        # ColumnSpec.optional).
        selected_ids = (
            tuple(default_columns or ()) or ShowParamsOption.default_column_ids()
        )
        # A cascading --config layers several files, so `Source` alone no longer
        # tells which one a value came from: draw the column naming it, in its
        # canonical place.
        if (
            config_option is not None
            and config_option.cascade
            and "config_file" not in selected_ids
        ):
            selected_ids = tuple(
                col_id
                for col_id in canonical_ids
                if col_id in selected_ids or col_id == "config_file"
            )

    # Validate the requested IDs against the column registry so unknown IDs
    # become a clear, actionable UsageError.
    unknown = [col_id for col_id in selected_ids if col_id not in canonical_ids]
    if unknown:
        joined = ", ".join(repr(c) for c in unknown)
        accepted = ", ".join(canonical_ids)
        raise click.UsageError(
            f"Unknown --columns ID(s): {joined}. Accepted: {accepted}.",
            ctx=subject_ctx,
        )

    rows: list[tuple[str, tuple[Any, ...]]] = []
    for keys, param, owning_ctx in walk_command_params(
        cmd, subject_ctx, (cmd.name or "",)
    ):
        path = PARAM_PATH_SEP.join(keys)
        param_value, source = get_param_value(param, owning_ctx)

        # Whether the parameter is reachable from a configuration file.
        allowed_in_conf_bool = None
        if config_option:
            allowed_in_conf_bool = not config_option.is_excluded(path)

        row = _format_param_row(param, owning_ctx, path, is_structured)

        # Config-file provenance: only meaningful when the effective value
        # came from the default_map; the layer walk then names the file it
        # resolved from.
        config_file: Path | str | None = None
        if source is ParameterSource.DEFAULT_MAP:
            location = param_config_source(subject_ctx.find_root(), keys)
            if location is not None:
                config_file = location
                # A remote configuration is located by its URL, a string: only a
                # local path has a home directory to shrink. Normalized as a
                # path, a URL would lose a slash after its scheme.
                if not is_structured and not isinstance(location, str):
                    config_file = shrinkuser(location)

        if is_structured:
            param_value = _structured_value(param_value)
            row["allowed_in_conf"] = allowed_in_conf_bool
            row["value"] = param_value
            row["source"] = source.name if source else None
            row["config_file"] = str(config_file) if config_file else None
        else:
            allowed_in_conf = None
            if allowed_in_conf_bool is not None:
                allowed_in_conf = ok_styled if allowed_in_conf_bool else ko_styled
            row["allowed_in_conf"] = allowed_in_conf
            row["value"] = repr(param_value)
            row["source"] = source.name if source else None
            row["config_file"] = config_file

        rows.append((path, select_row(row, selected_ids, canonical_ids)))

    # Depth first, then path, keeping top-level parameters on top. Sorted on the
    # path itself, so the order holds whichever column the projection puts first.
    rows.sort(key=lambda item: (item[0].count(PARAM_PATH_SEP), item[0]))

    selected_columns = select_columns(ShowParamsOption.TABLE_HEADERS, selected_ids)
    labels = tuple(col.label for col in selected_columns)
    header_labels: tuple[Any, ...]
    if is_structured:
        header_labels = labels
    else:
        header_style = Style(bold=True)
        header_labels = tuple(map(header_style, labels))

    print_table(
        [row for _, row in rows],
        headers=header_labels,
        table_format=table_format,
    )


class ShowParamsOption(ExtraOption, ParamStructure):
    """A pre-configured option adding a `--params` option.

    Between configuration files, default values and environment variables, it might be
    hard to guess under which set of parameters the CLI will be executed. This option
    prints information about the parameters that will be fed to the CLI.

    ```{note}
    The flag is named `--params`, not `--show-params`. It names the view it
    prints, matching the neighbouring bare-noun informational flags (`--help`,
    `--version`, `--man`, `--tree`), none of which carry a `show-` verb
    prefix. The class and the {func}`@show_params_option
    <click_extra.decorators.show_params_option>` decorator are named for what
    they do (show the parameters), while the flag and the parameter's ID use the
    bare noun.
    ```
    """

    TABLE_HEADERS: ClassVar[tuple[ColumnSpec, ...]] = (
        ColumnSpec(
            id="id",
            label="ID",
            description=(
                "Fully-qualified parameter path (`cli.subcommand.param_name`) "
                "derived from the [`click.Command`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Command) "
                "tree. Doubles as the key used to address the parameter from a "
                "configuration file, which also accepts the kebab-case "
                "spelling of the last segment."
            ),
        ),
        ColumnSpec(
            id="spec",
            label="Spec.",
            description=(
                "Option/argument specification string (like `-v, --verbose`) "
                "extracted from [`click.Parameter.get_help_record()`]"
                "(https://click.palletsprojects.com/en/stable/api/"
                "#click.Parameter)."
            ),
        ),
        ColumnSpec(
            id="help",
            label="Help",
            optional=True,
            description=(
                "The parameter's own help text, as written by the CLI author. "
                "Opt-in: it is the only column carrying free-form prose, so it "
                "stays out of the default table and is selected by ID "
                "(`--columns id,spec,help`). Structured formats are its main "
                "audience: it turns a `--params` dump into a self-describing "
                "inventory a tool or an agent can read without also parsing the "
                "rendered `--help` screen."
            ),
        ),
        ColumnSpec(
            id="class",
            label="Class",
            description=(
                "Fully-qualified class of the parameter: a subclass of "
                "[`click.Option`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Option), "
                "[`click.Argument`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Argument), "
                "[`cloup.Option`]"
                "(https://cloup.readthedocs.io/en/stable/autoapi/cloup/"
                "index.html#cloup.Option), "
                "or one of Click Extra's own wrappers "
                "([`click_extra.parameters.Option`](#click_extra.parameters.Option), "
                "[`click_extra.parameters.Argument`]"
                "(#click_extra.parameters.Argument), "
                "[`click_extra.parameters.ExtraOption`]"
                "(#click_extra.parameters.ExtraOption))."
            ),
        ),
        ColumnSpec(
            id="param_type",
            label="Param type",
            description=(
                "Click value converter class: a subclass of [`click.ParamType`]"
                "(https://click.palletsprojects.com/en/stable/api/"
                "#click.ParamType) like [`click.IntRange`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.IntRange), "
                "[`click.Choice`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Choice), "
                "or a Click Extra type."
            ),
        ),
        ColumnSpec(
            id="python_type",
            label="Python type",
            description=(
                "Python built-in type the parsed value resolves to: "
                "[`str`](https://docs.python.org/3/library/stdtypes.html"
                "#text-sequence-type-str), "
                "[`int`](https://docs.python.org/3/library/functions.html#int), "
                "[`float`](https://docs.python.org/3/library/functions.html#float), "
                "[`bool`](https://docs.python.org/3/library/functions.html#bool), "
                "or [`list`](https://docs.python.org/3/library/stdtypes.html#list). "
                "Computed by [`ParamStructure.get_param_type()`]"
                "(#click_extra.param_tools.ParamStructure.get_param_type) from "
                "the Click `Param type`."
            ),
        ),
        ColumnSpec(
            id="hidden",
            label="Hidden",
            description=(
                "Reflects [`click.Option`'s `hidden`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Option) "
                "constructor argument: the option is omitted from `--help` output. "
                "Empty for [`click.Argument`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Argument), "
                "which does not support hiding."
            ),
        ),
        ColumnSpec(
            id="exposed",
            label="Exposed",
            description=(
                "Reflects [`click.Parameter`'s `expose_value`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Parameter) "
                "constructor argument: whether the parsed value is forwarded to "
                "the command callback. Eager options like `--params` and "
                "`--help` typically run a callback and exit, so they are not "
                "exposed."
            ),
        ),
        ColumnSpec(
            id="allowed_in_conf",
            label="Allowed in conf?",
            description=(
                "Click Extra-specific: whether the parameter is reachable from a "
                "configuration file. Controlled by [`ParamStructure.excluded_params`]"
                "(#click_extra.param_tools.ParamStructure.excluded_params) and "
                "[`included_params`]"
                "(#click_extra.param_tools.ParamStructure.included_params). Empty "
                "when the CLI has no [`--config` option](config.md)."
            ),
        ),
        ColumnSpec(
            id="envvars",
            label="Env. vars.",
            description=(
                "Environment variables read for this parameter: the explicit "
                "[`click.Parameter`'s `envvar`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Parameter) "
                "plus the auto-resolved IDs documented in "
                "[Environment variables](envvar.md)."
            ),
        ),
        ColumnSpec(
            id="default",
            label="Default",
            description=(
                "Default value returned by [`click.Parameter.get_default()`]"
                "(https://click.palletsprojects.com/en/stable/api/"
                "#click.Parameter.get_default), rendered as its Python `repr()`."
            ),
        ),
        ColumnSpec(
            id="is_flag",
            label="Is flag",
            description=(
                "Reflects [`click.Option`'s `is_flag`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Option): "
                "whether the option behaves as a flag (no value taken from the "
                "command line). Empty for [`click.Argument`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Argument)."
            ),
        ),
        ColumnSpec(
            id="flag_value",
            label="Flag value",
            description=(
                "Reflects [`click.Option`'s `flag_value`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Option): "
                "the Python value substituted for the option when its flag is "
                "used. Defaults to `True` for boolean flags, can be any value "
                "for flag-value style options "
                "(like `@option('--upper', 'transform', flag_value='upper')`)."
            ),
        ),
        ColumnSpec(
            id="is_bool_flag",
            label="Is bool flag",
            description=(
                "Reflects `click.Option.is_bool_flag` (set internally by Click "
                "when `flag_value` is `True` or `False`): the option is a *true* "
                "boolean flag, as opposed to a flag-value style option."
            ),
        ),
        ColumnSpec(
            id="multiple",
            label="Multiple",
            description=(
                "Reflects [`click.Parameter`'s `multiple`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Parameter): "
                "the parameter can be repeated on the command line, collecting "
                "values into a tuple."
            ),
        ),
        ColumnSpec(
            id="nargs",
            label="Nargs",
            description=(
                "Reflects [`click.Parameter`'s `nargs`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Parameter): "
                "the number of CLI tokens the parameter consumes. `1` is the "
                "default; `-1` denotes a variadic argument."
            ),
        ),
        ColumnSpec(
            id="prompt",
            label="Prompt",
            description=(
                "Reflects [`click.Option`'s `prompt`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Option): "
                "the text shown to the user when the option is not provided on "
                "the command line. Empty when no prompt is configured."
            ),
        ),
        ColumnSpec(
            id="confirmation_prompt",
            label="Confirmation prompt",
            description=(
                "Reflects [`click.Option`'s `confirmation_prompt`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Option): "
                "whether the user is asked to enter the value twice for "
                "confirmation."
            ),
        ),
        ColumnSpec(
            id="value",
            label="Value",
            description=(
                "Current value of the parameter at invocation time, computed by "
                "[`click.Parameter.consume_value()`]"
                "(https://click.palletsprojects.com/en/stable/api/#click.Parameter) "
                "from the merged sources (CLI, environment, config file, default)."
            ),
        ),
        ColumnSpec(
            id="source",
            label="Source",
            description=(
                "Provenance of the resolved value: a [`click.core.ParameterSource`]"
                "(https://click.palletsprojects.com/en/stable/api/"
                "#click.core.ParameterSource) enum member such as `COMMANDLINE`, "
                "`ENVIRONMENT`, `DEFAULT_MAP`, or `DEFAULT`."
            ),
        ),
        ColumnSpec(
            id="config_file",
            label="Config file",
            optional=True,
            description=(
                "The configuration file the effective value was loaded from, "
                "when `Source` reports `DEFAULT_MAP`. With "
                "[`cascade=True`](config-discovery.md#cascading-configuration-files) "
                "several files are layered and this column names the one that "
                "won the parameter; with a single loaded file, every "
                "config-sourced parameter names that file. Empty for every "
                "other source and when no configuration file was loaded. "
                "Drawn by default when the `--config` option cascades, and "
                "opt-in otherwise, like `help`: paths are wide and stay "
                "redundant with `Source` until several files can take part."
            ),
        ),
    )
    """Rich column registry for the `--params` table.

    Each entry is a {class}`click_extra.columns.ColumnSpec` carrying the column's
    stable `id` (used by `--columns` and as structured-format key), its
    display `label`, and a MyST/Markdown `description` consumed by the
    documentation's auto-generated *Available columns* section. Iteration
    yields columns in canonical display order.
    """

    @classmethod
    def column_labels(cls) -> tuple[str, ...]:
        """Return just the display labels of {data}`TABLE_HEADERS` (in order)."""
        return tuple(col.label for col in cls.TABLE_HEADERS)

    @classmethod
    def column_ids(cls) -> tuple[str, ...]:
        """Return just the stable IDs of {data}`TABLE_HEADERS` (in order)."""
        return tuple(col.id for col in cls.TABLE_HEADERS)

    @classmethod
    def default_columns(cls) -> tuple[ColumnSpec, ...]:
        """Return the columns rendered when `--columns` asks for no projection.

        Every column but the {attr}`~click_extra.columns.ColumnSpec.optional` ones,
        which stay addressable by ID and out of the way until named.
        """
        return tuple(col for col in cls.TABLE_HEADERS if not col.optional)

    @classmethod
    def default_column_ids(cls) -> tuple[str, ...]:
        """Return the stable IDs of {meth}`default_columns` (in order)."""
        return tuple(col.id for col in cls.default_columns())

    @classmethod
    def default_column_labels(cls) -> tuple[str, ...]:
        """Return the display labels of {meth}`default_columns` (in order)."""
        return tuple(col.label for col in cls.default_columns())

    @classmethod
    def find_column(cls, column_id: str) -> ColumnSpec:
        """Return the {class}`~click_extra.columns.ColumnSpec` matching `column_id`.

        :raises KeyError: if no column has this ID. Convert it into a
            {class}`click.UsageError` before it reaches a user.
        """
        for col in cls.TABLE_HEADERS:
            if col.id == column_id:
                return col
        msg = f"Unknown column ID {column_id!r}"
        raise KeyError(msg)

    @classmethod
    def render_doc_table(cls) -> str:
        """Render {data}`TABLE_HEADERS` as a Markdown table for documentation.

        Used by the `show_params_columns_table` MyST substitution in
        `docs/conf.py` to feed the *Available columns* section of
        `docs/parameters.md`: editing a description here automatically
        rebuilds the docs table on the next `sphinx-build`.
        """
        return render_columns_markdown_table(cls.TABLE_HEADERS)

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        *,
        is_flag: bool = True,
        expose_value: bool = False,
        is_eager: bool = True,
        help: str = _(
            "Show all CLI parameters, their provenance, defaults and value, then exit.",
        ),
        **kwargs: Any,
    ) -> None:
        if not param_decls:
            param_decls = ("--params",)

        kwargs.setdefault("callback", self.print_params)

        self.excluded_params = frozenset()
        """Deactivates the blocking of any parameter."""

        self.included_params = None
        """No allowlist filter; show all parameters."""

        super().__init__(
            param_decls=param_decls,
            is_flag=is_flag,
            expose_value=expose_value,
            is_eager=is_eager,
            help=help,
            **kwargs,
        )

    def print_params(
        self,
        ctx: click.Context,
        param: click.Parameter,
        value: bool,
    ) -> None:
        """Introspect the current CLI and print its parameter metadata table.

        Thin wrapper over
        {func}`~click_extra.show_params.render_params_table`, the shared rendering core
        also driving `click-extra wrap --params` for foreign CLIs. The
        live invocation context carries everything the core needs: the captured
        {data}`~click_extra.context.RAW_ARGS` (attached by
        `Command`/`Group`) for value and source resolution, plus
        any sibling `--table-format` / `--columns` options.
        """
        # Exit early if the callback was processed but the option wasn't set.
        if not value:
            return

        # Load the configuration file first, so the value and source columns
        # reflect it even when this flag was processed ahead of the --config
        # option.
        ensure_config_loaded(ctx)

        # Warn when the live command is not a Command: without the captured
        # raw arguments, the value/source columns fall back to defaults.
        if context.get(ctx, context.RAW_ARGS) is None:
            logger.warning(
                f"Cannot extract parameter values: "
                f"{ctx.command} does not inherit from Command.",
            )

        # Hand over this class's own default column set, so a subclass widening
        # it (to draw an opt-in column on a CLI that exposes no --columns option
        # to reach it with) is honored. The base class's set is what the core
        # would have fallen back to anyway.
        render_params_table(ctx, default_columns=type(self).default_column_ids())
        ctx.exit()
