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
"""Introspect CLI metadata at runtime and print a colored ``--version`` string.

:class:`VersionOption` gathers the executed CLI's metadata (module and
package names, distribution version, author and license, environment profile,
and the live Git state) and renders them through a customizable, colorized
message template.

Git fields (``git_branch``, ``git_short_hash``, ...) are resolved at runtime by
shelling out to ``git``, with two fallbacks for ``git``-less environments: a
pre-baked ``__<field>__`` dunder in the CLI module (injected before build by
:mod:`click_extra.prebake`), then a committed ``.git_archival.json`` populated
by ``git archive``.
"""

from __future__ import annotations

import importlib
import inspect
import json
import logging
import os
import re
import subprocess
import sys
from email.utils import getaddresses
from functools import cached_property
from gettext import gettext as _
from importlib import metadata
from pathlib import Path

import click
from boltons.ecoutils import get_profile
from boltons.formatutils import BaseFormatField, tokenize_format_str

from . import Style, echo, get_current_context
from .context import _LazyMetaDict
from .parameters import ExtraOption

# The build-time pre-baking helpers moved to ``click_extra.prebake``. Re-exported
# here so the historical ``from click_extra.version import prebake_*`` import path
# keeps working. ``prebake`` imports nothing from this module, so there is no
# circular import.
from .prebake import (  # noqa: F401
    discover_package_init_files,
    prebake_dunder,
    prebake_version,
)
from .theme import BUILTIN_THEMES, nocolor_theme

# Frozen reference to the default theme's invoked-command style. Used as the
# default for several version-template fields below. Captured at module load
# time on purpose: defaults bind once at function-definition time, so reading
# through ``get_default_theme()`` here would hide later overrides anyway.
# Falls back to the colorless theme when themes.toml is absent (some packaging
# setups drop the data file, so the built-in "dark" palette is unavailable).
_default_invoked_command = BUILTIN_THEMES.get("dark", nocolor_theme).invoked_command

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence
    from importlib.metadata import PackageMetadata
    from types import FrameType, ModuleType
    from typing import Any, ClassVar

    from cloup.styling import IStyle

logger = logging.getLogger(__name__)


GIT_FIELDS: dict[str, tuple[str, ...]] = {
    "git_branch": ("rev-parse", "--abbrev-ref", "HEAD"),
    "git_long_hash": ("rev-parse", "HEAD"),
    "git_short_hash": ("rev-parse", "--short", "HEAD"),
    "git_date": ("show", "-s", "--format=%ci", "HEAD"),
    "git_tag": ("describe", "--tags", "--exact-match", "HEAD"),
}
"""Git fields whose live value *is* the stripped output of one static ``git``
subcommand, mapped to that subcommand's args.

``git_tag_sha``, ``git_distance`` and ``git_dirty`` are excluded: their
resolution is not a single static ``git`` invocation whose stripped output is
the value. ``git_tag_sha`` dereferences the tag (``git rev-list -1 <tag>``),
``git_distance`` parses ``git describe`` and ``git_dirty`` maps the porcelain
status to a label. See :func:`resolve_git_tag_sha`, :func:`resolve_git_distance`
and :func:`resolve_git_dirty`.

For the resolver of *every* pre-bakeable git field (these five plus the three
computed ones), keyed uniformly by field ID, see :data:`GIT_RESOLVERS`.
"""


def run_git(
    *args: str,
    cwd: Path | None = None,
    allow_empty: bool = False,
) -> str | None:
    """Run a ``git`` command and return its stripped output, or ``None``.

    *cwd* defaults to the current working directory when not provided.

    By default an empty output is collapsed to ``None`` (treated like a
    failure). Set *allow_empty* to keep an empty string instead, which some
    commands use meaningfully: ``git status --porcelain`` prints nothing for a
    clean work tree, and that is distinct from the command failing.
    """
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        return None
    output = result.stdout.strip()
    if output or allow_empty:
        return output
    return None


def resolve_git_dirty(cwd: Path | None = None) -> str | None:
    """Report the work-tree state as ``"dirty"``, ``"clean"`` or ``None``.

    Returns ``"dirty"`` when ``git status --porcelain`` reports uncommitted
    changes, ``"clean"`` when it reports none, and ``None`` when the state
    cannot be determined (not a Git repository, or ``git`` is unavailable).

    The empty output of a clean work tree is meaningful here, so the command is
    run with ``allow_empty`` to tell it apart from a failure.
    """
    status = run_git("status", "--porcelain", cwd=cwd, allow_empty=True)
    if status is None:
        return None
    return "dirty" if status else "clean"


def resolve_git_distance(cwd: Path | None = None) -> str | None:
    """Count commits since the most recent tag, as a string, or ``None``.

    Parses ``git describe --tags --long``, whose output has the form
    ``<tag>-<distance>-g<short_hash>``. Returns ``None`` when no tag is
    reachable, the directory is not a Git repository, or ``git`` is
    unavailable.
    """
    described = run_git("describe", "--tags", "--long", cwd=cwd)
    if described is None:
        return None
    match = re.search(r"-(\d+)-g[0-9a-f]+$", described)
    return match.group(1) if match else None


def resolve_git_tag_sha(cwd: Path | None = None) -> str | None:
    """Resolve the commit SHA the tag at ``HEAD`` points at, or ``None``.

    Runs ``git describe --tags --exact-match HEAD`` to find the tag, then
    ``git rev-list -1 <tag>`` to dereference it to a commit SHA. Returns
    ``None`` when ``HEAD`` is not at a tagged commit, the directory is not a
    Git repository, or ``git`` is unavailable.
    """
    tag = run_git(*GIT_FIELDS["git_tag"], cwd=cwd)
    if not tag:
        return None
    return run_git("rev-list", "-1", tag, cwd=cwd)


def _direct_git_resolver(
    field_id: str,
) -> Callable[[Path | None], str | None]:
    """Build a ``cwd``-taking resolver for a direct :data:`GIT_FIELDS` field.

    The returned callable runs the field's static ``git`` subcommand and
    returns its stripped output. Defined as a named factory (rather than an
    inline ``lambda``) so each resolver binds its own ``field_id``.
    """
    args = GIT_FIELDS[field_id]

    def resolver(cwd: Path | None = None) -> str | None:
        return run_git(*args, cwd=cwd)

    return resolver


GIT_RESOLVERS: dict[str, Callable[[Path | None], str | None]] = {
    **{field_id: _direct_git_resolver(field_id) for field_id in GIT_FIELDS},
    "git_tag_sha": resolve_git_tag_sha,
    "git_distance": resolve_git_distance,
    "git_dirty": resolve_git_dirty,
}
"""Canonical live resolver for every pre-bakeable ``git_*`` field.

Maps each field ID to a callable that takes an optional working directory and
returns the field's value by shelling out to ``git`` (or ``None`` when it
cannot be resolved). This is the single source of truth for *how each git field
is computed live*, shared by two consumers:

- :class:`VersionOption`'s runtime accessors, which wrap each resolver with the
  pre-baked-dunder and ``.git_archival.json`` fallbacks.
- the ``click-extra prebake all`` command, which calls every resolver to bake
  values into source files at build time.

Keeping it here means adding a new git field is a one-line edit in this module,
with no matching change needed in the CLI.
"""


def find_archival_file(start: Path) -> Path | None:
    """Walk up from *start* to find a ``.git_archival.json`` file.

    Returns the first match in *start* or any of its parents, or ``None``.
    """
    for path in (start, *start.parents):
        candidate = path / ".git_archival.json"
        if candidate.is_file():
            return candidate
    return None


def read_archival(path: Path) -> dict[str, str]:
    """Parse a ``.git_archival.json`` file into a string mapping.

    Returns an empty mapping when the file is missing, unreadable, or not a
    valid JSON object.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items()}


def archival_field(data: Mapping[str, str], field_id: str) -> str | None:
    """Resolve a ``git_*`` field from parsed ``.git_archival.json`` data.

    *data* follows the `setuptools-scm archival schema
    <https://setuptools-scm.readthedocs.io/en/latest/usage/#git-archives>`_:
    ``node`` (full hash), ``node-date``, ``describe-name`` and ``ref-names``.
    The same file is read by setuptools-scm and Dunamai, so a single committed
    ``.git_archival.json`` serves all three.

    Returns ``None`` when the field is absent, empty, or still holds an
    unsubstituted ``$Format:…$`` placeholder. That last case is what a plain
    checkout contains: ``git archive`` performs the substitution, so values are
    real only inside an exported archive (including GitHub's source tarballs).

    There is no entry for ``git_dirty``: an archive has no work tree, so its
    state is unknowable.
    """

    def value(key: str) -> str | None:
        raw = data.get(key, "").strip()
        if not raw or "$Format" in raw:
            return None
        return raw

    if field_id == "git_long_hash":
        return value("node")
    if field_id == "git_short_hash":
        node = value("node")
        return node[:7] if node else None
    if field_id == "git_date":
        return value("node-date")
    if field_id == "git_branch":
        refs = value("ref-names")
        if refs:
            for ref in refs.split(", "):
                # "HEAD -> main" names the checked-out branch.
                if " -> " in ref:
                    return ref.split(" -> ", 1)[1]
        return None
    if field_id == "git_tag":
        refs = value("ref-names")
        if refs:
            for ref in refs.split(", "):
                if ref.startswith("tag: "):
                    return ref[len("tag: ") :]
        return None
    if field_id == "git_tag_sha":
        # A tag among the refs points at the archived commit itself.
        if archival_field(data, "git_tag"):
            return value("node")
        return None
    if field_id == "git_distance":
        described = value("describe-name")
        if described is None:
            return None
        # "<tag>-<distance>-g<short_hash>"; a bare "<tag>" means distance zero.
        match = re.search(r"-(\d+)-g[0-9a-f]+$", described)
        return match.group(1) if match else "0"
    return None


def resolve_distribution(names: Iterable[str]) -> str | None:
    """Return the first installed distribution among *names*, or ``None``.

    Probes each candidate name in order with :func:`importlib.metadata.distribution`
    and returns the first that resolves to an installed distribution. Used to
    pick a distribution from a set of plausible spellings (for example the
    program name with ``-`` / ``_`` variants) before reading its metadata.
    """
    for name in names:
        if not name:
            continue
        try:
            metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        return name
    return None


def meta_value(meta: PackageMetadata, *keys: str) -> str | None:
    """Return the first non-empty value among core-metadata *keys*.

    Accessed through ``in`` + ``[]`` (rather than ``.get()``) to dodge the
    deprecated implicit-``None`` return on missing keys.
    """
    for key in keys:
        if key in meta:
            value = meta[key]
            if value:
                return value
    return None


def resolve_author(meta: PackageMetadata | None) -> str | None:
    """Return the author(s) from *meta*'s core metadata, or ``None``.

    Prefers the ``Author`` field, then the ``Maintainer`` field, then the
    display name parsed out of the ``Author-email`` / ``Maintainer-email``
    fields (``Name <email>``). Returns ``None`` when *meta* is ``None`` or no
    author can be determined.
    """
    if not meta:
        return None

    # Plain-name fields, in order of preference.
    name = meta_value(meta, "Author", "Maintainer")
    if name:
        return name

    # ``Name <email>`` combined fields: keep only the display names, falling
    # back to the raw value when no name part is present.
    contact = meta_value(meta, "Author-email", "Maintainer-email")
    if contact:
        names = [n for n, _addr in getaddresses([contact]) if n]
        return ", ".join(names) if names else contact

    return None


def resolve_license(meta: PackageMetadata | None) -> str | None:
    """Return the license from *meta*'s core metadata, or ``None``.

    Prefers the SPDX ``License-Expression`` field (`core metadata 2.4+
    <https://packaging.python.org/en/latest/specifications/core-metadata/#license-expression>`_).
    Falls back to the human-readable name of the first ``License ::`` trove
    classifier, then to the free-form ``License`` field (which may hold the
    full license text). Returns ``None`` when *meta* is ``None`` or no license
    can be determined.
    """
    if not meta:
        return None

    # SPDX expression (core metadata 2.4+), the modern canonical field.
    expression = meta_value(meta, "License-Expression")
    if expression:
        return expression

    # ``License :: OSI Approved :: GNU GPL v3 (GPLv3)`` → ``GNU GPL v3 (GPLv3)``.
    for classifier in meta.get_all("Classifier") or []:
        text = str(classifier)
        if text.startswith("License ::"):
            return text.split("::")[-1].strip()

    # Free-form legacy field (may hold the full license text).
    return meta_value(meta, "License")


class VersionOption(ExtraOption):
    """Gather CLI metadata and prints a colored version string.

    .. note::
        This started as a `copy of the standard @click.version_option() decorator
        <https://github.com/pallets/click/blob/cdab890/src/click/decorators.py#L421-L524>`_,
        but is **no longer a drop-in replacement**. Hence the ``Extra`` prefix.

        This address the following Click issues:

        - `click#2324 <https://github.com/pallets/click/issues/2324>`_,
          to allow its use with the declarative ``params=`` argument.

        - `click#2331 <https://github.com/pallets/click/issues/2331>`_,
          by distinguishing the module from the package.

        - `click#1756 <https://github.com/pallets/click/issues/1756>`_,
          by allowing path and Python version.
    """

    message: str = _("{prog_name}, version {version}")
    """Default message template used to render the version string."""

    template_fields: tuple[str, ...] = (
        "module",
        "module_name",
        "module_file",
        "module_version",
        "package_name",
        "package_version",
        "author",
        "license",
        "exec_name",
        "version",
        "git_repo_path",
        "git_branch",
        "git_long_hash",
        "git_short_hash",
        "git_date",
        "git_tag",
        "git_tag_sha",
        "git_distance",
        "git_dirty",
        "prog_name",
        "env_info",
    )
    """List of field IDs recognized by the message template."""

    default_styles: ClassVar[dict[str, IStyle]] = {
        "module_name": _default_invoked_command,
        "module_version": Style(fg="green"),
        "package_name": _default_invoked_command,
        "package_version": Style(fg="green"),
        "exec_name": _default_invoked_command,
        "version": Style(fg="green"),
        "git_repo_path": Style(fg="bright_black"),
        "git_branch": Style(fg="cyan"),
        "git_long_hash": Style(fg="yellow"),
        "git_short_hash": Style(fg="yellow"),
        "git_date": Style(fg="bright_black"),
        "git_tag": Style(fg="cyan"),
        "git_tag_sha": Style(fg="yellow"),
        "git_distance": Style(fg="green"),
        "git_dirty": Style(fg="red"),
        "prog_name": _default_invoked_command,
        "env_info": Style(fg="bright_black"),
    }
    """Default style for each template field.

    Fields absent from this mapping render with no style of their own and fall
    back to ``message_style`` (or no color when that is unset). User-provided
    ``styles`` are merged over these defaults.
    """

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        message: str | None = None,
        fields: Mapping[str, Any] | None = None,
        styles: Mapping[str, IStyle | None] | None = None,
        message_style: IStyle | None = None,
        is_flag=True,
        expose_value=False,
        is_eager=True,
        help=_("Show the version and exit."),
        **kwargs,
    ) -> None:
        """Preconfigured as a ``--version`` option flag.

        :param message: the message template to print, in `format string syntax
            <https://docs.python.org/3/library/string.html#format-string-syntax>`_.
            Defaults to ``{prog_name}, version {version}``.

        :param fields: mapping of template field name to a forced value,
            overriding the value auto-computed for that field. Keys must be
            members of ``template_fields`` (for example
            ``{"version": "1.2.3"}``).

        :param styles: mapping of template field name to its ``Style``, merged
            over ``default_styles``. Pass ``None`` as a value to clear a
            field's default style. Keys must be members of ``template_fields``.

        :param message_style: fallback style for the message literals and for
            any field that has no style of its own.
        """
        if not param_decls:
            param_decls = ("--version",)

        if message is not None:
            self.message = message
        self.message_style = message_style

        field_overrides = dict(fields) if fields else {}
        style_overrides = dict(styles) if styles else {}

        # Reject unknown field names early to catch typos.
        valid_fields = set(self.template_fields)
        for label, mapping in (
            ("fields", field_overrides),
            ("styles", style_overrides),
        ):
            unknown = set(mapping) - valid_fields
            if unknown:
                msg = (
                    f"Unknown {label}: {sorted(unknown)}. "
                    f"Must be among {self.template_fields}."
                )
                raise ValueError(msg)

        # A field value override shadows the cached_property of the same name.
        for field_id, field_value in field_overrides.items():
            setattr(self, field_id, field_value)

        # Per-field styles: class defaults overridden by user-provided styles.
        self.styles: dict[str, IStyle | None] = {
            **self.default_styles,
            **style_overrides,
        }

        kwargs.setdefault("callback", self.print_and_exit)

        super().__init__(
            param_decls=param_decls,
            is_flag=is_flag,
            expose_value=expose_value,
            is_eager=is_eager,
            help=help,
            **kwargs,
        )

    @staticmethod
    def cli_frame() -> FrameType:
        """Returns the frame in which the CLI is implemented.

        Inspects the execution stack frames to find the package in which the user's CLI
        is implemented.

        Returns the frame itself.
        """
        # Keep a list of all frames inspected for debugging.
        frame_chain: list[tuple[str | None, str]] = []

        candidate: FrameType | None = None

        # Walk the execution stack from bottom to top.
        for frame_info in inspect.stack():
            frame = frame_info.frame

            # Get the current package name from the frame's globals.
            frame_name = frame.f_globals.get("__name__")

            # Get the current function name.
            func_name = frame_info.function

            # Keep track of the inspected frames.
            frame_chain.append((frame_name, func_name))

            # Stop at the invoke() function of any CliRunner class, which is used for
            # testing.
            if func_name == "invoke" and isinstance(
                frame.f_locals.get("self"),
                click.testing.CliRunner,
            ):
                # Because click_extra.testing.CliRunner inherits from
                # click.testing.CliRunner, we'd like to keep looking for candidate as
                # long as the frame is an invoke() function of a CliRunner class.
                candidate = frame
                continue

            # We found the top-most frame that is an invoke() function.
            if candidate:
                return candidate

            # Skip the intermediate frames added by the `@cached_property` decorator
            # and the Click ecosystem.
            if frame_name and frame_name.split(".", 1)[0] in (
                "functools",
                "click_extra",
                "cloup",
                "click",
            ):
                continue

            # We found a frame that is not part of the Click ecosystem, and is not an
            # intermediate frame added by a decorator. We assume this is the frame in
            # which the user's CLI is implemented.
            return frame

        # Our heuristics to locate the CLI implementation failed. Fall back to
        # the outermost frame in the stack. This happens in Nuitka-compiled
        # binaries where the entry point module's ``__name__`` may be a
        # submodule of the Click ecosystem package (like
        # ``click_extra.__main__``) and all frames get skipped.
        count_size = len(str(len(frame_chain)))
        for counter, (p_name, f_name) in enumerate(frame_chain):
            logger.debug(f"Frame {counter:<{count_size}} # {p_name}:{f_name}")

        # The outermost frame is the last one returned by inspect.stack().
        outermost = inspect.stack()[-1].frame
        logger.debug(
            "cli_frame heuristics exhausted, falling back to outermost frame: "
            f"{outermost.f_globals.get('__name__')}:{outermost.f_code.co_name}"
        )
        return outermost

    @cached_property
    def module(self) -> ModuleType:
        """Returns the module in which the CLI resides."""
        frame = self.cli_frame()

        module = inspect.getmodule(frame)
        if not module:
            raise RuntimeError(f"Cannot find module of {frame!r}")

        # If the module is a generated entry point script (like .venv/bin/cli-name),
        # try to find the actual CLI module.
        if module.__name__ == "__main__" and not module.__package__:
            module_file = getattr(module, "__file__", None)
            if module_file:
                module_path = Path(module_file)
                # Entry points are typically in bin/ or Scripts/ directories.
                if module_path.parent.name in ("bin", "Scripts"):
                    script_name = module_path.name

                    # Try to find the package via entry_points API.
                    actual_module = self._resolve_entry_point_module(script_name)
                    if actual_module:
                        return actual_module

                    # Fallback: inspect frame globals for imported callables.
                    actual_module = self._resolve_module_from_frame(frame)
                    if actual_module:
                        return actual_module

        return module

    @staticmethod
    def _resolve_entry_point_module(script_name: str) -> ModuleType | None:
        """Resolve the module from a console_scripts entry point name."""
        # Search through all entry points in the 'console_scripts' group.
        eps = metadata.entry_points()

        console_scripts = eps.select(group="console_scripts")

        for ep in console_scripts:
            if ep.name == script_name:
                # ep.value is like "click_extra.__main__:main".
                module_name = ep.value.split(":")[0]
                if module_name in sys.modules:
                    return sys.modules[module_name]
                return importlib.import_module(module_name)

        return None

    @staticmethod
    def _resolve_module_from_frame(frame: FrameType) -> ModuleType | None:
        """Fallback: find module from callables in frame's globals."""
        for obj in frame.f_globals.values():
            if callable(obj) and hasattr(obj, "__module__"):
                actual_module_name = obj.__module__
                if actual_module_name in sys.modules:
                    actual_module = sys.modules[actual_module_name]
                    if getattr(actual_module, "__package__", None):
                        return actual_module
        return None

    @cached_property
    def module_name(self) -> str:
        """Returns the full module name or ``__main__``."""
        return self.module.__name__

    @cached_property
    def module_file(self) -> str | None:
        """Returns the module's file full path."""
        return self.module.__file__

    @cached_property
    def module_version(self) -> str | None:
        """Returns the string found in the local ``__version__`` variable.

        .. hint::
            ``__version__`` is an old pattern from early Python packaging. It is not a
            standard variable and is not defined in the packaging PEPs.

            You should prefer using the ``package_version`` property below instead,
            which uses the standard library `importlib.metadata` API.

            We're still supporting it for backward compatibility with existing
            codebases, as `Click removed it in version 8.2.0
            <https://github.com/pallets/click/issues/2598>`_.
        """
        # First, try to get __version__ from the detected module.
        version = getattr(self.module, "__version__", None)

        # If not found, try to get it from the command's callback globals.
        # This handles cases where the command is defined in a different context
        # (like Sphinx documentation blocks, or standalone scripts).
        if version is None:
            ctx = get_current_context(silent=True)
            if ctx and ctx.command and hasattr(ctx.command, "callback"):
                callback = ctx.command.callback
                if callback is not None:
                    # Get the callback's globals (where __version__ might be defined).
                    callback_globals = getattr(callback, "__globals__", {})
                    version = callback_globals.get("__version__")

        # If still not found, check the parent package. This handles
        # ``__main__`` entry points where ``__version__`` is defined in
        # the package's ``__init__.py`` (like Nuitka-compiled binaries).
        # Skip modules belonging to the Click ecosystem because
        # ``cli_frame()`` may resolve to a CliRunner frame instead of
        # the user's module, producing false-positive lookups. ``__main__``
        # modules are always entry points (never CliRunner artifacts), so
        # they are exempt from the exclusion.
        is_main_entry = self.module_name == "__main__" or self.module_name.endswith(
            ".__main__"
        )
        if (
            version is None
            and self.package_name
            and (
                is_main_entry
                or self.module_name.split(".")[0]
                not in ("click", "click_extra", "cloup")
            )
        ):
            parent = sys.modules.get(self.package_name)
            if parent:
                version = getattr(parent, "__version__", None)

        if version is not None and not isinstance(version, str):
            raise ValueError(
                f"Module version {version!r} expected to be a string or None."
            )
        return version

    @cached_property
    def package_name(self) -> str | None:
        """Returns the package name."""
        return self.module.__package__

    @cached_property
    def _distribution_name(self) -> str | None:
        """Resolve :attr:`package_name` to an installed distribution name.

        :attr:`package_name` is an *import* (top-level module) name, which
        may differ from the *distribution* name (``PIL`` vs ``Pillow``,
        ``jwt`` vs ``PyJWT``). This resolves it to the distribution name
        used for :mod:`importlib.metadata` lookups.

        If :attr:`package_name` already matches an installed distribution
        it is returned as-is. Otherwise it is resolved as an import name
        via :func:`importlib.metadata.packages_distributions`. Ambiguous
        mappings (one import name to several distributions) return
        ``None``: pass ``package_name`` explicitly to disambiguate.
        """
        if not self.package_name:
            logger.debug("No package name provided.")
            return None

        # ``package_name`` already matches an installed distribution.
        try:
            metadata.distribution(self.package_name)
        except metadata.PackageNotFoundError:
            pass
        else:
            return self.package_name

        # The given name didn't match an installed distribution. Try
        # resolving it as an import (top-level module) name.
        distributions = metadata.packages_distributions().get(self.package_name, [])
        if len(distributions) == 1:
            return distributions[0]
        if len(distributions) > 1:
            logger.debug(
                f"{self.package_name!r} maps to multiple installed "
                f"distributions ({', '.join(distributions)}); pass "
                "'package_name' to disambiguate."
            )
            return None
        logger.debug(f"{self.package_name!r} package not found or not installed.")
        return None

    @cached_property
    def package_version(self) -> str | None:
        """Returns the package version if installed.

        Resolved from the distribution name (see
        ``_distribution_name``) via :func:`importlib.metadata.version`.
        Returns ``None`` if the package is not installed or cannot be
        resolved.
        """
        name = self._distribution_name
        return metadata.version(name) if name else None

    @cached_property
    def _package_metadata(self) -> PackageMetadata | None:
        """Returns the distribution's core metadata, or ``None``.

        Reads the `core metadata
        <https://packaging.python.org/en/latest/specifications/core-metadata/>`_
        (``Author``, ``License-Expression``, classifiers, ...) of the
        resolved distribution (see ``_distribution_name``). Returns
        ``None`` when the package is not installed or cannot be resolved.
        """
        name = self._distribution_name
        return metadata.metadata(name) if name else None

    @cached_property
    def author(self) -> str | None:
        """Returns the package author(s) from its core metadata.

        Delegates to :func:`~click_extra.version.resolve_author`: prefers the
        ``Author`` field,
        then the ``Maintainer`` field, then the display name parsed out of the
        ``Author-email`` / ``Maintainer-email`` fields (``Name <email>``).
        Returns ``None`` if no author can be determined.
        """
        return resolve_author(self._package_metadata)

    @cached_property
    def license(self) -> str | None:
        """Returns the package license from its core metadata.

        Delegates to :func:`~click_extra.version.resolve_license`: prefers the SPDX
        ``License-Expression`` field, falls back to the human-readable name of
        the first ``License ::`` trove classifier, then to the free-form
        ``License`` field. Returns ``None`` if no license can be determined.
        """
        return resolve_license(self._package_metadata)

    @cached_property
    def exec_name(self) -> str:
        """User-friendly name of the executed CLI.

        Returns the module name. But if the later is ``__main__``, returns the package
        name.

        If not packaged, the CLI is assumed to be a simple standalone script, and the
        returned name is the script's file name (including its extension).
        """
        # The CLI has its own module.
        if self.module_name != "__main__":
            return self.module_name

        # The CLI module is a `__main__` entry-point, so returns its package name.
        if self.package_name:
            return self.package_name

        # The CLI is not packaged: it is a standalone script. Fallback to its
        # filename.
        if self.module_file:
            return os.path.basename(self.module_file)

        raise RuntimeError(
            "Could not determine the user-friendly name of the CLI from the frame "
            "stack."
        )

    @cached_property
    def version(self) -> str | None:
        """Return the version of the CLI.

        Returns the module version if a ``__version__`` variable is set alongside the
        CLI in its module.

        Else returns the package version if the CLI is implemented in a package, using
        `importlib.metadata.version()
        <https://docs.python.org/3/library/importlib.metadata.html?highlight=metadata#distribution-versions>`_.

        For development versions (containing ``.dev``), automatically appends the Git
        short hash as a `PEP 440 local version identifier
        <https://peps.python.org/pep-0440/#local-version-identifiers>`_, producing
        versions like ``1.2.3.dev0+abc1234``. This helps identify the exact commit a
        dev build was produced from. If Git is unavailable, the plain dev version is
        returned.

        Versions that already contain a ``+`` (a pre-baked local version
        identifier, typically set at build time by CI pipelines) are returned as-is
        to avoid producing invalid double-suffixed versions like
        ``1.2.3.dev0+abc1234+xyz5678``.
        """
        ver = self.module_version or self.package_version
        if ver and ".dev" in ver and "+" not in ver:
            git_hash = self.git_short_hash
            if git_hash:
                return f"{ver}+{git_hash}"
        return ver or None

    @cached_property
    def git_repo_path(self) -> Path | None:
        """Find the Git repository root directory."""
        if self.module_file:
            # Start from the module's directory.
            current_path = Path(self.module_file).parent
        else:
            # Fallback to current working directory.
            current_path = Path.cwd()

        # Walk up the directory tree to find .git.
        for path in [current_path] + list(current_path.parents):
            if (path / ".git").exists():
                return path

        return None

    def _run_git_command(self, *args: str) -> str | None:
        """Run a ``git`` command and return its output, or ``None``."""
        if not self.git_repo_path:
            return None
        return run_git(*args, cwd=self.git_repo_path)

    def _get_prebaked(self, field_id: str) -> str | None:
        """Check the CLI module for a pre-baked ``__<field_id>__`` dunder.

        Returns the dunder's value if it is a non-empty string, otherwise
        ``None``.
        """
        dunder_name = f"__{field_id}__"
        value = getattr(self.module, dunder_name, None)
        # ``isinstance`` first so mypy narrows ``value`` from ``Any`` to ``str``
        # for the return; the ``and value`` keeps only non-empty strings.
        if isinstance(value, str) and value:
            return value
        return None

    @cached_property
    def _archival_data(self) -> dict[str, str]:
        """Parsed ``.git_archival.json`` for the CLI, or an empty mapping.

        Found by walking up from the CLI module's directory (falling back to
        the current working directory). Only populated inside an archive
        produced by ``git archive`` (including GitHub's source tarballs),
        where git substitutes the ``$Format:…$`` placeholders. A normal
        checkout holds the raw placeholders and yields nothing here, so live
        ``git`` calls take precedence and this is consulted only as a fallback.
        """
        if self.module_file:
            start = Path(self.module_file).parent
        else:
            start = Path.cwd()
        path = find_archival_file(start)
        return read_archival(path) if path else {}

    def _resolve_uniform_git_field(self, field_id: str) -> str | None:
        """Resolve a ``git_*`` field that has a single static ``git`` command.

        Applies the precedence shared by every uniform git field: a pre-baked
        ``__<field_id>__`` dunder, then the live value from
        :data:`GIT_RESOLVERS` (run inside :attr:`git_repo_path`), then the
        ``.git_archival.json`` fallback.

        Only valid for the fields in :data:`GIT_FIELDS`. The computed fields
        (:attr:`git_tag_sha`, :attr:`git_distance`, :attr:`git_dirty`) diverge
        in their fallbacks and resolve themselves.
        """
        live = None
        if self.git_repo_path:
            live = GIT_RESOLVERS[field_id](self.git_repo_path)
        return (
            self._get_prebaked(field_id)
            or live
            or archival_field(self._archival_data, field_id)
        )

    @cached_property
    def git_branch(self) -> str | None:
        """Returns the current Git branch name.

        Checks for a pre-baked ``__git_branch__`` dunder first, then
        ``git rev-parse --abbrev-ref HEAD``, then ``.git_archival.json``.
        """
        return self._resolve_uniform_git_field("git_branch")

    @cached_property
    def git_long_hash(self) -> str | None:
        """Returns the full Git commit hash.

        Checks for a pre-baked ``__git_long_hash__`` dunder first, then
        ``git rev-parse HEAD``, then ``.git_archival.json``.
        """
        return self._resolve_uniform_git_field("git_long_hash")

    @cached_property
    def git_short_hash(self) -> str | None:
        """Returns the short Git commit hash.

        Checks for a pre-baked ``__git_short_hash__`` dunder first, then
        ``git rev-parse --short HEAD``, then ``.git_archival.json`` (where it
        is derived from the first 7 characters of the full hash).

        .. hint::
            The short hash is usually the first 7 characters of the full hash, but this
            is not guaranteed to be the case.

            But it is at least guaranteed to be unique within the repository, and
            a `minimum of 4 characters
            <https://git-scm.com/docs/git-config#Documentation/git-config.txt-coreabbrev>`_.
        """
        return self._resolve_uniform_git_field("git_short_hash")

    @cached_property
    def git_date(self) -> str | None:
        """Returns the commit date in ISO format: ``YYYY-MM-DD HH:MM:SS +ZZZZ``.

        Checks for a pre-baked ``__git_date__`` dunder first, then
        ``git show -s --format=%ci HEAD``, then ``.git_archival.json`` (whose
        ``node-date`` is strict ISO 8601, like ``2021-01-01T12:00:00+00:00``).
        """
        return self._resolve_uniform_git_field("git_date")

    @cached_property
    def git_tag(self) -> str | None:
        """Returns the Git tag pointing at HEAD, if any.

        Checks for a pre-baked ``__git_tag__`` dunder first, then
        ``git describe --tags --exact-match HEAD``, then ``.git_archival.json``.

        Returns ``None`` if HEAD is not at a tagged commit.
        """
        return self._resolve_uniform_git_field("git_tag")

    @cached_property
    def git_tag_sha(self) -> str | None:
        """Returns the commit SHA that the current tag points at.

        Checks for a pre-baked ``__git_tag_sha__`` dunder first, then
        ``git rev-list -1`` on the tag returned by :attr:`git_tag`, then
        ``.git_archival.json``. Returns ``None`` if HEAD is not at a tag.
        """
        prebaked = self._get_prebaked("git_tag_sha")
        if prebaked:
            return prebaked
        tag = self.git_tag
        if tag:
            live = self._run_git_command("rev-list", "-1", tag)
            if live:
                return live
        return archival_field(self._archival_data, "git_tag_sha")

    @cached_property
    def git_distance(self) -> str | None:
        """Number of commits since the most recent tag, or ``None``.

        Checks for a pre-baked ``__git_distance__`` dunder first, then parses
        ``git describe --tags --long``, then falls back to
        ``.git_archival.json``. ``None`` when no tag is reachable or Git is
        unavailable.
        """
        prebaked = self._get_prebaked("git_distance")
        if prebaked:
            return prebaked
        if self.git_repo_path:
            distance = resolve_git_distance(self.git_repo_path)
            if distance is not None:
                return distance
        return archival_field(self._archival_data, "git_distance")

    @cached_property
    def git_dirty(self) -> str | None:
        """Work-tree state: ``"dirty"``, ``"clean"`` or ``None``.

        Checks for a pre-baked ``__git_dirty__`` dunder first, then runs
        ``git status --porcelain``. ``None`` when not in a Git repository or
        Git is unavailable. There is no ``.git_archival.json`` fallback: an
        archive has no work tree, so its state is unknowable.
        """
        prebaked = self._get_prebaked("git_dirty")
        if prebaked:
            return prebaked
        if not self.git_repo_path:
            return None
        return resolve_git_dirty(self.git_repo_path)

    @cached_property
    def prog_name(self) -> str | None:
        """Return the name of the CLI, from Click's point of view.

        Get the `info_name
        <https://click.palletsprojects.com/en/stable/api/#click.Context.info_name>`_ of
        the `root
        <https://click.palletsprojects.com/en/stable/api/#click.Context.find_root>`_
        command.
        """
        return get_current_context().find_root().info_name

    @cached_property
    def env_info(self) -> dict[str, Any]:
        """Various environment info.

        Returns the data produced by `boltons.ecoutils.get_profile()
        <https://boltons.readthedocs.io/en/latest/ecoutils.html#boltons.ecoutils.get_profile>`_.
        """
        return get_profile(scrub=True)

    def colored_template(self, template: str | None = None) -> str:
        """Insert ANSI styles to a message template.

        Accepts a custom ``template`` as parameter, otherwise uses the default message
        defined on the Option instance.

        This step is necessary because we need to linearize the template to apply the
        ANSI codes on the string segments. This is a consequence of the nature of ANSI,
        directives which cannot be encapsulated within another (unlike markup tags
        like HTML).
        """
        if template is None:
            template = self.message

        # Normalize the default to a no-op Style() callable to simplify the code
        # of the colorization step.
        def noop(s: str) -> str:
            return s

        default_style = self.message_style if self.message_style else noop

        # Associate each field with its own style.
        field_styles = {}
        for field_id in self.template_fields:
            field_style = self.styles.get(field_id)
            # If no style is defined for this field, use the default style of the
            # message.
            if not field_style:
                field_style = default_style
            field_styles[field_id] = field_style

        # Split the template semantically between fields and literals.
        segments = tokenize_format_str(template, resolve_pos=False)

        # A copy of the template, where literals and fields segments are colored.
        colored_template = ""

        # Apply styles to field and literal segments.
        literal_accu = ""
        for i, segment in enumerate(segments):
            # Is the segment a format field?
            is_field = isinstance(segment, BaseFormatField)
            # If not, keep accumulating literal strings until the next field.
            if not is_field:
                # Re-escape literal curly braces to avoid messing up the format.
                literal_accu += segment.replace(  # type: ignore[union-attr]
                    "{", "{{"
                ).replace("}", "}}")

            # Dump the accumulated literals before processing the field, or at the end
            # of the template.
            is_last_segment = i + 1 == len(segments)
            if (is_field or is_last_segment) and literal_accu:
                # Colorize literals with the default style.
                colored_template += default_style(literal_accu)
                # Reset the accumulator.
                literal_accu = ""

            # Add the field to the template copy, colored with its own style.
            if is_field:
                colored_template += field_styles[
                    segment.base_name  # type: ignore[union-attr]
                ](str(segment))

        return colored_template

    def render_message(self, template: str | None = None) -> str:
        """Render the version string from the provided template.

        Accepts a custom ``template`` as parameter, otherwise uses the default
        ``self.colored_template()`` produced by the instance.
        """
        if template is None:
            template = self.colored_template()

        # Only resolve fields that actually appear in the template, so unused
        # properties (git calls, env_info, etc.) are never evaluated.
        used_fields = {
            seg.base_name
            for seg in tokenize_format_str(template, resolve_pos=False)
            if isinstance(seg, BaseFormatField)
        }
        return template.format(**{v: getattr(self, v) for v in used_fields})

    def print_debug_message(self) -> None:
        """Render in debug logs all template fields in color.

        .. todo::
            Pretty print JSON output (easier to read in bug reports)?
        """
        if logger.getEffectiveLevel() == logging.DEBUG:
            all_fields = {
                f"{{{{{field_id}}}}}": f"{{{field_id}}}"
                for field_id in self.template_fields
            }
            max_len = max(map(len, all_fields))
            raw_format = "\n".join(
                f"{k:<{max_len}}: {v}" for k, v in all_fields.items()
            )
            msg = self.render_message(self.colored_template(raw_format))
            logger.debug("Version string template variables:")
            for line in msg.splitlines():
                logger.debug(line)

    def print_and_exit(
        self,
        ctx: click.Context,
        param: click.Parameter,
        value: bool,
    ) -> None:
        """Print the version string and exits.

        Also stores all version string elements in the Context's ``meta`` `dict`.
        """
        # Install a lazy dict so that version fields in ctx.meta are only
        # evaluated when actually accessed, avoiding unnecessary git calls,
        # environment profiling, and stack inspection on every invocation.
        ctx._meta = _LazyMetaDict(ctx._meta, self, self.template_fields)

        # Eagerly resolve ``module`` now: cli_frame() relies on stack
        # inspection that only produces the correct result during the eager
        # callback. Once cached, all dependent properties (module_name,
        # package_name, etc.) will use this cached value regardless of when
        # they are accessed.
        self.module  # noqa: B018

        # Always log all template fields at DEBUG level, even if --version is
        # not called. This provides valuable execution context in bug reports.
        # The debug check inside the method ensures fields are only resolved
        # (and thus the lazy dict entries materialized) when DEBUG is active.
        self.print_debug_message()

        if not value or ctx.resilient_parsing:
            # Do not print the version and continue normal CLI execution.
            return

        echo(self.render_message(), color=ctx.color)
        ctx.exit()
