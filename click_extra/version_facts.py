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
"""Resolvers for the facts a `--version` message reports.

Each function answers one fact on its own, with no option or command around it:
the live Git state ({data}`GIT_RESOLVERS`, {func}`run_git`), the build host
({data}`BUILD_RESOLVERS`), the `.git_archival.json` and `direct_url.json`
fallbacks, the core metadata of a distribution ({func}`resolve_author`,
{func}`resolve_license`), and the interpreter and platform ({func}`default_facts`,
{func}`env_summary`). {class}`~click_extra.version.VersionOption` chains them
into its template fields, and `click-extra prebake all` calls them to bake the
values into a build.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import UTC, datetime

from ._utils import walk_up

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping
    from importlib.metadata import PackageMetadata
    from pathlib import Path
    from typing import Any

logger = logging.getLogger(__name__)


def _installed(name: str) -> bool:
    """Whether an installed distribution goes by *name*."""
    # Deferred import: keeps importlib.metadata off the startup path of every CLI.
    from importlib import metadata

    try:
        metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return False
    return True


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

    if _installed(package_name):
        return package_name

    # Deferred import: keeps importlib.metadata off the startup path of every CLI.
    from importlib import metadata

    # The given name matches no installed distribution: resolve it as an import
    # (top-level module) name.
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


GIT_TIMEOUT: float = 5
"""Seconds {func}`run_git` lets a `git` command run before it gives up on it.

A local read answers in milliseconds. The bound is for a repository that blocks,
like one on a network share that stopped answering.
"""


def run_git(
    *args: str,
    cwd: Path | None = None,
    allow_empty: bool = False,
    check: bool = False,
    timeout: float = GIT_TIMEOUT,
) -> str | None:
    """Run a `git` command and return its output, without the final newline.

    A command that fails returns `None`: no `git` on the `PATH`, a non-zero exit
    status, like the one of a `cwd` outside a repository, or a command still
    running after `timeout` seconds. Set `check` to raise instead: an
    {exc}`OSError` when `git` does not start, a
    {exc}`subprocess.CalledProcessError` on a non-zero exit status, and a
    {exc}`subprocess.TimeoutExpired` when the time runs out.

    By default an empty output returns `None` too, like a failure. Set
    `allow_empty` to keep the empty string, which some commands use
    meaningfully: `git status --porcelain` prints nothing for a clean work tree,
    and that is distinct from the command failing.

    The output decodes as UTF-8, and a byte that is no UTF-8 becomes a
    replacement character: Git prints a ref name as the bytes it stores, which a
    repository can hold in any encoding.

    :param cwd: the folder to run in. The current working directory when `None`.
    """
    # Deferred import: keeps subprocess off the startup path of every CLI.
    import subprocess

    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            encoding="UTF-8",
            errors="replace",
            check=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        if check:
            raise
        return None
    # Only the newline Git ends its output with goes: the other whitespace may
    # belong to the value, like the empty last field of a tab-separated line.
    output = result.stdout.removesuffix("\n")
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


def _describe_distance(described: str) -> str | None:
    """The distance in a `git describe` line, `<tag>-<distance>-g<hash>`, or `None`.

    `None` for a bare `<tag>`, which `git describe` prints for a tagged commit
    without `--long`. The pattern compiles on the first call, on a path few runs
    take, rather than at import.
    """
    match = re.search(r"-(\d+)-g[0-9a-f]+$", described)
    return match.group(1) if match else None


def resolve_git_distance(cwd: Path | None = None) -> str | None:
    """Count commits since the most recent tag, as a string, or `None`.

    Parses `git describe --tags --long`, whose output has the form
    `<tag>-<distance>-g<short_hash>`. Returns `None` when no tag is
    reachable, the directory is not a Git repository, or `git` is
    unavailable.
    """
    described = run_git("describe", "--tags", "--long", cwd=cwd)
    return None if described is None else _describe_distance(described)


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

- {class}`~click_extra.version.VersionOption`'s runtime accessors, which wrap
  each resolver with the pre-baked-dunder and `.git_archival.json` fallbacks.
- the `click-extra prebake all` command, which calls every resolver to bake
  values into source files at build time.

Keeping it here means adding a new git field is a one-line edit in this module,
with no matching change needed in the CLI.
"""


SOURCE_DATE_EPOCH = "SOURCE_DATE_EPOCH"
"""Environment variable a reproducible build sets to pin every timestamp it writes.

See the [reproducible-builds.org specification](https://reproducible-builds.org/docs/source-date-epoch/).
"""


def build_moment() -> datetime:
    """The instant a build happens, in UTC.

    Reads `SOURCE_DATE_EPOCH` when the build sets it, so two runs of a
    reproducible build stamp the same instant. Falls back to the current time.
    """
    epoch = os.environ.get(SOURCE_DATE_EPOCH)
    if epoch:
        return datetime.fromtimestamp(int(epoch), tz=UTC)
    return datetime.now(tz=UTC)


def resolve_build_time() -> str:
    """The moment the distribution is built, as an RFC 3339 UTC timestamp.

    See {func}`build_moment` for where the instant comes from.
    """
    return build_moment().isoformat(timespec="seconds").replace("+00:00", "Z")


def resolve_build_os() -> str:
    """The operating system the build runs on."""
    # Deferred import: keeps extra_platforms off the startup path of every CLI.
    from extra_platforms import current_platform

    return current_platform().name


def resolve_build_target() -> str:
    """The platform a distribution built here installs on.

    This is the wheel platform tag (`macosx-15.0-arm64`, `linux-x86_64`,
    `win-amd64`), which is Python's answer to the target triple shadow-rs bakes
    into a Rust binary. It states an ABI floor the two fields beside it cannot:
    `macosx-15.0-arm64` says the binary needs macOS 15, where
    {func}`~click_extra.version_facts.resolve_build_os` only says it was built
    on macOS.
    """
    # Deferred import: keeps sysconfig off the startup path of every CLI.
    import sysconfig

    return sysconfig.get_platform()


def resolve_build_target_arch() -> str:
    """The CPU architecture the build runs on."""
    # Deferred import: keeps extra_platforms off the startup path of every CLI.
    from extra_platforms import current_architecture

    return current_architecture().name


BUILD_RESOLVERS: dict[str, Callable[[], str]] = {
    "build_time": resolve_build_time,
    "build_os": resolve_build_os,
    "build_target": resolve_build_target,
    "build_target_arch": resolve_build_target_arch,
}
"""Canonical resolver for every pre-bakeable `build_*` field.

These describe the machine and moment a distribution was *built*, which
{data}`GIT_RESOLVERS` and {func}`env_summary` both leave unanswered: git states
what source went in, {func}`env_summary` states where the binary is running now,
and neither one identifies the host that produced it. That gap is what a
cross-built binary turns into a support question, and what shadow-rs answers for
Rust with its `BUILD_TIME`, `BUILD_OS` and `BUILD_TARGET` constants.

A build fact has no live fallback, unlike a git one: nothing at runtime can
recover the host a binary was compiled on, so `click-extra prebake all` is the
only thing that ever writes these. A field left unbaked stays empty, and its
{class}`~click_extra.version.VersionOption` accessor answers `None`.

Adding a field here is a one-line edit, with no matching change in the CLI.
"""


def dunder_name(field_id: str) -> str:
    """The module-level name a pre-baked template field is stored under.

    `git_branch` is baked as `__git_branch__`: the one spelling
    {class}`~click_extra.version.VersionOption` reads back, and
    `click-extra prebake` writes. Keeping the contract in one place is what lets
    the two sides stay agreed.
    """
    return f"__{field_id}__"


def find_git_root(start: Path) -> Path | None:
    """Walk up from *start* to the first folder holding a `.git` entry.

    The entry is a folder in a plain clone, and a file in a worktree or a
    submodule. Returns that folder, *start* included, or `None`.
    """
    for path in walk_up(start):
        if (path / ".git").exists():
            return path
    return None


def find_archival_file(start: Path) -> Path | None:
    """Walk up from *start* to find a `.git_archival.json` file.

    Returns the first match in *start* or any of its parents, or `None`.
    """
    for path in walk_up(start):
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
        data = json.loads(path.read_text(encoding="UTF-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items()}


def archival_field(data: Mapping[str, str], field_id: str) -> str | None:
    """Resolve a `git_*` field from parsed `.git_archival.json` data.

    *data* follows the [setuptools-scm archival schema](https://setuptools-scm.readthedocs.io/latest/usage/#git-archives):
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

    def refs() -> list[str]:
        """The refs pointing at the archived commit, like `HEAD -> main`."""
        names = value("ref-names")
        return names.split(", ") if names else []

    match field_id:
        case "git_long_hash":
            return value("node")
        case "git_short_hash":
            node = value("node")
            return node[:7] if node else None
        case "git_date":
            return value("node-date")
        case "git_branch":
            # "HEAD -> main" names the checked-out branch.
            return next(
                (ref.partition(" -> ")[2] for ref in refs() if " -> " in ref), None
            )
        case "git_tag":
            return next(
                (
                    ref.removeprefix("tag: ")
                    for ref in refs()
                    if ref.startswith("tag: ")
                ),
                None,
            )
        case "git_tag_sha":
            # A tag among the refs points at the archived commit itself.
            return value("node") if archival_field(data, "git_tag") else None
        case "git_distance":
            described = value("describe-name")
            if described is None:
                return None
            # A bare "<tag>" means distance zero.
            return _describe_distance(described) or "0"
    return None


def read_direct_url(distribution: str | None) -> dict[str, Any]:
    """Parse the `direct_url.json` record of an installed distribution.

    [PEP 610](https://peps.python.org/pep-0610/) has installers write this record
    beside the metadata of a distribution installed from a URL, like
    `uvx --from git+https://...` or `pip install git+https://...`.

    Returns an empty mapping when the distribution is not installed, carries no
    record, or holds a record that is not a JSON object.
    """
    if not distribution:
        return {}

    # Deferred import: keeps importlib.metadata off the startup path of every CLI.
    from importlib import metadata

    try:
        text = metadata.distribution(distribution).read_text("direct_url.json")
    except metadata.PackageNotFoundError:
        return {}
    try:
        data = json.loads(text) if text else None
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def direct_url_field(data: Mapping[str, Any], field_id: str) -> str | None:
    """Resolve a `git_*` field from a parsed `direct_url.json` record.

    Only an install from a Git URL records a commit: the full hash of the checkout
    the installer built, in `vcs_info.commit_id`. It answers `git_long_hash`, and
    its first 7 characters `git_short_hash`.

    Every other field answers `None`. The `vcs_info.requested_revision` the record
    may also hold names a branch, a tag or a commit, with nothing to tell which.
    """
    vcs_info = data.get("vcs_info")
    if not isinstance(vcs_info, dict) or vcs_info.get("vcs") != "git":
        return None
    commit = vcs_info.get("commit_id")
    if not isinstance(commit, str) or not commit:
        return None
    if field_id == "git_long_hash":
        return commit
    if field_id == "git_short_hash":
        return commit[:7]
    return None


def resolve_distribution(names: Iterable[str]) -> str | None:
    """Return the first installed distribution among *names*, or `None`.

    Probes each candidate name in order with {func}`importlib.metadata.distribution`
    and returns the first that resolves to an installed distribution. Used to
    pick a distribution from a set of plausible spellings (like the program name
    with `-` / `_` variants) before reading its metadata.
    """
    return next((name for name in names if name and _installed(name)), None)


def meta_value(meta: PackageMetadata, *keys: str) -> str | None:
    """Return the first non-empty value among core-metadata *keys*.

    Each key is tested with `in` before `[]` reads it: `[]` on a missing key
    returns `None` with a `DeprecationWarning`, and is to raise `KeyError`.
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
        # Deferred import: keeps email.utils off the startup path of every CLI.
        from email.utils import getaddresses

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
            return text.rsplit("::", maxsplit=1)[-1].strip()

    # Free-form legacy field (may hold the full license text).
    return meta_value(meta, "License")


def platform_label() -> str:
    """Current platform and CPU architecture, as displayed to the user."""
    # Deferred import: keeps extra_platforms off the startup path of every CLI.
    from extra_platforms import current_architecture, current_platform

    return f"{current_platform().name} {current_architecture().name}"


def env_summary() -> str:
    """One-line interpreter and platform summary.

    Reads `Python 3.14.7, macOS ARM64 (AArch64)` on an Apple Silicon Mac: the
    same two facts {func}`default_facts` puts on the version screen, joined for a
    CLI that would rather spend one line of its plain `--version` on them than
    draw a screen at all:
    `@version_option(message="{prog_name} {version} (" + env_summary() + ")")`.
    """
    facts = default_facts()
    return f"Python {facts['Python']}, {facts['Platform']}"


def dependency_versions() -> str:
    """The Click and Cloup releases this install is sitting on.

    Worth a row on a screen whose main job is to be pasted into a bug report: Click
    Extra subclasses both, so which of the three is at fault is the first question
    any such report raises. Not a default fact, since a CLI built on Click Extra may
    reasonably consider that its own business rather than its user's.

    Read from the installed distributions: Click deprecates its own `__version__`
    attribute.
    """
    # Deferred import: keeps importlib.metadata off the startup path of every CLI.
    from importlib import metadata

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
    # Deferred import: keeps platform off the startup path of every CLI.
    import platform

    return {
        "Python": platform.python_version(),
        "Platform": platform_label(),
    }
