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
"""Introspect CLI metadata at runtime and print a colored `--version` string.

{class}`VersionOption` gathers the executed CLI's metadata (module and
package names, distribution version, author and license, environment profile,
and the live Git state) and renders them through a customizable, colorized
message template.

Git fields (`git_branch`, `git_short_hash`, ...) are resolved at runtime by
shelling out to `git`, with two fallbacks for `git`-less environments: a
pre-baked `__<field>__` dunder in the CLI module (injected before build by
{mod}`click_extra.prebake`), then a committed `.git_archival.json` populated
by `git archive`.
"""

from __future__ import annotations

import copy
import importlib
import inspect
import json
import logging
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import sysconfig
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import getaddresses
from functools import cached_property
from gettext import gettext as _
from importlib import metadata
from pathlib import Path

import click
from boltons.formatutils import BaseFormatField, tokenize_format_str
from boltons.strutils import strip_ansi
from click import echo, get_current_context
from click._utils import UNSET
from extra_platforms import current_architecture, current_platform

from ._utils import memoize_enums, patch_attr
from .color import invocation_color, is_a_tty
from .context import ACCESSIBLE, _LazyMetaDict, get
from .parameters import ExtraOption
from .styling import Style
from .theme import get_current_theme

RESET = "\x1b[0m"
"""The sequence closing every style, for padding that must inherit none of one."""

MUTED = Style(fg="bright_black")
"""The recessive style the version screen gives its tagline and its fact labels."""

CLI_ECOSYSTEM_PACKAGES = frozenset({"functools", "click_extra", "cloup", "click"})
"""Top-level packages that never implement the *user's* CLI.

`functools` shows up as the intermediate frames a `@cached_property` adds; the
other three are the Click ecosystem itself. A frame belonging to one of them is
plumbing between the `--version` callback and the CLI that declared it, so
{meth}`VersionOption.cli_frame` walks past it, and both
{attr}`VersionOption.module` and {attr}`VersionOption.module_version` read
landing on one as a failed walk. A module {func}`is_main_module` recognizes is
the exception: it is an entry point, whichever package it sits under.
"""


def is_main_module(module_name: str) -> bool:
    """Is *module_name* a `__main__` entry point, of a package or of a script?

    An entry point is where the interpreter started: `python -m package`, a
    console script, or a compiled binary. It is never plumbing a stack walk
    lands on after running out of user frames, so it is exempt from
    {data}`CLI_ECOSYSTEM_PACKAGES` even when it sits under one of those
    packages, as `click_extra.__main__` does in Click Extra's own binary.
    """
    return module_name == "__main__" or module_name.endswith(".__main__")


def distribution_of(package_name: str | None) -> str | None:
    """Resolve an import package name to the installed distribution providing it.

    An import (top-level module) name may differ from the distribution name
    (`PIL` vs `Pillow`, `jwt` vs `PyJWT`). A name already matching an installed
    distribution is returned as-is; otherwise it is resolved through
    {func}`importlib.metadata.packages_distributions`. Ambiguous mappings (one
    import name to several distributions) return `None`: pass `package_name`
    explicitly to disambiguate.

    Returns `None` when nothing installed provides the name, which is what makes
    it usable as a test of whether a module belongs to a real distribution.
    """
    if not package_name:
        logger.debug("No package name provided.")
        return None

    # `package_name` already matches an installed distribution.
    try:
        metadata.distribution(package_name)
    except metadata.PackageNotFoundError:
        pass
    else:
        return package_name

    # The given name didn't match an installed distribution. Try resolving it as
    # an import (top-level module) name.
    distributions = metadata.packages_distributions().get(package_name, [])
    if len(distributions) == 1:
        return distributions[0]
    if len(distributions) > 1:
        logger.debug(
            f"{package_name!r} maps to multiple installed distributions "
            f"({', '.join(distributions)}); pass 'package_name' to disambiguate."
        )
        return None
    logger.debug(f"{package_name!r} package not found or not installed.")
    return None


def theme_slot(slot: str) -> IStyle:
    """A style reading its palette slot off the active theme, on every call.

    The version template's fields used to hold a style captured from the `dark`
    palette at import, on the reasoning that a default binds once anyway. That
    froze the message to one palette: `--theme light` recolored every help screen
    and left `--version` painting the program name bright white, which on a light
    terminal is white on white. Deferring the lookup to call time is what makes the
    message follow `--theme`, `CLICK_EXTRA_THEME` and the background-sniffing
    `auto` alike, and what drops its color entirely under the monochrome `manpage`
    palette.

    {func}`~click_extra.theme.get_current_theme` already answers with the colorless
    theme outside an invocation, and with a full palette inside one, so no slot can
    come back missing.
    """

    def apply(text: str) -> str:
        return getattr(get_current_theme(), slot)(text)  # type: ignore[no-any-return]

    return apply


def unstyled(text: str) -> str:
    """Identity style, for a segment left with no color of its own."""
    return text


TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence
    from importlib.metadata import PackageMetadata
    from types import FrameType, ModuleType
    from typing import Any, ClassVar, TypeAlias

    from cloup.styling import IStyle

    Facts: TypeAlias = Mapping[str, str]
    """Label-to-value rows of a version screen, in the order they are drawn."""

logger = logging.getLogger(__name__)


GIT_FIELDS: dict[str, tuple[str, ...]] = {
    "git_branch": ("rev-parse", "--abbrev-ref", "HEAD"),
    "git_long_hash": ("rev-parse", "HEAD"),
    "git_short_hash": ("rev-parse", "--short", "HEAD"),
    "git_date": ("show", "-s", "--format=%ci", "HEAD"),
    "git_tag": ("describe", "--tags", "--exact-match", "HEAD"),
}
"""Git fields whose live value *is* the stripped output of one static `git`
subcommand, mapped to that subcommand's args.

`git_tag_sha`, `git_distance` and `git_dirty` are excluded: their
resolution is not a single static `git` invocation whose stripped output is
the value. `git_tag_sha` dereferences the tag (`git rev-list -1 <tag>`),
`git_distance` parses `git describe` and `git_dirty` maps the porcelain
status to a label. See {func}`resolve_git_tag_sha`, {func}`resolve_git_distance`
and {func}`resolve_git_dirty`.

For the resolver of *every* pre-bakeable git field (these five plus the three
computed ones), keyed uniformly by field ID, see {data}`GIT_RESOLVERS`.
"""


def run_git(
    *args: str,
    cwd: Path | None = None,
    allow_empty: bool = False,
) -> str | None:
    """Run a `git` command and return its stripped output, or `None`.

    *cwd* defaults to the current working directory when not provided.

    By default an empty output is collapsed to `None` (treated like a
    failure). Set *allow_empty* to keep an empty string instead, which some
    commands use meaningfully: `git status --porcelain` prints nothing for a
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
    """Report the work-tree state as `"dirty"`, `"clean"` or `None`.

    Returns `"dirty"` when `git status --porcelain` reports uncommitted
    changes, `"clean"` when it reports none, and `None` when the state
    cannot be determined (not a Git repository, or `git` is unavailable).

    The empty output of a clean work tree is meaningful here, so the command is
    run with `allow_empty` to tell it apart from a failure.
    """
    status = run_git("status", "--porcelain", cwd=cwd, allow_empty=True)
    if status is None:
        return None
    return "dirty" if status else "clean"


def resolve_git_distance(cwd: Path | None = None) -> str | None:
    """Count commits since the most recent tag, as a string, or `None`.

    Parses `git describe --tags --long`, whose output has the form
    `<tag>-<distance>-g<short_hash>`. Returns `None` when no tag is
    reachable, the directory is not a Git repository, or `git` is
    unavailable.
    """
    described = run_git("describe", "--tags", "--long", cwd=cwd)
    if described is None:
        return None
    match = re.search(r"-(\d+)-g[0-9a-f]+$", described)
    return match.group(1) if match else None


def resolve_git_tag_sha(cwd: Path | None = None) -> str | None:
    """Resolve the commit SHA the tag at `HEAD` points at, or `None`.

    Runs `git describe --tags --exact-match HEAD` to find the tag, then
    `git rev-list -1 <tag>` to dereference it to a commit SHA. Returns
    `None` when `HEAD` is not at a tagged commit, the directory is not a
    Git repository, or `git` is unavailable.
    """
    tag = run_git(*GIT_FIELDS["git_tag"], cwd=cwd)
    if not tag:
        return None
    return run_git("rev-list", "-1", tag, cwd=cwd)


def _direct_git_resolver(
    field_id: str,
) -> Callable[[Path | None], str | None]:
    """Build a `cwd`-taking resolver for a direct {data}`GIT_FIELDS` field.

    The returned callable runs the field's static `git` subcommand and
    returns its stripped output. Defined as a named factory (rather than an
    inline `lambda`) so each resolver binds its own `field_id`.
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
"""Canonical live resolver for every pre-bakeable `git_*` field.

Maps each field ID to a callable that takes an optional working directory and
returns the field's value by shelling out to `git` (or `None` when it
cannot be resolved). This is the single source of truth for *how each git field
is computed live*, shared by two consumers:

- {class}`VersionOption`'s runtime accessors, which wrap each resolver with the
  pre-baked-dunder and `.git_archival.json` fallbacks.
- the `click-extra prebake all` command, which calls every resolver to bake
  values into source files at build time.

Keeping it here means adding a new git field is a one-line edit in this module,
with no matching change needed in the CLI.
"""


SOURCE_DATE_EPOCH = "SOURCE_DATE_EPOCH"
"""Environment variable a reproducible build sets to pin every timestamp it writes.

See the [reproducible-builds.org specification](https://reproducible-builds.org/docs/source-date-epoch/).
"""


def resolve_build_time() -> str:
    """The moment the distribution is built, as an RFC 3339 UTC timestamp.

    Reads `SOURCE_DATE_EPOCH` when the build sets it, so two runs of a
    reproducible build stamp the same instant. Falls back to the current time.
    """
    epoch = os.environ.get(SOURCE_DATE_EPOCH)
    if epoch:
        moment = datetime.fromtimestamp(int(epoch), tz=timezone.utc)
    else:
        moment = datetime.now(tz=timezone.utc)
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")


def resolve_build_os() -> str:
    """The operating system the build runs on."""
    return current_platform().name


def resolve_build_target() -> str:
    """The platform a distribution built here installs on.

    This is the wheel platform tag (`macosx-15.0-arm64`, `linux-x86_64`,
    `win-amd64`), which is Python's answer to the target triple shadow-rs bakes
    into a Rust binary. It states an ABI floor the two fields beside it cannot:
    `macosx-15.0-arm64` says the binary needs macOS 15, where
    {func}`~click_extra.version.resolve_build_os` only says it was built on macOS.
    """
    return sysconfig.get_platform()


def resolve_build_target_arch() -> str:
    """The CPU architecture the build runs on."""
    return current_architecture().name


BUILD_RESOLVERS: dict[str, Callable[[], str]] = {
    "build_time": resolve_build_time,
    "build_os": resolve_build_os,
    "build_target": resolve_build_target,
    "build_target_arch": resolve_build_target_arch,
}
"""Canonical resolver for every pre-bakeable `build_*` field.

These describe the machine and moment a distribution was *built*, which
{data}`GIT_RESOLVERS` and `{env_info}` both leave unanswered: git states what
source went in, `{env_info}` states where the binary is running now, and neither
one identifies the host that produced it. That gap is what a cross-built binary
turns into a support question, and what shadow-rs answers for Rust with its
`BUILD_TIME`, `BUILD_OS` and `BUILD_TARGET` constants.

A build fact has no live fallback, unlike a git one: nothing at runtime can
recover the host a binary was compiled on, so `click-extra prebake all` is the
only thing that ever writes these. A field left unbaked stays empty, and its
{class}`VersionOption` accessor answers `None`.

Adding a field here is a one-line edit, with no matching change in the CLI.
"""


def find_archival_file(start: Path) -> Path | None:
    """Walk up from *start* to find a `.git_archival.json` file.

    Returns the first match in *start* or any of its parents, or `None`.
    """
    for path in (start, *start.parents):
        candidate = path / ".git_archival.json"
        if candidate.is_file():
            return candidate
    return None


def read_archival(path: Path) -> dict[str, str]:
    """Parse a `.git_archival.json` file into a string mapping.

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
    """Resolve a `git_*` field from parsed `.git_archival.json` data.

    *data* follows the [setuptools-scm archival schema](https://setuptools-scm.readthedocs.io/en/latest/usage/#git-archives):
    `node` (full hash), `node-date`, `describe-name` and `ref-names`.
    The same file is read by setuptools-scm and Dunamai, so a single committed
    `.git_archival.json` serves all three.

    Returns `None` when the field is absent, empty, or still holds an
    unsubstituted `$Format:…$` placeholder. That last case is what a plain
    checkout contains: `git archive` performs the substitution, so values are
    real only inside an exported archive (including GitHub's source tarballs).

    There is no entry for `git_dirty`: an archive has no work tree, so its
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
    """Return the first installed distribution among *names*, or `None`.

    Probes each candidate name in order with {func}`importlib.metadata.distribution`
    and returns the first that resolves to an installed distribution. Used to
    pick a distribution from a set of plausible spellings (for example the
    program name with `-` / `_` variants) before reading its metadata.
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

    Accessed through `in` + `[]` (rather than `.get()`) to dodge the
    deprecated implicit-`None` return on missing keys.
    """
    for key in keys:
        if key in meta:
            value = meta[key]
            if value:
                return value
    return None


def resolve_author(meta: PackageMetadata | None) -> str | None:
    """Return the author(s) from *meta*'s core metadata, or `None`.

    Prefers the `Author` field, then the `Maintainer` field, then the
    display name parsed out of the `Author-email` / `Maintainer-email`
    fields (`Name <email>`). Returns `None` when *meta* is `None` or no
    author can be determined.
    """
    if not meta:
        return None

    # Plain-name fields, in order of preference.
    name = meta_value(meta, "Author", "Maintainer")
    if name:
        return name

    # `Name <email>` combined fields: keep only the display names, falling
    # back to the raw value when no name part is present.
    contact = meta_value(meta, "Author-email", "Maintainer-email")
    if contact:
        names = [n for n, _addr in getaddresses([contact]) if n]
        return ", ".join(names) if names else contact

    return None


def resolve_license(meta: PackageMetadata | None) -> str | None:
    """Return the license from *meta*'s core metadata, or `None`.

    Prefers the SPDX `License-Expression` field ([core metadata 2.4+](https://packaging.python.org/en/latest/specifications/core-metadata/#license-expression)).
    Falls back to the human-readable name of the first `License ::` trove
    classifier, then to the free-form `License` field (which may hold the
    full license text). Returns `None` when *meta* is `None` or no license
    can be determined.
    """
    if not meta:
        return None

    # SPDX expression (core metadata 2.4+), the modern canonical field.
    expression = meta_value(meta, "License-Expression")
    if expression:
        return expression

    # `License :: OSI Approved :: GNU GPL v3 (GPLv3)` → `GNU GPL v3 (GPLv3)`.
    for classifier in meta.get_all("Classifier") or []:
        text = str(classifier)
        if text.startswith("License ::"):
            return text.split("::")[-1].strip()

    # Free-form legacy field (may hold the full license text).
    return meta_value(meta, "License")


def platform_label() -> str:
    """Current platform and CPU architecture, as displayed to the user."""
    return f"{current_platform().name} {current_architecture().name}"


def env_summary() -> str:
    """One-line interpreter and platform summary.

    The same two facts {func}`default_facts` puts on the version screen, joined for
    a CLI that would rather spend one line of its plain `--version` on them than
    draw a screen at all: `@version_option(fields={"env_info": env_summary()})`.
    """
    return f"Python {platform.python_version()}, {platform_label()}"


def _scrubbed_host(*args: Any) -> str:
    """Stand in for a host name lookup, returning what `scrub` would write.

    Takes the arguments `socket.getfqdn()` accepts, so it can answer for both
    it and `socket.gethostname()`. See {attr}`VersionOption.env_info`.
    """
    return "-"


def dependency_versions() -> str:
    """The Click and Cloup releases this install is sitting on.

    Worth a row on a screen whose main job is to be pasted into a bug report: Click
    Extra subclasses both, so which of the three is at fault is the first question
    any such report raises. Not a default fact, since a CLI built on Click Extra may
    reasonably consider that its own business rather than its user's.

    Read from the installed distributions rather than the packages' own
    `__version__`, which Click deprecated in `8.4.0` and removes in `9.1`.
    """
    return ", ".join(
        f"{name.capitalize()} {metadata.version(name)}" for name in ("click", "cloup")
    )


def default_facts() -> dict[str, str]:
    """The facts every version screen carries, as an ordered label-to-value map.

    A mapping rather than a sequence of pairs so a CLI can adjust one row without
    restating the rest, `dict` preserving insertion order and replacement keeping a
    key where it already sat:

    ```{code-block} python
    default_facts() | {"Platform": my_own_label}   # replaces, in place
    default_facts() | {"Docs": DOCS_URL}           # appends, at the end
    ```
    """
    return {
        "Python": platform.python_version(),
        "Platform": platform_label(),
    }


def visible_width(text: str) -> int:
    """Columns *text* occupies once its escape sequences are discounted.

    ```{caution}
    Counts characters, not display cells, so a logo drawn with double-width
    characters (CJK, emoji) measures short and its screen lays out ragged. Every
    character a terminal renders one cell wide is fine, which covers ASCII, the
    block and box-drawing ranges, and braille.
    ```
    """
    return len(strip_ansi(text))


@dataclass(frozen=True)
class VersionScreen:
    """A logo, and the facts to seat beside it, as `--version` should draw them.

    Owns the layout only. The artwork arrives already rendered — a string, or the
    lines of one — so a CLI is free to draw its mark however it likes, in ASCII line
    art, half-blocks or anything else, without this class knowing. Hand one to
    {class}`VersionOption` through its `screen` argument, or to a whole CLI through
    `default_params(screen=…)`.
    """

    logo: str | Sequence[str]
    """The mark, pre-rendered. A string is split on newlines."""

    tagline: str = ""
    """One line under the program name. Omitted, with its blank line, when empty."""

    facts: Facts | Callable[[], Facts] = default_facts
    """Label-to-value rows under the tagline, or a callable producing them.

    A callable defers the work to render time, which matters when a value costs
    something to compute: a CLI counting plugins should not pay for that on every
    invocation just to have the number ready in case `--version` is asked for.
    """

    gutter: str = "   "
    """Blank columns between the mark and the facts, and between label and value."""

    @property
    def lines(self) -> tuple[str, ...]:
        """The mark's lines, every one padded out to {attr}`width`.

        Padding here rather than asking for it is what lets a caller hand over
        whatever its renderer produced. Trailing blanks are invisible on a line by
        itself and ragged the moment anything is placed beside it, and a caller
        cannot repair that afterwards: `str.ljust` counts the escape sequences it
        cannot see, so on a styled line it silently does nothing.
        """
        raw = self.logo.split("\n") if isinstance(self.logo, str) else list(self.logo)
        width = self.width
        padded = []
        for line in raw:
            gap = width - visible_width(line)
            # Close any style the line left open, so the padding cannot inherit a
            # background and bleed across the gutter.
            reset = RESET if gap and "\x1b[" in line else ""
            padded.append(f"{line}{reset}{' ' * gap}")
        return tuple(padded)

    @property
    def width(self) -> int:
        """Columns the mark occupies, taken from its widest line."""
        raw = self.logo.split("\n") if isinstance(self.logo, str) else self.logo
        return max((visible_width(line) for line in raw), default=0)

    def rows(self, prog_name: str, version: str, styles: Mapping[str, IStyle | None]):
        """The column of facts, as (plain, styled) pairs.

        Both forms are built together because the styled one cannot be measured: its
        escape sequences take columns that never reach the screen, and the plain twin
        is what {meth}`render` sizes the layout against.

        The program name and version take the same styles the plain message gives
        them, so the two renderings of `--version` cannot drift apart on color.
        """
        facts = self.facts() if callable(self.facts) else self.facts
        # One column per the longest label, so the values line up without anyone
        # having to declare a width that a later row could outgrow.
        label_width = max((len(label) for label in facts), default=0)

        def paint(field: str, text: str) -> str:
            style = styles.get(field)
            return style(text) if style else text

        header = [
            (
                f"{prog_name}, version {version}",
                paint("prog_name", prog_name)
                + ", version "
                + paint("version", version),
            ),
        ]
        if self.tagline:
            header.append((self.tagline, MUTED(self.tagline)))
        if facts:
            header.append(("", ""))
        return (
            *header,
            *(
                (
                    f"{label:<{label_width}}{self.gutter}{value}",
                    MUTED(f"{label:<{label_width}}") + self.gutter + value,
                )
                for label, value in facts.items()
            ),
        )

    def render(
        self, prog_name: str, version: str, styles: Mapping[str, IStyle | None]
    ) -> str | None:
        """Compose the mark and the facts into the screen, or decline to.

        The facts are centred against the mark's height, and either column may be
        the taller of the two: a line missing from one side simply renders blank.

        Returns `None` when the terminal is too narrow to seat the two columns side
        by side, leaving the caller to fall back rather than emit a wrapped mess. The
        threshold is measured off the facts actually built, since their widest row
        grows with whatever a CLI chose to report. A non-interactive stream reports
        `shutil`'s 80-column default, wide enough that a redirected-but-forced-color
        run still gets the screen it asked for.
        """
        rows = self.rows(prog_name, version, styles)
        needed = (
            self.width
            + len(self.gutter)
            + max((len(plain) for plain, _ in rows), default=0)
        )
        if needed > shutil.get_terminal_size().columns:
            return None

        logo = self.lines
        offset = max(0, (len(logo) - len(rows)) // 2)
        blank = " " * self.width
        lines = []
        for index in range(max(len(logo), offset + len(rows))):
            left = logo[index] if index < len(logo) else blank
            row = index - offset
            right = rows[row][1] if 0 <= row < len(rows) else ""
            lines.append(f"{left}{self.gutter}{right}".rstrip())
        # Open on a blank line: `--version` is often the tail of a noisier command (a
        # `uv run` resolving, a wrapper announcing itself), and the mark reads as part
        # of that noise when it starts flush against it.
        return "\n" + "\n".join(lines)


def colors_reach_output() -> bool:
    """Will ANSI codes survive all the way to the user's terminal?

    Resolves Click Extra's color tri-state, deferring to the output stream's TTY
    status on its `auto` default, exactly as `click.echo` does when it decides
    whether to strip the codes itself.

    ```{note}
    The stream probed is {data}`sys.stdout`, not Click's own resolution of it:
    `click.echo` reaches stdout through a private cached wrapper, whose public
    alias Click deprecated in `8.5.0` for removal in `9.0`. That wrapper exists
    to fix the output encoding and delegates `isatty()` to the stream beneath
    it, so both answer alike. Checked against Click `8.5.0` on a pipe, a
    {class}`io.StringIO`, a stream faking `isatty()`, a real terminal, and
    inside `CliRunner.invoke`.
    ```
    """
    color = invocation_color()
    if color is None:
        return is_a_tty(sys.stdout)
    return color


class VersionOption(ExtraOption):
    """Gather CLI metadata and prints a colored version string.

    ```{note}
    This started as a [copy of the standard @click.version_option() decorator](https://github.com/pallets/click/blob/cdab890/src/click/decorators.py#L421-L524),
    but is **no longer a drop-in replacement**. Hence the `Extra` prefix.

    This address the following Click issues:

    - [click#2324](https://github.com/pallets/click/issues/2324),
      to allow its use with the declarative `params=` argument.

    - [click#2331](https://github.com/pallets/click/issues/2331),
      by distinguishing the module from the package.

    - [click#1756](https://github.com/pallets/click/issues/1756),
      by allowing path and Python version.
    ```
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
        "build_time",
        "build_os",
        "build_target",
        "build_target_arch",
        "prog_name",
        "env_info",
    )
    """List of field IDs recognized by the message template."""

    default_styles: ClassVar[dict[str, IStyle]] = {
        "module_name": theme_slot("invoked_command"),
        "module_version": theme_slot("success"),
        "package_name": theme_slot("invoked_command"),
        "package_version": theme_slot("success"),
        "exec_name": theme_slot("invoked_command"),
        "version": theme_slot("success"),
        "git_repo_path": Style(fg="bright_black"),
        "git_branch": Style(fg="cyan"),
        "git_long_hash": Style(fg="yellow"),
        "git_short_hash": Style(fg="yellow"),
        "git_date": Style(fg="bright_black"),
        "git_tag": Style(fg="cyan"),
        "git_tag_sha": Style(fg="yellow"),
        "git_distance": theme_slot("success"),
        "git_dirty": Style(fg="red"),
        "build_time": Style(fg="bright_black"),
        "build_os": Style(fg="bright_black"),
        "build_target": Style(fg="bright_black"),
        "build_target_arch": Style(fg="bright_black"),
        "prog_name": theme_slot("invoked_command"),
        "env_info": Style(fg="bright_black"),
    }
    """Default style for each template field.

    Fields absent from this mapping render with no style of their own and fall
    back to `message_style` (or no color when that is unset). User-provided
    `styles` are merged over these defaults.

    The name and version fields defer to the active palette through
    {func}`theme_slot` rather than naming a color. Both slots render exactly what
    the literals they replaced did under the `dark` default — `invoked_command` is
    bright white bold, `success` is green — so nothing moves for a CLI that never
    touches `--theme`, while one that does finally gets a version message to match.
    """

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        message: str | None = None,
        fields: Mapping[str, Any] | None = None,
        styles: Mapping[str, IStyle | None] | None = None,
        message_style: IStyle | None = None,
        screen: VersionScreen | None = None,
        is_flag=True,
        expose_value=False,
        is_eager=True,
        help=_("Show the version and exit."),
        **kwargs,
    ) -> None:
        """Preconfigured as a `--version` option flag.

        :param message: the message template to print, in [format string syntax](https://docs.python.org/3/library/string.html#format-string-syntax).
            Defaults to ``{prog_name}, version {version}``.

        :param fields: mapping of template field name to a forced value,
            overriding the value auto-computed for that field. Keys must be
            members of `template_fields` (for example
            ``{"version": "1.2.3"}``).

        :param styles: mapping of template field name to its `Style`, merged
            over `default_styles`. Pass `None` as a value to clear a
            field's default style. Keys must be members of `template_fields`.

        :param message_style: fallback style for the message literals and for
            any field that has no style of its own.

        :param screen: a {class}`VersionScreen` to draw instead of the one-line
            message, whenever the terminal can take it. Left unset, `--version`
            behaves exactly as it always has.
        """
        if not param_decls:
            param_decls = ("--version",)

        if message is not None:
            self.message = message
        self.message_style = message_style
        self.screen = screen

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

    def __deepcopy__(self, memo: dict[int, Any]) -> VersionOption:
        """Copy the option, dropping every cached field value.

        {mod}`~click_extra.multicall` deep-copies a group's parameters to
        build each personality, and the cache cannot travel along: the
        `module` entry holds a module object `copy.deepcopy` cannot
        reconstruct, and a copy is a new option anyway, free to resolve its
        fields against its own invocations. Only the configuration state
        (message template, styles, screen, field overrides) is carried over.

        The copy reaches Click's `UNSET` sentinel, on this option or on a
        sibling sharing its option group, so the memo is seeded with that
        sentinel's members before the copy: see
        {func}`~click_extra._utils.memoize_enums` for why Python 3.10 cannot
        copy one on its own.
        """
        cls = type(self)
        clone = cls.__new__(cls)
        memo[id(self)] = clone
        memoize_enums(self, memo, UNSET)
        for key, value in self.__dict__.items():
            if isinstance(getattr(cls, key, None), cached_property):
                continue
            setattr(clone, key, copy.deepcopy(value, memo))
        return clone

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
            if frame_name and frame_name.split(".", 1)[0] in CLI_ECOSYSTEM_PACKAGES:
                continue

            # We found a frame that is not part of the Click ecosystem, and is not an
            # intermediate frame added by a decorator. We assume this is the frame in
            # which the user's CLI is implemented.
            return frame

        # Our heuristics to locate the CLI implementation failed. Fall back to
        # the outermost frame in the stack. This happens in Nuitka-compiled
        # binaries where the entry point module's `__name__` may be a
        # submodule of the Click ecosystem package (like
        # `click_extra.__main__`) and all frames get skipped.
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

    @staticmethod
    def command_module(ctx: click.Context) -> ModuleType | None:
        """Returns the module implementing the root command's callback.

        The stack walk in {meth}`cli_frame` can only find the CLI when the CLI's
        own module is on the stack. That holds for a normal invocation, and for a
        `CliRunner` driven from the test module that declares the command, but not
        when a runner invokes a command it merely *imported*: the walk then finds
        no user frame at all and stops on the runner's own `invoke()`, inside the
        Click ecosystem.

        The Sphinx `click:run` directive is exactly that shape, so a documented
        `--version` used to render the version of whichever ecosystem package
        owned the runner (`None`, once `click_extra.sphinx` resolved to no
        installed distribution) in place of the CLI's own.

        A command's callback names its defining module directly and needs no
        stack, so it settles the case the walk cannot see. Returns `None` when the
        command has no callback (a bare {class}`click.Group`) or its module is not
        imported, leaving the walk's own answer in place.
        """
        callback = ctx.find_root().command.callback
        module_name = getattr(callback, "__module__", None)
        if not module_name:
            return None
        return sys.modules.get(module_name)

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

        # The walk ended on ecosystem plumbing that no installed distribution
        # provides, so it never found the CLI at all: it ran out of user frames
        # and stopped on the runner that invoked an imported command. Defer to
        # that command's own callback module, which needs no stack.
        #
        # Both halves of the test matter. A runner living in a real distribution
        # (`click.testing`, `click_extra.testing`) still answers as it always
        # has, which is what a CLI declared in the module driving the runner
        # relies on. Only a runner under a subpackage that resolves to nothing
        # (`click_extra.sphinx`, which the `click:run` directive invokes through)
        # reaches the fallback.
        #
        # An entry point is excluded outright, because the distribution test
        # cannot see it: a Nuitka binary ships no metadata at all, so
        # `distribution_of()` answers `None` for the CLI's own package too.
        # Click Extra's own binary starts in `click_extra.__main__`, and trading
        # that for the callback's module costs it the {func}`is_main_module`
        # exemption `module_version` needs to read the pre-baked `__version__`
        # off the parent package.
        if (
            not is_main_module(module.__name__)
            and module.__name__.split(".", 1)[0] in CLI_ECOSYSTEM_PACKAGES
            and distribution_of(module.__package__) is None
        ):
            ctx = click.get_current_context(silent=True)
            if ctx is not None:
                from_command = self.command_module(ctx)
                if from_command is not None:
                    return from_command

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
        """Returns the full module name or `__main__`."""
        return self.module.__name__

    @cached_property
    def module_file(self) -> str | None:
        """Returns the module's file full path."""
        return self.module.__file__

    @cached_property
    def module_version(self) -> str | None:
        """Returns the string found in the local `__version__` variable.

        ```{hint}
        `__version__` is an old pattern from early Python packaging. It is not a
        standard variable and is not defined in the packaging PEPs.

        You should prefer using the `package_version` property below instead,
        which uses the standard library `importlib.metadata` API.

        We're still supporting it for backward compatibility with existing
        codebases, as [Click removed it in version 8.2.0](https://github.com/pallets/click/issues/2598).
        ```
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
        # `__main__` entry points where `__version__` is defined in
        # the package's `__init__.py` (like Nuitka-compiled binaries).
        # Skip modules belonging to the Click ecosystem because
        # `cli_frame()` may resolve to a CliRunner frame instead of
        # the user's module, producing false-positive lookups. `__main__`
        # modules are always entry points (never CliRunner artifacts), so
        # they are exempt from the exclusion.
        if (
            version is None
            and self.package_name
            and (
                is_main_module(self.module_name)
                or self.module_name.split(".", 1)[0] not in CLI_ECOSYSTEM_PACKAGES
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
        """Resolve {attr}`package_name` to an installed distribution name.

        {attr}`package_name` is an *import* (top-level module) name, which
        may differ from the *distribution* name (`PIL` vs `Pillow`,
        `jwt` vs `PyJWT`). This resolves it to the distribution name
        used for {mod}`importlib.metadata` lookups.

        If {attr}`package_name` already matches an installed distribution
        it is returned as-is. Otherwise it is resolved as an import name
        via {func}`importlib.metadata.packages_distributions`. Ambiguous
        mappings (one import name to several distributions) return
        `None`: pass `package_name` explicitly to disambiguate.
        """
        return distribution_of(self.package_name)

    @cached_property
    def package_version(self) -> str | None:
        """Returns the package version if installed.

        Resolved from the distribution name (see
        `_distribution_name`) via {func}`importlib.metadata.version`.
        Returns `None` if the package is not installed or cannot be
        resolved.
        """
        name = self._distribution_name
        return metadata.version(name) if name else None

    @cached_property
    def _package_metadata(self) -> PackageMetadata | None:
        """Returns the distribution's core metadata, or `None`.

        Reads the [core metadata](https://packaging.python.org/en/latest/specifications/core-metadata/)
        (`Author`, `License-Expression`, classifiers, ...) of the
        resolved distribution (see `_distribution_name`). Returns
        `None` when the package is not installed or cannot be resolved.
        """
        name = self._distribution_name
        return metadata.metadata(name) if name else None

    @cached_property
    def author(self) -> str | None:
        """Returns the package author(s) from its core metadata.

        Delegates to {func}`~click_extra.version.resolve_author`: prefers the
        `Author` field,
        then the `Maintainer` field, then the display name parsed out of the
        `Author-email` / `Maintainer-email` fields (`Name <email>`).
        Returns `None` if no author can be determined.
        """
        return resolve_author(self._package_metadata)

    @cached_property
    def license(self) -> str | None:
        """Returns the package license from its core metadata.

        Delegates to {func}`~click_extra.version.resolve_license`: prefers the SPDX
        `License-Expression` field, falls back to the human-readable name of
        the first `License ::` trove classifier, then to the free-form
        `License` field. Returns `None` if no license can be determined.
        """
        return resolve_license(self._package_metadata)

    @cached_property
    def exec_name(self) -> str:
        """User-friendly name of the executed CLI.

        Returns the module name. But if the later is `__main__`, returns the package
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

        Returns the module version if a `__version__` variable is set alongside the
        CLI in its module.

        Else returns the package version if the CLI is implemented in a package, using
        [importlib.metadata.version()](https://docs.python.org/3/library/importlib.metadata.html?highlight=metadata#distribution-versions).

        For development versions (containing `.dev`), automatically appends the Git
        short hash as a [PEP 440 local version identifier](https://peps.python.org/pep-0440/#local-version-identifiers), producing
        versions like `1.2.3.dev0+abc1234`. This helps identify the exact commit a
        dev build was produced from. If Git is unavailable, the plain dev version is
        returned.

        Versions that already contain a `+` (a pre-baked local version
        identifier, typically set at build time by CI pipelines) are returned as-is
        to avoid producing invalid double-suffixed versions like
        `1.2.3.dev0+abc1234+xyz5678`.
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
        """Run a `git` command and return its output, or `None`."""
        if not self.git_repo_path:
            return None
        return run_git(*args, cwd=self.git_repo_path)

    def _get_prebaked(self, field_id: str) -> str | None:
        """Check the CLI module for a pre-baked `__<field_id>__` dunder.

        Returns the dunder's value if it is a non-empty string, otherwise
        `None`.
        """
        dunder_name = f"__{field_id}__"
        value = getattr(self.module, dunder_name, None)
        # `isinstance` first so mypy narrows `value` from `Any` to `str`
        # for the return; the `and value` keeps only non-empty strings.
        if isinstance(value, str) and value:
            return value
        return None

    @cached_property
    def _archival_data(self) -> dict[str, str]:
        """Parsed `.git_archival.json` for the CLI, or an empty mapping.

        Found by walking up from the CLI module's directory (falling back to
        the current working directory). Only populated inside an archive
        produced by `git archive` (including GitHub's source tarballs),
        where git substitutes the `$Format:…$` placeholders. A normal
        checkout holds the raw placeholders and yields nothing here, so live
        `git` calls take precedence and this is consulted only as a fallback.
        """
        if self.module_file:
            start = Path(self.module_file).parent
        else:
            start = Path.cwd()
        path = find_archival_file(start)
        return read_archival(path) if path else {}

    def _resolve_uniform_git_field(self, field_id: str) -> str | None:
        """Resolve a `git_*` field that has a single static `git` command.

        Applies the precedence shared by every uniform git field: a pre-baked
        `__<field_id>__` dunder, then the live value from
        {data}`GIT_RESOLVERS` (run inside {attr}`git_repo_path`), then the
        `.git_archival.json` fallback.

        Only valid for the fields in {data}`GIT_FIELDS`. The computed fields
        ({attr}`git_tag_sha`, {attr}`git_distance`, {attr}`git_dirty`) diverge
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

        Checks for a pre-baked `__git_branch__` dunder first, then
        `git rev-parse --abbrev-ref HEAD`, then `.git_archival.json`.
        """
        return self._resolve_uniform_git_field("git_branch")

    @cached_property
    def git_long_hash(self) -> str | None:
        """Returns the full Git commit hash.

        Checks for a pre-baked `__git_long_hash__` dunder first, then
        `git rev-parse HEAD`, then `.git_archival.json`.
        """
        return self._resolve_uniform_git_field("git_long_hash")

    @cached_property
    def git_short_hash(self) -> str | None:
        """Returns the short Git commit hash.

        Checks for a pre-baked `__git_short_hash__` dunder first, then
        `git rev-parse --short HEAD`, then `.git_archival.json` (where it
        is derived from the first 7 characters of the full hash).

        ```{hint}
        The short hash is usually the first 7 characters of the full hash, but this
        is not guaranteed to be the case.

        But it is at least guaranteed to be unique within the repository, and
        a [minimum of 4 characters](https://git-scm.com/docs/git-config#Documentation/git-config.txt-coreabbrev).
        ```
        """
        return self._resolve_uniform_git_field("git_short_hash")

    @cached_property
    def git_date(self) -> str | None:
        """Returns the commit date in ISO format: `YYYY-MM-DD HH:MM:SS +ZZZZ`.

        Checks for a pre-baked `__git_date__` dunder first, then
        `git show -s --format=%ci HEAD`, then `.git_archival.json` (whose
        `node-date` is strict ISO 8601, like `2021-01-01T12:00:00+00:00`).
        """
        return self._resolve_uniform_git_field("git_date")

    @cached_property
    def git_tag(self) -> str | None:
        """Returns the Git tag pointing at HEAD, if any.

        Checks for a pre-baked `__git_tag__` dunder first, then
        `git describe --tags --exact-match HEAD`, then `.git_archival.json`.

        Returns `None` if HEAD is not at a tagged commit.
        """
        return self._resolve_uniform_git_field("git_tag")

    @cached_property
    def git_tag_sha(self) -> str | None:
        """Returns the commit SHA that the current tag points at.

        Checks for a pre-baked `__git_tag_sha__` dunder first, then
        `git rev-list -1` on the tag returned by {attr}`git_tag`, then
        `.git_archival.json`. Returns `None` if HEAD is not at a tag.
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
        """Number of commits since the most recent tag, or `None`.

        Checks for a pre-baked `__git_distance__` dunder first, then parses
        `git describe --tags --long`, then falls back to
        `.git_archival.json`. `None` when no tag is reachable or Git is
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
        """Work-tree state: `"dirty"`, `"clean"` or `None`.

        Checks for a pre-baked `__git_dirty__` dunder first, then runs
        `git status --porcelain`. `None` when not in a Git repository or
        Git is unavailable. There is no `.git_archival.json` fallback: an
        archive has no work tree, so its state is unknowable.
        """
        prebaked = self._get_prebaked("git_dirty")
        if prebaked:
            return prebaked
        if not self.git_repo_path:
            return None
        return resolve_git_dirty(self.git_repo_path)

    def _resolve_build_field(self, field_id: str) -> str | None:
        """Resolve a `build_*` field, which only a pre-bake can answer.

        A git field falls back to a live `git` call and then to
        `.git_archival.json`; a build field has neither, because no runtime
        can recover the host that produced the binary it is running. So this
        reads the pre-baked `__<field_id>__` dunder and stops there, answering
        `None` when `click-extra prebake all` never wrote one.

        Only valid for the fields in {data}`BUILD_RESOLVERS`.
        """
        return self._get_prebaked(field_id)

    @cached_property
    def build_time(self) -> str | None:
        """When the distribution was built, as an RFC 3339 UTC timestamp.

        Reads the pre-baked `__build_time__` dunder. See
        {func}`~click_extra.version.resolve_build_time`.
        """
        return self._resolve_build_field("build_time")

    @cached_property
    def build_os(self) -> str | None:
        """The operating system the build ran on.

        Reads the pre-baked `__build_os__` dunder. See
        {func}`~click_extra.version.resolve_build_os`.
        """
        return self._resolve_build_field("build_os")

    @cached_property
    def build_target(self) -> str | None:
        """The platform a distribution built here installs on.

        Reads the pre-baked `__build_target__` dunder. See
        {func}`~click_extra.version.resolve_build_target`.
        """
        return self._resolve_build_field("build_target")

    @cached_property
    def build_target_arch(self) -> str | None:
        """The CPU architecture the build ran on.

        Reads the pre-baked `__build_target_arch__` dunder. See
        {func}`~click_extra.version.resolve_build_target_arch`.
        """
        return self._resolve_build_field("build_target_arch")

    @property
    def prog_name(self) -> str | None:
        """Return the name of the CLI, from Click's point of view.

        Get the [info_name](https://click.palletsprojects.com/en/stable/api/#click.Context.info_name) of
        the [root](https://click.palletsprojects.com/en/stable/api/#click.Context.find_root)
        command.

        ```{note}
        Unlike its siblings, this field is resolved on every access instead
        of being cached on the instance: it is the one template field whose
        value legitimately varies between invocations of the same option
        instance sharing a process. {mod}`~click_extra.multicall` dispatch
        relies on that, running one CLI under many names in sequence, and a
        `prog_name` passed to `main()` varies it without any multicall at
        all. A cached value would pin the first name seen forever.
        ```
        """
        if "_prog_name_override" in self.__dict__:
            override: str | None = self.__dict__["_prog_name_override"]
            return override
        return get_current_context().find_root().info_name

    @prog_name.setter
    def prog_name(self, value: str | None) -> None:
        """Pin a forced value, the way `fields={"prog_name": …}` does.

        Field overrides are applied with `setattr()`, which needs a setter
        now that the field is a property instead of a `@cached_property` its
        instance `__dict__` entry could shadow.
        """
        self.__dict__["_prog_name_override"] = value

    @cached_property
    def env_info(self) -> dict[str, Any]:
        """Various environment info.

        Returns the data produced by [boltons.ecoutils.get_profile()](https://boltons.readthedocs.io/en/latest/ecoutils.html#boltons.ecoutils.get_profile).
        """
        # `boltons.ecoutils` introspects the interpreter, OS and platform to
        # build its profile, and is comparatively expensive to import. It is
        # only consulted when a version string actually renders ``{env_info}``,
        # so it is imported lazily here to keep it off every CLI's startup
        # path. Do not hoist this back to module scope.
        from boltons.ecoutils import get_profile

        # `get_profile()` resolves the host's name and fully-qualified name,
        # then overwrites both with "-" because `scrub` is set. The second of
        # those is a reverse DNS lookup, so a host whose resolver does not
        # answer pays that timeout in full for a value already thrown away:
        # ~35 s per call on a GitHub macOS runner, which is what made a
        # `--verbosity DEBUG` run there take over an hour. Answering both from
        # a stub returns the very string `scrub` would have written. `ecoutils`
        # reaches them through its own `import socket`, so patching the module
        # here patches the object it reads.
        with (
            patch_attr(socket, "gethostname", _scrubbed_host),
            patch_attr(socket, "getfqdn", _scrubbed_host),
        ):
            return get_profile(scrub=True)

    def field_style(self, field_id: str | None = None) -> IStyle:
        """Style painting the *field_id* segment of a rendered message.

        A field carrying no style of its own falls back to `message_style`, and one
        left unset by the caller too renders bare. Call with no `field_id` for the
        style of the template's literal segments, which is `message_style` alone.
        """
        style = self.styles.get(field_id) if field_id else None
        return style or self.message_style or unstyled

    def colored_template(self, template: str | None = None) -> str:
        """Insert ANSI styles to a message template.

        Accepts a custom `template` as parameter, otherwise uses the default message
        defined on the Option instance.

        This step is necessary because we need to linearize the template to apply the
        ANSI codes on the string segments. This is a consequence of the nature of ANSI,
        directives which cannot be encapsulated within another (unlike markup tags
        like HTML).
        """
        if template is None:
            template = self.message

        default_style = self.field_style()

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
                colored_template += self.field_style(
                    segment.base_name  # type: ignore[union-attr]
                )(str(segment))

        return colored_template

    def render_message(self, template: str | None = None) -> str:
        """Render the version string from the provided template.

        Accepts a custom `template` as parameter, otherwise uses the default
        `self.colored_template()` produced by the instance.

        A CLI carrying a {class}`VersionScreen` gets that drawn instead, whenever
        three conditions hold. Failing any one of them falls back to the plain
        template unchanged, which is a deliberate guarantee rather than a default:
        that form is the one every machine reader parses.

        - **Color reaches the output.** Not because a mark needs it — a good one
          survives having its escapes stripped — but because it is the one lever a
          caller already has. A redirected `--version`, or one run under
          `--no-color` or [`NO_COLOR`](https://no-color.org), is asking for
          something parseable.
        - **The terminal is wide enough** to seat the facts beside the mark without
          wrapping them.
        - **Accessible mode is off.** A mark read out character by character is
          noise to a screen reader, so `--accessible` keeps the plain message.
        """
        if template is None and self.screen is not None:
            ctx = click.get_current_context(silent=True)
            accessible = bool(ctx is not None and get(ctx, ACCESSIBLE, False))
            if not accessible and colors_reach_output():
                screen = self.screen.render(
                    str(self.prog_name or ""),
                    str(self.version or ""),
                    self.styles,
                )
                if screen is not None:
                    return screen

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

        A field resolving to a nested structure is dumped as indented JSON under its
        own label, instead of the single-line `repr` a template would produce for it.
        Only `{env_info}` is built that way today, and it alone accounts for two
        thirds of this listing: a thousand characters on one line is what a bug
        report carries otherwise. Upstream reads its profile the same way, through
        [`boltons.ecoutils.get_profile_json(indent=True)`](https://boltons.readthedocs.io/en/latest/ecoutils.html).
        """
        if logger.getEffectiveLevel() != logging.DEBUG:
            return

        # Double the braces: the label renders as a literal `{field_id}`, naming the
        # placeholder a template would write, rather than expanding it.
        labels = {field_id: f"{{{{{field_id}}}}}" for field_id in self.template_fields}
        max_len = max(map(len, labels.values()))

        logger.debug("Version string template variables:")
        for field_id, label in labels.items():
            value = getattr(self, field_id)
            if isinstance(value, (dict, list)):
                logger.debug(
                    self.render_message(self.colored_template(f"{label:<{max_len}}:"))
                )
                style = self.field_style(field_id)
                dump = json.dumps(value, sort_keys=True, indent=2, default=str)
                for line in dump.splitlines():
                    logger.debug(style(f"  {line}"))
            else:
                logger.debug(
                    self.render_message(
                        self.colored_template(f"{label:<{max_len}}: {{{field_id}}}")
                    )
                )

    def print_and_exit(
        self,
        ctx: click.Context,
        param: click.Parameter,
        value: bool,
    ) -> None:
        """Print the version string and exits.

        Also stores all version string elements in the Context's `meta` `dict`.
        """
        # Install a lazy dict so that version fields in ctx.meta are only
        # evaluated when actually accessed, avoiding unnecessary git calls,
        # environment profiling, and stack inspection on every invocation.
        ctx._meta = _LazyMetaDict(ctx._meta, self, self.template_fields)

        # Eagerly resolve `module` now: cli_frame() relies on stack
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
