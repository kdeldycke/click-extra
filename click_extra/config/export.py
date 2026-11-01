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
"""Export the resolved configuration of a CLI as a configuration file.

Holds {class}`ExportConfigOption`, the `--export-config FORMAT` option, and
{func}`ensure_config_loaded`, which loads the configuration ahead of the
introspection flags that read it.
"""

from __future__ import annotations

import logging
from enum import Enum
from gettext import gettext as _

import click
from click import Choice, echo
from click._utils import UNSET

from .. import context
from .._utils import remove_blanks, set_nested
from ..output import MissingExtraError
from ..param_tools import (
    PARAM_PATH_SEP,
    ParamStructure,
    replay_raw_args,
    require_sibling_param,
    search_params,
)
from ..parameters import ExtraOption
from ..types import EnumChoice
from .formats import (
    SERIALIZABLE_FORMATS,
    ConfigFormat,
    _serialize_toml_with_unset,
    serialize_content,
)
from .option import ConfigOption

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any

logger = logging.getLogger(__name__)


_EXPORT_FORMAT_BY_TOKEN: dict[str, ConfigFormat] = {
    fmt.label.lower(): fmt for fmt in SERIALIZABLE_FORMATS
}
"""Mapping of `--export-config` choice tokens to their
{class}`~click_extra.config.formats.ConfigFormat`.

Built from {data}`~click_extra.config.formats.SERIALIZABLE_FORMATS`, so the
accepted tokens are exactly the formats
{func}`~click_extra.config.formats.serialize_content` can write: `toml`,
`yaml`, `json`, `json5`, `jsonc`, `hjson`, `xml` and `plist`.
"""


def ensure_config_loaded(ctx: click.Context) -> None:
    """Run the sibling `ConfigOption`'s resolution if it has not run yet.

    Click processes eager parameters given on the command line before eager
    parameters left at their defaults, so an explicitly-passed introspection
    flag (`--params`, `--export-config`) fires before the `--config`
    option had a chance to discover and load the configuration file. The views
    those flags render would then miss the configuration layer entirely,
    showing defaults where the user's config applies.

    Idempotent: does nothing when the config option already resolved (its
    callback stamps {data}`~click_extra.context.CONF_SOURCE` on the context
    even when no file was found), when the command has no config option, or
    when the option carries no callback.
    """
    if context.get(ctx, context.CONF_SOURCE, UNSET) is not UNSET:
        return
    config_option = search_params(ctx.command.params, ConfigOption)
    if config_option is None:
        return
    if config_option.callback is None:
        return
    opts = replay_raw_args(ctx)
    value, source = config_option.consume_value(ctx, opts)
    if value is UNSET:
        return
    # Record the provenance so the callback's explicit-vs-discovery logic sees
    # the same source as it would under normal parameter processing.
    if config_option.name is not None and source is not None:
        ctx.set_parameter_source(config_option.name, source)
    config_option.callback(ctx, config_option, value)


def _under_opaque_path(keys: Sequence[str], opaque_paths: frozenset[str]) -> bool:
    """Does the parameter reached by *keys* sit inside an opaque schema sub-tree?

    `keys` opens with the CLI name, which the opaque paths do not carry: they are
    relative to the app's configuration section.
    """
    if not opaque_paths:
        return False
    relative = PARAM_PATH_SEP.join(keys[1:])
    return any(
        relative == path or relative.startswith(f"{path}{PARAM_PATH_SEP}")
        for path in opaque_paths
    )


def _config_dump_value(param: click.Parameter, value: Any) -> Any:
    """Coerce a resolved parameter value into a config-serializable form.

    Produces what a user would write in a configuration file, so the dump
    round-trips back through `--config`:

    - native scalars (`str`, `int`, `float`, `bool`) and `None` pass
      through unchanged;
    - sequences are coerced element-wise into a `list`;
    - an {class}`~enum.Enum` member becomes its
      {class}`~click_extra.types.EnumChoice` token (or its value/name otherwise);
    - a scalar string whose parameter resolves to a numeric Python type is
      converted to that type, so `--count 7` dumps as `count = 7` rather than
      `count = "7"` (Click hands back raw strings for command-line and
      environment values, ahead of its own type conversion);
    - anything else (a {class}`~pathlib.Path`, a custom object) is stringified.
    """
    # A repeatable boolean flag collects occurrences of a toggle rather than
    # values, so none of them means unset, not an empty list of booleans.
    if (
        param.multiple
        and getattr(param, "is_bool_flag", False)
        and isinstance(value, (list, tuple))
        and not value
    ):
        value = None
    if value is None:
        # An unset multi-value parameter reads naturally as an empty list,
        # which also survives serialization in null-less formats like TOML.
        if ParamStructure.get_param_type(param) is list:
            return []
        return None
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_config_dump_value(param, item) for item in value]
    # bool is an int subclass: handle it before the numeric coercion below.
    if isinstance(value, bool):
        return value
    if isinstance(value, Enum):
        param_type = getattr(param, "type", None)
        if isinstance(param_type, EnumChoice):
            return param_type.get_choice_string(value)
        member_value = value.value
        if isinstance(member_value, (str, int, float, bool)):
            return member_value
        return value.name
    if isinstance(value, str):
        python_type = ParamStructure.get_param_type(param)
        if python_type is int or python_type is float:
            try:
                return python_type(value)
            except ValueError:
                return value
        return value
    if isinstance(value, (int, float)):
        return value
    return str(value)


class ExportConfigOption(ExtraOption):
    """A pre-configured option adding `--export-config FORMAT`.

    Resolves the CLI's current parameter values following Click's precedence
    chain (command line, then environment variables, then configuration file,
    then defaults), renders them as a configuration file in the requested format
    on `<stdout>`, and exits.

    ```{hint}
    Combine the flag with other options or environment variables to capture
    them in the generated configuration. For example,
    `mycli --verbosity DEBUG --export-config toml` emits a configuration whose
    `verbosity` is already set to `DEBUG`.
    ```

    Like {class}`~click_extra.config.option.ValidateConfigOption`, it relies on a
    sibling {class}`~click_extra.config.option.ConfigOption` to provide the
    parameter structure and the `excluded_params` / `included_params` filter, so
    the export contains exactly the parameters that can be loaded back from a
    configuration file.

    ```{note}
    The accepted formats are those
    {func}`~click_extra.config.formats.serialize_content` can write
    ({data}`~click_extra.config.formats.SERIALIZABLE_FORMATS`). `INI`, `SQLITE`,
    `ARGFILE` and `PYPROJECT_TOML` have no serializer and cannot be dumped.
    ```
    """

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        *,
        type: click.ParamType | Any = None,
        metavar: str = "FORMAT",
        is_eager: bool = True,
        expose_value: bool = False,
        help: str = _(
            "Export the configuration in the selected format to <stdout>, then exit.",
        ),
        **kwargs: Any,
    ) -> None:
        if not param_decls:
            param_decls = ("--export-config",)

        # Restrict the choice to the writable formats, addressed by their
        # lower-case token (`toml`, `json`, ...). A short `FORMAT` metavar
        # keeps the token list out of the one-line help while the full set still
        # surfaces in the Choice error message.
        if type is None:
            type = Choice(tuple(_EXPORT_FORMAT_BY_TOKEN), case_sensitive=False)

        kwargs.setdefault("callback", self.export_config)

        super().__init__(
            param_decls=param_decls,
            type=type,
            metavar=metavar,
            is_eager=is_eager,
            expose_value=expose_value,
            help=help,
            **kwargs,
        )

    def build_config(
        self,
        ctx: click.Context,
        config_option: ConfigOption,
    ) -> dict[str, Any]:
        """Resolve every config-eligible parameter into a dumpable tree.

        Walks the sibling {class}`~click_extra.config.option.ConfigOption`'s
        parameter structure, resolves each parameter's effective value by replaying
        {data}`~click_extra.context.RAW_ARGS` (falling back to defaults when the
        command did not capture them), drops the parameters
        {meth}`~click_extra.param_tools.ParamStructure.is_excluded` rejects, and
        layers the coerced values into the ``{cli-name: {param: value, ...}}``
        shape a configuration file uses. Parameter keys are rendered in their
        kebab-case spelling, the canonical presentation for configuration
        files; either spelling loads back to the same parameter.

        Parameters without a default are kept as `None` leaves so the export
        names every key a configuration file can set: serializers render them
        as `null`, except TOML which comments them out (see
        `_serialize_toml_with_unset`). Loading `null` back is harmless:
        {meth}`~click_extra.config.option.ConfigOption._install_default_map`
        cleans blank values out of the merged result.
        """
        opts = replay_raw_args(ctx)
        has_raw_args = context.get(ctx, context.RAW_ARGS) is not None
        if not has_raw_args:
            logger.warning(
                f"Cannot resolve parameter values: {ctx.command} does not "
                "inherit from Command; dumping defaults.",
            )

        tree: dict[str, Any] = {}
        for keys, target in config_option.walk_params():
            if config_option.is_excluded(PARAM_PATH_SEP.join(keys)):
                continue
            # A sub-tree the schema marks opaque holds app-owned data, not CLI
            # parameters: the loader hands it to the app's own validator, which
            # knows nothing of a subcommand sharing the namespace. Exporting
            # that subcommand's options there writes a file the same loader
            # refuses to read back.
            if _under_opaque_path(keys, config_option._opaque_paths):
                continue
            if has_raw_args:
                raw, _source = target.consume_value(ctx, opts)
                resolved = None if raw is UNSET else raw
            else:
                resolved = target.get_default(ctx)
            leaf = _config_dump_value(target, resolved)
            # Render the option under its kebab-case spelling, the canonical
            # presentation for configuration files (matching the CLI flags and
            # the TOML/YAML convention). Loading normalizes either spelling
            # back to the parameter ID. Section keys (the CLI and subcommand
            # names) are kept verbatim: the app-section lookup matches the
            # root exactly, and command names are displayed as invoked.
            set_nested(tree, (*keys[:-1], keys[-1].replace("_", "-")), leaf)

        return remove_blanks(tree, remove_none=False, remove_str=False)

    def export_config(
        self,
        ctx: click.Context,
        param: click.Parameter,
        value: str | None,
    ) -> None:
        """Render the resolved configuration to `<stdout>` and exit."""
        # Stay dormant during help rendering and shell completion, like Click's
        # own eager callbacks, so a typed `--export-config FORMAT` does not
        # export and exit mid-completion.
        if not value or ctx.resilient_parsing:
            return

        # Load the configuration file first, so the export reflects the full
        # precedence chain the docstring promises (config file included) even
        # when this flag was processed ahead of the --config option.
        ensure_config_loaded(ctx)

        fmt = _EXPORT_FORMAT_BY_TOKEN[value.lower()]
        config_option = require_sibling_param(ctx.command.params, param, ConfigOption)
        tree = self.build_config(ctx, config_option)

        try:
            # TOML cannot hold nulls: unset parameters are commented out.
            if fmt is ConfigFormat.TOML:
                output = _serialize_toml_with_unset(tree)
            elif fmt is ConfigFormat.PLIST:
                # plist has no null type either, and plistlib raises on None
                # values: unset parameters are dropped from the export.
                output = serialize_content(fmt, remove_blanks(tree, remove_str=False))
            else:
                output = serialize_content(fmt, tree)
        except ImportError:
            raise MissingExtraError(
                fmt.label.lower(), subject=f"{fmt} export"
            ) from None

        echo(output.rstrip("\n"))
        ctx.exit()
