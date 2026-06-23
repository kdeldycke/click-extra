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
"""Click Extra's own built-in configuration schema and validators.

These are concrete *instances* of the configuration machinery, kept apart from
the reusable engine in :mod:`~click_extra.config.schema` and the option classes
in :mod:`~click_extra.config.option`:

- the dataclasses describing click-extra's own ``[tool.click-extra]`` section
  (:class:`ClickExtraConfig` and its ``test-plan`` and ``prebake`` sub-tables);
- :func:`_builtin_config_validators`, the validators click-extra registers on
  every :class:`~click_extra.config.option.ConfigOption`.

A downstream project defines its *own* equivalent of this module; click-extra
just happens to ship one, built on the same generic engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .schema import CONFIG_PATH_METADATA_KEY, ConfigValidator

THEMES_CONFIG_KEY: str = "themes"
"""Sub-key under ``[tool.<cli>]`` where user-defined themes live in config.

Used by :class:`~click_extra.config.option.ConfigOption` to find ``[tool.<cli>.themes.<name>]`` tables,
build them via :meth:`HelpTheme.from_dict
<click_extra.theme.HelpTheme.from_dict>`, and stash the result on
``ctx.meta[click_extra.context.THEME_OVERRIDES]``. The constant is the
single source of truth shared by ``_builtin_config_validators``,
``ConfigOption._apply_theme_overrides``, and
:func:`click_extra.theme.themes_from_config`.
"""


@dataclass
class TestPlanConfig:
    """Config schema for a project's test plan, read from ``[tool.<cli>.test-plan]``.

    The ``test-plan`` CLI command resolves its cases from this config when no
    plan is given on the command line. Map it onto an app's config section with
    a field carrying ``metadata={CONFIG_PATH_METADATA_KEY: "test-plan"}``.
    """

    file: str = "./tests/cli-test-plan.yaml"
    """Path to a YAML test plan file, resolved relative to the project root."""

    inline: str | None = None
    """Inline YAML test plan, an alternative to :attr:`file`. Takes precedence."""

    timeout: int | None = None
    """Default timeout (seconds) for each case that does not set its own.

    ``None`` leaves cases unbounded unless ``--timeout`` is passed.
    """


@dataclass
class PrebakeConfig:
    """Config schema for the prebake commands, read from ``[tool.<cli>.prebake]``.

    Lets a project pin the target ``__init__.py`` once for its build pipeline,
    instead of passing ``--module`` to every ``click-extra prebake`` command.
    """

    module: str | None = None
    """Path to the ``__init__.py`` to pre-bake, resolved relative to the project
    root. Overrides the ``[project.scripts]`` auto-discovery; leave unset to keep
    it."""


@dataclass
class ClickExtraConfig:
    """Schema for the ``[tool.click-extra]`` configuration section.

    Wired as the ``config_schema`` of the top-level ``click-extra`` group, so
    every subcommand reads the same section and pulls its own sub-table through
    :func:`~click_extra.config.schema.get_tool_config`.
    """

    test_plan: TestPlanConfig = field(
        default_factory=TestPlanConfig,
        metadata={CONFIG_PATH_METADATA_KEY: "test-plan"},
    )
    """The ``[tool.click-extra.test-plan]`` sub-table (file/inline/timeout)."""

    prebake: PrebakeConfig = field(
        default_factory=PrebakeConfig,
        metadata={CONFIG_PATH_METADATA_KEY: "prebake"},
    )
    """The ``[tool.click-extra.prebake]`` sub-table (target module)."""


def _builtin_config_validators() -> tuple[ConfigValidator, ...]:
    """Return the validators click-extra registers on every :class:`~click_extra.config.option.ConfigOption`.

    Currently a single validator for ``[tool.<cli>.themes.<name>]`` tables.
    Lazy-imports :func:`~click_extra.theme.validate_themes_config` to avoid
    a load-time cycle: :mod:`click_extra.theme` is imported after
    :mod:`click_extra.config` from the package ``__init__``.
    """
    from ..theme import validate_themes_config

    return (
        ConfigValidator(
            extension_path=THEMES_CONFIG_KEY,
            validator=validate_themes_config,
            description=(
                "Validate user-defined and override themes declared under "
                "[tool.<cli>.themes.<name>]."
            ),
        ),
    )
