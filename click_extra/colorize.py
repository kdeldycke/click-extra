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
"""Helpers and utilities to apply ANSI coloring to terminal content.

.. note::
    ``_nearest_256`` (24-bit RGB to 256-color quantization) lives here rather than in
    ``pygments.py`` because both ``cli.py`` and ``pygments.py`` need it, and
    ``pygments.py`` is gated behind the optional ``pygments`` extra. Placing it in
    ``colorize.py`` (which has no optional dependencies) keeps the function available
    to the CLI regardless of whether Pygments is installed.
"""

from __future__ import annotations

import os
import re
from configparser import RawConfigParser
from dataclasses import dataclass, field, fields
from enum import Enum
from functools import lru_cache
from gettext import gettext as _

import click
import cloup

from . import ParameterSource, theme as _theme
from .parameters import ExtraOption
from .theme import HelpExtraTheme

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from typing import ClassVar


_CUBE_VALUES = (0, 95, 135, 175, 215, 255)
"""6-level RGB channel values for the 6x6x6 color cube (indices 16-231)."""


def _nearest_256(r: int, g: int, b: int) -> int:
    """Map a 24-bit RGB triplet to the nearest index in the 256-color palette.

    Compares the Euclidean distance in RGB space against both the 6x6x6 color cube
    (indices 16-231) and the grayscale ramp (indices 232-255), returning whichever is
    closer.

    .. seealso::
        `Previous implementation
        <https://github.com/kdeldycke/dotfiles/blob/64d29369/starship-ansi-colors.py>`_
        of full-color to 8-bit quantization.
    """
    # Color cube (indices 16-231).
    ci = [
        min(
            range(6),
            key=lambda i, v=v: abs(v - _CUBE_VALUES[i]),  # type: ignore[misc]
        )
        for v in (r, g, b)
    ]
    cube_idx = 16 + 36 * ci[0] + 6 * ci[1] + ci[2]
    cube_dist = sum((v - _CUBE_VALUES[i]) ** 2 for v, i in zip((r, g, b), ci))

    # Grayscale ramp (indices 232-255).
    gray = round((r + g + b) / 3)
    gi = min(range(24), key=lambda i: abs(gray - (10 * i + 8)))
    gray_idx = 232 + gi
    gray_val = 10 * gi + 8
    gray_dist = sum((v - gray_val) ** 2 for v in (r, g, b))

    return gray_idx if gray_dist < cube_dist else cube_idx


color_envvars = {
    # Colors.
    "COLOR": True,
    "COLORS": True,
    "CLICOLOR": True,
    "CLICOLORS": True,
    "FORCE_COLOR": True,
    "FORCE_COLORS": True,
    "CLICOLOR_FORCE": True,
    "CLICOLORS_FORCE": True,
    # No colors.
    "NOCOLOR": False,
    "NOCOLORS": False,
    "NO_COLOR": False,
    "NO_COLORS": False,
    # LLM agents have no use for ANSI codes.
    "LLM": False,
}
"""List of environment variables recognized as flags to switch color rendering on or
off.

The key is the name of the variable and the boolean value the value to pass to
``--color`` option flag when encountered.

Source:

- https://github.com/pallets/click/issues/558
- https://github.com/pallets/click/issues/1090
- https://github.com/pallets/click/issues/1498
- https://github.com/pallets/click/issues/3022
- https://blog.codemine.be/posts/2026/20260222-be-quiet/
"""


class ColorOption(ExtraOption):
    """A pre-configured option that is adding a ``--color``/``--no-color`` (aliased by
    ``--ansi``/``--no-ansi``) to keep or strip colors and ANSI codes from CLI output.

    This option is eager by default to allow for other eager options (like
    ``--version``) to be rendered colorless.

    .. todo::

        Should we switch to ``--color=<auto|never|always>`` `as GNU tools does
        <https://news.ycombinator.com/item?id=36102377>`_?

        Also see `how the isatty property defaults with this option
        <https://news.ycombinator.com/item?id=36100865>`_, and `how it can be
        implemented in Python <https://bixense.com/clicolors/>`_.

    .. todo::

        Support the `TERM environment variable convention
        <https://news.ycombinator.com/item?id=36101712>`_?
    """

    @staticmethod
    def disable_colors(
        ctx: click.Context,
        param: click.Parameter,
        value: bool,
    ) -> None:
        """Callback disabling all coloring utilities.

        Re-inspect the environment for existence of colorization flags to re-interpret
        the provided value.
        """
        # Collect all colorize flags in environment variables we recognize.
        colorize_from_env = set()
        for var, default in color_envvars.items():
            if var in os.environ:
                # Presence of the variable in the environment without a value encodes
                # for an activation, hence the default to True.
                var_value = os.environ.get(var, "true")
                # `os.environ` is a dict whose all values are strings. Here we normalize
                # these string into booleans. If we can't, we fallback to True, in the
                # same spirit as above.
                var_boolean = RawConfigParser.BOOLEAN_STATES.get(
                    var_value.lower(),
                    True,
                )
                colorize_from_env.add(default ^ (not var_boolean))

        # Re-interpret the provided value against the recognized environment variables.
        if colorize_from_env:
            # The environment can only override the provided value if it comes from
            # the default value or the config file.
            env_takes_precedence = (
                ctx.get_parameter_source("color") == ParameterSource.DEFAULT
            )
            if env_takes_precedence:
                # One env var is enough to activate colorization.
                value = True in colorize_from_env

        # Set the official context color flag. This is used by Click's
        # ``resolve_color_default()`` → ``should_strip_ansi()`` chain in ``echo()``.
        ctx.color = value

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        is_flag=True,
        default=True,
        is_eager=True,
        expose_value=False,
        help=_("Strip out all colors and all ANSI codes from output."),
        **kwargs,
    ) -> None:
        if not param_decls:
            param_decls = ("--color/--no-color", "--ansi/--no-ansi")

        kwargs.setdefault("callback", self.disable_colors)

        super().__init__(
            param_decls=param_decls,
            is_flag=is_flag,
            default=default,
            is_eager=is_eager,
            expose_value=expose_value,
            help=help,
            **kwargs,
        )


@dataclass
class HelpKeywords:
    """Structured collection of keywords extracted from a Click context for
    help screen highlighting.

    Each field corresponds to a semantic category with its own styling.
    """

    cli_names: set[str] = field(default_factory=set)
    subcommands: set[str] = field(default_factory=set)
    command_aliases: set[str] = field(default_factory=set)
    arguments: set[str] = field(default_factory=set)
    long_options: set[str] = field(default_factory=set)
    short_options: set[str] = field(default_factory=set)
    choices: set[str] = field(default_factory=set)
    choice_metavars: set[str] = field(default_factory=set)
    metavars: set[str] = field(default_factory=set)
    envvars: set[str] = field(default_factory=set)
    defaults: set[str] = field(default_factory=set)

    def merge(self, other: HelpKeywords) -> None:
        """Merge another ``HelpKeywords`` into this one.

        Each set field is updated with the corresponding set from ``other``.
        """
        for f in fields(self):
            getattr(self, f.name).update(getattr(other, f.name))

    def subtract(self, other: HelpKeywords) -> None:
        """Remove keywords found in ``other`` from this instance.

        Each set field is difference-updated with the corresponding set from
        ``other``. Mirror of :meth:`merge`.
        """
        for f in fields(self):
            getattr(self, f.name).difference_update(getattr(other, f.name))


class ExtraHelpColorsMixin:  # (Command)??
    """Adds extra-keywords highlighting to Click commands.

    This mixin for ``click.Command``-like classes intercepts the top-level helper-
    generation method to initialize the formatter with dynamic settings. This is
    implemented at this stage so we have access to the global context.
    """

    #: Extra keywords to merge into the auto-collected set. Consumers can set
    #: this attribute on a command instance to inject additional keywords for
    #: help screen highlighting (e.g. placeholder option names like
    #: ``--<manager-id>`` that appear in prose but are not real parameters).
    extra_keywords: HelpKeywords | None = None

    #: Keywords to remove from the auto-collected set. Mirror of
    #: :attr:`extra_keywords`: any string listed here will not be highlighted
    #: even if it was collected from the Click context.
    excluded_keywords: HelpKeywords | None = None

    def collect_keywords(self, ctx: click.Context) -> HelpKeywords:
        """Parse click context to collect option names, choices and metavar keywords.

        Override this method to customize keyword collection. Call ``super()`` and
        mutate the returned ``HelpKeywords`` to extend the default set.
        """
        kw = HelpKeywords()
        subcommand_objs: set[click.Command] = set()

        # Includes the full command path and each ancestor name, so that
        # individual components are highlighted even when interleaved with
        # options (e.g. "repomatic --table-format github sync-uv-lock").
        if ctx.command_path:
            kw.cli_names.add(ctx.command_path)
        ancestor: click.Context | None = ctx
        while ancestor:
            if ancestor.info_name:
                kw.cli_names.add(ancestor.info_name)
            ancestor = ancestor.parent
        command = ctx.command

        # Will fetch command's metavar (i.e. the "[OPTIONS]" after the CLI name in
        # "Usage:") and dig into subcommands to get subcommand_metavar:
        # ("COMMAND1 [ARGS]... [COMMAND2 [ARGS]...]...").
        kw.metavars.update(command.collect_usage_pieces(ctx))

        # Get subcommands and their aliases. Process in listed order for stable
        # and predictable loading, which is important on lazy-loading.
        if isinstance(command, click.Group):
            for sub_id in command.list_commands(ctx):
                subcommand = command.get_command(ctx, sub_id)
                if not subcommand:
                    raise RuntimeError(f"Subcommand {sub_id!r} not found.")
                kw.subcommands.add(sub_id)
                kw.command_aliases.update(getattr(subcommand, "aliases", []))
                # Keep reference to subcommand object for deprecated message
                # collection below.
                subcommand_objs.add(subcommand)

        # Collect options, choices, metavars, envvars, defaults from current
        # command parameters. User-defined help options (e.g. -h, --help) are
        # seeded into the options set.
        options: set[str] = set(ctx.help_option_names)
        # Static methods are qualified with the class name (not ``self``) so
        # ``collect_keywords`` can be called on commands that don't inherit the
        # mixin (used by ``wrap.patch_click`` for third-party CLIs).
        ExtraHelpColorsMixin._collect_params(
            command.get_params(ctx),
            ctx,
            kw,
            options,
        )

        # Collect option names and choices from parent groups. Subcommand
        # docstrings often reference parent options in usage examples (e.g.
        # "myapp --table-format github sub").
        parent_ctx = ctx.parent
        while parent_ctx:
            for param in parent_ctx.command.get_params(parent_ctx):
                if isinstance(param, click.Option) and not param.hidden:
                    options.update(param.opts)
                    options.update(param.secondary_opts)
                    if isinstance(param.type, click.Choice):
                        ExtraHelpColorsMixin._collect_choice_keywords(
                            param,
                            parent_ctx,
                            kw,
                        )
            parent_ctx = parent_ctx.parent

        # Split options into short and long by length heuristic. Short options
        # are no longer than 2 characters like "-D", "/d", "/?", "+w", "-w".
        # XXX We cannot reuse the _short_opts and _long_opts attributes from
        # Click's parser because their values are not passed when the context
        # is updated. So we rely on simple heuristics to guess the category.
        for name in options:
            if len(name) <= 2:
                kw.short_options.add(name)
            else:
                kw.long_options.add(name)

        # Merge consumer-provided extra keywords. Uses ``getattr`` so the
        # method works on commands that don't inherit the mixin.
        extra_kw = getattr(self, "extra_keywords", None)
        if extra_kw is not None:
            kw.merge(extra_kw)

        # Note: excluded_keywords is NOT applied here. It is applied later
        # in highlight_extra_keywords(), after choice metavars have been
        # placeholdered, so that exclusions only affect cross-ref passes.

        return kw

    @staticmethod
    def _collect_choice_keywords(
        param: click.Parameter,
        ctx: click.Context,
        kw: HelpKeywords,
    ) -> None:
        """Collect choice keywords from a ``click.Choice`` parameter.

        When a custom metavar (e.g. ``LEVEL``) replaces the standard
        ``[choice1|choice2]`` rendering, original-case choice strings are
        collected to match developer-written prose (e.g. "Either CRITICAL,
        ERROR, ...") without producing false-positive highlights for common
        English words like "error" and "info".
        """
        assert isinstance(param.type, click.Choice)
        if isinstance(param, click.Option) and param.metavar:
            # Custom metavar hides the normalized choice list. Collect
            # original-case values. This is the first step of Click's own
            # ``normalize_choice()`` before case folding is applied.
            kw.choices.update(
                c.name if isinstance(c, Enum) else str(c) for c in param.type.choices
            )
        else:
            # Standard metavar: collect the normalized forms that
            # match what Click renders in ``[choice1|choice2]``.
            kw.choices.update(
                param.type.normalize_choice(c, ctx) for c in param.type.choices
            )
            # Also collect the rendered metavar string (e.g.
            # ``[json|xml|csv]``) so it can be styled and placeholdered
            # before cross-ref highlighting. This protects choices that
            # appear in ``excluded_keywords`` from losing their
            # highlight inside their own metavar.
            kw.choice_metavars.add(param.make_metavar(ctx=ctx))

    @staticmethod
    def _collect_params(
        params: list[click.Parameter],
        ctx: click.Context,
        kw: HelpKeywords,
        options: set[str],
    ) -> None:
        """Extract keywords from a list of parameters into ``kw`` and ``options``."""
        for param in params:
            # Ignore hidden options that are not meant to be displayed.
            if isinstance(param, click.Option) and param.hidden:
                continue

            # Only collect option names from actual Option parameters, not from
            # Arguments. An Argument's opts contains the bare parameter name
            # (e.g. "keys") which would pollute the option keywords and
            # interfere with highlighting of real options like "--list-keys".
            if isinstance(param, click.Option):
                options.update(param.opts)
                options.update(param.secondary_opts)
            elif isinstance(param, click.Argument):
                # Collect argument metavars (e.g. "MY_ARG") as a distinct
                # category from option metavars.
                kw.arguments.add(param.make_metavar(ctx=ctx))

            # Only Choice and DateTime types produce their own structured
            # metavar (with delimiters like brackets and pipes). All other
            # types fall back to a plain uppercased name (e.g. TEXT, INTEGER).
            if isinstance(param.type, click.Choice):
                ExtraHelpColorsMixin._collect_choice_keywords(param, ctx, kw)
            elif isinstance(param.type, click.DateTime):
                # Highlight each datetime format string as a choice.
                kw.choices.update(param.type.formats)
            elif not isinstance(param, click.Argument):
                # Argument metavars are collected in the arguments set.
                kw.metavars.add(param.make_metavar(ctx=ctx))

            # A user-provided metavar (e.g. ``metavar="LEVEL"``) is always
            # worth highlighting, even for Choice/DateTime types.
            if param.metavar and not isinstance(param, click.Argument):
                kw.metavars.add(param.metavar)

            if param.envvar:
                if isinstance(param.envvar, str):
                    kw.envvars.add(param.envvar)
                else:
                    kw.envvars.update(param.envvar)

            if isinstance(param, click.Option):
                default_string = param.get_help_extra(ctx).get("default")
                if default_string:
                    kw.defaults.add(default_string)

    def get_help(self, ctx: click.Context) -> str:
        """Replace default formatter by our own."""
        ctx.formatter_class = HelpExtraFormatter
        return super().get_help(ctx)  # type: ignore[no-any-return,misc]

    @staticmethod
    def _collect_excluded_keywords(ctx: click.Context) -> HelpKeywords | None:
        """Merge ``excluded_keywords`` from the current command and all ancestors.

        Mirrors the parent-context traversal that collects parent choices in
        :meth:`collect_keywords`. Returns a fresh :class:`HelpKeywords` so that
        no command's original ``excluded_keywords`` is mutated.
        """
        excluded: HelpKeywords | None = None
        cmd_ctx: click.Context | None = ctx
        while cmd_ctx:
            cmd_excluded = getattr(cmd_ctx.command, "excluded_keywords", None)
            if cmd_excluded is not None:
                if excluded is None:
                    excluded = HelpKeywords()
                excluded.merge(cmd_excluded)
            cmd_ctx = cmd_ctx.parent
        return excluded

    def format_help(self, ctx: click.Context, formatter: HelpExtraFormatter) -> None:
        """Feed our custom formatter instance with the keywords to highlight."""
        formatter.keywords = self.collect_keywords(ctx)
        formatter.excluded_keywords = self._collect_excluded_keywords(ctx)
        super().format_help(ctx, formatter)  # type: ignore[misc]


@lru_cache(maxsize=512)
def _escape_for_help_screen(text: str) -> str:
    """Prepares a string to be used in a regular expression for matches in help screen.

    Applies `re.escape <https://docs.python.org/3/library/re.html#re.escape>`_, then
    accounts for long strings being wrapped on multiple lines and padded with spaces to
    fit the columnar layout.

    It allows for:

    - additional number of optional blank characters (line-returns, spaces, tabs, ...)
      after a dash, as the help renderer is free to wrap strings after a dash.
    - a space to be replaced by any number of blank characters.
    """
    return re.escape(text).replace("-", "-\\s*").replace("\\ ", "\\s+")


class HelpExtraFormatter(cloup.HelpFormatter):
    """Extends Cloup's custom HelpFormatter to highlights options, choices, metavars and
    default values.

    This is being discussed for upstream integration at:

    - https://github.com/janluke/cloup/issues/97
    - https://github.com/click-contrib/click-help-colors/issues/17
    - https://github.com/janluke/cloup/issues/95
    """

    theme: HelpExtraTheme

    def __init__(self, *args, **kwargs) -> None:
        """Forces theme to our default.

        Also transform Cloup's standard ``HelpTheme`` to our own ``HelpExtraTheme``.

        Reads :data:`click_extra.theme.default_theme` through the ``_theme`` module
        reference so :class:`~click_extra.theme.ThemeOption` reassignments are
        picked up at call time.
        """
        theme = kwargs.get("theme", _theme.default_theme)
        if not isinstance(theme, HelpExtraTheme):
            theme = _theme.default_theme.with_(**theme._asdict())
        kwargs["theme"] = theme
        super().__init__(*args, **kwargs)

    keywords: HelpKeywords = HelpKeywords()
    excluded_keywords: HelpKeywords | None = None

    #: Matches range expressions like ``0<=x<=9``, ``x>=1024``, ``0<=x<100``.
    _range_re: ClassVar[re.Pattern] = re.compile(r"(?:\S+(?:<|<=))?x(?:<|<=|>|>=)\S+")
    _bracket_re: ClassVar[re.Pattern] = re.compile(
        r"(  )"  # 2 spaces (column or description spacing).
        r"\["  # Opening bracket.
        r"("  # Capture the bracket content.
        r"(?:env\s+var:|default:|required"  # Must start with a recognized label
        r"|(?:\S+(?:<|<=))?x(?:<|<=|>|>=)\S+)"  # or a range expression.
        r"[^\]]*"  # Followed by any non-] characters.
        r")"
        r"\]",  # Closing bracket.
        re.DOTALL,
    )
    _sep_re: ClassVar[re.Pattern] = re.compile(r";\s+")
    _envvar_re: ClassVar[re.Pattern] = re.compile(r"(env\s+var:\s+)(.*)", re.DOTALL)
    _default_re: ClassVar[re.Pattern] = re.compile(r"(default:\s+)(.*)", re.DOTALL)

    #: Matches ``(Deprecated)``, ``(DEPRECATED)``, ``(DEPRECATED: reason)``,
    #: etc., regardless of casing. Catches both Click-native deprecated markers
    #: and manually-added ones in help strings.
    _deprecated_re: ClassVar[re.Pattern] = re.compile(
        r"\(deprecated(?::\s[^)]+)?\)",
        re.IGNORECASE,
    )

    def _style_bracket_fields(self, match: re.Match) -> str:
        """Style a trailing ``[env var: ...; default: ...; ...]`` block.

        Parses the bracket content by splitting on ``;`` separators and
        matching each field by its label prefix. Applied post-wrapping because
        Click's text wrapper splits lines after ``get_help_record()`` returns,
        which would break pre-styled ANSI codes.
        """
        prefix = match.group(1)
        content = match.group(2)

        # Split on semicolons, keeping the separators.
        parts = re.split(r"(;\s+)", content)

        styled: list[str] = []
        for part in parts:
            # Separator between fields.
            if self._sep_re.fullmatch(part):
                styled.append(self.theme.bracket(part))
            # Environment variable field.
            elif m := self._envvar_re.match(part):
                styled.append(
                    self.theme.bracket(m.group(1)) + self.theme.envvar(m.group(2))
                )
            # Default value field.
            elif m := self._default_re.match(part):
                styled.append(
                    self.theme.bracket(m.group(1)) + self.theme.default(m.group(2))
                )
            # Required label.
            elif part == "required":
                styled.append(self.theme.required(part))
            # Range expression.
            elif self._range_re.fullmatch(part):
                styled.append(self.theme.range_label(part))
            # Fallback: style as generic bracket content.
            else:
                styled.append(self.theme.bracket(part))

        return (  # type: ignore[no-any-return]
            prefix + self.theme.bracket("[") + "".join(styled) + self.theme.bracket("]")
        )

    def _style_choice_metavar(self, metavar: str, choices: set[str]) -> str | None:
        """Style individual choices inside a choice metavar string.

        Takes a rendered metavar like ``[json|xml|csv]`` and returns a styled
        version where each known choice is wrapped with ``theme.choice``.
        Returns ``None`` if ``metavar`` does not look like a choice list.
        """
        # Strip the surrounding brackets.
        if not (metavar.startswith("[") and metavar.endswith("]")):
            return None
        inner = metavar[1:-1]
        parts = inner.split("|")
        styled_parts = [
            self.theme.choice(part) if part in choices else part for part in parts
        ]
        return "[" + "|".join(styled_parts) + "]"

    @staticmethod
    def _add_placeholder(styled: str, store: dict[str, str]) -> str:
        """Register a styled fragment as a null-byte placeholder.

        Returns the placeholder key. Used to protect already-styled regions
        from subsequent regex passes.
        """
        key = f"\x00B{len(store)}\x00"
        store[key] = styled
        return key

    def highlight_extra_keywords(self, help_text: str) -> str:
        """Highlight extra keywords in help screens based on the theme.

        Uses the ``highlight()`` function for all keyword categories. Each
        category is processed as a batch of regex patterns with a single styling
        function, which handles overlapping matches and prevents double-styling.
        """
        kw = self.keywords

        # Highlight deprecated messages. Uses a case-insensitive regex to catch
        # both Click-native "(DEPRECATED)" markers and manually-added variants
        # like "(Deprecated)" in help strings.
        help_text = highlight(help_text, [self._deprecated_re], self.theme.deprecated)

        # Highlight subcommand names. Requires 2-space indentation as a
        # leading boundary.
        if kw.subcommands:
            help_text = highlight(
                help_text,
                (
                    re.compile(rf"(?<=  ){re.escape(name)}(?=\s)")
                    for name in sorted(kw.subcommands, key=len, reverse=True)
                ),
                self.theme.subcommand,
            )

        # Highlight command aliases inside parenthetical groups like
        # "(lock, freeze, snapshot)". Aliases are preceded by "(" or ", "
        # and followed by "," or ")".
        if kw.command_aliases:
            help_text = highlight(
                help_text,
                (
                    re.compile(rf"(?<=[(, ]){re.escape(name)}(?=[,)])")
                    for name in sorted(kw.command_aliases, key=len, reverse=True)
                ),
                self.theme.subcommand,
            )

        # Style trailing bracket fields [env var: ...; default: ...; ...].
        # This must happen post-wrapping because Click's text wrapper splits
        # lines after get_help_record() returns, which would break pre-styled
        # ANSI codes.
        #
        # To prevent cross-reference highlighting from restyling keywords that
        # appear inside bracket field content (e.g. a choice value like
        # "outline" within a default value "rounded-outline"), we replace each
        # styled bracket field with a null-byte placeholder, run all cross-ref
        # passes on the placeholder text, then restore the styled fields.
        bracket_placeholders: dict[str, str] = {}

        def _bracket_to_placeholder(match: re.Match) -> str:
            return self._add_placeholder(
                self._style_bracket_fields(match), bracket_placeholders
            )

        help_text = self._bracket_re.sub(_bracket_to_placeholder, help_text)

        # Style and placeholder choice metavars (e.g. ``[json|xml|csv]``)
        # before applying excluded_keywords and running cross-ref passes.
        # This ensures that choices excluded from cross-ref highlighting
        # (like "version") are still highlighted inside their own metavar.
        for metavar_str in kw.choice_metavars:
            styled = self._style_choice_metavar(metavar_str, kw.choices)
            if styled is None:
                continue
            pattern = re.compile(_escape_for_help_screen(metavar_str))
            help_text = pattern.sub(
                lambda m, s=styled: self._add_placeholder(s, bracket_placeholders),  # type: ignore[misc]
                help_text,
            )

        # Apply excluded_keywords after metavar placeholdering so that
        # exclusions only affect the cross-ref passes below.
        if self.excluded_keywords is not None:
            kw.subtract(self.excluded_keywords)

        # The remaining passes search free-form text (descriptions, docstrings)
        # for option names, choices, arguments, metavars and CLI names.
        # Cross-reference highlighting can be disabled via the theme to avoid
        # over-interpretation in help text that references external identifiers.
        if self.theme.cross_ref_highlight:
            # Highlight CLI names and commands.
            if kw.cli_names:
                help_text = highlight(
                    help_text,
                    (
                        re.compile(rf"(?<=\s){re.escape(name)}(?=\s)")
                        for name in sorted(kw.cli_names, key=len, reverse=True)
                    ),
                    self.theme.invoked_command,
                )

            # Highlight options (long and short combined). Per-keyword lookbehind
            # excludes the option's own leading symbol to prevent matching repeated
            # prefixes (e.g. "---debug" should not match "--debug").
            all_options = sorted(
                kw.long_options | kw.short_options, key=len, reverse=True
            )
            if all_options:
                help_text = highlight(
                    help_text,
                    (
                        re.compile(
                            rf"(?<=[^\w{re.escape(kw[0])}])"
                            rf"{_escape_for_help_screen(kw)}"
                            rf"(?=[^\w\-])"
                        )
                        for kw in all_options
                    ),
                    self.theme.option,
                )

            # Highlight other keywords, which are expected to be separated by
            # any character but word characters.
            for keywords, style_func in (
                # Arguments before metavars: argument names like MY_ARG are a
                # subset of metavars, so highlighting them first with a distinct
                # style takes priority.
                (kw.arguments, self.theme.argument),
                # Choices are already featured in metavars, so we process them
                # before metavars to avoid double-highlighting.
                (kw.choices, self.theme.choice),
                (kw.metavars, self.theme.metavar),
            ):
                if keywords:
                    # Transform keywords into regex patterns.
                    patterns = (
                        # Negative lookbehind rejects matches preceded by:
                        # - a word character (\w),
                        # - a dot: "pyproject.toml" (\.),
                        # - a hyphen: "rounded-outline" (\-),
                        # - a slash: "https://github.com" (\/),
                        # - an exclamation mark: "[!WARNING]" (!),
                        # - an ANSI escape: already-styled text (\x1b).
                        # Negative lookahead rejects matches followed by:
                        # - a word character (\w),
                        # - a hyphen: "github-actions" (\-).
                        re.compile(
                            rf"(?<![\w\.\x1b\-/!])"
                            rf"{_escape_for_help_screen(keyword)}"
                            rf"(?![\w\-])"
                        )
                        for keyword in sorted(keywords, reverse=True)
                    )
                    help_text = highlight(
                        content=help_text,
                        patterns=patterns,
                        styling_func=style_func,
                    )

        # Restore styled bracket fields.
        for key, styled in bracket_placeholders.items():
            help_text = help_text.replace(key, styled)

        return help_text

    def getvalue(self) -> str:
        """Wrap original `Click.HelpFormatter.getvalue()` to force extra-colorization on
        rendering."""
        help_text = super().getvalue()
        return self.highlight_extra_keywords(help_text)


def highlight(
    content: str,
    patterns: Iterable[str | re.Pattern] | str | re.Pattern,
    styling_func: Callable,
    ignore_case: bool = False,
) -> str:
    """Highlights parts of the ``content`` that matches ``patterns``.

    Takes care of overlapping parts within the ``content``, so that the styling function
    is applied only once to each contiguous range of matching characters.

    .. todo::
        Support case-foldeing, so we can have the ``Straße`` string matching the
        ``Strasse`` content.

        This could be tricky as it messes with string length and characters index, which
        our logic relies on.

        .. danger::
            Roundtrip through lower-casing/upper-casing is a can of worms, because some
            characters change length when their case is changed:

            - `Unicode roundtrip-unsafe characters
              <https://gist.github.com/rendello/4d8266b7c52bf0e98eab2073b38829d9>`_
            - `Unicode codepoints expanding or contracting on case changes
              <https://gist.github.com/rendello/d37552507a389656e248f3255a618127>`_
    """
    # Normalize input to a set of patterns.
    if isinstance(patterns, (str, re.Pattern)):
        pattern_list = {patterns}
    else:
        pattern_list = set(patterns)

    # Set of character indices flagged for highlighting.
    matched_indices: set[int] = set()

    # Normalize patterns into regular expressions and find matches.
    for pattern in pattern_list:
        # Pattern is already a compiled regex.
        if isinstance(pattern, re.Pattern):
            regex = pattern
        # Treat as literal string and escape for regex.
        elif isinstance(pattern, str):
            regex = re.compile(re.escape(pattern), re.IGNORECASE if ignore_case else 0)
        else:
            raise TypeError(f"Unsupported pattern type: {pattern!r}")

        # Force IGNORECASE flag if not already compiled with it.
        if ignore_case and not (regex.flags & re.IGNORECASE):
            regex = re.compile(regex.pattern, regex.flags | re.IGNORECASE)

        # Find all matches, including overlapping ones. Because re.search()
        # returns only the first match, we skip ahead one character past the
        # start of each match to find overlapping occurrences.
        start_pos = 0
        while start_pos < len(content):
            match = regex.search(content, start_pos)
            if not match:
                break

            start_idx = match.start()
            end_idx = match.end()

            # Skip zero-length matches (e.g. from pure lookbehind/lookahead).
            if start_idx >= end_idx:
                start_pos = start_idx + 1
                continue

            matched_indices.update(range(start_idx, end_idx))
            start_pos = start_idx + 1

    if not matched_indices:
        return content

    # Build the styled string in one pass: contiguous runs of matched or
    # unmatched characters are grouped, and only matched runs are styled.
    parts: list[str] = []
    in_match = 0 in matched_indices
    run_start = 0

    for i in range(1, len(content) + 1):
        current_in_match = i in matched_indices if i < len(content) else not in_match
        if current_in_match != in_match:
            segment = content[run_start:i]
            parts.append(styling_func(segment) if in_match else segment)
            run_start = i
            in_match = current_in_match

    # Flush the last run.
    if run_start < len(content):
        segment = content[run_start:]
        parts.append(styling_func(segment) if in_match else segment)

    return "".join(parts)
