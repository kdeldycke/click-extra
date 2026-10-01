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
"""Fail a Sphinx build on the warning types a project lists, and only on those.

Sphinx fails a build on warnings all or nothing: `--fail-on-warning` counts
every warning, and `suppress_warnings` can hide a type but never make one
fatal. A project that lives with some warnings, like the unresolved references
autodoc produces for third-party names, then cannot stop the build on the ones
it does not accept.

The case this module was written for is `myst.xref_missing`. myst-parser
resolves every `[text](#anchor)` and `[text](page.md#anchor)` link against what
the build produced. For a link it cannot place, it logs that warning and ships
the link as written anyway, so a dead fragment reaches the published site
behind a green build.

A handler on the `sphinx` logger records each warning whose type the project
lists in {data}`FAIL_ON_WARNINGS_CONFIG`. Once the build is over, it reports
them in one error and sets the exit status to `1`. The build itself runs to
its end, so every offending warning is reported, not only the first.

```{todo}
Contribute this upstream as a Sphinx config value, on
[sphinx-doc/sphinx#7949](https://github.com/sphinx-doc/sphinx/issues/7949),
which asks for the same feature and has waited for a design since 2020.

Sphinx already holds both halves. `sphinx.util.logging.is_suppressed_warning`
is the matching this module reuses, and the exit status `--fail-on-warning`
sets is the outcome. A config value read where
`sphinx.util.logging.WarningSuppressor` already counts each warning would
replace this module.

Should it land, keep this module as a shim for the Sphinx releases that
predate it, then drop it once click-extra's Sphinx floor moves past them.
```
"""

from __future__ import annotations

import logging

from sphinx.util.logging import NAMESPACE, getLogger, is_suppressed_warning

TYPE_CHECKING = False
if TYPE_CHECKING:
    from sphinx.application import Sphinx


logger = getLogger(__name__)


FAIL_ON_WARNINGS_CONFIG = "click_extra_fail_on_warnings"
"""Name of the `conf.py` value listing the warning types that fail the build.

Entries use the syntax of `suppress_warnings`: `myst` covers every subtype,
`myst.xref_missing` only that one. Empty by default, which leaves Sphinx's
behavior untouched: which warnings a project can live with is its own call.
"""


class ListedWarningCollector(logging.Handler):
    """Collect the warnings whose type the project listed as fatal.

    Attached to the `sphinx` logger rather than to Sphinx's warning stream, so
    it sees every warning, whatever `--quiet` does to the console. A warning
    that `suppress_warnings` hides is skipped, the same way `--fail-on-warning`
    skips it.
    """

    def __init__(self, app: Sphinx) -> None:
        super().__init__(level=logging.WARNING)
        self.app = app
        self.matched: dict[logging.LogRecord, str] = {}
        """The `type.subtype` label of each matched record.

        Sphinx buffers the warnings of a build phase and replays them through
        every handler when the phase ends, after this handler saw them live.
        A record hashes by identity, so keying on it counts each one once.
        """

    def emit(self, record: logging.LogRecord) -> None:
        """Keep `record` if its type is listed and not suppressed."""
        warning_type = getattr(record, "type", "") or ""
        subtype = getattr(record, "subtype", "") or ""
        if not warning_type:
            return
        listed = getattr(self.app.config, FAIL_ON_WARNINGS_CONFIG)
        suppressed = self.app.config.suppress_warnings
        if not is_suppressed_warning(warning_type, subtype, listed):
            return
        if is_suppressed_warning(warning_type, subtype, suppressed):
            return
        self.matched[record] = f"{warning_type}.{subtype}" if subtype else warning_type

    def finish(self, app: Sphinx, exception: Exception | None) -> None:
        """Detach, then fail the build if a listed warning was logged."""
        logging.getLogger(NAMESPACE).removeHandler(self)
        if exception is not None or not self.matched:
            return
        types = sorted(set(self.matched.values()))
        count = len(self.matched)
        logger.error(
            "click_extra.sphinx: %d warning%s of a type listed in %s (%s).",
            count,
            "" if count == 1 else "s",
            FAIL_ON_WARNINGS_CONFIG,
            ", ".join(types),
        )
        app.statuscode = 1


def setup(app: Sphinx) -> None:
    """Register the config value and attach a collector for `app`.

    Called from {func}`click_extra.sphinx.setup` so projects only need to list
    `"click_extra.sphinx"` in their `extensions`. The collector reports at
    priority 900, after the default 500 of other `build-finished` handlers, so
    a warning one of them logs still counts.
    """
    app.add_config_value(
        FAIL_ON_WARNINGS_CONFIG, default=[], rebuild="", types=[list, tuple]
    )
    collector = ListedWarningCollector(app)
    logging.getLogger(NAMESPACE).addHandler(collector)
    app.connect("build-finished", collector.finish, priority=900)
