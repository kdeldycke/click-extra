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
"""Fixtures, configuration and helpers for tests."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from inspect import cleandoc
from pathlib import Path
from textwrap import indent
from typing import Generator, Sequence

import pytest
from extra_platforms.pytest import skip_windows
from sphinx.application import Sphinx
from sphinx.util.docutils import docutils_namespace

from click_extra.pytest import (  # noqa: F401
    assert_output_regex,
    create_config,
    extra_runner,
    invoke,
)

skip_windows_colors = skip_windows(reason="Click overstrip colors on Windows")
"""Skips color tests on Windows as ``click.testing.invoke`` overzealously strips colors.

See:
- https://github.com/pallets/click/issues/2111
- https://github.com/pallets/click/issues/2110
"""


class FormatType(Enum):
    """Sphinx document format types and their file extensions."""

    RST = ".rst"
    MYST = ".md"


class SphinxAppWrapper:
    """Wrapper around Sphinx application with additional testing methods."""

    def __init__(self, app: Sphinx, format_type: FormatType):
        self.app = app
        self.format_type = format_type

    def __getattr__(self, name):
        """Delegate attribute access to the wrapped Sphinx app."""
        return getattr(self.app, name)

    @classmethod
    def create(
        cls, format_type: FormatType, tmp_path, return_srcdir: bool = False
    ) -> Generator[SphinxAppWrapper | tuple[SphinxAppWrapper, Path], None, None]:
        """Factory method to create a SphinxAppWrapper with given format."""
        srcdir = tmp_path / "source"
        outdir = tmp_path / "build"
        doctreedir = outdir / ".doctrees"
        confdir = srcdir

        srcdir.mkdir()
        outdir.mkdir()

        # Sphinx's configuration is Python code.
        conf = {
            "master_doc": "index",
            "extensions": ["click_extra.sphinx"],
        }
        if format_type == FormatType.MYST:
            conf["extensions"].append("myst_parser")  # type: ignore[attr-defined]
            conf["myst_enable_extensions"] = ["colon_fence"]

        # Write the conf.py file.
        config_content = "\n".join(
            f"{key} = {repr(value)}" for key, value in conf.items()
        )
        (srcdir / "conf.py").write_text(config_content)

        with docutils_namespace():
            app = Sphinx(
                str(srcdir),
                str(confdir),
                str(outdir),
                str(doctreedir),
                "html",
                verbosity=0,
                warning=None,
            )
            wrapper = cls(app, format_type)
            yield (wrapper, srcdir) if return_srcdir else wrapper

    def build_document(self, content: str) -> str | None:
        """Build a Sphinx document with content and return the HTML output.

        Automatically detects the format from the app configuration and uses the
        appropriate file extension (.rst or .md).
        """
        # Determine file extension based on format type.
        file_extension = self.format_type.value

        index_file = Path(self.app.srcdir) / f"index{file_extension}"
        index_file.write_text(content)

        # Build the documentation.
        self.app.build()

        # Read the generated HTML.
        output_file = Path(self.app.outdir) / "index.html"
        if output_file.exists():
            html_output = output_file.read_text()
            assert html_output
            return html_output

        return None

    def generate_test_content(self, test_case: DirectiveTestCase) -> str:
        """Generate content for a test case based on the app's format type."""
        # If document is provided, use it directly.
        if test_case.document is not None:
            return test_case.document

        # Produce click:source and click:run directives in the appropriate format.
        lines = []

        if test_case.source_block:
            if self.format_type == FormatType.RST:
                lines.append(".. click:source::")
                # We need a blank line if there are no options.
                if not test_case.source_block.startswith(":"):
                    lines.append("")
                lines.append(indent(test_case.source_block, " " * 4))
            elif self.format_type == FormatType.MYST:
                lines += [
                    "```{click:source}",
                    test_case.source_block,
                    "```",
                ]

        # Separate directives with a blank line.
        if lines:
            lines.append("")

        if test_case.run_block:
            if self.format_type == FormatType.RST:
                lines.append(".. click:run::")
                # We need a blank line if there are no options.
                if not test_case.run_block.startswith(":"):
                    lines.append("")
                lines.append(indent(test_case.run_block, " " * 4))
            elif self.format_type == FormatType.MYST:
                lines += [
                    "```{click:run}",
                    test_case.run_block,
                    "```",
                ]

        return "\n".join(lines)


@pytest.fixture(params=[FormatType.RST, FormatType.MYST])
def sphinx_app(request, tmp_path):
    """Create a Sphinx application for testing."""
    yield from SphinxAppWrapper.create(request.param, tmp_path)


@pytest.fixture
def sphinx_app_rst(tmp_path):
    """Create a Sphinx application for testing RST format only."""
    yield from SphinxAppWrapper.create(FormatType.RST, tmp_path)


@pytest.fixture
def sphinx_app_myst(tmp_path):
    """Create a Sphinx application for testing MyST format only."""
    yield from SphinxAppWrapper.create(FormatType.MYST, tmp_path)


@pytest.fixture
def sphinx_app_myst_with_include(tmp_path):
    """Create a Sphinx application for testing MyST format with include files."""
    yield from SphinxAppWrapper.create(FormatType.MYST, tmp_path, return_srcdir=True)


@dataclass
class DirectiveTestCase:
    """Test case data for directive tests."""

    name: str
    format_type: FormatType | None = None
    source_block: str | None = None
    run_block: str | None = None
    document: str | None = None
    html_matches: Sequence[str] | str | None = None

    def __post_init__(self):
        if not self.html_matches:
            self.html_matches = tuple()
        elif isinstance(self.html_matches, str):
            self.html_matches = (self.html_matches,)

        # Validate mutually exclusive options.
        if self.document is not None:
            if self.source_block is not None or self.run_block is not None:
                raise ValueError(
                    "DirectiveTestCase: 'document' cannot be used with 'source_block' "
                    "or 'run_block'"
                )
            if self.format_type is None:
                raise ValueError(
                    "DirectiveTestCase: 'format_type' must be specified when using "
                    "'document'"
                )

        # Dedent code fields to remove leading and trailing whitespace.
        if self.source_block:
            self.source_block = cleandoc(self.source_block)
        if self.run_block:
            self.run_block = cleandoc(self.run_block)
        if self.document:
            self.document = cleandoc(self.document)

    def supports_format(self, format_type: FormatType) -> bool:
        """Check if this test case supports the given format type.

        .. todo::
            Get rid of this method, and make the test case provide its own sphinx_app.
        """
        return self.format_type is None or self.format_type == format_type

    def __str__(self) -> str:
        return self.name


# Common HTML fragments for assertions.
HTML = {
    "python_highlight": '<div class="highlight-python notranslate"><div class="highlight"><pre><span></span>',
    "markdown_highlight": '<div class="highlight-markdown notranslate"><div class="highlight"><pre><span></span>',
    "shell_session": '<div class="highlight-ansi-shell-session notranslate"><div class="highlight"><pre><span></span>',
    "sql_highlight": '<div class="highlight-sql notranslate"><div class="highlight"><pre><span></span>',
    "import_click": '<span class="kn">from</span><span class="w"> </span><span class="nn">click</span><span class="w"> </span><span class="kn">import</span> <span class="n">command</span><span class="p">,</span> <span class="n">echo</span>\n',
}


def python_block(*lines: str) -> str:
    """Build expected Python highlight block."""
    return HTML["python_highlight"] + "".join(lines) + "</pre></div>\n"


def shell_block(*lines: str) -> str:
    """Build expected shell session block."""
    return HTML["shell_session"] + "".join(lines) + "</pre></div>\n"


def admonition_block(admonition_type: str, content: str) -> str:
    """Build expected admonition block.

    Args:
        admonition_type: The type of admonition (note, tip, warning, etc.)
        content: The inner HTML content of the admonition (without the title)
    """
    title = admonition_type.capitalize()
    return (
        f'<div class="admonition {admonition_type}">\n'
        f'<p class="admonition-title">{title}</p>\n'
        f"{content}"
        "</div>\n"
    )
