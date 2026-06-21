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
"""Resolve whether terminal output should be colored.

Owns the ``--color[=WHEN]`` and ``--no-color`` options, the color environment
variables (``NO_COLOR``, ``FORCE_COLOR``, ``CLICOLOR``, and friends), and the
tri-state WHEN resolution. The actual styling lives elsewhere:
:mod:`click_extra.styling` (the ``Style`` primitive), :mod:`click_extra.theme`
(palettes), and :mod:`click_extra.highlight` (help-screen rendering).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from configparser import RawConfigParser
from contextlib import contextmanager
from gettext import gettext as _

import click

from . import ParameterSource
from .parameters import ExtraOption

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any, ClassVar

    from click.parser import _OptionParser


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


COLOR_DISABLING_TERMS = frozenset({"dumb", "unknown"})
"""``TERM`` values marking a terminal too limited for ANSI niceties.

A ``dumb`` or ``unknown`` terminal advertises neither SGR color nor the
cursor-control codes (carriage return, clear-line) an animation relies on, so both
Click Extra's color resolution (:func:`resolve_color_env`) and the spinner's
animation gating (:meth:`click_extra.spinner.Spinner._resolve_enabled`) treat these
two values as a hard opt-out. Sharing the set keeps the color and animation axes from
drifting apart.

An *unset* ``TERM`` is deliberately excluded: it is common on legitimately
color-capable streams (subprocesses, some IDEs) where defaulting to off would be a
regression. This matches `Rich
<https://github.com/Textualize/rich/blob/master/rich/console.py>`_, which keys its
own dumb-terminal detection on the same two values and not on absence.
"""


def resolve_color_env() -> bool | None:
    """Reconcile the recognized color environment variables into a tri-state.

    Inspects every variable listed in :data:`color_envvars` and returns:

    - ``True`` if at least one *enabling* variable (``FORCE_COLOR``, ``CLICOLOR``, …)
      is set. Enabling wins over disabling, so a single one is enough to keep colors.
    - ``False`` if only *disabling* variables (``NO_COLOR``, ``LLM``, …) are set.
    - ``None`` when no recognized variable is present, leaving the caller free to
      apply its own default (typically ``auto``).

    A bare variable (no value), or one whose value cannot be parsed as a boolean,
    counts as activation, in the permissive spirit of the `NO_COLOR
    <https://no-color.org>`_ and `FORCE_COLOR <https://force-color.org>`_ conventions.

    A ``dumb`` or ``unknown`` ``TERM`` (see :data:`COLOR_DISABLING_TERMS`) casts a
    disabling vote as well, so a terminal that cannot render ANSI is treated as
    color-off even when it still reports as a TTY. Because enabling wins, an explicit
    ``FORCE_COLOR`` stays authoritative over it.
    """
    enabling = set()
    for var, enables in color_envvars.items():
        if var in os.environ:
            # Presence without a value encodes an activation, hence the default to
            # "true"; an unparsable value falls back to True in the same spirit.
            raw_value = os.environ.get(var, "true")
            parsed = RawConfigParser.BOOLEAN_STATES.get(raw_value.lower(), True)
            enabling.add(enables ^ (not parsed))
    # A dumb/unknown terminal cannot render ANSI color: cast a disabling vote that an
    # explicit enabling variable still overrides, but which beats the auto default
    # when no recognized color variable is set.
    if os.environ.get("TERM", "").lower() in COLOR_DISABLING_TERMS:
        enabling.add(False)
    if not enabling:
        return None
    return True in enabling


@contextmanager
def forced_color() -> Iterator[None]:
    """Force ANSI color while Click Extra captures CLI text for documentation.

    Click Extra renders CLI help and output into docs from both the MkDocs plugin
    (:mod:`click_extra.mkdocs`) and the Sphinx directives
    (:mod:`click_extra.sphinx.click`). During a build that output is a pipe, not a TTY,
    so the underlying renderers strip their escape codes. Two independent color systems
    have to be defeated:

    - Click's, gated by ``should_strip_ansi`` / ``ctx.color`` (what ``click.echo`` and
      the Click and Click Extra help formatters consult). Sphinx's runner additionally
      flips this one with ``click.testing.CliRunner(color=True)``.
    - Rich's, gated by ``rich.console.Console.is_terminal``, which ignores the above and
      reads ``FORCE_COLOR`` (https://force-color.org). This is the system ``rich-click``
      uses, and ``color=True`` never reaches it.

    ``FORCE_COLOR`` is the only signal common to both systems (Rich reads it directly;
    Click Extra recognizes it through :data:`color_envvars`), so it is the lever we set
    here. We also clear the color-disabling variables Click Extra recognizes
    (``NO_COLOR``, ``LLM``, …) so an opt-out in the build environment cannot suppress the
    rendering, and pin ``COLORTERM=truecolor`` so the branded 24-bit themes render at
    full depth instead of being quantized to the 256-color palette (see
    :func:`~click_extra.styling.supports_truecolor`). The previous environment is
    restored on exit, so the override never leaks beyond a single capture.
    """
    disabling = [var for var, enables in color_envvars.items() if not enables]
    saved = {
        var: os.environ.get(var) for var in ("FORCE_COLOR", "COLORTERM", *disabling)
    }
    os.environ["FORCE_COLOR"] = "1"
    os.environ["COLORTERM"] = "truecolor"
    for var in disabling:
        os.environ.pop(var, None)
    try:
        yield
    finally:
        for var, value in saved.items():
            if value is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = value


COLOR_WHEN = ("auto", "always", "never")
"""GNU-canonical tri-state values accepted by ``--color=<WHEN>``.

``auto`` defers to terminal detection, ``always`` forces ANSI on, ``never`` strips
it. See the `GNU coding standards
<https://www.gnu.org/prep/standards/html_node/_002d_002dcolor.html>`_ and `this
discussion <https://news.ycombinator.com/item?id=36102377>`_.
"""


_WHEN_TO_TRISTATE: dict[str, bool | None] = {
    "auto": None,
    "always": True,
    "never": False,
}
"""Map each :data:`COLOR_WHEN` choice to the ``ctx.color`` value it produces.

``None`` lets Click auto-detect colorization from the output stream's TTY status,
``True`` keeps ANSI codes, ``False`` strips them.
"""


COLOR_WHEN_ALIASES: dict[str, str] = {
    # ``always`` synonyms.
    "yes": "always",
    "force": "always",
    # ``never`` synonyms.
    "no": "never",
    "none": "never",
    # ``auto`` synonyms.
    "tty": "auto",
    "if-tty": "auto",
}
"""GNU coreutils synonyms accepted as hidden aliases for each :data:`COLOR_WHEN`
value.

GNU ``ls`` accepts ``yes``/``force`` for ``always``, ``no``/``none`` for ``never``
and ``tty``/``if-tty`` for ``auto``, alongside the three canonical spellings (see
:data:`COLOR_WHEN`). Click Extra mirrors that leniency but keeps the synonyms out of
``--help`` output, error messages and shell completion, which only ever advertise
:data:`COLOR_WHEN`.
"""


_COLOR_WHEN_LOOKUP = {**{when: when for when in COLOR_WHEN}, **COLOR_WHEN_ALIASES}
"""Lowercase-keyed map folding every accepted spelling to its canonical
:data:`COLOR_WHEN` value.

Combines the identity mapping of the canonical values with
:data:`COLOR_WHEN_ALIASES`, for the case-insensitive lookup in
:meth:`ColorWhenChoice.convert`.
"""


_COLOR_CLI_OVERRIDE_KEY = "click_extra.color_cli_override"
"""Context meta key flagging an explicit ``--no-color`` on the command line.

Set by :meth:`NoColorOption.set_no_color` and read by :meth:`ColorOption.set_color` so
an explicit negative alias outranks the color environment variables, which may only
override the built-in default.
"""


class ColorWhenChoice(click.Choice):
    """:class:`click.Choice` over :data:`COLOR_WHEN` that also accepts the hidden GNU
    synonyms (:data:`COLOR_WHEN_ALIASES`) and native configuration booleans, folding
    them to a canonical value before validation.

    Only the three canonical :data:`COLOR_WHEN` values reach ``--help``, error
    messages and shell completion, because the public ``choices`` stay canonical.
    Synonyms and booleans are accepted silently and normalized, so downstream code
    (:meth:`ColorOption.set_color`, :data:`_WHEN_TO_TRISTATE`) only ever sees
    ``auto``, ``always`` or ``never``.

    Matching is case-insensitive and whitespace-tolerant, which also makes the
    canonical values forgiving, such as ``--color=ALWAYS``.
    """

    def convert(
        self,
        value: Any,
        param: click.Parameter | None,
        ctx: click.Context | None,
    ) -> Any:
        """Fold synonyms and booleans to canonical, then defer to ``click.Choice``.

        A native :class:`bool` only reaches this method from a structured
        configuration file: TOML or JSON booleans, or YAML's coercion of
        ``yes``/``no``/``on``/``off``/``true``/``false``. ``True`` maps to
        ``always`` and ``False`` to ``never``, consistent with a bare ``--color``
        and ``--no-color``. The command line always delivers strings, so this never
        turns ``--color=true`` into a valid CLI spelling.

        .. caution::
            A configuration boolean therefore diverges from git's `color.ui
            <https://git-scm.com/docs/git-config>`_, where ``true`` means ``auto``.
            Click Extra keeps ``true`` equal to ``always`` so the ``yes`` string
            synonym and YAML's coercion of ``yes`` to ``True`` resolve identically
            across file formats.
        """
        if isinstance(value, bool):
            value = "always" if value else "never"
        elif isinstance(value, str):
            value = _COLOR_WHEN_LOOKUP.get(value.strip().lower(), value)
        return super().convert(value, param, ctx)


class ColorOption(ExtraOption):
    """A pre-configured ``--color[=WHEN]`` tri-state option.

    Mirrors the `GNU convention
    <https://www.gnu.org/prep/standards/html_node/_002d_002dcolor.html>`_: ``WHEN`` is
    one of :data:`COLOR_WHEN` (``auto``, ``always`` or ``never``), and a bare
    ``--color`` (no value) means ``always``. The negative alias ``--no-color`` is
    carried by the separate :class:`NoColorOption`, because Click forbids attaching
    ``/--no-x`` secondary flags to a value option.

    The resolved tri-state lands on ``ctx.color``, the Click-standard attribute that
    ``echo()`` reads through its ``resolve_color_default()`` → ``should_strip_ansi()``
    chain: ``True`` keeps ANSI codes, ``False`` strips them, ``None`` (``auto``) defers
    to the output stream's TTY status.

    This option is eager by default, so other eager options (like ``--version``) are
    rendered with the resolved color state.

    .. note::
        ``--color`` is deliberately not wired to an ``envvar``. The color environment
        variables (``NO_COLOR``, ``FORCE_COLOR``, …) are read manually through
        :func:`resolve_color_env`. Letting Click manage them would dump the whole
        :data:`color_envvars` set into the ``--show-params`` env-var column, and only
        bind one variable per option anyway.
    """

    _gnu_optional_value: ClassVar[bool] = True
    """Marks the option for GNU-style optional-argument parsing.

    Read by :meth:`add_to_parser` to make a bare ``--color`` resolve to
    ``flag_value`` instead of swallowing the following token.
    """

    def add_to_parser(self, parser: _OptionParser, ctx: click.Context) -> None:
        """Register the option, then teach the parser GNU optional-argument rules.

        Click's optional-value parser binds ``--color`` to the next token whenever it
        does not look like an option, so ``mycli --color subcommand`` would consume
        ``subcommand`` as the color value and fail. GNU instead binds an optional
        argument only when it is attached with ``=``.

        This wraps the parser's long-option matcher so a bare ``--color``
        replays as ``--color=<flag_value>`` (``always``) and leaves the following
        argument untouched, while ``--color=<when>`` keeps working. The wrapper stays
        inert for every option that does not carry :attr:`_gnu_optional_value`, so it
        is safe to install on the shared parser.
        """
        super().add_to_parser(parser, ctx)

        wrapped = parser._match_long_opt

        def _match_long_opt(opt, explicit_value, state):
            if explicit_value is None:
                parsed = parser._long_opt.get(opt)
                if parsed is not None and getattr(
                    parsed.obj,
                    "_gnu_optional_value",
                    False,
                ):
                    # Replay as if the user had typed --color=<flag_value>.
                    wrapped(opt, parsed.obj.flag_value, state)
                    return
            wrapped(opt, explicit_value, state)

        parser._match_long_opt = _match_long_opt  # type: ignore[method-assign]

    def set_color(
        self,
        ctx: click.Context,
        param: click.Parameter,
        value: str,
    ) -> None:
        """Resolve ``--color=<WHEN>`` against the environment and pin ``ctx.color``.

        Precedence, highest first:

        #. An explicit ``--color`` on the command line.
        #. The color environment variables, but only when the value comes from the
           built-in default. A configuration file or ``--accessible`` (both seen here
           as a non-``DEFAULT`` source) therefore wins over the environment, matching
           :class:`~click_extra.accessibility.AccessibleOption`.
        #. A color state already pinned by ``--no-color``, a forced
           test runner, or an explicit ``Context(color=...)``: preserved when this
           option only resolves to ``auto`` from its default.
        #. The ``auto`` default, leaving ``ctx.color`` at ``None`` for TTY detection.
        """
        when = value
        source = ctx.get_parameter_source("color")

        # The environment can only override a pure built-in default, never a value
        # coming from the command line, a configuration file or --accessible. An
        # explicit --no-color (recorded by NoColorOption) is a
        # command-line choice and therefore outranks the environment too.
        if source == ParameterSource.DEFAULT and not ctx.meta.get(
            _COLOR_CLI_OVERRIDE_KEY,
        ):
            env_color = resolve_color_env()
            if env_color is not None:
                ctx.color = env_color
                return

        tristate = _WHEN_TO_TRISTATE[when]

        # "auto" defers to TTY detection. Do not overwrite a color state already
        # pinned upstream (--no-color, a forced runner, Context(color=...)) unless the
        # user explicitly spelled out --color=auto on the command line.
        if (
            tristate is None
            and source != ParameterSource.COMMANDLINE
            and ctx.color is not None
        ):
            return

        ctx.color = tristate

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        is_flag=False,
        flag_value="always",
        default="auto",
        is_eager=True,
        expose_value=False,
        help=_("Colorize the output. A bare --color is the same as --color=always."),
        **kwargs,
    ) -> None:
        if not param_decls:
            param_decls = ("--color",)

        kwargs.setdefault("callback", self.set_color)
        kwargs.setdefault("type", ColorWhenChoice(COLOR_WHEN))

        super().__init__(
            param_decls=param_decls,
            is_flag=is_flag,
            flag_value=flag_value,
            default=default,
            is_eager=is_eager,
            expose_value=expose_value,
            help=help,
            **kwargs,
        )


class NoColorOption(ExtraOption):
    """``--no-color`` flag that forces ``--color=never``.

    Click rejects ``/--no-x`` secondary flags on a value option, so the negative
    alias of the tri-state :class:`ColorOption` cannot live on it and is provided
    here as a standalone boolean flag. When set, it pins ``ctx.color`` to ``False``;
    when absent it is a no-op, leaving the resolution to :class:`ColorOption`.

    Shown on its own line directly below ``--color`` (mirroring ``--no-config``
    below ``--config``), since every other negative in the default option set is
    visible too. Eager by default, like :class:`ColorOption`, so the color state is
    settled before other eager options render.
    """

    def set_no_color(
        self,
        ctx: click.Context,
        param: click.Parameter,
        value: bool,
    ) -> None:
        """Force ``ctx.color`` off when a negative alias is passed; no-op otherwise."""
        if value:
            ctx.color = False
            # Flag the explicit choice so ColorOption keeps the environment from
            # overriding it (the environment may only override the built-in default).
            ctx.meta[_COLOR_CLI_OVERRIDE_KEY] = True

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        is_flag=True,
        default=False,
        is_eager=True,
        expose_value=False,
        help=_("Disable colorization (alias of --color=never)."),
        **kwargs,
    ) -> None:
        if not param_decls:
            param_decls = ("--no-color",)

        kwargs.setdefault("callback", self.set_no_color)

        super().__init__(
            param_decls=param_decls,
            is_flag=is_flag,
            default=default,
            is_eager=is_eager,
            expose_value=expose_value,
            help=help,
            **kwargs,
        )
