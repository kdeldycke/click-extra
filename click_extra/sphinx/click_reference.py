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
"""Reference directives of the `click` domain: `click:tree` and `click:config`.

Each one evaluates a Python expression in the runner namespace that the
`click:source` and `click:run` blocks of the page share, and expands what it
yields into MyST: a summary table, then one section per command or per
configuration option.

{class}`ClickDomain` lives here too, because it registers every `click:*`
directive: this module imports the ones of {mod}`click_extra.sphinx.click`, which
cannot import this module back.
"""

from __future__ import annotations

import re
from dataclasses import is_dataclass
from functools import cached_property

import click
from docutils import nodes
from sphinx.directives import directives
from sphinx.util.logging import getLogger

from ..config.option import ConfigOption
from ..config.schema import schema_field_infos
from ..param_tools import iter_subcommands, make_resilient_context
from ..table import TableFormat, render_table
from ._base import StatelessDomain, parse_into_section
from .click import ClickDirective, RunDirective, SourceDirective, _code_fence

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any, ClassVar

    from sphinx.util.typing import OptionSpec

    from ..config.schema import SchemaFieldInfo

logger = getLogger(__name__)


CONFIG_DOCSTRING_HEADING_WARNING = "click_extra.config_docstring_heading"
"""Type and subtype of the warning about a heading in a `click:config` docstring.

List it in `suppress_warnings` to silence the warning, or in
{data}`click_extra.sphinx.fail_on_warnings.FAIL_ON_WARNINGS_CONFIG` to fail the
build on it.
"""


def _slug(value: str) -> str:
    """Lower-case `value`, each run of other characters a hyphen, like `make_id`.

    The anchor a reference table links a section by, mirroring the id docutils'
    `make_id` derives from that section's heading.
    """
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _table_cell(text: str) -> str:
    """Escape the pipes of `text`, which would otherwise split its table cell."""
    return text.replace("|", "\\|")


def _short_description(command: click.Command) -> str:
    """The one-line summary of `command` for a table cell, without its final period."""
    return _table_cell((command.get_short_help_str() or "").rstrip("."))


class ReferenceDirective(ClickDirective):
    """Base of the directives expanding a Python expression into a MyST reference.

    `click:tree` and `click:config` both take one required argument, an
    expression evaluated in the per-document runner namespace, and an optional
    body of Python run in that namespace first. Both write MyST headings under
    the section hosting them, so both refuse an rST host.
    """

    required_arguments = 1
    optional_arguments = 0

    def resolve_argument(self) -> tuple[str, Any]:
        """Run the body, then evaluate the argument in the runner namespace.

        The body lets a page inline `from mypkg.cli import mycli` instead of
        seeding the namespace with a separate `click:source` `:hide-source:`
        block. Hard errors (not `self.error()`) so the build fails fast: a
        partially rendered reference page hides bugs in what the directive was
        meant to document.

        :return: the expression as written, and what it evaluated to.
        :raises RuntimeError: on an rST host, or when the expression cannot be
            evaluated.
        """
        if not self.is_myst_syntax:
            raise RuntimeError(
                f"{self.name} currently only supports MyST syntax. "
                "Place the directive in a .md document with myst_parser enabled.",
            )
        if self.content:
            self.runner.execute_source(self)
        expression = self.arguments[0].strip()
        return expression, self.evaluate(expression, self.name)

    @cached_property
    def heading_offset(self) -> int:
        """Levels the generated headings are shifted down by.

        Set by `:heading-offset:`. Without it, the headings nest one level below
        the surrounding section, so the document outline stays consistent
        wherever the directive is placed: at the document's top level this
        resolves to `1`, a root rendered at `h2` under a document title at `h1`,
        and inside an `h3` section to `3`, a root rendered at `h4`.

        The surrounding level is read from `state.memo.section_level`, which the
        `MockState` of `myst-parser` fills, never below `1`.
        """
        if "heading-offset" in self.options:
            return self.options["heading-offset"]  # type: ignore[no-any-return]
        return max(int(self.state.memo.section_level), 1)


class TreeDirective(ReferenceDirective):
    """Render a complete CLI reference for a Click command and all its subcommands.

    Walks the Click command tree at build time and emits, in MyST syntax:

    - A GFM summary table linking each command to its section anchor.
    - A heading + `click:run` `--help` block for the root command.
    - One heading + `click:run` `--help` block per subcommand, nested by
      depth.

    The directive walks the live command tree on every build, so the reference
    cannot drift from the CLI it documents.

    The required argument is a Python expression evaluated in the per-document
    runner namespace; it must yield a {class}`click.Command`. The optional
    directive body is Python preamble exec'd in the same namespace before
    evaluation, so authors may either import the CLI in a prior
    `click:source :hide-source:` block or inline the import here.

    ```{note}
    Currently MyST-only. Use the directive in a `.md` document with
    `myst_parser` enabled.
    ```
    """

    option_spec: ClassVar[OptionSpec] = {
        "max-depth": directives.positive_int,
        "heading-offset": directives.nonnegative_int,
        "anchor-prefix": directives.unchanged,
        "label-prefix": directives.unchanged,
        "root-label": directives.unchanged,
        "no-table": directives.flag,
        "no-root": directives.flag,
    }
    """Recognized directive options.

    `max-depth` caps the recursion into nested {class}`click.Group` commands
    (default: `10`). `heading-offset` shifts all generated headings down
    by N levels. When unset, the directive reads
    `state.memo.section_level` and uses the surrounding section depth so
    the root nests one level below the enclosing section: inside the
    document's `h1` title this yields `1` (root at `h2`); inside an
    `h3` section it yields `3` (root at `h4`). Override only when the
    auto-detected depth is wrong for the page layout. `anchor-prefix` and
    `label-prefix` override the slug and display prefix used for anchors
    and labels; both default to the CLI's {attr}`click.Command.name`.
    `root-label` sets the heading text for the root help block
    (default: `"Help screen"`). `no-table` skips the summary table;
    `no-root` skips the root `--help` block.
    """

    def _walk(
        self,
        root: click.Command,
        max_depth: int,
    ) -> list[tuple[list[str], click.Command]]:
        """Depth-first traversal of the command tree, in listing order.

        Returns `(path, command)` tuples where `path` is the list of
        subcommand names from the root (exclusive) down to `command`. The
        root itself is not included; callers that want a root entry add it
        separately (see {meth}`run`).

        Each group is read like the `--tree` option reads it, through
        {func}`~click_extra.param_tools.iter_subcommands`: in the order
        {meth}`click.Group.list_commands` returns, lazy subcommands included and
        hidden ones skipped. Each level is walked under its own resilient child
        context.
        """
        entries: list[tuple[list[str], click.Command]] = []

        def recurse(cmd: click.Command, ctx: click.Context, path: list[str]) -> None:
            for name, sub in iter_subcommands(cmd, ctx):
                sub_path = [*path, name]
                entries.append((sub_path, sub))
                if isinstance(sub, click.Group) and len(sub_path) < max_depth:
                    sub_ctx = make_resilient_context(sub, name, parent=ctx)
                    recurse(sub, sub_ctx, sub_path)

        if isinstance(root, click.Group):
            recurse(root, make_resilient_context(root), [])
        return entries

    def run(self) -> list[nodes.Node]:
        cli_expr, cli = self.resolve_argument()
        if not isinstance(cli, click.Command):
            raise TypeError(
                f"click:tree: {cli_expr!r} did not yield a click.Command "
                f"(got {type(cli).__name__}).",
            )

        max_depth = self.options.get("max-depth", 10)
        label_prefix = self.options.get("label-prefix") or cli.name or cli_expr
        anchor_prefix = self.options.get("anchor-prefix") or _slug(label_prefix)
        root_label = self.options.get("root-label", "Help screen")
        include_table = "no-table" not in self.options
        include_root = "no-root" not in self.options

        # Each command's heading label and anchor, shared by the row linking to
        # its section and the section itself.
        entries = [
            (
                path,
                cmd,
                f"{label_prefix} {' '.join(path)}".strip(),
                "-".join([anchor_prefix, *map(_slug, path)]),
            )
            for path, cmd in self._walk(cli, max_depth)
        ]

        lines: list[str] = []

        # Summary table.
        if include_table:
            rows: list[list[str]] = []
            if include_root:
                rows.append([
                    f"[`{label_prefix}`](#{anchor_prefix})",
                    _short_description(cli),
                ])
            rows.extend(
                [f"[`{label}`](#{anchor})", _short_description(cmd)]
                for _path, cmd, label, anchor in entries
            )
            if rows:
                lines.extend((
                    render_table(
                        rows,
                        headers=["Command", "Description"],
                        table_format=TableFormat.GITHUB,
                    ),
                    "",
                ))

        # Root help block. Placed at the same heading level as top-level
        # commands so subcommands always nest one level deeper than their
        # parent.
        if include_root:
            heading = "#" * (self.heading_offset + 1)
            lines.extend((
                f"({anchor_prefix})=",
                f"{heading} {root_label}",
                "",
                "```{click:run}",
                f"invoke({cli_expr}, args=['--help'])",
                "```",
                "",
            ))

        # Per-command sections.
        for path, _cmd, label, anchor in entries:
            heading = "#" * (self.heading_offset + len(path))
            args_repr = ", ".join(repr(a) for a in [*path, "--help"])
            lines.extend((
                f"({anchor})=",
                f"{heading} `{label}`",
                "",
                "```{click:run}",
                f"invoke({cli_expr}, args=[{args_repr}])",
                "```",
                "",
            ))

        # Nested `{click:run}` directives execute during the shared parse and
        # resolve the CLI variable from the same runner namespace.
        return parse_into_section(self, lines)


def _format_default(value: object) -> str:
    """Format a schema field default as a Markdown fragment.

    Used in both the summary table cells and the per-option `**Default:**`
    lines of `click:config`. Multi-line strings are elided to a pointer,
    since the TOML example block below renders them in full.
    """
    match value:
        case None:
            return "*(none)*"
        case bool():
            return f"`{str(value).lower()}`"
        case int():
            return f"`{value}`"
        case str() if "\n" in value:
            return "*(see example)*"
        case str():
            return f'`"{value}"`'
        case list():
            return f"`{value!r}`"
        case _:
            return str(value)


def _toml_value(value: object) -> str | None:
    """Format a Python value as a TOML literal.

    Returns `None` when no sensible literal exists (`None` defaults,
    opaque objects), which suppresses the option's example block in
    `click:config`.
    """
    match value:
        case bool():
            return "true" if value else "false"
        case int():
            return str(value)
        case str() if "\n" in value:
            return f"'''\n{value}\n'''"
        case str():
            return f'"{value}"'
        case list():
            literals = []
            for item in value:
                literal = _toml_value(item)
                if literal is None:
                    return None
                literals.append(literal)
            return f"[{', '.join(literals)}]"
        case _:
            return None


class ConfigDirective(ReferenceDirective):
    """Render the configuration reference of a CLI's `config_schema`.

    Introspects a configuration schema dataclass at build time and expands,
    in MyST syntax:

    - A GFM summary table linking each option to its section anchor, with its
      one-line summary and default value.
    - One heading per option, with its docstring, type, default, and a TOML
      example pinned to the default value.

    Option metadata comes from
    {func}`~click_extra.config.schema.schema_field_infos`: dotted kebab-case
    keys, type annotations, defaults from a pristine schema instance, and
    attribute docstrings (which are parsed as the host document's markup).
    The directive documents the live schema on every build, so the reference
    cannot drift from the configuration it describes.

    The required argument is a Python expression evaluated in the per-document
    runner namespace; it must yield either a {class}`click.Command` whose
    `config_schema` is set (the schema is pulled off its
    {class}`~click_extra.config.option.ConfigOption`), or a schema dataclass
    directly. The optional directive body is Python preamble exec'd in the
    same namespace before evaluation, so authors may either import the CLI in
    a prior `click:source` `:hide-source:` block or inline the import
    here.

    ```{caution}
    Attribute docstrings are recovered from the schema's source file, so
    a schema defined inside an exec'd `click:source` block documents
    its options without descriptions. Import the schema from a real
    module instead (see
    {func}`~click_extra.config.schema.field_docstrings`).
    ```

    ```{note}
    Currently MyST-only. Use the directive in a `.md` document with
    `myst_parser` enabled.
    ```
    """

    option_spec: ClassVar[OptionSpec] = {
        "heading-offset": directives.nonnegative_int,
        "section": directives.unchanged,
        "no-table": directives.flag,
        "no-examples": directives.flag,
    }
    """Recognized directive options.

    `heading-offset` shifts all generated headings down by N levels; when
    unset, the surrounding section depth is used (same behavior as
    `click:tree`). `section` overrides the TOML table header shown in the
    per-option examples: it defaults to ``tool.{cli-name}`` when the argument
    is a CLI (matching how click-extra and its downstream CLIs read their
    section from `pyproject.toml`), and to no header at all for a bare
    schema; an explicitly empty `:section:` suppresses the header.
    `no-table` skips the summary table; `no-examples` skips the TOML
    example blocks.
    """

    def run(self) -> list[nodes.Node]:
        target_expr, target = self.resolve_argument()

        section = self.options.get("section")
        if isinstance(target, click.Command):
            schema = next(
                (
                    param.config_schema
                    for param in target.params
                    if isinstance(param, ConfigOption) and param.config_schema
                ),
                None,
            )
            if schema is None:
                raise RuntimeError(
                    f"click:config: {target_expr!r} has no config_schema wired "
                    "to its ConfigOption.",
                )
            if section is None and target.name:
                section = f"tool.{target.name}"
        else:
            schema = target

        # Also narrows the ConfigOption union (its config_schema may be a bare
        # callable) down to the dataclass type schema_field_infos expects.
        if not (isinstance(schema, type) and is_dataclass(schema)):
            raise TypeError(
                f"click:config: {target_expr!r} did not yield a dataclass "
                f"schema (got {schema!r}).",
            )

        infos = schema_field_infos(schema)
        self._report_docstring_headings(infos)

        include_table = "no-table" not in self.options
        include_examples = "no-examples" not in self.options

        lines: list[str] = []

        # Summary table. Each option links to the natural anchor docutils
        # derives from its heading below.
        if include_table and infos:
            rows = [
                [
                    f"[`{info.key}`](#{_slug(info.key)})",
                    _table_cell(info.summary),
                    _format_default(info.default),
                ]
                for info in infos
            ]
            lines.extend((
                render_table(
                    rows,
                    headers=["Option", "Description", "Default"],
                    table_format=TableFormat.GITHUB,
                ),
                "",
            ))

        # Per-option sections: lead with the summary, then type and default,
        # then the rest of the docstring, and finally a TOML example pinned
        # to the field's default value.
        heading = "#" * (self.heading_offset + 1)
        for info in infos:
            # Strip the summary (already shown first) from the full docstring.
            _head, _sep, tail = info.description.partition("\n\n")
            rest = tail.strip()

            lines.extend((f"{heading} `{info.key}`", ""))
            if info.summary:
                lines.extend((info.summary, ""))
            # The "| None" half of an optional type is noise here: the
            # Default line right next to it already says whether the option
            # defaults to nothing.
            type_hint = info.type_hint.replace(" | None", "")
            default = _format_default(info.default)
            lines.extend((f"**Type:** `{type_hint}` | **Default:** {default}", ""))
            if rest:
                lines.extend((*rest.splitlines(), ""))
            example = _toml_value(info.default) if include_examples else None
            if example is not None:
                example_lines = [f"[{section}]"] if section else []
                example_lines.extend(f"{info.key} = {example}".splitlines())
                fence = _code_fence(example_lines)
                lines.extend((
                    "**Example:**",
                    "",
                    f"{fence}toml",
                    *example_lines,
                    fence,
                    "",
                ))

        # Hand the generated MyST source back to the parser, like click:tree.
        return parse_into_section(self, lines)

    def _report_docstring_headings(self, infos: Sequence[SchemaFieldInfo]) -> None:
        """Warn about each Markdown heading in the docstring of an option.

        The directive inserts each docstring into the MyST it generates, so a
        heading there becomes a section of the page, and a level-1 heading a
        top-level section of the document. A line wrap that leaves a lone `=` or
        `-` under a paragraph is enough to make one.

        Each docstring is parsed with the MyST configuration `conf.py` sets for
        the project. Each heading is reported as a
        {data}`CONFIG_DOCSTRING_HEADING_WARNING` at the directive, with the
        option and the docstring line that makes the heading: the underline of a
        setext heading, the line of an ATX one.
        """
        # Deferred import: keeps myst-parser, which only the `sphinx` extra
        # installs, optional for a project that writes its pages in reST.
        from myst_parser.config.main import MdParserConfig
        from myst_parser.mdit_to_docutils.base import DocutilsRenderer
        from myst_parser.parsers.mdit import create_md_parser

        parser = create_md_parser(
            getattr(self.env, "myst_config", None) or MdParserConfig(),
            DocutilsRenderer,
        )
        warning_type, _, subtype = CONFIG_DOCSTRING_HEADING_WARNING.partition(".")
        for info in infos:
            for token in parser.parse(info.description):
                # The map ends after the last line of the heading, so it is that
                # line's number counted from 1.
                if token.type == "heading_open" and token.map:
                    logger.warning(
                        "click:config: line %d of the docstring of option %r makes "
                        "a Markdown heading.",
                        token.map[1],
                        info.key,
                        type=warning_type,
                        subtype=subtype,
                        location=self.get_location(),
                    )


class ClickDomain(StatelessDomain):
    """Register the directives of the `click` namespace:

    - `click:source` which renders a Click CLI source code
    - `click:run` which renders the results of running a Click CLI
    - `click:tree` which walks a Click command tree and renders the full
      `--help` reference for every subcommand, with a summary table on top
    - `click:config` which documents a CLI's `config_schema`: a summary
      table plus one section per option, with types, defaults, and TOML
      examples
    """

    name = "click"
    label = "Click"
    directives: ClassVar[dict] = {
        "source": SourceDirective,
        "run": RunDirective,
        "tree": TreeDirective,
        "config": ConfigDirective,
    }
