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
import re
from dataclasses import dataclass
from enum import Enum
from functools import cache, partial
from gettext import gettext as _
from io import StringIO

import click
from boltons.strutils import strip_ansi
from click import echo

from . import context
from .config.formats import ConfigFormat, serialize_content
from .parameters import ExtraOption, missing_extra_message
from .styling import ansi_to_html, ansi_to_jira, ansi_to_latex, ansi_to_textile
from .types import EnumChoice, MultiChoice

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence
    from typing import Any


@cache
def _setup_tabulate() -> None:
    """Import ``tabulate``, apply Click Extra's patches, and register its formats.

    ``tabulate`` is a comparatively heavy dependency, only needed when a table
    is actually rendered through it (the CSV, structured and serialization
    formats use other backends). Importing and configuring it here, on the first
    render rather than at module load, keeps it off the default import path of
    every CLI built with Click Extra. This mirrors the optional
    serialization-format imports deferred elsewhere in this module.

    .. note::
        ``@cache`` ensures the import and the one-time monkeypatches below run
        only once. Do not hoist ``import tabulate`` back to module scope.
    """
    import tabulate
    from tabulate import DataRow, TableFormat as TabulateTableFormat

    # Neutralize spurious double-spacing in table rendering.
    tabulate.MIN_PADDING = 0

    fmts = tabulate._table_formats  # type: ignore[attr-defined]

    # Register the custom ``aligned`` format: a minimal format with single-space
    # column separators and no borders or decorations. Similar to ``plain`` but
    # more compact (single space instead of double space between columns). Useful
    # for bar plugin output or other contexts requiring minimal formatting.
    fmts["aligned"] = TabulateTableFormat(
        lineabove=None,
        linebelowheader=None,
        linebetweenrows=None,
        linebelow=None,
        headerrow=DataRow("", " ", ""),
        datarow=DataRow("", " ", ""),
        padding=0,
        with_header_hide=None,
    )

    # Patch the ``github`` format to support alignment colons in separator rows,
    # matching the ``pipe`` format. Backport of
    # https://github.com/astanin/python-tabulate/pull/410
    fmts["github"] = fmts["pipe"]

    # Backport ``colon_grid`` for tabulate < 0.10 by aliasing it to ``grid``.
    # Lets downstream distributions ship click-extra without bumping tabulate
    # globally.
    if "colon_grid" not in fmts:
        fmts["colon_grid"] = fmts["grid"]


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

        ANSI codes never reach a markup rendering raw: they are either
        translated to the format's native styling (see :attr:`supports_styling`)
        or stripped from cell values. Forcing ``--color`` on the command line
        preserves them as-is in the markup formats without styling support.
        """
        return self in MARKUP_FORMATS

    @property
    def supports_styling(self) -> bool:
        """Whether ANSI codes are translated to this format's native styling.

        See :data:`~click_extra.table.STYLED_FORMATS` for the registry, and
        the rationale behind each excluded markup format.
        """
        return self in STYLED_FORMATS


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


STYLED_FORMATS: dict[TableFormat, Callable[[str], str]] = {
    TableFormat.HTML: ansi_to_html,
    TableFormat.JIRA: ansi_to_jira,
    TableFormat.LATEX: ansi_to_latex,
    TableFormat.LATEX_BOOKTABS: ansi_to_latex,
    TableFormat.LATEX_LONGTABLE: ansi_to_latex,
    TableFormat.LATEX_RAW: ansi_to_latex,
    TableFormat.MEDIAWIKI: ansi_to_html,
    TableFormat.TEXTILE: ansi_to_textile,
    TableFormat.UNSAFEHTML: ansi_to_html,
}
"""Markup formats able to express styles natively, mapped to their ANSI translator.

:func:`print_table` runs the rendered output of these formats through their
translator, converting the ANSI codes carried by cells and headers into the
format's own styling markup: inline-CSS HTML ``<span>``\\ s for the HTML pair
and MediaWiki (which accepts embedded HTML), Textile ``%{...}`` spans, Jira
``{color:...}`` macros, and xcolor-based LaTeX macros.

.. note::
    Translation happens on the rendered output, not on cell values, on
    purpose. tabulate escapes cell content for some formats (``html``
    escapes HTML entities, non-raw ``latex`` variants escape TeX specials)
    while ANSI sequences pass through unscathed, so pre-render translation
    would get its markup mangled by those escaping rules. Post-render
    injection also keeps column-width computation on the ANSI text, which
    tabulate measures correctly.

.. important::
    Every markup format absent from this registry keeps the historical
    behavior: ANSI codes are stripped from cells before rendering. The
    verdict, format by format:

    - ``asciidoc``: no portable inline styling. Colors require
      stylesheet-defined roles or ``+++`` passthrough blocks tied to the
      HTML backend, both lossy and non-standard.
    - ``csv``, ``csv-excel``, ``csv-excel-tab``, ``csv-unix``, ``tsv``:
      data interchange formats, with no concept of styling.
    - ``github``, ``pipe``: GitHub sanitizes inline ``style`` attributes
      from rendered Markdown, so translated HTML spans would not display any
      color there. Raw ANSI can still be forced with ``--color`` for
      terminal Markdown viewers which support escape sequences.
    - ``hjson``, ``json``, ``json5``, ``jsonc``, ``toml``, ``xml``,
      ``yaml``: structured serialization formats meant for programmatic
      consumption. Styling is presentation, not data.
    - ``moinmoin``: MoinMoin wiki markup has no standard inline color
      syntax, and embedded HTML is disabled by default.
    - ``orgtbl``: Org-mode has emphasis markers but no inline color markup.
    - ``rst``: reStructuredText needs custom roles backed by a stylesheet
      for inline color; there is no standard inline syntax.
    - ``youtrack``: undocumented by JetBrains and `scheduled for removal in
      python-tabulate 0.11
      <https://github.com/astanin/python-tabulate/issues/375>`_.
"""


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
    return serialize_content(
        ConfigFormat.JSON, _rows_as_dicts(table_data, headers), **kwargs
    )


def _render_yaml(
    table_data: Sequence[Sequence[str | None]],
    headers: Sequence[str | None] | None = None,
    **kwargs,
) -> str:
    """Render a table as YAML.

    Requires the ``pyyaml`` package (installable via the ``[yaml]`` extra).
    """
    return serialize_content(
        ConfigFormat.YAML, _rows_as_dicts(table_data, headers), **kwargs
    )


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

    return serialize_content(ConfigFormat.TOML, {RECORD_KEY: aot}, **kwargs)


def _render_hjson(
    table_data: Sequence[Sequence[str | None]],
    headers: Sequence[str | None] | None = None,
    **kwargs,
) -> str:
    """Render a table as HJSON.

    Requires the ``hjson`` package (installable via the ``[hjson]`` extra).
    """
    return serialize_content(
        ConfigFormat.HJSON, _rows_as_dicts(table_data, headers), **kwargs
    )


def _render_xml(
    table_data: Sequence[Sequence[str | None]],
    headers: Sequence[str | None] | None = None,
    **kwargs,
) -> str:
    """Render a table as XML.

    ``None`` values are omitted. Requires the ``xmltodict`` package (installable
    via the ``[xml]`` extra).
    """

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

    return serialize_content(
        ConfigFormat.XML, {XML_ROOT_KEY: {RECORD_KEY: records}}, **kwargs
    )


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
"""Matches a GFM table separator row (like ``|:---|:---|``)."""


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
        # tabulate()'s format ID uses underscores instead of dashes.
        "tablefmt": table_format.value.replace("-", "_"),
    }
    defaults.update(kwargs)
    _setup_tabulate()
    import tabulate

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

    For all formats other than CSV and structured serializations, we rely on Click's
    ``echo()`` as the print function, to benefit from its sensitivity to global
    colorization settings. Thanks to this the ``--color``/``--no-color`` option is
    automatically supported.

    For CSV and structured serialization formats we return the Python standard
    ``print()`` function, to preserve line terminations and avoid extra line returns.
    """
    # Structured serializations and CSV variants embed their own line terminations,
    # so they bypass echo() (which would add an extra line return).
    is_csv = table_format is not None and table_format.value.startswith("csv")
    if table_format in SERIALIZATION_FORMATS or is_csv:
        print_func: Callable[[str], None] = partial(print, end="")
    else:
        print_func = echo

    match table_format:
        case (
            TableFormat.CSV
            | TableFormat.CSV_EXCEL
            | TableFormat.CSV_EXCEL_TAB
            | TableFormat.CSV_UNIX
        ):
            return partial(_render_csv, table_format=table_format), print_func
        case TableFormat.HJSON:
            return _render_hjson, print_func
        case TableFormat.JSON | TableFormat.JSON5 | TableFormat.JSONC:
            return _render_json, print_func
        case TableFormat.TOML:
            return _render_toml, print_func
        case TableFormat.XML:
            return _render_xml, print_func
        case TableFormat.YAML:
            return _render_yaml, print_func
        case TableFormat.VERTICAL:
            return _render_vertical, print_func
        case _:
            return partial(_render_tabulate, table_format=table_format), print_func


def _split_header_defs(
    headers: Sequence[str | ColumnSpec | tuple[str, str | None] | None] | None,
) -> tuple[
    Sequence[str | None] | None,
    tuple[tuple[str | None, str | None], ...] | None,
]:
    """Split header definitions into render labels and sortable column defs.

    ``headers`` entries may be plain strings (a label carrying no column ID),
    :class:`ColumnSpec` instances or ``(label, column_id)`` pairs. Returns the
    labels to render and the ``(label, column_id)`` definitions, the latter
    ``None`` when no entry carries a column ID (nothing to sort on).
    """
    if headers is None:
        return None, None
    labels: list[str | None] = []
    defs: list[tuple[str | None, str | None]] = []
    for header in headers:
        label: str | None
        col_id: str | None
        if isinstance(header, ColumnSpec):
            label, col_id = header.label, header.id
        elif isinstance(header, (tuple, list)):
            label, col_id = header
        else:
            label, col_id = header, None
        labels.append(label)
        defs.append((label, col_id))
    if not any(col_id for _, col_id in defs):
        return labels, None
    return labels, tuple(defs)


def _context_sort_key(
    header_defs: Sequence[tuple[str | None, str | None]],
) -> Callable[[Sequence[str | None]], tuple] | None:
    """Build a sort key from the ``--sort-by`` selection of the current context.

    Reads :data:`click_extra.context.SORT_BY`, which ``ctx.meta`` shares
    across the whole context tree, so a selection made on a parent group is
    visible from the subcommand doing the printing. Returns ``None`` outside
    any Click context, when no selection is active, or when the table carries
    none of the selected columns.
    """
    ctx = click.get_current_context(silent=True)
    if ctx is None:
        return None
    sort_columns = context.get(ctx, context.SORT_BY)
    if not sort_columns:
        return None
    return column_sort_key(header_defs, sort_columns)


def _resolve_table_inputs(
    table_data: Sequence[Sequence[str | None]],
    headers: Sequence[str | ColumnSpec | tuple[str, str | None] | None] | None,
    sort_key: Callable[[Sequence[str | None]], Any] | None,
) -> tuple[Sequence[Sequence[str | None]], Sequence[str | None] | None]:
    """Split header definitions and apply the resolved row sort.

    The shared preamble of :func:`render_table` and :func:`print_table`: the
    render labels are split from the sortable column definitions, the active
    ``--sort-by`` selection is resolved when no explicit *sort_key* is given,
    and rows are sorted when a key applies.
    """
    labels, header_defs = _split_header_defs(headers)
    if sort_key is None and header_defs:
        sort_key = _context_sort_key(header_defs)
    if sort_key is not None:
        table_data = sorted(table_data, key=sort_key)
    return table_data, labels


def render_table(
    table_data: Sequence[Sequence[str | None]],
    headers: Sequence[str | ColumnSpec | tuple[str, str | None] | None] | None = None,
    table_format: TableFormat | None = None,
    sort_key: Callable[[Sequence[str | None]], Any] | None = None,
    **kwargs,
) -> str:
    """Render a table and return it as a string.

    ``headers`` entries carrying a column ID (:class:`ColumnSpec` instances or
    ``(label, column_id)`` pairs) plug the table into the active ``--sort-by``
    selection: when no explicit ``sort_key`` is given, rows sort by the
    selected columns this table carries, and keep their original order when it
    carries none. See :func:`column_sort_key` for the exact semantics.

    :param sort_key: Optional callable passed to :py:func:`sorted` as the ``key``
        argument. When provided, rows are sorted before rendering.
    """
    table_data, headers = _resolve_table_inputs(table_data, headers, sort_key)
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


def _color_disabled() -> bool:
    """Whether color output is disabled for the current invocation.

    Reads the resolved ``ctx.color`` tri-state, which subcommand contexts
    inherit from their parents. Only an explicit ``False`` (``--no-color``,
    ``NO_COLOR``, ``--color=never``) disables styling: the ``None`` (auto)
    default keeps it, as a markup document carries its own rendering and no
    TTY is involved.
    """
    ctx = click.get_current_context(silent=True)
    return ctx is not None and ctx.color is False


def _color_forced() -> bool:
    """Whether ``--color`` was explicitly forced on the command line.

    Walks up the context chain, so a color option declared on a parent group is
    honored from the subcommand doing the printing. The default set by a
    :class:`~click_extra.color.ColorOption` does not count as forced: only an
    explicit command line flag does.
    """
    ctx: click.Context | None = click.get_current_context(silent=True)
    while ctx is not None:
        if ctx.get_parameter_source("color") == click.core.ParameterSource.COMMANDLINE:
            return ctx.color is True
        ctx = ctx.parent
    return False


def print_table(
    table_data: Sequence[Sequence[str | None]],
    headers: Sequence[str | ColumnSpec | tuple[str, str | None] | None] | None = None,
    table_format: TableFormat | None = None,
    sort_key: Callable[[Sequence[str | None]], Any] | None = None,
    **kwargs,
) -> None:
    """Render a table and print it to the console.

    ``headers`` entries carrying a column ID (:class:`ColumnSpec` instances or
    ``(label, column_id)`` pairs) plug the table into the active ``--sort-by``
    selection: when no explicit ``sort_key`` is given, rows sort by the
    selected columns this table carries, and keep their original order when it
    carries none. See :func:`column_sort_key` for the exact semantics.

    ANSI codes carried by cell values and headers depend on the format:

    - Markup formats with native styling support (see
      :data:`~click_extra.table.STYLED_FORMATS`) get them translated to the
      format's own styling markup, unless color output is disabled
      (``--no-color``, ``NO_COLOR``, ...).
    - Other markup formats get them stripped from cell values before
      rendering, unless ``--color`` is explicitly forced on the command line.
    - Plain-text formats keep them raw, and defer to ``echo()``'s sensitivity
      to the global colorization settings.

    :param sort_key: Optional callable passed to :py:func:`sorted` as the ``key``
        argument. When provided, rows are sorted before rendering.
    """
    table_data, headers = _resolve_table_inputs(table_data, headers, sort_key)

    ansi_translator: Callable[[str], str] | None = None
    if table_format:
        if table_format.supports_styling and not _color_disabled():
            # Translation to native styling runs on the rendered output, not
            # on cells: see the STYLED_FORMATS docstring for the rationale.
            ansi_translator = STYLED_FORMATS[table_format]
        elif table_format.is_markup and not _color_forced():
            # Strip ANSI codes from cell data before rendering. Pre-render
            # stripping is necessary because some renderers (JSON, YAML)
            # escape raw ESC bytes, making post-render strip_ansi()
            # ineffective.
            table_data, headers = _strip_ansi_cells(table_data, headers)

    render_func, print_func = _select_table_funcs(table_format)
    try:
        output = render_func(table_data, headers, **kwargs)
    except ImportError:
        assert table_format is not None
        raise SystemExit(f"Error: {_missing_extra_message(table_format)}") from None
    if ansi_translator is not None:
        output = ansi_translator(output)
    print_func(output)


def _missing_extra_message(
    table_format: TableFormat,
    package: str = "click-extra",
) -> str:
    """Build a user-friendly error message for a missing optional dependency."""
    return missing_extra_message(
        table_format.value, package=package, subject=f"{table_format.value} output"
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

    Only formats in :py:data:`~click_extra.table.SERIALIZATION_FORMATS` are
    supported.

    :param data: Arbitrary data to serialize (dicts, lists, scalars).
    :param table_format: Target serialization format.
    :param default: Fallback serializer for types not natively supported. Defaults
        to :py:class:`str`, so :py:class:`~pathlib.Path` and similar types are
        stringified automatically. Set to a custom callable for different behavior.
    :param root_element: Root element name for XML output.
    :param kwargs: Extra keyword arguments forwarded to the underlying serializer
        (like ``sort_keys`` or ``indent`` for JSON).
    :raises ValueError: If the format is not a serialization format.
    """
    if table_format not in SERIALIZATION_FORMATS:
        msg = f"Unsupported serialization format: {table_format}"
        raise ValueError(msg)

    clean = _apply_default(data, default if default is not None else str)

    match table_format:
        case TableFormat.JSON | TableFormat.JSON5 | TableFormat.JSONC:
            return serialize_content(ConfigFormat.JSON, clean, **kwargs)

        case TableFormat.HJSON:
            return serialize_content(ConfigFormat.HJSON, clean, **kwargs)

        case TableFormat.TOML:
            return serialize_content(
                ConfigFormat.TOML, _strip_none_and_wrap(clean), **kwargs
            )

        case TableFormat.YAML:
            return serialize_content(ConfigFormat.YAML, clean, **kwargs)

        case TableFormat.XML:
            return serialize_content(
                ConfigFormat.XML, {root_element: _strip_none_and_wrap(clean)}, **kwargs
            )

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
    :param default: Fallback serializer for custom types. Defaults to :py:class:`str`.
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
    ``ctx.meta[click_extra.context.TABLE_FORMAT]``, where the
    :meth:`~click_extra.context.Context.render_table` and
    :meth:`~click_extra.context.Context.print_table` context methods pick it
    up as their default format. ``ctx.meta`` is shared along the context
    chain, so declaring this option on a group makes the selected format reach
    every subcommand:

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
        """Save the resolved ``table_format`` in the context's shared ``meta``.

        The :meth:`~click_extra.context.Context.render_table` and
        :meth:`~click_extra.context.Context.print_table` context methods read
        it back at call time.
        """
        if ctx.resilient_parsing:
            return

        context.set(ctx, context.TABLE_FORMAT, table_format)

        # Foreign click/cloup commands run with a plain click.Context, which
        # lacks the enhanced Context.render_table/print_table methods: give
        # them bound equivalents as instance attributes so this option stays a
        # drop-in on any Click CLI.
        if not isinstance(ctx, context.Context):
            ctx.render_table = partial(  # type: ignore[attr-defined]
                render_table,
                table_format=table_format,
            )
            ctx.print_table = partial(  # type: ignore[attr-defined]
                print_table,
                table_format=table_format,
            )


def _row_sort_key(
    sort_order: Sequence[int],
    cell_key: Callable[[str | None], Any] | None = None,
) -> Callable[[Sequence[str | None]], tuple]:
    """Build a row sort key comparing cells at the ``sort_order`` positions.

    Each cell is passed through ``cell_key`` before comparison. Defaults to
    ANSI-stripped, case-folded string comparison, with ``None`` and empty
    cells collating as the empty string.
    """
    if cell_key is None:

        def cell_key(v):
            return strip_ansi(v).casefold() if v else ""

    def key_func(row: Sequence[str | None]) -> tuple:
        return tuple(cell_key(row[i]) for i in sort_order)

    return key_func


def column_sort_key(
    header_defs: Sequence[ColumnSpec | tuple[str | None, str | None]],
    sort_columns: Sequence[str] | None = None,
    cell_key: Callable[[str | None], Any] | None = None,
) -> Callable[[Sequence[str | None]], tuple] | None:
    """Build a row sort key from the ``sort_columns`` a table actually carries.

    ``header_defs`` describes the rendered columns: :class:`ColumnSpec`
    instances or ``(label, column_id)`` tuples, with ``column_id=None`` for
    columns that cannot be sorted on. The requested ``sort_columns`` the table
    carries drive the comparison first, de-duplicated and in request order;
    the remaining columns follow in their natural left-to-right order for
    tie-breaking.

    Returns ``None`` when the table carries none of the requested columns,
    signalling that rows should keep their original order. This is what lets
    one ``--sort-by`` selection apply across subcommands rendering
    heterogeneous tables: each table sorts by the requested fields it knows,
    and a table knowing none of them is left untouched.
    """
    defs = tuple(_normalize_column_def(c) for c in header_defs)
    col_index = {col_id: i for i, (_, col_id) in enumerate(defs) if col_id}
    primaries = [
        col_index[col_id]
        for col_id in dict.fromkeys(sort_columns or ())
        if col_id in col_index
    ]
    if not primaries:
        return None
    sort_order = (
        *primaries,
        *(i for i in range(len(defs)) if i not in primaries),
    )
    return _row_sort_key(sort_order, cell_key)


def _column_sort_key(
    header_defs: Sequence[tuple[str, str | None]],
    sort_columns: Sequence[str] | None = None,
    cell_key: Callable[[str | None], Any] | None = None,
) -> Callable[[Sequence[str | None]], tuple]:
    """Like :func:`column_sort_key`, but always sorts.

    When none of the ``sort_columns`` is carried by ``header_defs`` (or none
    is requested), rows still sort, comparing every column in natural
    left-to-right order. This is the key :class:`SortByOption` publishes on
    the context (``click_extra.context.TABLE_SORT_KEY``) when its column
    definitions are known at declaration time.
    """
    key = column_sort_key(header_defs, sort_columns, cell_key)
    if key is None:
        key = _row_sort_key(range(len(header_defs)), cell_key)
    return key


@dataclass(frozen=True, slots=True)
class ColumnSpec:
    """Rich description of a single column in a rendered table.

    Three fields, all required-by-convention even though ``description`` defaults to
    empty so quick prototypes do not have to write a sentence for every column:

    - ``id``: stable, snake_case identifier used by ``--columns`` to address the column,
      to key structured-format serializations, and to thread state through
      :data:`click_extra.context.COLUMNS`.
    - ``label``: the human-readable header shown at the top of the rendered table.
    - ``description``: a MyST/Markdown blurb describing what the column represents.
      Used to auto-generate the column reference in the documentation.

    .. note::
        Frozen + slots: instances are immutable and lightweight. Tuples of
        ``ColumnSpec`` are intended to be defined as module-level constants
        (like :data:`click_extra.parameters.ShowParamsOption.TABLE_HEADERS`).
    """

    id: str
    """Stable, snake_case identifier addressing this column from CLI flags and code."""

    label: str
    """Human-readable header label rendered at the top of the table."""

    description: str = ""
    """MyST/Markdown description of what the column carries.

    Used to auto-generate the *Available columns* section in the docs via the
    ``show_params_columns_table`` MyST substitution. Plain text without inline
    markup is fine: links and emphasis are optional sugar."""


def render_columns_markdown_table(columns: Iterable[ColumnSpec]) -> str:
    """Render an iterable of :class:`ColumnSpec` as a 2-column Markdown table.

    Output shape::

        | Column | Description |
        | :--- | :--- |
        | `Label` | description |
        ...

    Suitable for inlining into MyST documents via ``myst_substitutions`` so the
    *Available columns* reference can be auto-generated from a single source of
    truth.
    """
    lines = ["| Column | Description |", "| :--- | :--- |"]
    for col in columns:
        # Pipe characters in descriptions would break the markdown row: escape them.
        description = col.description.replace("|", "\\|")
        lines.append(f"| `{col.label}` | {description} |")
    return "\n".join(lines)


def select_columns(
    columns: Sequence[ColumnSpec],
    selected_ids: Sequence[str] | None,
) -> tuple[ColumnSpec, ...]:
    """Filter and reorder ``columns`` according to ``selected_ids``.

    Returns ``columns`` unchanged when ``selected_ids`` is falsy (no projection).
    Otherwise yields the matching :class:`ColumnSpec` in the order ``selected_ids``
    specifies, SQL-``SELECT``-style. Raises ``KeyError`` for unknown IDs so the
    caller can convert it into a :class:`click.UsageError`.
    """
    if not selected_ids:
        return tuple(columns)
    by_id = {c.id: c for c in columns}
    return tuple(by_id[col_id] for col_id in selected_ids)


def select_row(
    row: Mapping[str, Any],
    selected_ids: Sequence[str] | None,
    canonical_ids: Sequence[str],
) -> tuple:
    """Build a positional row by reading cells from ``row`` in the selection order.

    Falls back to ``canonical_ids`` when ``selected_ids`` is empty / unset, so the
    row preserves its canonical column order in the absence of any user selection.
    """
    ids = selected_ids if selected_ids else canonical_ids
    return tuple(row[col_id] for col_id in ids)


class ColumnsType(MultiChoice):
    """Column-flavored alias of :class:`click_extra.types.MultiChoice`.

    Pins the comma separator and case-sensitive matching (column IDs are
    snake_case identifiers, not free-form strings), and renames the metavar
    fallback to ``COLUMNS`` instead of the generic ``MULTI``. The
    ``accepted_ids`` constructor keyword is a column-flavored alias of
    ``MultiChoice.choices``.
    """

    name = "columns"

    def __init__(self, accepted_ids: Sequence[str] = ()) -> None:
        super().__init__(choices=accepted_ids, separator=",", case_sensitive=True)


class ColumnsOption(ExtraOption):
    """A ``--columns`` option that lets users restrict and reorder table columns.

    Accepts a comma-separated list of column IDs, SQL-``SELECT``-style:

    .. code-block:: shell-session

        $ my-cli --columns id,spec,value --params

    The selection is stored in
    :data:`ctx.meta[click_extra.context.COLUMNS] <click_extra.context.COLUMNS>` and
    consumed by table-rendering callbacks (like
    :class:`click_extra.parameters.ShowParamsOption`) to project rows + headers
    before rendering.

    Pass ``columns=`` at construction time with the column registry the option
    should advertise: the help text then lists the accepted IDs and the default
    selection, and the callback validates the user input against that registry
    so unknown IDs fail fast with a :class:`click.UsageError`. Without
    ``columns=``, the option stays generic: it parses any IDs and leaves
    validation to the downstream consumer.

    Empty / unset means *render every column in canonical order*: the default
    behavior, indistinguishable from not passing ``--columns`` at all.
    """

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        columns: Sequence[ColumnSpec] | None = None,
        type=None,
        default: Sequence[str] | None = (),
        expose_value: bool = False,
        is_eager: bool = True,
        help: str = _(
            "Restrict and reorder table columns, SQL SELECT-style. "
            "Comma-separated list of column IDs. Default: all columns in "
            "canonical order.",
        ),
        **kwargs,
    ) -> None:
        if not param_decls:
            param_decls = ("--columns",)

        self.columns: tuple[ColumnSpec, ...] = tuple(columns) if columns else ()
        """Column registry this option advertises and validates against (may be empty)."""

        # When the registry is known, expose the IDs in the metavar (parallel to
        # ``click.Choice`` showing ``[a|b|c]``) so the help screen enumerates the
        # accepted values inline rather than burying them in the description.
        if type is None:
            type = ColumnsType(accepted_ids=tuple(c.id for c in self.columns))

        kwargs.setdefault("callback", self.init_columns)

        super().__init__(
            param_decls=param_decls,
            type=type,
            default=default,
            expose_value=expose_value,
            help=help,
            is_eager=is_eager,
            **kwargs,
        )

    def init_columns(
        self,
        ctx: click.Context,
        param: click.Parameter,
        columns: tuple[str, ...],
    ) -> None:
        """Store the selected column IDs on the context for later projection.

        Validation of the IDs against the registry happens inside
        :meth:`~click_extra.types.MultiChoice.convert`, before this callback runs,
        so this just
        threads the parsed selection onto the context.
        """
        if ctx.resilient_parsing:
            return
        context.set(ctx, context.COLUMNS, tuple(columns) if columns else ())


def _normalize_column_def(column: ColumnSpec | tuple[str | None, str | None] | str):
    """Coerce a column definition to a ``(label, column_id)`` tuple.

    Accepts a :class:`ColumnSpec` (so a registry can be shared with
    ``--columns``), a raw ``(label, column_id)`` tuple, or a bare column ID
    string, which declares a sortable field untied to any table layout (its
    label is ``None``).
    """
    if isinstance(column, ColumnSpec):
        return (column.label, column.id)
    if isinstance(column, str):
        return (None, column)
    return tuple(column)


class SortByOption(ExtraOption):
    """A ``--sort-by`` option whose choices are derived from column definitions.

    Stores the selected column IDs in ``ctx.meta[click_extra.context.SORT_BY]``
    and publishes the derived row sort key in
    ``ctx.meta[click_extra.context.TABLE_SORT_KEY]``, which ``ctx.print_table``
    picks up so that table output is automatically sorted, without changing its
    ``(table_data, headers)`` call contract. The option accepts
    ``multiple=True``, so users can repeat ``--sort-by`` to define a
    multi-column sort priority.

    Column definitions may be ``ColumnSpec`` instances or raw
    ``(label, column_id)`` tuples, passed positionally or via the ``columns=``
    keyword. Passing a ``ColumnSpec`` registry via ``columns=`` lets the same
    tuple drive both ``ColumnsOption`` (``--columns``) and ``--sort-by``, so
    the two options stay in sync from a single source of truth.

    .. code-block:: python

        COLUMNS = (
            ColumnSpec("package_id", "Package ID"),
            ColumnSpec("package_name", "Name"),
            ColumnSpec("manager_id", "Manager"),
        )


        @command
        @table_format_option
        @columns_option(columns=COLUMNS)
        @sort_by_option(columns=COLUMNS)
        @pass_context
        def my_cmd(ctx):
            ctx.print_table(rows, [col.label for col in COLUMNS])

    Definitions may instead be bare column ID strings, declaring a
    **field vocabulary** untied to any single table layout. This fits a
    ``--sort-by`` declared once on a group whose subcommands render
    heterogeneous tables: no sort key is published since no layout is known up
    front. The selection is resolved per table by :func:`print_table`, from
    the column IDs its headers carry — each table sorts by the selected fields
    it knows (remaining columns breaking ties left to right) and keeps its
    original row order when it knows none.

    .. code-block:: python

        @group
        @sort_by_option("package_id", "package_name", "manager_id")
        def my_cli():
            pass


        @my_cli.command
        def installed():
            print_table(rows, [("Package ID", "package_id"), ("Manager", "manager_id")])


        @my_cli.command
        def managers():
            print_table(rows, [("Manager", "manager_id"), ("Path", None)])
    """

    def __init__(
        self,
        *header_defs: ColumnSpec | tuple[str, str | None] | str,
        param_decls: Sequence[str] | None = None,
        columns: Sequence[ColumnSpec | tuple[str, str | None] | str] | None = None,
        default: str | Sequence[str] | None = None,
        expose_value: bool = False,
        cell_key: Callable[[str | None], Any] | None = None,
        help: str = _("Sort table by this column. Repeat to set priority."),
        **kwargs,
    ) -> None:
        if not param_decls:
            param_decls = ("--sort-by",)

        # Accept a shared ``columns=`` registry (the same ``ColumnSpec`` tuple
        # passed to ``--columns``) or positional definitions. Each entry may be a
        # ``ColumnSpec``, a raw ``(label, column_id)`` tuple, or a bare column ID
        # string.
        if columns is not None and header_defs:
            msg = "Pass column definitions positionally or via columns=, not both."
            raise TypeError(msg)
        raw_defs = columns if columns is not None else header_defs
        self.header_defs = tuple(_normalize_column_def(c) for c in raw_defs)
        self.cell_key = cell_key

        # Bare column IDs declare a table-less field vocabulary; labeled
        # definitions describe one table's layout. Mixing both would leave the
        # labeled part baking a sort over a layout the vocabulary part denies.
        labeled = [d for d in self.header_defs if d[0] is not None]
        if labeled and len(labeled) != len(self.header_defs):
            msg = "Pass either bare column IDs or labeled column definitions, not both."
            raise TypeError(msg)

        self.field_vocabulary = bool(self.header_defs) and not labeled
        """Whether definitions are bare column IDs, untied to any table layout.

        In this mode :meth:`init_sort` only publishes the selection on the
        context: the sort is resolved per table at :func:`print_table` time.
        """

        sortable_ids = [col_id for _, col_id in self.header_defs if col_id]

        # Normalize default to a tuple for multiple mode. ``None`` derives the
        # first sortable ID; an explicit empty sequence declares no default
        # sort, so bare invocations keep the original row order.
        if default is None:
            default = (sortable_ids[0],) if sortable_ids else ()
        elif isinstance(default, str):
            default = (default,)
        else:
            default = tuple(default)

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
        """Publish the row sort key on the context's shared ``meta``.

        Builds the sort key from this option's column definitions and the
        selected ``sort_columns``, then stores it under
        ``ctx.meta[click_extra.context.TABLE_SORT_KEY]``, where
        ``ctx.print_table`` picks it up. The call contract is the same sorted
        or not: ``ctx.print_table(table_data, headers)``.

        In field-vocabulary mode no table layout is known at declaration time,
        so no key is published: only the selection lands on the context
        (``ctx.meta`` is shared with every subcommand), resolved per table by
        :func:`print_table` from the column IDs its headers carry.
        """
        if ctx.resilient_parsing:
            return

        context.set(ctx, context.SORT_BY, sort_columns)

        if self.field_vocabulary:
            return

        sort_key = _column_sort_key(self.header_defs, sort_columns, self.cell_key)
        context.set(ctx, context.TABLE_SORT_KEY, sort_key)

        # Same foreign-command escape hatch as TableFormatOption.init_formatter:
        # rebind the instance attribute with the sort baked in, since a plain
        # click.Context has no meta-reading print_table method.
        if not isinstance(ctx, context.Context):
            ctx.print_table = partial(  # type: ignore[attr-defined]
                print_table,
                table_format=context.get(ctx, context.TABLE_FORMAT),
                sort_key=sort_key,
            )
