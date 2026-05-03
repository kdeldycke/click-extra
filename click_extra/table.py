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
"""Collection of table rendering utilities."""

from __future__ import annotations

import csv
import json
import re
from enum import Enum
from functools import partial
from gettext import gettext as _
from io import StringIO

import click
import tabulate
from boltons.strutils import strip_ansi
from tabulate import DataRow, TableFormat as TabulateTableFormat

from . import EnumChoice, context, echo, style
from .parameters import ExtraOption

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import Any


tabulate.MIN_PADDING = 0
"""Neutralize spurious double-spacing in table rendering."""


tabulate._table_formats.update(  # type: ignore[attr-defined]
    {
        "aligned": TabulateTableFormat(
            lineabove=None,
            linebelowheader=None,
            linebetweenrows=None,
            linebelow=None,
            headerrow=DataRow("", " ", ""),
            datarow=DataRow("", " ", ""),
            padding=0,
            with_header_hide=None,
        ),
    },
)
"""Custom table formats registered with tabulate.

``aligned``
    A minimal format with single-space column separators and no borders or decorations.
    Similar to ``plain`` but more compact (single space instead of double space between
    columns). Useful for bar plugin output or other contexts requiring minimal formatting.
"""

# Patch the ``github`` format to support alignment colons in separator rows, matching
# the ``pipe`` format. Backport of https://github.com/astanin/python-tabulate/pull/410
_fmts = tabulate._table_formats  # type: ignore[attr-defined]
_fmts["github"] = _fmts["pipe"]

# Backport ``colon_grid`` for tabulate < 0.10 by aliasing it to ``grid``. Lets
# downstream distributions ship click-extra without bumping tabulate globally.
if "colon_grid" not in _fmts:
    _fmts["colon_grid"] = _fmts["grid"]


class TableFormat(Enum):
    """Enumeration of supported table formats.

    Hard-coded to be in alphabetical order. Content of this enum is checked in
    unit tests.

    .. warning::
        The ``youtrack`` format is missing in action from any official JetBrains
        documentation. It `will be removed in python-tabulate v0.11
        <https://github.com/astanin/python-tabulate/issues/375>`_.
    """

    ALIGNED = "aligned"
    ASCIIDOC = "asciidoc"
    COLON_GRID = "colon-grid"
    CSV = "csv"
    CSV_EXCEL = "csv-excel"
    CSV_EXCEL_TAB = "csv-excel-tab"
    CSV_UNIX = "csv-unix"
    DOUBLE_GRID = "double-grid"
    DOUBLE_OUTLINE = "double-outline"
    FANCY_GRID = "fancy-grid"
    FANCY_OUTLINE = "fancy-outline"
    GITHUB = "github"
    GRID = "grid"
    HEAVY_GRID = "heavy-grid"
    HEAVY_OUTLINE = "heavy-outline"
    HJSON = "hjson"
    HTML = "html"
    JIRA = "jira"
    JSON = "json"
    JSON5 = "json5"
    JSONC = "jsonc"
    LATEX = "latex"
    LATEX_BOOKTABS = "latex-booktabs"
    LATEX_LONGTABLE = "latex-longtable"
    LATEX_RAW = "latex-raw"
    MEDIAWIKI = "mediawiki"
    MIXED_GRID = "mixed-grid"
    MIXED_OUTLINE = "mixed-outline"
    MOINMOIN = "moinmoin"
    ORGTBL = "orgtbl"
    OUTLINE = "outline"
    PIPE = "pipe"
    PLAIN = "plain"
    PRESTO = "presto"
    PRETTY = "pretty"
    PSQL = "psql"
    ROUNDED_GRID = "rounded-grid"
    ROUNDED_OUTLINE = "rounded-outline"
    RST = "rst"
    SIMPLE = "simple"
    SIMPLE_GRID = "simple-grid"
    SIMPLE_OUTLINE = "simple-outline"
    TEXTILE = "textile"
    TOML = "toml"
    TSV = "tsv"
    UNSAFEHTML = "unsafehtml"
    VERTICAL = "vertical"
    XML = "xml"
    YAML = "yaml"
    YOUTRACK = "youtrack"

    def __str__(self):
        return self.name.lower().replace("_", "-")

    @property
    def is_markup(self) -> bool:
        """Whether this format is a markup rendering.

        Markup formats have ANSI color codes stripped from their output by default.
        Use the ``--color`` flag to preserve them.
        """
        return self in MARKUP_FORMATS


MARKUP_FORMATS = frozenset(
    {
        TableFormat.ASCIIDOC,
        TableFormat.CSV,
        TableFormat.CSV_EXCEL,
        TableFormat.CSV_EXCEL_TAB,
        TableFormat.CSV_UNIX,
        TableFormat.GITHUB,
        TableFormat.HJSON,
        TableFormat.HTML,
        TableFormat.JIRA,
        TableFormat.JSON,
        TableFormat.JSON5,
        TableFormat.JSONC,
        TableFormat.LATEX,
        TableFormat.LATEX_BOOKTABS,
        TableFormat.LATEX_LONGTABLE,
        TableFormat.LATEX_RAW,
        TableFormat.MEDIAWIKI,
        TableFormat.MOINMOIN,
        TableFormat.ORGTBL,
        TableFormat.PIPE,
        TableFormat.RST,
        TableFormat.TEXTILE,
        TableFormat.TOML,
        TableFormat.TSV,
        TableFormat.UNSAFEHTML,
        TableFormat.XML,
        TableFormat.YAML,
        TableFormat.YOUTRACK,
    },
)
"""Subset of table formats that are considered as markup rendering."""


DEFAULT_FORMAT = TableFormat.ROUNDED_OUTLINE
"""Default table format, if none is specified."""

RECORD_KEY = "record"
"""Key used for each record in structured formats that require named containers
(TOML ``[[record]]``, XML ``<record>``)."""

XML_ROOT_KEY = "records"
"""Root element name for XML table output."""

SERIALIZATION_FORMATS = frozenset(
    {
        TableFormat.HJSON,
        TableFormat.JSON,
        TableFormat.JSON5,
        TableFormat.JSONC,
        TableFormat.TOML,
        TableFormat.XML,
        TableFormat.YAML,
    },
)
"""Structured serialization formats whose renderers escape raw ESC bytes, making
post-render ``strip_ansi()`` ineffective."""


def _get_csv_dialect(table_format: TableFormat | None = None) -> str:
    """Extract, validate and normalize CSV dialect ID from format.

    Defaults to ``excel`` rendering, like in Python's csv module.
    """
    dialect = "excel"

    # Extract dialect ID from table format, if any.
    if table_format:
        format_id = table_format.value
        assert format_id.startswith("csv")
        parts = format_id.split("-", 1)
        assert parts[0] == "csv"
        if len(parts) > 1:
            dialect = parts[1]

    csv.get_dialect(dialect)  # Validate dialect.
    return dialect


def _render_csv(
    table_data: Sequence[Sequence[str | None]],
    headers: Sequence[str | None] | None = None,
    table_format: TableFormat | None = None,
    **kwargs,
) -> str:
    """Render a table in CSV format.

    .. note::
        StringIO is used to capture CSV output in memory. `Hard-coded to default to
        UTF-8 <https://github.com/python/cpython/blob/9291095/Lib/_pyio.py#L2652>`_.
    """
    defaults = {"dialect": _get_csv_dialect(table_format)}
    defaults.update(kwargs)

    with StringIO(newline="") as output:
        writer = csv.writer(output, **defaults)  # type: ignore[arg-type]
        if headers:
            writer.writerow(headers)
        writer.writerows(table_data)
        return output.getvalue()


def _rows_as_dicts(
    table_data: Sequence[Sequence[str | None]],
    headers: Sequence[str | None] | None = None,
) -> list[dict[str, str | None]] | list[list[str | None]]:
    """Convert table data to a list of dicts keyed by headers.

    Falls back to a list of lists when no headers are provided.
    """
    if headers:
        return [{str(k): v for k, v in zip(headers, row)} for row in table_data]
    return [list(row) for row in table_data]


def _render_json(
    table_data: Sequence[Sequence[str | None]],
    headers: Sequence[str | None] | None = None,
    **kwargs,
) -> str:
    """Render a table as JSON."""
    data = _rows_as_dicts(table_data, headers)
    defaults: dict = {"ensure_ascii": False, "indent": 2}
    defaults.update(kwargs)
    return json.dumps(data, **defaults) + "\n"


def _render_yaml(
    table_data: Sequence[Sequence[str | None]],
    headers: Sequence[str | None] | None = None,
    **kwargs,
) -> str:
    """Render a table as YAML.

    Requires the ``pyyaml`` package (installable via the ``[yaml]`` extra).
    """
    import yaml

    data = _rows_as_dicts(table_data, headers)
    defaults: dict = {"allow_unicode": True, "default_flow_style": False}
    defaults.update(kwargs)
    return str(yaml.dump(data, **defaults))


def _render_toml(
    table_data: Sequence[Sequence[str | None]],
    headers: Sequence[str | None] | None = None,
    **kwargs,
) -> str:
    """Render a table as TOML using array-of-tables syntax.

    ``None`` values are omitted (TOML has no null type). Requires the ``tomlkit``
    package (installable via the ``[toml]`` extra).
    """
    import tomlkit

    aot = tomlkit.aot()
    for row in table_data:
        t = tomlkit.table()
        if headers:
            for key, value in zip(headers, row):
                if value is not None and key is not None:
                    t.add(key, value)
        else:
            for i, value in enumerate(row):
                if value is not None:
                    t.add(str(i), value)
        aot.append(t)

    doc = tomlkit.document()
    doc.add(RECORD_KEY, aot)
    return tomlkit.dumps(doc)


def _render_hjson(
    table_data: Sequence[Sequence[str | None]],
    headers: Sequence[str | None] | None = None,
    **kwargs,
) -> str:
    """Render a table as HJSON.

    Requires the ``hjson`` package (installable via the ``[hjson]`` extra).
    """
    import hjson

    data = _rows_as_dicts(table_data, headers)
    defaults: dict = {"ensure_ascii": False}
    defaults.update(kwargs)
    return str(hjson.dumps(data, **defaults)) + "\n"


def _render_xml(
    table_data: Sequence[Sequence[str | None]],
    headers: Sequence[str | None] | None = None,
    **kwargs,
) -> str:
    """Render a table as XML.

    ``None`` values are omitted. Requires the ``xmltodict`` package (installable
    via the ``[xml]`` extra).
    """
    import xmltodict

    def _xml_safe_name(name: str) -> str:
        """Replace characters invalid in XML element names."""
        safe = "".join(c if c.isalnum() or c in "_.-" else "_" for c in name)
        return safe.lstrip("0123456789.-") or "_"

    if headers:
        records = [
            {
                _xml_safe_name(k): v
                for k, v in zip(headers, row)
                if v is not None and k is not None
            }
            for row in table_data
        ]
    else:
        records = [
            {str(i): v for i, v in enumerate(row) if v is not None}
            for row in table_data
        ]

    defaults: dict = {
        "pretty": True,
        "encoding": "unicode",
        "full_document": False,
    }
    defaults.update(kwargs)
    result: str = xmltodict.unparse({XML_ROOT_KEY: {RECORD_KEY: records}}, **defaults)
    return result + "\n"


def _render_vertical(
    table_data: Sequence[Sequence[str | None]],
    headers: Sequence[str | None] | None = None,
    sep_character: str = "*",
    sep_length: int = 27,
    **kwargs,
) -> str:
    """Re-implements ``cli-helpers``'s vertical table layout.

    .. note::
        See `cli-helpers source code for reference
        <https://github.com/dbcli/cli_helpers/blob/v2.7.0/cli_helpers/tabular_output/vertical_table_adapter.py>`_.

    .. caution::
        This layout is `hard-coded to 27 asterisks to separate rows
        <https://github.com/dbcli/cli_helpers/blob/c34ae9f/cli_helpers/tabular_output/vertical_table_adapter.py#L34>`_,
        as in the original implementation.
    """
    if not headers:
        headers = []

    # Calculate header lengths and pad headers in one pass.
    header_length = [0 if h is None else len(h) for h in headers]
    max_length = max(header_length) if header_length else 0
    padded_headers = ["" if h is None else h.ljust(max_length) for h in headers]

    table_lines = []
    sep = sep_character * sep_length
    for index, row in enumerate(table_data):
        table_lines.append(f"{sep}[ {index + 1}. row ]{sep}")
        for cell_label, cell_value in zip(padded_headers, row):
            # Like other formats, render None as an empty string.
            cell_value = "" if cell_value is None else cell_value
            table_lines.append(f"{cell_label} | {cell_value}")
    return "\n".join(table_lines)


_GFM_SEPARATOR_RE = re.compile(r"^\|[-: |]+\|$")
"""Matches a GFM table separator row (e.g. ``|:---|:---|``)."""


def _pad_gfm_separator(text: str) -> str:
    """Add space padding to GFM table separator rows.

    Tabulate's ``pipe`` format fills padding positions with dashes in separator
    rows (``|:---|``), while mdformat normalizes them to spaces (``| :-- |``).
    This post-processing step matches mdformat's canonical form, preventing an
    infinite formatting cycle between table-generating and markdown-formatting
    tools.

    .. note::
        Proposed upstream at https://github.com/astanin/python-tabulate/pull/426
        If merged, this workaround can be removed.
    """
    lines = []
    for line in text.split("\n"):
        if not _GFM_SEPARATOR_RE.fullmatch(line):
            lines.append(line)
            continue
        parts = line.split("|")
        new_parts = [parts[0]]
        for cell in parts[1:-1]:
            stripped = cell.strip()
            if (
                not stripped
                or "-" not in stripped
                or not all(c in "-:" for c in stripped)
            ):
                new_parts.append(cell)
                continue
            # Already padded.
            if cell.startswith(" ") and cell.endswith(" "):
                new_parts.append(cell)
                continue
            left = ":" if stripped.startswith(":") else ""
            right = ":" if stripped.endswith(":") else ""
            dash_count = stripped.count("-")
            new_dashes = max(dash_count - 2, 1)
            new_parts.append(f" {left}{'-' * new_dashes}{right} ")
        new_parts.append(parts[-1])
        lines.append("|".join(new_parts))
    return "\n".join(lines)


def _render_tabulate(
    table_data: Sequence[Sequence[str | None]],
    headers: Sequence[str | None] | None = None,
    table_format: TableFormat | None = None,
    **kwargs,
) -> str:
    """Render a table with ``tabulate``.

    Default format is ``TableFormat.ROUNDED_OUTLINE``.
    """
    if not headers:
        headers = ()
    if not table_format:
        table_format = DEFAULT_FORMAT
    defaults = {
        "disable_numparse": True,
        "numalign": None,
        # tabulate()'s  format ID uses underscores instead of dashes.
        "tablefmt": table_format.value.replace("-", "_"),
    }
    defaults.update(kwargs)
    result = tabulate.tabulate(table_data, headers, **defaults)  # type: ignore[arg-type]
    # Normalize separator rows for GFM-compatible formats so that mdformat
    # treats the output as already canonical and does not re-pad it.
    if table_format in (TableFormat.GITHUB, TableFormat.PIPE):
        result = _pad_gfm_separator(result)
    return result


def _select_table_funcs(
    table_format: TableFormat | None = None,
) -> tuple[Callable[..., str], Callable[[str], None]]:
    """Returns the rendering and print functions for the given ``table_format``.

    For all formats other than CSV, we relying on Click's ``echo()`` as the print
    function, to benefit from its sensitivity to global colorization settings. Thanks
    to this the ``--color``/``--no-color`` option is automatically supported.

    For CSV formats we returns the Python standard ``print()`` function, to preserve
    line terminations and avoid extra line returns.
    """
    print_func = echo
    match table_format:
        case (
            TableFormat.CSV
            | TableFormat.CSV_EXCEL
            | TableFormat.CSV_EXCEL_TAB
            | TableFormat.CSV_UNIX
        ):
            print_func = partial(print, end="")
            return partial(_render_csv, table_format=table_format), print_func
        case TableFormat.HJSON:
            print_func = partial(print, end="")
            return _render_hjson, print_func
        case TableFormat.JSON | TableFormat.JSON5 | TableFormat.JSONC:
            print_func = partial(print, end="")
            return _render_json, print_func
        case TableFormat.TOML:
            print_func = partial(print, end="")
            return _render_toml, print_func
        case TableFormat.XML:
            print_func = partial(print, end="")
            return _render_xml, print_func
        case TableFormat.YAML:
            print_func = partial(print, end="")
            return _render_yaml, print_func
        case TableFormat.VERTICAL:
            return _render_vertical, print_func
        case _:
            return partial(_render_tabulate, table_format=table_format), print_func


def render_table(
    table_data: Sequence[Sequence[str | None]],
    headers: Sequence[str | None] | None = None,
    table_format: TableFormat | None = None,
    sort_key: Callable[[Sequence[str | None]], Any] | None = None,
    **kwargs,
) -> str:
    """Render a table and return it as a string.

    :param sort_key: Optional callable passed to :py:func:`sorted` as the ``key``
        argument. When provided, rows are sorted before rendering.
    """
    if sort_key is not None:
        table_data = sorted(table_data, key=sort_key)
    render_func, _ = _select_table_funcs(table_format)
    return render_func(table_data, headers, **kwargs)


def _strip_ansi_cells(
    table_data: Sequence[Sequence[str | None]],
    headers: Sequence[str | None] | None = None,
) -> tuple[list[list[str | None]], Sequence[str | None] | None]:
    """Strip ANSI escape codes from all string cells and headers."""
    cleaned_data: list[list[str | None]] = [
        [strip_ansi(v) if isinstance(v, str) else v for v in row] for row in table_data
    ]
    cleaned_headers = (
        [strip_ansi(h) if isinstance(h, str) else h for h in headers]
        if headers
        else headers
    )
    return cleaned_data, cleaned_headers


def print_table(
    table_data: Sequence[Sequence[str | None]],
    headers: Sequence[str | None] | None = None,
    table_format: TableFormat | None = None,
    sort_key: Callable[[Sequence[str | None]], Any] | None = None,
    **kwargs,
) -> None:
    """Render a table and print it to the console.

    For markup formats, ANSI color codes are stripped from cell values before
    rendering unless ``--color`` is explicitly set.

    :param sort_key: Optional callable passed to :py:func:`sorted` as the ``key``
        argument. When provided, rows are sorted before rendering.
    """
    if sort_key is not None:
        table_data = sorted(table_data, key=sort_key)
    # Strip ANSI codes from cell data before rendering for markup formats.
    # Pre-render stripping is necessary because some renderers (JSON, YAML) escape
    # raw ESC bytes, making post-render strip_ansi() ineffective.
    if table_format and table_format.is_markup:
        ctx = click.get_current_context(silent=True)
        # Only preserve ANSI codes when --color was explicitly passed on the
        # command line. The default True from ColorOption should not prevent
        # stripping.
        color_explicit = False
        if ctx is not None:
            source = ctx.get_parameter_source("color")
            color_explicit = (
                ctx.color is True and source == click.core.ParameterSource.COMMANDLINE
            )
        if not color_explicit:
            table_data, headers = _strip_ansi_cells(table_data, headers)

    render_func, print_func = _select_table_funcs(table_format)
    try:
        print_func(render_func(table_data, headers, **kwargs))
    except ImportError:
        assert table_format is not None
        raise SystemExit(f"Error: {_missing_extra_message(table_format)}") from None


def _missing_extra_message(
    table_format: TableFormat,
    package: str = "click-extra",
) -> str:
    """Build a user-friendly error message for a missing optional dependency."""
    extra = table_format.value
    return (
        f"{extra} output requires an optional dependency."
        f" Install it with: pip install {package}[{extra}]"
    )


def _strip_none(data: Any) -> Any:
    """Recursively drop ``None`` values from dicts.

    Needed for formats without a null type (TOML, XML).
    """
    if isinstance(data, dict):
        return {k: _strip_none(v) for k, v in data.items() if v is not None}
    if isinstance(data, (list, tuple)):
        return [_strip_none(v) for v in data]
    return data


def _strip_none_and_wrap(data: Any) -> dict:
    """Strip ``None`` values and wrap bare lists under the ``record`` key.

    Shared preprocessing for TOML and XML, which have no null type and require a
    top-level mapping.
    """
    stripped = _strip_none(data)
    if isinstance(stripped, list):
        return {RECORD_KEY: stripped}
    assert isinstance(stripped, dict)
    return stripped


def serialize_data(
    data: Any,
    table_format: TableFormat,
    *,
    default: Callable | None = None,
    root_element: str = XML_ROOT_KEY,
    **kwargs,
) -> str:
    """Serialize arbitrary Python data to a structured format.

    Unlike :py:func:`render_table` which expects tabular rows and headers, this
    function accepts any JSON-compatible data structure (dicts, lists, nested
    combinations) and serializes it to the requested format.

    Only formats in :py:data:`SERIALIZATION_FORMATS` are supported.

    :param data: Arbitrary data to serialize (dicts, lists, scalars).
    :param table_format: Target serialization format.
    :param default: Fallback serializer for types not natively supported. Defaults
        to :py:func:`str`, so :py:class:`~pathlib.Path` and similar types are
        stringified automatically. Set to a custom callable for different behavior.
    :param root_element: Root element name for XML output.
    :param kwargs: Extra keyword arguments forwarded to the underlying serializer
        (e.g. ``sort_keys``, ``indent`` for JSON).
    :raises ValueError: If the format is not a serialization format.
    """
    if table_format not in SERIALIZATION_FORMATS:
        msg = f"Unsupported serialization format: {table_format}"
        raise ValueError(msg)

    clean = _apply_default(data, default if default is not None else str)

    match table_format:
        case TableFormat.JSON | TableFormat.JSON5 | TableFormat.JSONC:
            return (
                json.dumps(clean, **{"ensure_ascii": False, "indent": 2, **kwargs})
                + "\n"
            )

        case TableFormat.HJSON:
            import hjson

            return str(hjson.dumps(clean, **{"ensure_ascii": False, **kwargs})) + "\n"

        case TableFormat.TOML:
            import tomlkit

            stripped = _strip_none_and_wrap(clean)
            doc = tomlkit.document()
            for k, v in stripped.items():
                doc.add(k, v)
            return tomlkit.dumps(doc)

        case TableFormat.YAML:
            import yaml

            return str(
                yaml.dump(
                    clean,
                    **{"allow_unicode": True, "default_flow_style": False, **kwargs},
                )
            )

        case TableFormat.XML:
            import xmltodict

            stripped = _strip_none_and_wrap(clean)
            result: str = xmltodict.unparse(
                {root_element: stripped},
                **{
                    "pretty": True,
                    "encoding": "unicode",
                    "full_document": False,
                    **kwargs,
                },
            )
            return result + "\n"

        case _:
            msg = f"Unhandled serialization format: {table_format}"
            raise NotImplementedError(msg)


def _apply_default(data: Any, default: Callable) -> Any:
    """Recursively apply a ``default`` callback to non-native types.

    Walks dicts, lists, and tuples. For any other type, calls ``default(obj)``
    which should return a JSON-serializable value or raise :py:class:`TypeError`.
    """
    if isinstance(data, dict):
        return {k: _apply_default(v, default) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [_apply_default(v, default) for v in data]
    if isinstance(data, (str, int, float, bool)) or data is None:
        return data
    return default(data)


def print_data(
    data: Any,
    table_format: TableFormat,
    *,
    default: Callable | None = None,
    root_element: str = XML_ROOT_KEY,
    package: str = "click-extra",
    **kwargs,
) -> None:
    """Serialize arbitrary Python data and print it to the console.

    Wraps :py:func:`serialize_data` with user-friendly error handling for missing
    optional dependencies.

    :param data: Arbitrary data to serialize.
    :param table_format: Target serialization format.
    :param default: Fallback serializer for custom types. Defaults to :py:func:`str`.
    :param root_element: Root element name for XML output.
    :param package: Package name for install instructions in error messages.
    :param kwargs: Extra keyword arguments forwarded to the underlying serializer.
    """
    try:
        output = serialize_data(
            data,
            table_format,
            default=default,
            root_element=root_element,
            **kwargs,
        )
    except ImportError:
        raise SystemExit(
            f"Error: {_missing_extra_message(table_format, package)}"
        ) from None
    echo(output, color=False)


class TableFormatOption(ExtraOption):
    """A pre-configured option that is adding a ``--table-format`` flag to select
    the rendering style of a table.

    The selected table format ID is made available in the context in
    ``ctx.meta[click_extra.context.TABLE_FORMAT]``, and two helper methods
    are added to the context:
    - ``ctx.render_table(table_data, headers, **kwargs)``: renders and returns
      the table as a string,
    - ``ctx.print_table(table_data, headers, **kwargs)``: renders and prints
      the table to the console.

    Where:
    - ``table_data`` is a 2-dimensional iterable of iterables for rows and cells values,
    - ``headers`` is a list of string to be used as column headers,
    - ``**kwargs`` are any extra keyword arguments supported by the underlying table
      formatting function.
    """

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        type=EnumChoice(TableFormat),
        default=DEFAULT_FORMAT,
        expose_value=False,
        is_eager=True,
        help=_("Rendering style of tables."),
        **kwargs,
    ) -> None:
        if not param_decls:
            param_decls = ("--table-format",)

        kwargs.setdefault("callback", self.init_formatter)

        super().__init__(
            param_decls=param_decls,
            type=type,
            default=default,
            expose_value=expose_value,
            help=help,
            is_eager=is_eager,
            **kwargs,
        )

    def init_formatter(
        self,
        ctx: click.Context,
        param: click.Parameter,
        table_format: TableFormat | None,
    ) -> None:
        """Save in the context: ``table_format``, ``render_table`` & ``print_table``."""
        ctx.meta[context.TABLE_FORMAT] = table_format

        ctx.render_table = partial(  # type: ignore[attr-defined]
            render_table,
            table_format=table_format,
        )

        ctx.print_table = partial(  # type: ignore[attr-defined]
            print_table,
            table_format=table_format,
        )


def _column_sort_key(
    header_defs: Sequence[tuple[str, str | None]],
    sort_columns: Sequence[str] | None = None,
    cell_key: Callable[[str | None], Any] | None = None,
) -> Callable[[Sequence[str | None]], tuple]:
    """Build a multi-column sort key from header definitions.

    Specified sort columns are moved to the front of the comparison order;
    remaining columns provide tie-breaking in their natural (header) order.
    Each cell is passed through ``cell_key`` before comparison. Defaults to
    ANSI-stripped, case-folded string comparison.
    """
    if cell_key is None:

        def cell_key(v):
            return strip_ansi(v).casefold() if v else ""

    column_count = len(header_defs)
    sort_order = list(range(column_count))

    if sort_columns:
        col_index = {col_id: i for i, (_, col_id) in enumerate(header_defs) if col_id}
        # Move specified columns to the front in reverse order so the first
        # specified column ends up at position 0.
        for sort_col in reversed(sort_columns):
            if sort_col in col_index:
                idx = col_index[sort_col]
                sort_order.remove(idx)
                sort_order.insert(0, idx)

    def key_func(row: Sequence[str | None]) -> tuple:
        return tuple(cell_key(row[i]) for i in sort_order)

    return key_func


def print_sorted_table(
    header_defs: Sequence[tuple[str, str | None]],
    table_data: Sequence[Sequence[str | None]],
    sort_columns: Sequence[str] | None = None,
    table_format: TableFormat | None = None,
    *,
    cell_key: Callable[[str | None], Any] | None = None,
    **kwargs,
) -> None:
    """Sort and print a table using named column definitions.

    ``header_defs`` is an ordered sequence of ``(label, column_id)`` tuples. Columns
    with ``column_id=None`` are not selectable for sorting but still participate in
    tie-breaking.

    :param header_defs: Column definitions as ``(label, column_id)`` pairs.
    :param table_data: Rows of cell values.
    :param sort_columns: Column IDs to sort by, in priority order. Falls back to
        natural header order.
    :param table_format: Rendering format.
    :param cell_key: Per-cell comparison key. Defaults to ANSI-stripped, case-folded
        string comparison.
    """
    if not table_data:
        return

    headers = tuple(style(label, bold=True) for label, _ in header_defs)
    sort_key = _column_sort_key(header_defs, sort_columns, cell_key)
    print_table(
        table_data=table_data,
        headers=headers,
        table_format=table_format,
        sort_key=sort_key,
        **kwargs,
    )


class SortByOption(ExtraOption):
    """A ``--sort-by`` option whose choices are derived from column definitions.

    Stores the selected column IDs in ``ctx.meta[click_extra.context.SORT_BY]`` and replaces
    ``ctx.print_table`` with :py:func:`print_sorted_table` so that table output is
    automatically sorted. The option accepts ``multiple=True``, so users can repeat
    ``--sort-by`` to define a multi-column sort priority.

    .. code-block:: python

        @command
        @table_format_option
        @sort_by_option(
            ("Package ID", "package_id"),
            ("Name", "package_name"),
            ("Manager", "manager_id"),
            ("Version", None),
        )
        @pass_context
        def my_cmd(ctx):
            ctx.print_table(header_defs, rows)
    """

    def __init__(
        self,
        *header_defs: tuple[str, str | None],
        param_decls: Sequence[str] | None = None,
        default: str | Sequence[str] | None = None,
        expose_value: bool = False,
        cell_key: Callable[[str | None], Any] | None = None,
        help: str = _("Sort table by this column. Repeat to set priority."),
        **kwargs,
    ) -> None:
        if not param_decls:
            param_decls = ("--sort-by",)

        self.header_defs = header_defs
        self.cell_key = cell_key
        sortable_ids = [col_id for _, col_id in header_defs if col_id]

        # Normalize default to a tuple for multiple mode.
        if not default:
            default = (sortable_ids[0],) if sortable_ids else ()
        elif isinstance(default, str):
            default = (default,)

        kwargs.setdefault("callback", self.init_sort)

        super().__init__(
            param_decls=param_decls,
            type=click.Choice(sortable_ids, case_sensitive=False),
            default=default,
            expose_value=expose_value,
            help=help,
            multiple=True,
            **kwargs,
        )

    def init_sort(
        self,
        ctx: click.Context,
        param: click.Parameter,
        sort_columns: tuple[str, ...],
    ) -> None:
        """Store sort columns and override ``ctx.print_table`` with sorted variant."""
        ctx.meta[context.SORT_BY] = sort_columns

        table_format = ctx.meta.get(context.TABLE_FORMAT)
        ctx.print_table = partial(  # type: ignore[attr-defined]
            print_sorted_table,
            table_format=table_format,
            sort_columns=sort_columns,
            cell_key=self.cell_key,
        )
