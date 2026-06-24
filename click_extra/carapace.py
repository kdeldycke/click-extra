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
"""Export a Click command tree as a Carapace completion spec.

`Carapace <https://carapace.sh>`_ is a multi-shell completion engine: a single
spec file drives identical completions across Bash, Zsh, Fish, Nushell,
PowerShell, Elvish, Xonsh, Oil and more. This module walks a Click/Cloup command
tree and serializes it to the YAML `carapace-spec
<https://github.com/carapace-sh/carapace-spec>`_ format, answering the request
for native Carapace support in `Click issue #3188
<https://github.com/pallets/click/issues/3188>`_ (closed as out of scope for core
Click, redirected here).

Two completion strategies cooperate:

- **Static.** Choices, file/directory operands and the command hierarchy are
  inlined straight into the spec. These complete with no process launch and work
  in every shell Carapace supports, which is the advantage a spec has over
  Carapace's existing bridge to a single shell's native Click completion.

- **Dynamic.** A parameter carrying a custom ``shell_complete`` (a callback, or a
  :class:`~click.ParamType` that overrides
  :meth:`~click.ParamType.shell_complete`) cannot be frozen into the spec, so its
  action calls back into the CLI through Carapace's shell macro. The callback
  reuses Click's own completion machinery via :class:`CarapaceComplete`.

.. note::
    Dynamic completion needs the :class:`CarapaceComplete` class registered in
    the target process, which happens on ``import click_extra``. A CLI built with
    Click Extra gets it for free; a plain Click CLI would have to import
    ``click_extra`` for the dynamic callback to resolve. Static completion has no
    such requirement.

The dataclasses below mirror the upstream ``carapace-spec`` `JSON schema
<https://github.com/carapace-sh/carapace-spec/blob/master/schema.json>`_; the
flag-key grammar and macro contract are taken from that project's ``flag.go`` and
``core.go``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path

import click
from click.shell_completion import (
    ShellComplete,
    add_completion_class,
    split_arg_string,
)
from cloup.constraints import mutually_exclusive

from .commands import DEFAULT_HELP_NAMES, default_params
from .parameters import (
    full_short_help,
    is_repeatable,
    iter_subcommands,
    make_resilient_context,
    missing_extra_message,
    option_value_kind,
    param_spellings,
    short_long_opts,
)

try:
    import yaml
except ImportError:
    # PyYAML ships behind the ``carapace`` extra: importing this module stays
    # cheap, and only the YAML-serializing entry points raise (see _require_yaml).
    yaml = None  # type: ignore[assignment]

TYPE_CHECKING = False
if TYPE_CHECKING:
    from click import Command, Context, Parameter


CARAPACE_SPECS_DIR = Path("~/.config/carapace/specs").expanduser()
"""User spec directory Carapace loads on startup.

Writing ``<prog>.yaml`` here (see :func:`install_carapace_spec`) is all it takes
for Carapace to pick up a CLI's completions. Mirrors the ``$XDG_CONFIG_HOME``
default documented by Carapace; an explicit ``XDG_CONFIG_HOME`` is honored by
:func:`install_carapace_spec` at call time rather than baked in here.
"""


def _require_yaml() -> None:
    """Raise a pointed error when the optional PyYAML dependency is missing."""
    if yaml is None:
        raise ImportError(
            missing_extra_message("carapace", subject="Carapace spec serialization")
        )


def _clean_description(text: str | None) -> str:
    """Collapse a help string to a single Carapace-friendly description line.

    Strips reST inline-literal backticks (Click stores docstrings verbatim, so
    ``"``...``"`` markup leaks through), keeps only the first paragraph and
    squashes internal whitespace. Carapace truncates long descriptions itself.
    """
    if not text:
        return ""
    paragraph = text.replace("``", "").split("\n\n", 1)[0]
    return " ".join(paragraph.split())


# --- flag-key construction --------------------------------------------------


def _flag_key(
    opts: list[str],
    *,
    value: bool,
    optarg: bool = False,
    repeatable: bool = False,
) -> str:
    """Build a Carapace flag key from option spellings and modifiers.

    Reproduces ``carapace-spec``'s own ``Flag.format()`` grammar: the short
    spelling first, then the long spelling joined by ``", "``, then ``?`` for an
    optional value or ``=`` for a mandatory one, then a trailing ``*`` when the
    flag is repeatable. So a plain switch is ``--foo``, a valued option
    ``--foo=``, an optional-value option ``--foo?``, a counter ``--foo*`` and a
    repeatable valued option ``--foo=*``.
    """
    short, long = short_long_opts(opts)
    key = short
    if short and long:
        key += ", "
    key += long
    if optarg:
        key += "?"
    elif value:
        key += "="
    if repeatable:
        key += "*"
    return key


def _flag_name(opts: list[str]) -> str:
    """Carapace completion key for a flag: long spelling, else short, no dashes."""
    short, long = short_long_opts(opts)
    return (long or short).lstrip("-")


# --- completion action derivation -------------------------------------------


def _env_var(prog_name: str) -> str:
    """Completion env var Click derives from a program name (``_FOO_COMPLETE``)."""
    return f"_{prog_name}_COMPLETE".replace("-", "_").upper()


def _dynamic_action(prog_name: str) -> str:
    """A Carapace shell-macro action that calls back into the CLI for completion.

    Carapace's default ``$(...)`` macro runs ``sh -c '<script>' -- <words>``,
    exposing the already-typed words as ``$*`` and parsing each output line as
    ``value\\tdescription``. The script re-invokes the program in Click's
    completion mode (:class:`CarapaceComplete`, registered as the ``carapace``
    shell), which prints exactly that. Carapace prefix-filters the result, so the
    callback returns the full candidate set.

    .. warning::
        The macro string is derived from ``carapace-spec``'s ``core.go`` shell
        macro rather than a live run. It is the one part of the export that
        warrants a smoke test against an installed ``carapace`` binary.
    """
    return (
        f'$(env "{_env_var(prog_name)}=carapace_complete" '
        f'"COMP_WORDS={prog_name} $*" {prog_name} 2>/dev/null)'
    )


def _static_action(param_type: click.ParamType) -> list[str] | None:
    """Inline completion action for a statically-knowable type, else ``None``.

    Maps choice-like types to their literal values and path/file types to
    Carapace's ``$files`` / ``$directories`` macros, mirroring how Click's own
    :meth:`Choice.shell_complete <click.Choice.shell_complete>` and
    :meth:`Path.shell_complete <click.Path.shell_complete>` behave.
    """
    choices = getattr(param_type, "choices", None)
    if choices:
        return [str(choice) for choice in choices]
    if isinstance(param_type, click.Path):
        if param_type.dir_okay and not param_type.file_okay:
            return ["$directories"]
        return ["$files"]
    if isinstance(param_type, click.File):
        return ["$files"]
    return None


def _overrides_shell_complete(param_type: click.ParamType) -> bool:
    """Whether a type provides a non-static custom ``shell_complete`` override."""
    if isinstance(param_type, (click.Choice, click.Path, click.File)):
        return False
    if getattr(param_type, "choices", None):
        return False
    return type(param_type).shell_complete is not click.ParamType.shell_complete


def _param_action(param: Parameter, prog_name: str) -> list[str]:
    """Resolve the Carapace completion action for one parameter.

    An explicit ``shell_complete=`` callback always routes to the dynamic macro;
    otherwise a statically-knowable type is inlined; otherwise a type that
    overrides ``shell_complete`` falls back to the dynamic macro. Anything else
    yields an empty action (no completion offered).
    """
    if getattr(param, "_custom_shell_complete", None) is not None:
        return [_dynamic_action(prog_name)]
    static = _static_action(param.type)
    if static is not None:
        return static
    if _overrides_shell_complete(param.type):
        return [_dynamic_action(prog_name)]
    return []


# --- spec data model --------------------------------------------------------


@dataclass
class CarapaceCompletion:
    """The ``completion`` block of a command: per-flag and positional actions."""

    flag: dict[str, list[str]] = field(default_factory=dict)
    """Map of flag name (long spelling, no dashes) to its completion action."""

    positional: list[list[str]] = field(default_factory=list)
    """Per-position completion actions for fixed-arity arguments, in order."""

    positionalany: list[str] = field(default_factory=list)
    """Completion action repeated for every trailing variadic argument."""

    def is_empty(self) -> bool:
        """Whether nothing here is worth serializing."""
        return not (self.flag or any(self.positional) or self.positionalany)

    def to_dict(self) -> dict:
        """Serialize to the ``carapace-spec`` ``completion`` mapping, dropping
        empty members and trailing empty positional slots."""
        out: dict = {}
        if self.flag:
            out["flag"] = self.flag
        positional = list(self.positional)
        while positional and not positional[-1]:
            positional.pop()
        if positional:
            out["positional"] = positional
        if self.positionalany:
            out["positionalany"] = self.positionalany
        return out


@dataclass
class CarapaceCommand:
    """One node of a Carapace spec: a command and its flags, completions and
    subcommands, mirroring the upstream ``Command`` schema."""

    name: str
    """The command's invocation name (the root carries the program name)."""

    description: str = ""
    """One-line command description (NAME-section short help)."""

    aliases: tuple[str, ...] = ()
    """Alternative names the command also answers to (from Cloup)."""

    hidden: bool = False
    """Whether the command is hidden from listings (still completable)."""

    flags: dict[str, str] = field(default_factory=dict)
    """Map of flag key (with shape suffixes) to its description."""

    persistentflags: dict[str, str] = field(default_factory=dict)
    """Flags inherited by every subcommand (the root's default option set)."""

    exclusiveflags: list[list[str]] = field(default_factory=list)
    """Groups of mutually-exclusive flag names (from Cloup constraints)."""

    completion: CarapaceCompletion = field(default_factory=CarapaceCompletion)
    """Static and dynamic completion actions for this command's parameters."""

    commands: list[CarapaceCommand] = field(default_factory=list)
    """Nested subcommands."""

    def to_dict(self) -> dict:
        """Serialize to a ``carapace-spec`` command mapping, dropping empties.

        Only ``name`` is required by the schema, so every other member is
        omitted when empty to keep the YAML compact.
        """
        out: dict = {"name": self.name}
        if self.description:
            out["description"] = self.description
        if self.aliases:
            out["aliases"] = list(self.aliases)
        if self.hidden:
            out["hidden"] = True
        if self.flags:
            out["flags"] = self.flags
        if self.persistentflags:
            out["persistentflags"] = self.persistentflags
        if self.exclusiveflags:
            out["exclusiveflags"] = self.exclusiveflags
        completion = self.completion.to_dict()
        if completion:
            out["completion"] = completion
        if self.commands:
            out["commands"] = [sub.to_dict() for sub in self.commands]
        return out


# --- extraction -------------------------------------------------------------


def _default_param_opts() -> frozenset[str]:
    """All option spellings injected on every Click Extra command by default.

    Used to route the root command's default options into ``persistentflags``
    (so Carapace offers them under every subcommand) and to skip the same
    options on subcommands, where they would otherwise be duplicated. A plain
    Click CLI carries none of these, so its ``persistentflags`` stays empty.
    """
    opts = set(DEFAULT_HELP_NAMES)
    for param in default_params():
        opts.update(param_spellings(param))
    return frozenset(opts)


def _exclusive_flag_groups(command: Command) -> list[list[str]]:
    """Mutually-exclusive flag-name groups from Cloup option-group constraints.

    Only ``@option_group(..., constraint=mutually_exclusive)`` is exported:
    Carapace's ``exclusiveflags`` has no equivalent for Cloup's richer
    constraints (``RequireAtLeast``, ``RequireExactly``, ``If``), which are
    dropped.
    """
    groups: list[list[str]] = []
    for option_group in getattr(command, "option_groups", ()):
        if getattr(option_group, "constraint", None) is not mutually_exclusive:
            continue
        names = [
            _flag_name(option.opts)
            for option in option_group.options
            if not getattr(option, "hidden", False)
        ]
        if len(names) > 1:
            groups.append(names)
    return groups


def _add_option(
    node: CarapaceCommand,
    param: Parameter,
    *,
    persistent: bool,
    root_name: str,
) -> None:
    """Encode one Click option into ``flags``/``persistentflags`` and completion.

    A boolean flag with a secondary spelling (``--foo`` / ``--no-foo``) is split
    into two independent Carapace flags, since the spec has no negation primitive.
    Only value-taking options contribute a ``completion.flag`` action. Dynamic
    actions reference ``root_name``, the binary Carapace dispatches on.
    """
    flags = node.persistentflags if persistent else node.flags
    description = _clean_description(getattr(param, "help", None))
    kind = option_value_kind(param)
    value = kind != "flag"
    optarg = kind == "optional"
    repeatable = is_repeatable(param)

    flags[_flag_key(param.opts, value=value, optarg=optarg, repeatable=repeatable)] = (
        description
    )
    # Boolean flags expose their negative spelling as a separate switch.
    if getattr(param, "secondary_opts", None):
        flags[_flag_key(param.secondary_opts, value=False, repeatable=False)] = (
            description
        )

    if value:
        action = _param_action(param, root_name)
        if action:
            node.completion.flag[_flag_name(param.opts)] = action


def extract_carapace_command(
    command: Command,
    ctx: Context,
    *,
    is_root: bool,
    default_opts: frozenset[str],
    inherited_opts: frozenset[str],
    root_name: str,
) -> CarapaceCommand:
    """Build a :class:`CarapaceCommand` from a Click command and its context.

    The context must have been created for ``command`` (typically via
    :meth:`click.Command.make_context` with ``resilient_parsing=True``).
    Subcommands are discovered dynamically and recursed into.

    ``default_opts`` is the abstract set of spellings Click Extra injects on every
    command; on the root, options drawn from it become ``persistentflags``.
    ``inherited_opts`` is what an ancestor actually published as persistent, so a
    subcommand drops exactly those (Carapace already offers them) and keeps the
    rest, including a same-named option the root never carried. ``root_name`` is
    the binary Carapace dispatches on, used to build dynamic callback macros.
    """
    node = CarapaceCommand(
        name=ctx.info_name or command.name or "",
        description=full_short_help(command),
        aliases=tuple(getattr(command, "aliases", ()) or ()),
        hidden=bool(getattr(command, "hidden", False)),
    )

    positional: list[list[str]] = []
    persistent_spellings = set(inherited_opts)
    for param in command.get_params(ctx):
        if isinstance(param, click.Argument):
            action = _param_action(param, root_name)
            if param.nargs == -1:
                node.completion.positionalany = action
            else:
                positional.extend([action] * max(param.nargs, 1))
            continue

        if is_root and set(param.opts) <= default_opts:
            # A root default option: publish it once as persistent so every
            # subcommand inherits it, and remember its spellings to skip below.
            _add_option(node, param, persistent=True, root_name=root_name)
            persistent_spellings.update(param_spellings(param))
        elif set(param.opts) <= inherited_opts:
            # Already offered by an ancestor's persistent flags: do not repeat.
            continue
        else:
            _add_option(node, param, persistent=False, root_name=root_name)

    node.completion.positional = positional
    node.exclusiveflags = _exclusive_flag_groups(command)

    child_inherited = frozenset(persistent_spellings)
    for sub_name, sub in iter_subcommands(command, ctx, skip_hidden=False):
        sub_ctx = make_resilient_context(sub, sub_name, parent=ctx)
        node.commands.append(
            extract_carapace_command(
                sub,
                sub_ctx,
                is_root=False,
                default_opts=default_opts,
                inherited_opts=child_inherited,
                root_name=root_name,
            )
        )

    return node


def to_carapace_spec(
    command: Command,
    prog_name: str | None = None,
    ctx: Context | None = None,
) -> dict:
    """Build the Carapace spec for a command tree as a plain dict.

    Reuses ``ctx`` when given (the live invocation context), otherwise builds a
    throwaway one with ``resilient_parsing=True``. The returned mapping conforms
    to the ``carapace-spec`` schema and is ready to hand to ``yaml.safe_dump``.
    """
    name = prog_name or command.name or ""
    if ctx is None:
        ctx = make_resilient_context(command, name)
    node = extract_carapace_command(
        command,
        ctx,
        is_root=True,
        default_opts=_default_param_opts(),
        inherited_opts=frozenset(),
        root_name=name,
    )
    # The root node's name follows the program name, not the context's.
    node.name = name
    return node.to_dict()


def _generator_tag() -> str:
    """Provenance tag stamped into the generated spec's header comment."""
    try:
        return f"Click Extra {metadata.version('click-extra')}"
    except metadata.PackageNotFoundError:
        return "Click Extra"


def dump_carapace_spec(
    command: Command,
    prog_name: str | None = None,
    ctx: Context | None = None,
) -> str:
    """Serialize a command tree to a Carapace spec YAML string.

    Requires the optional PyYAML dependency (``click-extra[carapace]``). The
    output keeps Click's declaration order rather than sorting keys, so flags and
    subcommands line up with the help screen, and is prefixed with a provenance
    comment.
    """
    _require_yaml()
    spec = to_carapace_spec(command, prog_name, ctx)
    body = yaml.safe_dump(spec, sort_keys=False, allow_unicode=True, width=88)
    header = f"# Generated by {_generator_tag()}. Do not edit by hand.\n"
    return header + body


def write_carapace_spec(
    command: Command,
    target: str | Path,
    prog_name: str | None = None,
) -> Path:
    """Render the spec and write it to ``target``, returning the written path.

    Creates parent directories as needed.
    """
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_carapace_spec(command, prog_name), encoding="utf-8")
    return path


def install_carapace_spec(
    command: Command,
    prog_name: str | None = None,
) -> Path:
    """Write the spec into Carapace's user spec directory.

    Targets ``$XDG_CONFIG_HOME/carapace/specs/<prog>.yaml`` (honoring an explicit
    ``XDG_CONFIG_HOME``), which Carapace loads on startup. Returns the path.
    """
    name = prog_name or command.name or "cli"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() / "carapace" / "specs" if xdg else CARAPACE_SPECS_DIR
    return write_carapace_spec(command, base / f"{name}.yaml", prog_name=name)


# --- dynamic completion backend ---------------------------------------------


@add_completion_class
class CarapaceComplete(ShellComplete):
    """Click completion backend that emits Carapace's value/description lines.

    Registered as the ``carapace`` shell, so ``_FOO_COMPLETE=carapace_complete``
    makes a Click CLI print completions in the ``value\\tdescription`` text format
    Carapace's shell macro parses. This is the callback target of the dynamic
    actions emitted by :func:`_dynamic_action`; it reuses Click's own
    :meth:`~click.shell_completion.ShellComplete.get_completions`, so a parameter's
    custom ``shell_complete`` is honored verbatim.

    The current word is left to Carapace to filter, so completion args are the
    already-typed words with an empty incomplete value.
    """

    name = "carapace"
    """Shell name Click registers this backend under (the ``carapace_complete``
    completion instruction)."""

    source_template = ""

    def source(self) -> str:
        """No-op source step: Carapace, not a shell, consumes this backend."""
        return ""

    def get_completion_args(self) -> tuple[list[str], str]:
        """Read the words Carapace passed via ``COMP_WORDS`` (program name first).

        Returns the typed arguments with an empty incomplete value; Carapace
        applies its own prefix filtering to the candidates we return.
        """
        words = split_arg_string(os.environ.get("COMP_WORDS", ""))
        args = words[1:] if words else []
        return args, ""

    def format_completion(self, item) -> str:
        """Render one completion as Carapace's ``value`` or ``value\\tdescription``."""
        if item.help:
            return f"{item.value}\t{item.help}"
        return str(item.value)
