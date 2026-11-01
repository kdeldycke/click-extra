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
"""Render tables for a terminal, a markup document or a serialization format.

```{todo}
Drop the `github` patch of `_setup_tabulate` once a python-tabulate release
ships [astanin/python-tabulate#410](https://github.com/astanin/python-tabulate/pull/410):
`github` then marks column alignment in its separator row, as `pipe` does.
```

```{todo}
Delete `_pad_gfm_separator` once a python-tabulate release ships
[astanin/python-tabulate#426](https://github.com/astanin/python-tabulate/pull/426):
the separator rows of `pipe` and `github` then carry the padding `mdformat`
writes.
```
"""

from __future__ import annotations

import csv
import os
import re
import shutil
from contextvars import ContextVar
from enum import Enum
from functools import cache, partial
from io import StringIO
from itertools import zip_longest
from types import SimpleNamespace

import click
from click import echo

from . import context
from ._utils import AUTO
from .ansi import strip_ansi
from .columns import ColumnSpec
from .config.formats import ConfigFormat, serialize_content
from .layout import cell_width, wrap_ansi
from .output import MissingExtraError
from .styling import (
    ansi_to_html,
    ansi_to_jira,
    ansi_to_latex,
    ansi_to_textile,
)

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from types import ModuleType
    from typing import Any, Final, TypeAlias

    from .columns import ColumnWidth

    MaxColumnWidths = Sequence[ColumnWidth] | ColumnWidth
    """Width limits of a table: one entry per column, or a scalar for all of them."""

    THeader: TypeAlias = "str | ColumnSpec | None"
    """One entry of a table's `headers`: a plain label, or a
    {class}`~click_extra.columns.ColumnSpec`."""

    TColumnDef: TypeAlias = "ColumnSpec | str"
    """One column definition of {class}`~click_extra.table_options.SortByOption`
    or {func}`~click_extra.table_options.column_sort_key`.

    A {class}`~click_extra.columns.ColumnSpec`, or a bare column ID.
    """


@cache
def _setup_tabulate() -> ModuleType:
    """Import `tabulate`, apply Click Extra's patches, register its formats, and
    return the module.

    `tabulate` is a comparatively heavy dependency, only needed when a table is
    rendered through it (the CSV, vertical and serialization formats use other
    backends). Importing and configuring it on the first render keeps it off the
    import path of every CLI built with Click Extra.

    ```{note}
    `@cache` runs the import and the monkeypatches below once. Do not hoist
    `import tabulate` back to module scope.
    ```
    """
    # Deferred import: keeps tabulate and wcwidth off the startup path of every CLI.
    import tabulate
    from tabulate import DataRow, TableFormat as TabulateTableFormat
    from wcwidth import wcwidth as char_width

    # Neutralize spurious double-spacing in table rendering.
    tabulate.MIN_PADDING = 0

    # tabulate pads cells with its own import of wcwidth. Point it at the
    # measure Click Extra uses everywhere else, so a table's padding and its
    # wrapping cannot disagree on an emoji-presentation sequence: see
    # _paints_wider_than_it_advances(), and _LAID_OUT_FOR_TERMINAL for the
    # markup renderings the terminal never sees.
    # Only the string entry point changes: the emoji-presentation rule is one
    # about a sequence, which a single character cannot carry.
    tabulate.wcwidth = SimpleNamespace(  # type: ignore[attr-defined]
        wcswidth=_terminal_wcswidth,
        wcwidth=char_width,
    )

    fmts = tabulate._table_formats  # type: ignore[attr-defined]

    # Register the custom `aligned` format: a minimal format with single-space
    # column separators and no borders or decorations. Similar to `plain` but
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

    # Mark column alignment with colons in the separator row of `github`, as
    # `pipe` does.
    fmts["github"] = fmts["pipe"]

    return tabulate


class TableFormat(Enum):
    """Enumeration of supported table formats.

    Hard-coded to be in alphabetical order. Content of this enum is checked in
    unit tests.

    ```{warning}
    The `youtrack` format is missing in action from any official JetBrains
    documentation. It [will be removed in python-tabulate v0.11](https://github.com/astanin/python-tabulate/issues/375).
    ```
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

    def __str__(self) -> str:
        return self.value

    @property
    def is_markup(self) -> bool:
        """Whether this format is a markup rendering.

        ANSI codes never reach a markup rendering raw: they are either
        translated to the format's native styling (see {attr}`supports_styling`)
        or stripped from cell values. Forcing `--color` on the command line
        preserves them as-is in the markup formats without styling support.
        """
        return self in MARKUP_FORMATS

    @property
    def supports_styling(self) -> bool:
        """Whether ANSI codes are translated to this format's native styling.

        See {data}`~click_extra.table.STYLED_FORMATS` for the registry.
        """
        return self in STYLED_FORMATS

    @property
    def is_wrappable(self) -> bool:
        """Whether this format renders a cell wrapped onto several lines.

        See {data}`~click_extra.table.WRAPPABLE_FORMATS` for the registry, and
        the rationale behind each excluded format.
        """
        return self in WRAPPABLE_FORMATS


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

{func}`print_table` runs the rendered output of these formats through their
translator, converting the ANSI codes carried by cells and headers into the
format's own styling markup: inline-CSS HTML `<span>`\\ s for the HTML pair
and MediaWiki (which accepts embedded HTML), Textile ``%{...}`` spans, Jira
``{color:...}`` macros, and xcolor-based LaTeX macros.

```{note}
Translation happens on the rendered output, not on cell values, on
purpose. tabulate escapes cell content for some formats (`html`
escapes HTML entities, non-raw `latex` variants escape TeX specials)
while ANSI sequences pass through unscathed, so pre-render translation
would get its markup mangled by those escaping rules. Post-render
injection also keeps column-width computation on the ANSI text, which
tabulate measures correctly.
```

Every markup format absent from this registry strips ANSI codes from its cells
before rendering. The *Colors and styles* section of {doc}`/table` gives the
reason, format by format.
"""


DEFAULT_FORMAT = TableFormat.ROUNDED_OUTLINE
"""Default table format, if none is specified."""

RECORD_KEY = "record"
"""Key used for each record in structured formats that require named containers
(TOML `[[record]]`, XML `<record>`)."""

XML_ROOT_KEY = "records"
"""Root element name for XML table output."""

CSV_FORMATS = frozenset(
    {
        TableFormat.CSV,
        TableFormat.CSV_EXCEL,
        TableFormat.CSV_EXCEL_TAB,
        TableFormat.CSV_UNIX,
    },
)
"""Formats rendered by Python's `csv` module, each named after its dialect."""

_SERIALIZERS: dict[TableFormat, ConfigFormat] = {
    TableFormat.HJSON: ConfigFormat.HJSON,
    TableFormat.JSON: ConfigFormat.JSON,
    TableFormat.JSON5: ConfigFormat.JSON,
    TableFormat.JSONC: ConfigFormat.JSON,
    TableFormat.TOML: ConfigFormat.TOML,
    TableFormat.XML: ConfigFormat.XML,
    TableFormat.YAML: ConfigFormat.YAML,
}
"""The configuration format each serialization format writes with.

JSON5 and JSONC are supersets of JSON, so plain JSON is valid output for both.
"""

SERIALIZATION_FORMATS = frozenset(_SERIALIZERS)
"""Structured serialization formats whose renderers escape raw ESC bytes, making
post-render `strip_ansi()` ineffective."""

AUTO_WIDTH: Final = AUTO
"""Sentinel asking for a column width derived from the space left on the terminal.

Annotated `Final` so it narrows to `Literal["auto"]` instead of `str`, which is
what lets it stand in for the raw string anywhere a
{data}`~click_extra.columns.ColumnWidth` is expected.
"""

MIN_COLUMN_WIDTH = 8
"""Floor applied to an {data}`AUTO_WIDTH` column, so a crowded table still renders
a usable column instead of collapsing it to nothing."""

WRAPPABLE_FORMATS = frozenset(
    {
        TableFormat.COLON_GRID,
        TableFormat.DOUBLE_GRID,
        TableFormat.DOUBLE_OUTLINE,
        TableFormat.FANCY_GRID,
        TableFormat.FANCY_OUTLINE,
        TableFormat.GRID,
        TableFormat.HEAVY_GRID,
        TableFormat.HEAVY_OUTLINE,
        TableFormat.MIXED_GRID,
        TableFormat.MIXED_OUTLINE,
        TableFormat.OUTLINE,
        TableFormat.PLAIN,
        TableFormat.PRESTO,
        TableFormat.PRETTY,
        TableFormat.PSQL,
        TableFormat.ROUNDED_GRID,
        TableFormat.ROUNDED_OUTLINE,
        TableFormat.RST,
        TableFormat.SIMPLE,
        TableFormat.SIMPLE_GRID,
        TableFormat.SIMPLE_OUTLINE,
        TableFormat.VERTICAL,
    },
)
"""Formats laying a wrapped cell over several lines while keeping it one cell.

Column widths are a presentation hint: they are honored by the formats listed
here and silently dropped by every other one, the same way styling degrades per
format in {data}`~click_extra.table.STYLED_FORMATS`. Dropping is the point, as a
width forced onto a format below would corrupt its output.

```{important}
Every format absent from this registry renders `max_column_widths` unusable,
for one of four reasons:

- `aligned`: this module's own zero-padding format. tabulate does not
  indent its continuation lines, so a wrapped cell escapes its column.
- `github`, `jira`, `orgtbl`, `pipe`: continuation lines are emitted
  as additional table rows. They look right in a terminal, but a Markdown,
  Jira or Org renderer reads them as extra records.
- `asciidoc`, `html`, `latex`, `latex-booktabs`,
  `latex-longtable`, `latex-raw`, `mediawiki`, `moinmoin`,
  `textile`, `unsafehtml`, `youtrack`: the line break lands raw inside
  the cell markup, where the target renderer either collapses it back to a
  space or breaks the row. These formats delegate wrapping to whatever
  displays them.
- {data}`~click_extra.table.CSV_FORMATS`, `tsv`, and the
  {data}`~click_extra.table.SERIALIZATION_FORMATS`: data interchange, where a
  line break inside a field changes the record rather than its presentation.
```
"""


def _render_csv(
    table_data: Sequence[Sequence[str | None]],
    headers: Sequence[str | None] | None = None,
    table_format: TableFormat = TableFormat.CSV,
    **kwargs,
) -> str:
    """Render a table with Python's `csv` module.

    The dialect is the part of the format ID after `csv-`, and `excel` for a
    bare `csv`, like the `csv` module's own default. `kwargs` go to
    {func}`csv.writer`, and override the dialect.

    ```{note}
    StringIO is used to capture CSV output in memory. [Hard-coded to default to UTF-8](https://github.com/python/cpython/blob/9291095/Lib/_pyio.py#L2652).
    ```
    """
    dialect = table_format.value.removeprefix("csv").removeprefix("-") or "excel"
    with StringIO(newline="") as output:
        writer = csv.writer(output, **{"dialect": dialect, **kwargs})
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


def _render_records(
    fmt: ConfigFormat,
    table_data: Sequence[Sequence[str | None]],
    headers: Sequence[str | None] | None = None,
    **kwargs,
) -> str:
    """Render a table as a list of records serialized in `fmt`.

    Serves JSON, YAML and HJSON, which all take the {func}`_rows_as_dicts`
    shape as is. A format shipped by an extra (`[yaml]`, `[hjson]`) raises
    `ImportError` when that extra is missing, like
    {func}`~click_extra.config.formats.serialize_content` does.
    """
    return serialize_content(fmt, _rows_as_dicts(table_data, headers), **kwargs)


def _records_without_none(
    table_data: Sequence[Sequence[str | None]],
    headers: Sequence[str | None] | None,
    key: Callable[[str], str] = lambda name: name,
) -> list[dict[str, str]]:
    """One mapping per row, keyed by header or by position, `None` cells left out.

    The shape of the formats with no null type, TOML and XML. `key` reshapes a
    header into the name the format accepts.
    """
    records: list[dict[str, str]] = []
    for row in table_data:
        if headers:
            pairs = ((key(k), v) for k, v in zip(headers, row) if k is not None)
        else:
            pairs = ((str(i), v) for i, v in enumerate(row))
        records.append({k: v for k, v in pairs if v is not None})
    return records


def _render_toml(
    table_data: Sequence[Sequence[str | None]],
    headers: Sequence[str | None] | None = None,
    **kwargs,
) -> str:
    """Render a table as TOML using array-of-tables syntax.

    `None` values are omitted (TOML has no null type). Requires the `tomlrt`
    package (installable via the `[toml]` extra), which writes a list of
    mappings as an array of tables.
    """
    records = _records_without_none(table_data, headers)
    return serialize_content(ConfigFormat.TOML, {RECORD_KEY: records}, **kwargs)


def _xml_safe_name(name: str) -> str:
    """Replace characters invalid in XML element names."""
    safe = "".join(c if c.isalnum() or c in "_.-" else "_" for c in name)
    return safe.lstrip("0123456789.-") or "_"


def _render_xml(
    table_data: Sequence[Sequence[str | None]],
    headers: Sequence[str | None] | None = None,
    **kwargs,
) -> str:
    """Render a table as XML.

    `None` values are omitted.
    """
    records = _records_without_none(table_data, headers, key=_xml_safe_name)
    return serialize_content(
        ConfigFormat.XML, {XML_ROOT_KEY: {RECORD_KEY: records}}, **kwargs
    )


EMOJI_PRESENTATION_SELECTOR = "\ufe0f"
"""Unicode VARIATION SELECTOR-16, asking for the emoji form of what precedes it."""


EMOJI_PRESENTATION_RE = re.compile(f".{EMOJI_PRESENTATION_SELECTOR}")
"""Matches one emoji-presentation sequence: a character and the selector."""


_LAID_OUT_FOR_TERMINAL: ContextVar[bool] = ContextVar(
    "laid_out_for_terminal", default=True
)
"""Whether the table being rendered is laid out for the running terminal.

Set by {func}`render_table` and {func}`print_table` for the duration of one
rendering, and read by {func}`_terminal_wcswidth`, the measure
{func}`_setup_tabulate` hands `tabulate` once for the whole process. `True`
outside any rendering, so a direct `tabulate` call keeps measuring for the
screen.

A markup format renders under `False`. It carries the table to a reader who
never sees this terminal, and to a formatter like `mdformat` that pads it with
the Unicode widths alone.

A context variable rather than a module global, so two threads rendering at
once, one for the screen and one for a file, cannot swap each other's measure.
"""


def _term_program() -> str:
    """`$TERM_PROGRAM`, naming the terminal a table is laid out for.

    Read per call rather than at import, so a test can name a terminal and a
    long-running process can be handed a different environment. Handing the
    name to {func}`~click_extra.layout.cell_width` matters for the same reason:
    `wcwidth`'s own auto-detection caches the first answer for the life of the
    process.

    A multiplexer overwrites this variable with its own name, and rightly so:
    under `tmux` or `screen` it is the multiplexer that lays the cells out.
    """
    return os.environ.get("TERM_PROGRAM", "")


def _paints_wider_than_it_advances(text: str) -> bool:
    """Whether the terminal at hand paints `text` past the columns it advances.

    [UTS #51](https://www.unicode.org/reports/tr51/) makes an emoji-presentation
    sequence (a character followed by {data}`EMOJI_PRESENTATION_SELECTOR`) two
    columns wide, and a terminal implementing Unicode 9 widths advances by that.
    Several advance by the base character's own width instead, so `⁉️` (U+2049
    U+FE0F) takes one column and its glyph is painted over the next one.

    Measuring such a cell as two columns there pads its row one column short,
    and every rule right of that cell lands early: the table looks broken on
    exactly the rows carrying an emoji.

    Which terminals, and which sequences, comes from `wcwidth`'s per-terminal
    correction tables rather than a roster kept here. The answer varies by
    sequence as much as by terminal: a character wide in its own right (`✅`,
    U+2705) is advanced two columns everywhere.
    """
    # Deferred import: keeps wcwidth off the startup path of every CLI.
    from wcwidth import wcswidth

    return cell_width(text, term_program=_term_program()) < wcswidth(text)


def _terminal_wcswidth(text: str) -> int:
    """Columns `text` takes in the layout being rendered.

    For the running terminal, {func}`wcwidth.width` corrected for the one named
    in `$TERM_PROGRAM`: see {func}`_paints_wider_than_it_advances`. For a markup
    rendering, the Unicode widths alone: see {data}`_LAID_OUT_FOR_TERMINAL`.

    Keeps `wcswidth`'s own convention of returning `-1` for a string carrying a
    non-printable character, since `tabulate` measures with this too and reads
    that value.
    """
    # Deferred import: keeps wcwidth off the startup path of every CLI.
    from wcwidth import wcswidth

    width = wcswidth(text)
    if width < 0 or not _LAID_OUT_FOR_TERMINAL.get():
        return width
    return cell_width(text, term_program=_term_program())


def _pad_sequence(match: re.Match[str]) -> str:
    """Follow an emoji-presentation sequence with the column it paints into.

    Only on a terminal painting it wider than it advances: see
    {func}`_paints_wider_than_it_advances`.
    """
    sequence = match.group()
    if _paints_wider_than_it_advances(sequence):
        return f"{sequence} "
    return sequence


def _pad_emoji_presentation(cell: str | None) -> str | None:
    """Give an emoji-presentation glyph the column it paints into.

    A terminal advancing a single column for the sequence paints its glyph
    across two, over whatever follows: a space disappears and a letter is half
    covered, so `⁉️ unstable` reads as `⁉️unstable` while `✅ stable` keeps its
    gap. A space inserted after each such sequence is the column the glyph
    paints into, and it measures like any other, so the layout follows it.

    Each sequence is weighed on its own by
    {func}`_paints_wider_than_it_advances`, which is the same call the measure
    goes through: the padding and the widths cannot disagree.

    Terminal renderings only. A markup or serialization format carries the cell
    to a reader who never sees this terminal, and a space added there would be
    content, not presentation.
    """
    # A cell without the selector holds no sequence: skip the regex scan.
    if not isinstance(cell, str) or EMOJI_PRESENTATION_SELECTOR not in cell:
        return cell
    return EMOJI_PRESENTATION_RE.sub(_pad_sequence, cell)


def _visible_width(cell: object) -> int:
    """Number of terminal columns a cell occupies once rendered.

    ANSI escapes are discarded and double-width characters counted as two, so
    the measure matches what a terminal lays out rather than what {func}`len`
    counts.
    """
    if cell is None:
        return 0
    return max(_terminal_wcswidth(strip_ansi(str(cell))), 0)


def _natural_column_widths(
    table_data: Sequence[Sequence[str | None]],
    headers: Sequence[str | None] | None = None,
) -> list[int]:
    """Width each column takes when no wrapping is applied.

    Headers participate in the measure, as they widen a column the same way
    cells do. A row shorter than the others leaves its missing cells at zero.
    """
    rows = (headers, *table_data) if headers else table_data
    return [max(map(_visible_width, column)) for column in zip_longest(*rows)]


def _column_width_limit(
    max_column_widths: Sequence[int | None] | None,
    column: int,
) -> int | None:
    """Width limit declared for a column, if the table carries one."""
    if not max_column_widths or column >= len(max_column_widths):
        return None
    return max_column_widths[column]


def _render_vertical(
    table_data: Sequence[Sequence[str | None]],
    headers: Sequence[str | None] | None = None,
    sep_character: str = "*",
    sep_length: int = 27,
    max_column_widths: Sequence[int | None] | None = None,
    **kwargs,
) -> str:
    """Re-implements `cli-helpers`'s vertical table layout.

    Labels are padded to the visible width of the widest one, so a styled or a
    double-width label keeps the separator column aligned.

    A cell exceeding its `max_column_widths` entry wraps onto extra lines,
    each aligned under the first one so the label column stays readable. Unlike
    the tabulate-backed formats, this layout does the wrapping itself: there is
    no backend to delegate it to. {func}`~click_extra.layout.wrap_ansi` does
    the measuring, so a styled cell breaks on its visible width and keeps its
    styling across the wrap.

    ```{note}
    See [cli-helpers source code for reference](https://github.com/dbcli/cli_helpers/blob/v2.7.0/cli_helpers/tabular_output/vertical_table_adapter.py).
    ```

    ```{caution}
    This layout is [hard-coded to 27 asterisks to separate rows](https://github.com/dbcli/cli_helpers/blob/c34ae9f/cli_helpers/tabular_output/vertical_table_adapter.py#L34),
    as in the original implementation.
    ```
    """
    labels = ["" if header is None else header for header in headers or ()]
    label_widths = [_visible_width(label) for label in labels]
    gutter = max(label_widths, default=0)
    padded_labels = [
        label + " " * (gutter - width)
        for label, width in zip(labels, label_widths, strict=True)
    ]
    # Continuation lines of a wrapped cell line up under the first one, past
    # the label column and its separator.
    continuation = " " * gutter
    sep = sep_character * sep_length

    table_lines = []
    for index, row in enumerate(table_data, start=1):
        table_lines.append(f"{sep}[ {index}. row ]{sep}")
        for column, (label, cell) in enumerate(zip(padded_labels, row)):
            # Like other formats, render None as an empty string.
            text = "" if cell is None else str(cell)
            limit = _column_width_limit(max_column_widths, column)
            parts = [text]
            if limit and _visible_width(text) > limit:
                parts = wrap_ansi(text, limit)
            table_lines.append(f"{label} | {parts[0]}")
            table_lines.extend(f"{continuation} | {part}" for part in parts[1:])
    return "\n".join(table_lines)


_GFM_SEPARATOR_PATTERN = r"\|[-: |]+\|"
"""Matches a GFM table separator row (like `|:---|:---|`).

Kept as a string: `re` compiles and caches it on first use, which keeps the
compilation off the startup path.
"""


def _pad_gfm_separator(text: str) -> str:
    """Add space padding to GFM table separator rows.

    Tabulate's `pipe` format fills padding positions with dashes in separator
    rows (`|:---|`), while mdformat normalizes them to spaces (`| :-- |`).
    This post-processing step matches mdformat's canonical form, preventing an
    infinite formatting cycle between table-generating and markdown-formatting
    tools.
    """
    lines = []
    for line in text.split("\n"):
        if not re.fullmatch(_GFM_SEPARATOR_PATTERN, line):
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
    table_format: TableFormat = DEFAULT_FORMAT,
    max_column_widths: Sequence[int | None] | None = None,
    **kwargs,
) -> str:
    """Render a table with `tabulate`.

    Column widths are handed over to tabulate's own `maxcolwidths`, whose
    wrapper measures visible width, so cells keep their styling across a wrap.
    """
    options: dict[str, Any] = {
        "disable_numparse": True,
        "numalign": None,
        # tabulate()'s format ID uses underscores instead of dashes.
        "tablefmt": table_format.value.replace("-", "_"),
    }
    if max_column_widths is not None:
        options["maxcolwidths"] = list(max_column_widths)
    options.update(kwargs)
    headers = headers or ()
    if not table_format.is_markup:
        table_data = [
            [_pad_emoji_presentation(cell) for cell in row] for row in table_data
        ]
        headers = [_pad_emoji_presentation(header) for header in headers]
    result: str = _setup_tabulate().tabulate(table_data, headers, **options)
    # Normalize separator rows for GFM-compatible formats so that mdformat
    # treats the output as already canonical and does not re-pad it.
    if table_format in (TableFormat.GITHUB, TableFormat.PIPE):
        result = _pad_gfm_separator(result)
    return result


def _available_width() -> int:
    """Total width a table may occupy, resolved like a help screen.

    Reads the formatter of the current context, so the `terminal_width` and
    `max_content_width` context settings drive tables exactly as they drive
    help output and {func}`~click_extra.tree.render_command_tree`. Falls back
    to the raw terminal size outside any Click context.
    """
    ctx = click.get_current_context(silent=True)
    if ctx is not None:
        return ctx.make_formatter().width
    return shutil.get_terminal_size().columns


def _declared_max_widths(
    headers: Sequence[THeader] | None,
) -> list[ColumnWidth] | None:
    """Per-column width declared by the {class}`~click_extra.columns.ColumnSpec` entries
    of `headers`.

    Returns `None` when no header carries a `max_width`, which keeps an
    explicit `max_column_widths` argument as the only source in that case.
    """
    if not headers:
        return None
    widths: list[ColumnWidth] = [
        header.max_width if isinstance(header, ColumnSpec) else None
        for header in headers
    ]
    return widths if any(width is not None for width in widths) else None


def _normalize_max_widths(
    max_column_widths: MaxColumnWidths,
    column_count: int,
) -> list[ColumnWidth] | None:
    """Expand a scalar, then pad or trim the result to one entry per column."""
    if max_column_widths is None:
        return None
    if isinstance(max_column_widths, (int, str)):
        return [max_column_widths] * column_count
    widths: list[ColumnWidth] = list(max_column_widths)
    widths.extend([None] * (column_count - len(widths)))
    return widths[:column_count]


def _decoration_width(
    table_data: Sequence[Sequence[str | None]],
    headers: Sequence[str | None] | None,
    table_format: TableFormat,
    natural: Sequence[int],
) -> int:
    """Columns the borders and padding of a format add to its widest row.

    Measured on a real unconstrained render rather than derived from the
    box-drawing definition of the format, so every tabulate layout is covered
    by the same code path, custom registrations included.
    """
    baseline = _render_tabulate(table_data, headers, table_format=table_format)
    widest = max((_visible_width(line) for line in baseline.splitlines()), default=0)
    return max(widest - sum(natural), 0)


def _resolve_auto_widths(
    widths: Sequence[ColumnWidth],
    table_data: Sequence[Sequence[str | None]],
    headers: Sequence[str | None] | None,
    table_format: TableFormat,
) -> list[int | None]:
    """Turn every {data}`AUTO_WIDTH` entry into a concrete character count.

    An `auto` column absorbs whatever the terminal has left once the
    decoration of the format and the width of the other columns are paid for.
    Several `auto` columns share that remainder evenly, and none is ever
    resolved below {data}`MIN_COLUMN_WIDTH`.
    """
    auto_width = MIN_COLUMN_WIDTH
    # Measuring the terminal and the natural render is only worth it when a
    # column actually asked for it.
    if AUTO_WIDTH in widths:
        natural = _natural_column_widths(table_data, headers)
        natural.extend([0] * (len(widths) - len(natural)))
        available = _available_width()

        if table_format is TableFormat.VERTICAL:
            # Vertical stacks one cell per line, so a column competes with the
            # label gutter rather than with its neighbors.
            label_width = max((_visible_width(h) for h in headers or ()), default=0)
            budget = available - label_width - len(" | ")
        else:
            fixed = 0
            auto_count = 0
            for index, width in enumerate(widths):
                if width == AUTO_WIDTH:
                    auto_count += 1
                elif isinstance(width, int):
                    fixed += min(natural[index], width)
                else:
                    fixed += natural[index]
            decoration = _decoration_width(table_data, headers, table_format, natural)
            budget = (available - decoration - fixed) // auto_count

        auto_width = max(budget, MIN_COLUMN_WIDTH)

    return [
        auto_width
        if width == AUTO_WIDTH
        else (width if isinstance(width, int) else None)
        for width in widths
    ]


def _resolve_column_widths(
    table_data: Sequence[Sequence[str | None]],
    headers: Sequence[THeader] | None,
    labels: Sequence[str | None] | None,
    table_format: TableFormat,
    max_column_widths: MaxColumnWidths,
) -> list[int | None] | None:
    """Resolve the width limits a render should apply, or `None` for no limit.

    An explicit `max_column_widths` wins over the `max_width` declared by
    {class}`~click_extra.columns.ColumnSpec` headers. Widths tied to a `ColumnSpec`
    follow their column through a `--columns` projection, where a positional list would
    silently shift onto the wrong columns.

    Formats unable to lay a wrapped cell over several lines (everything outside
    {data}`~click_extra.table.WRAPPABLE_FORMATS`) resolve to `None`: the hint
    is dropped rather than allowed to corrupt their output.
    """
    if not table_format.is_wrappable:
        return None

    column_count = max((len(row) for row in table_data), default=0)
    if labels:
        column_count = max(column_count, len(labels))
    if not column_count:
        return None

    widths = _normalize_max_widths(max_column_widths, column_count)
    if widths is None:
        widths = _normalize_max_widths(_declared_max_widths(headers), column_count)
    if widths is None or all(width is None for width in widths):
        return None

    return _resolve_auto_widths(widths, table_data, labels, table_format)


def _render_func(table_format: TableFormat) -> Callable[..., str]:
    """The function rendering a table in `table_format`."""
    if table_format in CSV_FORMATS:
        return partial(_render_csv, table_format=table_format)
    if table_format is TableFormat.VERTICAL:
        return _render_vertical
    match _SERIALIZERS.get(table_format):
        case None:
            return partial(_render_tabulate, table_format=table_format)
        case ConfigFormat.TOML:
            return _render_toml
        case ConfigFormat.XML:
            return _render_xml
        case config_format:
            return partial(_render_records, config_format)


def _print_func(table_format: TableFormat) -> Callable[[str], None]:
    """The function printing a table rendered in `table_format`.

    CSV and the serialization formats end their output with their own line
    terminations, so Python's `print()` writes it as is, where `echo()` would add
    a line return. Every other format goes through Click's `echo()`, which
    honors the colorization settings: that is what makes `--color` and
    `--no-color` reach a table.
    """
    if table_format in CSV_FORMATS or table_format in SERIALIZATION_FORMATS:
        return partial(print, end="")
    return echo


def _normalize_column_def(column: TColumnDef) -> tuple[str | None, str | None]:
    """Coerce a column definition to a `(label, column_id)` tuple.

    Accepts a {class}`~click_extra.columns.ColumnSpec` (so a registry can be shared with
    `--columns`), whose column ID is dropped when it is not `sortable`, or a
    bare column ID string, which declares a sortable field untied to any table
    layout (its label is `None`).
    """
    if isinstance(column, str):
        return (None, column)
    return (column.label, column.id if column.sortable else None)


def _split_header_defs(
    headers: Sequence[THeader] | None,
) -> tuple[
    Sequence[str | None] | None,
    tuple[tuple[str | None, str | None], ...] | None,
]:
    """Split header definitions into render labels and sortable column defs.

    `headers` entries may be plain strings (a label carrying no column ID) or
    {class}`~click_extra.columns.ColumnSpec` instances. Returns the labels to render and
    the `(label, column_id)` definitions, the latter `None` when no entry carries a
    sortable column ID (nothing to sort on).
    """
    if headers is None:
        return None, None
    defs = tuple(
        _normalize_column_def(header)
        if isinstance(header, ColumnSpec)
        else (header, None)
        for header in headers
    )
    labels = [label for label, _ in defs]
    if not any(col_id for _, col_id in defs):
        return labels, None
    return labels, defs


def _context_sort_key(
    header_defs: Sequence[tuple[str | None, str | None]],
) -> Callable[[Sequence[str | None]], tuple] | None:
    """Build a sort key from the `--sort-by` selection of the current context.

    Reads {data}`click_extra.context.SORT_BY`, which `ctx.meta` shares
    across the whole context tree, so a selection made on a parent group is
    visible from the subcommand doing the printing. Returns `None` outside
    any Click context, when no selection is active, or when the table carries
    none of the selected columns.
    """
    ctx = click.get_current_context(silent=True)
    if ctx is None:
        return None
    sort_columns = context.get(ctx, context.SORT_BY)
    if not sort_columns:
        return None
    return _defs_sort_key(header_defs, sort_columns)


def _resolve_table_inputs(
    table_data: Sequence[Sequence[str | None]],
    headers: Sequence[THeader] | None,
    sort_key: Callable[[Sequence[str | None]], Any] | None,
) -> tuple[Sequence[Sequence[str | None]], Sequence[str | None] | None]:
    """Split header definitions and apply the resolved row sort.

    The shared preamble of {func}`render_table` and {func}`print_table`: the
    render labels are split from the sortable column definitions, the active
    `--sort-by` selection is resolved when no explicit `sort_key` is given,
    and rows are sorted when a key applies.
    """
    labels, header_defs = _split_header_defs(headers)
    if sort_key is None and header_defs:
        sort_key = _context_sort_key(header_defs)
    if sort_key is not None:
        table_data = sorted(table_data, key=sort_key)
    return table_data, labels


CORNER_GLYPH = "↴"
"""The arrow {func}`corner_header` places after the row axis.

The Sphinx extension looks for it to find a table with a corner label: see
{mod}`click_extra.sphinx.tables`.
"""


def corner_header(rows: str, columns: str) -> str:
    r"""Name both axes of a two-axis table in its top-left header cell.

    `rows` says what the first column lists, read downward, and `columns` what
    the other headers list, read rightward: `corner_header("City", "Month")`
    returns `City ↴ \ Month →`.
    """
    return f"{rows} {CORNER_GLYPH} \\ {columns} →"


def _render_rows(
    table_data: Sequence[Sequence[str | None]],
    headers: Sequence[THeader] | None,
    labels: Sequence[str | None] | None,
    table_format: TableFormat,
    max_column_widths: MaxColumnWidths,
    **kwargs,
) -> str:
    """Render rows already sorted, under the labels split from their headers.

    The rendering core of {func}`render_table` and {func}`print_table`. A
    markup rendering is measured with the Unicode widths for as long as it
    renders: the column widths resolved here and the padding tabulate applies
    must read every cell the same way.
    """
    token = _LAID_OUT_FOR_TERMINAL.set(not table_format.is_markup)
    try:
        widths = _resolve_column_widths(
            table_data, headers, labels, table_format, max_column_widths
        )
        if widths is not None:
            kwargs["max_column_widths"] = widths
        return _render_func(table_format)(table_data, labels, **kwargs)
    finally:
        _LAID_OUT_FOR_TERMINAL.reset(token)


def render_table(
    table_data: Sequence[Sequence[str | None]],
    headers: Sequence[THeader] | None = None,
    table_format: TableFormat | None = None,
    sort_key: Callable[[Sequence[str | None]], Any] | None = None,
    max_column_widths: MaxColumnWidths = None,
    **kwargs,
) -> str:
    """Render a table and return it as a string.

    `headers` entries carrying a column ID ({class}`~click_extra.columns.ColumnSpec`
    instances) plug the table into the active `--sort-by` selection: when no explicit
    `sort_key` is given, rows sort by the selected columns this table carries, and keep
    their original order when it carries none. See
    {func}`~click_extra.table_options.column_sort_key` for the exact semantics.

    :param sort_key: Optional callable passed to {func}`sorted` as the `key`
        argument. When provided, rows are sorted before rendering.
    :param max_column_widths: Width limits, as one entry per column or a single
        value for all of them. Each entry is a character count, `"auto"` to
        absorb the width left on the terminal, or `None` for no limit.
        Defaults to the `max_width` declared by {class}`~click_extra.columns.ColumnSpec`
        headers. Silently dropped by formats outside
        {data}`~click_extra.table.WRAPPABLE_FORMATS`.
    """
    table_data, labels = _resolve_table_inputs(table_data, headers, sort_key)
    return _render_rows(
        table_data,
        headers,
        labels,
        table_format or DEFAULT_FORMAT,
        max_column_widths,
        **kwargs,
    )


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

    Reads the resolved `ctx.color` tri-state, which subcommand contexts
    inherit from their parents. Only an explicit `False` (`--no-color`,
    `NO_COLOR`, `--color=never`) disables styling: the `None` (auto)
    default keeps it, as a markup document carries its own rendering and no
    TTY is involved.
    """
    ctx = click.get_current_context(silent=True)
    return ctx is not None and ctx.color is False


def _color_forced() -> bool:
    """Whether `--color` was explicitly forced on the command line.

    Walks up the context chain, so a color option declared on a parent group is
    honored from the subcommand doing the printing. The default set by a
    {class}`~click_extra.color.ColorOption` does not count as forced: only an
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
    headers: Sequence[THeader] | None = None,
    table_format: TableFormat | None = None,
    sort_key: Callable[[Sequence[str | None]], Any] | None = None,
    max_column_widths: MaxColumnWidths = None,
    **kwargs,
) -> None:
    """Render a table and print it to the console.

    `headers` entries carrying a column ID ({class}`~click_extra.columns.ColumnSpec`
    instances) plug the table into the active `--sort-by` selection: when no explicit
    `sort_key` is given, rows sort by the selected columns this table carries, and keep
    their original order when it carries none. See
    {func}`~click_extra.table_options.column_sort_key` for the exact semantics.

    ANSI codes carried by cell values and headers depend on the format:

    - Markup formats with native styling support (see
      {data}`~click_extra.table.STYLED_FORMATS`) get them translated to the
      format's own styling markup, unless color output is disabled
      (`--no-color`, `NO_COLOR`, ...).
    - Other markup formats get them stripped from cell values before
      rendering, unless `--color` is explicitly forced on the command line.
    - Plain-text formats keep them raw, and defer to `echo()`'s sensitivity
      to the global colorization settings.

    :param sort_key: Optional callable passed to {func}`sorted` as the `key`
        argument. When provided, rows are sorted before rendering.
    :param max_column_widths: Width limits, as one entry per column or a single
        value for all of them. Each entry is a character count, `"auto"` to
        absorb the width left on the terminal, or `None` for no limit.
        Defaults to the `max_width` declared by {class}`~click_extra.columns.ColumnSpec`
        headers. Silently dropped by formats outside
        {data}`~click_extra.table.WRAPPABLE_FORMATS`.
    :raises ~click_extra.output.MissingExtraError: the renderer of
        `table_format` is not installed.
    """
    table_format = table_format or DEFAULT_FORMAT
    table_data, labels = _resolve_table_inputs(table_data, headers, sort_key)

    ansi_translator: Callable[[str], str] | None = None
    if table_format.supports_styling and not _color_disabled():
        # Translation to native styling runs on the rendered output, not on
        # cells: see the STYLED_FORMATS docstring for the rationale.
        ansi_translator = STYLED_FORMATS[table_format]
    elif table_format.is_markup and not _color_forced():
        # Strip ANSI codes from cell data before rendering. Pre-render
        # stripping is necessary because some renderers (JSON, YAML) escape raw
        # ESC bytes, making post-render strip_ansi() ineffective. Widths are
        # resolved after it, so an `auto` column is measured on the text that
        # gets rendered.
        table_data, labels = _strip_ansi_cells(table_data, labels)

    try:
        output = _render_rows(
            table_data, headers, labels, table_format, max_column_widths, **kwargs
        )
    except ImportError:
        raise MissingExtraError(
            table_format.value, subject=f"{table_format.value} output"
        ) from None
    if ansi_translator is not None:
        output = ansi_translator(output)
    _print_func(table_format)(output)


def _strip_none(data: Any) -> Any:
    """Recursively drop `None` values from dicts.

    Needed for formats without a null type (TOML, XML).
    """
    if isinstance(data, dict):
        return {k: _strip_none(v) for k, v in data.items() if v is not None}
    if isinstance(data, (list, tuple)):
        return [_strip_none(v) for v in data]
    return data


def _strip_none_and_wrap(data: Any) -> dict:
    """Strip `None` values and wrap bare lists under the `record` key.

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

    Unlike {func}`render_table` which expects tabular rows and headers, this
    function accepts any JSON-compatible data structure (dicts, lists, nested
    combinations) and serializes it to the requested format.

    Only formats in {data}`~click_extra.table.SERIALIZATION_FORMATS` are
    supported.

    :param data: Arbitrary data to serialize (dicts, lists, scalars).
    :param table_format: Target serialization format.
    :param default: Fallback serializer for types not natively supported. Defaults
        to {class}`str`, so {class}`~pathlib.Path` and similar types are
        stringified automatically. Set to a custom callable for different behavior.
    :param root_element: Root element name for XML output.
    :param kwargs: Extra keyword arguments forwarded to the underlying serializer
        (like `sort_keys` or `indent` for JSON).
    :raises ValueError: If the format is not a serialization format.
    """
    config_format = _SERIALIZERS.get(table_format)
    if config_format is None:
        msg = f"Unsupported serialization format: {table_format}"
        raise ValueError(msg)

    clean = _apply_default(data, default if default is not None else str)
    # TOML and XML have no null type, and want a mapping at the top.
    if config_format is ConfigFormat.TOML:
        clean = _strip_none_and_wrap(clean)
    elif config_format is ConfigFormat.XML:
        clean = {root_element: _strip_none_and_wrap(clean)}
    return serialize_content(config_format, clean, **kwargs)


def _apply_default(data: Any, default: Callable) -> Any:
    """Recursively apply a `default` callback to non-native types.

    Walks dicts, lists, and tuples. For any other type, calls `default(obj)`
    which should return a JSON-serializable value or raise {exc}`TypeError`.
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

    Wraps {func}`serialize_data` with user-friendly error handling for missing
    optional dependencies.

    :param data: Arbitrary data to serialize.
    :param table_format: Target serialization format.
    :param default: Fallback serializer for custom types. Defaults to {class}`str`.
    :param root_element: Root element name for XML output.
    :param package: Package name for install instructions in error messages.
    :param kwargs: Extra keyword arguments forwarded to the underlying serializer.
    :raises ~click_extra.output.MissingExtraError: the serializer of
        `table_format` is not installed.
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
        raise MissingExtraError(
            table_format.value, subject=f"{table_format.value} output", package=package
        ) from None
    echo(output, color=False)


def _default_cell_key(cell: str | None) -> str:
    """Compare a cell on its ANSI-stripped, case-folded text, `None` as empty."""
    return strip_ansi(cell).casefold() if cell else ""


def _row_sort_key(
    sort_order: Sequence[int],
    cell_key: Callable[[str | None], Any] | None = None,
) -> Callable[[Sequence[str | None]], tuple]:
    """Build a row sort key comparing cells at the `sort_order` positions.

    Each cell is passed through `cell_key` before comparison. Defaults to
    {func}`_default_cell_key`: ANSI-stripped, case-folded string comparison,
    with `None` and empty cells collating as the empty string.
    """
    key = cell_key if cell_key is not None else _default_cell_key

    def key_func(row: Sequence[str | None]) -> tuple:
        return tuple(key(row[i]) for i in sort_order)

    return key_func


def _defs_sort_key(
    defs: Sequence[tuple[str | None, str | None]],
    sort_columns: Sequence[str] | None = None,
    cell_key: Callable[[str | None], Any] | None = None,
) -> Callable[[Sequence[str | None]], tuple] | None:
    """{func}`~click_extra.table_options.column_sort_key` over definitions already
    normalized to pairs."""
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
