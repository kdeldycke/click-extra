# Changelog

## [4.11.4 (unreleased)](https://github.com/kdeldycke/click-extra/compare/v4.11.3...main)

> [!IMPORTANT]
> This version is not released yet and is under active development.

## [4.11.3 (2024-11-11)](https://github.com/kdeldycke/click-extra/compare/v4.11.2...v4.11.3)

- Aligns dependencies.

## [4.11.2 (2024-11-10)](https://github.com/kdeldycke/click-extra/compare/v4.11.1...v4.11.2)

- Aligns dependencies.

## [4.11.1 (2024-10-27)](https://github.com/kdeldycke/click-extra/compare/v4.11.0...v4.11.1)

- Fix tests against development version of Click.

## [4.11.0 (2024-10-08)](https://github.com/kdeldycke/click-extra/compare/v4.10.0...v4.11.0)

- Add support for Python 3.13.
- Drop supports for Python 3.9.
- Run tests on Python 3.14-dev.
- Add tests on `ubuntu-24.04`. Remove tests on `ubuntu-20.04`.
- Upgrade tests from `macos-14` to `macos-15`.

## [4.10.0 (2024-09-04)](https://github.com/kdeldycke/click-extra/compare/v4.9.0...v4.10.0)

- Move all platform detection utilities to its own standalone [Extra Platforms project](https://github.com/kdeldycke/extra-platforms).
- Add dependency on `extra-platforms`.

## [4.9.0 (2024-07-25)](https://github.com/kdeldycke/click-extra/compare/v4.8.3...v4.9.0)

- Switch from Poetry to `uv`.
- Drop support for Python 3.8.
- Mark Python 3.13-dev tests as stable.
- Remove dependency on `regex`.

## [4.8.3 (2024-05-25)](https://github.com/kdeldycke/click-extra/compare/v4.8.2...v4.8.3)

- Fix string interpolation in log message.

## [4.8.2 (2024-05-25)](https://github.com/kdeldycke/click-extra/compare/v4.8.1...v4.8.2)

- Do not raise error if package version cannot be fetched.

## [4.8.1 (2024-05-23)](https://github.com/kdeldycke/click-extra/compare/v4.8.0...v4.8.1)

- Do not fail on `docs_update` import if `pygments` is not installed.

## [4.8.0 (2024-05-22)](https://github.com/kdeldycke/click-extra/compare/v4.7.5...v4.8.0)

- Slim down package by moving unit tests out of the main package.
- Allow reuse of Pytest fixures and marks by other packages.
- Move dependencies extending `pygments`, `sphinx` and `pytest` into optional extra dependencies. Closes {issue}`836`.
- Split `dev` dependency groups into optional `test`, `typing` and `docs` groups.
- Remove direct dependency on `mypy`.
- Allow running tests with Python 3.8 and 3.9 on `macos-14` runners.

## [4.7.5 (2024-04-04)](https://github.com/kdeldycke/click-extra/compare/v4.7.4...v4.7.5)

- Remove bypass of `cloup.Color` re-import.

## [4.7.4 (2024-02-23)](https://github.com/kdeldycke/click-extra/compare/v4.7.3...v4.7.4)

- Allow standalone `--version` option to output its debug messages.
- Force closing of context before exiting CLIs to provoque callback calls and prevent state leaks.
- Run tests on `macos-14`. Remove tests on `macos-12`.

## [4.7.3 (2024-01-06)](https://github.com/kdeldycke/click-extra/compare/v4.7.2...v4.7.3)

- Run tests on Python 3.13-dev branch.

## [4.7.2 (2023-11-06)](https://github.com/kdeldycke/click-extra/compare/v4.7.1...v4.7.2)

- Run tests on released Python 3.12 version.

## [4.7.1 (2023-09-19)](https://github.com/kdeldycke/click-extra/compare/v4.7.0...v4.7.1)

- Distinguish between parameter type and Python type in `--show-params` output.
- Recognize custom parameter type as string-based. Closes {issue}`721`.
- Rely on `bump-my-version` to update citation file metadata.

## [4.7.0 (2023-09-04)](https://github.com/kdeldycke/click-extra/compare/v4.6.5...v4.7.0)

- Switch to format string style for version template.
- Add new variables for version string template: `{module}`, `{module_name}`, `{module_file}`, `{module_version}`, `{package_version}` and `{exec_name}`.
- Remove support for Click-specific `%(prog)` and `%(package)` variables in version string.
- Print all versions string variables in debug mode.

## [4.6.5 (2023-09-01)](https://github.com/kdeldycke/click-extra/compare/v4.6.4...v4.6.5)

- Highlight required label and value range in option description. Closes {issue}`748`.

## [4.6.4 (2023-08-23)](https://github.com/kdeldycke/click-extra/compare/v4.6.3...v4.6.4)

- Fix collection of subcommand parameters in `--show-params` output. Closes {issue}`725`.
- Set `%(package_name)` in `--version` to file name for CLI that are standalone scripts and not packaged. Fix {issue}`729`.
- Allow standalone scripts to define a local `__version__` variable to set the `%(version)` element in `--version` output.
- Allow building of documentation with Sphinx 7.
- Run tests on `macos-13`. Remove tests on `macos-11`.
- Ignore unstable tests on upcoming Click `8.2.x` / `main` branch.

## [4.6.3 (2023-07-16)](https://github.com/kdeldycke/click-extra/compare/v4.6.2...v4.6.3)

- Forces `ExtraContext` to properly close itself before exiting the program, to trigger all callbacks.

## [4.6.2 (2023-07-15)](https://github.com/kdeldycke/click-extra/compare/v4.6.1...v4.6.2)

- Remove workaround for Cloup handling of `command_class` default on custom groups.
- Force `@extra_group` to produce sub-groups of the same class.

## [4.6.1 (2023-07-13)](https://github.com/kdeldycke/click-extra/compare/v4.6.0...v4.6.1)

- Inspect in `--version` the whole execution stack to find the package in which the user's CLI is implemented.

## [4.6.0 (2023-07-12)](https://github.com/kdeldycke/click-extra/compare/v4.5.0...v4.6.0)

- Keep the promise of drop-in replacement for `@version_option` which is now a proxy to Click's original.
- Rename the colored, enhanced `--version` option to `@extra_version_option` for its decorator, and `ExtraVersionOption` for its class.
- Activate colors on `@extra_command` and `@extra_group` by default, even if stripped of all their default parameters. Closes {issue}`534` and {pr}`543`.
- Expose location and content of user's configuration file in the Context's `meta` property. Closes {issue}`673`.
- Render specs of hidden parameters in `--show-params` output. Fixes {issue}`689`.
- Swap `Exposed` and `Allowed in conf?` columns in `--show-params` output.
- Add a `hidden` column to `--show-params` output. Refs {issue}`689`.

## [4.5.0 (2023-07-06)](https://github.com/kdeldycke/click-extra/compare/v4.4.0...v4.5.0)

- Expose verbosity level name, table format ID and CLI start timestamp in the Context's `meta` property.
- Refactor `VersionOption`. Introduce internal caching.
- Expose version string elements in the Context's `meta` property. Closes {issue}`325`.
- Remove `print_env_info` option from `VersionOption` class and `version_option` decorators.
- Add new `%(env_info)` element. Default value is the same as what the removed `print_env_info` produced (i.e. a JSON dump of the environment).
- Allow `%(env_info)` value to be set by user on `--version`.
- Rename in version string formatting the `%(prog)` element to `%(prog_name)`, and `%(package)` to `%(package_name)`.
- Detect Click-specific `%(prog)` and `%(package)` and raise a deprecated warning.
- Do not print environment info in `--version` by default. Change default message from `%(prog)s, version %(version)s\n%(env_info)` to `%(prog_name)s, version %(version)s`.
- Automaticcaly augment version string with environment info in `DEBUG` log level.
- Expose `click_extra.search_params` utility.

## [4.4.0 (2023-06-14)](https://github.com/kdeldycke/click-extra/compare/v4.3.0...v4.4.0)

- Add a `reduce()` utility to reduce a collection of `Group` and `Platform` to a minimal set.
- Remove `@destructive` and `@non_destructive` pytest markers.
- Rename the `exclude_params` argument of `ParamStructure` and `ConfigOption` to `excluded_params`.
- Fix over-styling of usage heading in help screen.
- Move `bump-my-version` configuration to `pyproject.toml`.
- Remove `bump2version` from dev dependencies, and let the external workflows install it.
- Remove workaround for `pallets-sphinx-themes`'s outdated reference to old `click`'s Python 2 compatibility hack.

## [4.3.0 (2023-06-01)](https://github.com/kdeldycke/click-extra/compare/v4.2.0...v4.3.0)

- Colorize envvars and default values in `--show-params` option.
- Keep `<stdout>` and `<stderr>` streams independent in `ExtraCliRunner`.
- Always collect `<stderr>` output and never raise an exception.
- Add a new `<output>` stream to simulate what the user sees in its terminal.
- Only mix `<stdout>` and `<stderr>` in `<output>` when `mix_stderr=True`.
- Print detailed CLI execution trace in logs.
- Document inline tests in Sphinx CLI execution blocks.
- Improve Pygments ANSI formatter and lexers documentation.
- Document usage of `pygmentize` command line.
- Regroup all parameter-related code.
- Regroup all testing and CLI execution utilities.
- Activate zoom on big Mermaid graphs.

## [4.2.0 (2023-05-23)](https://github.com/kdeldycke/click-extra/compare/v4.1.0...v4.2.0)

- Add support for dedicated styling of environment variables, defaults, command aliases, aliases punctuation, subcommands and deprecated tag in help screen.
- Update default colors of help screen to improve readability.
- Change default style of critical log messages' prefix to bold red.
- Document the full matrix of colors and styles.
- Render bright variants of ANSI colors in documentation.
- Dynamically patch the style provided to `AnsiHtmlFormatter` to augment it with ANSI colors.
- Remove main dependency on `furo`, make it a development dependency.
- Remove the custom `ansi-click-extra-furo-style` Pygments style for Furo and its `AnsiClickExtraFuroStyle` class.

## [4.1.0 (2023-05-11)](https://github.com/kdeldycke/click-extra/compare/v4.0.0...v4.1.0)

- Add new global `show_envvar` option to display all environment variables in help screens.
- Global `show_choices` setting to show or hide choices when prompting a user for input.
- Populate the `Allowed in conf?` column in `--show-params` output if there is a `--config` option in the command.
- Print all modified loggers and their levels in `DEBUG` mode.
- Directly download Pygments source code from GitHub to check for candidates for ANSI-coloring in unittests.
- Test continuously against Click and Cloup development version. Closes {issue}`525`.
- Move `click_extra.commands.TimerOption` to `click_extra.timer.TimerOption`.

## [4.0.0 (2023-05-08)](https://github.com/kdeldycke/click-extra/compare/v3.10.0...v4.0.0)

- Drop support for Python 3.7.
- Add a simple `--telemetry`/`--no-telemetry` option flag which respects the `DO_NOT_TRACK` environment variable.
- Add new `populate_auto_envvars` parameter to `@extra_command`/`@extra_group` decorators to allow auto-generated environment variables to be displayed in help screens.
- Display all environment variables in `--show-params` output, including those auto-generated by the way of the `auto_envvar_prefix` context parameter.
- Allow user to override hard-coded context defaults on `@extra_command`/`@extra_group`.
- Change default log level from `INFO` to `WARNING` to aligns with Python's global root logger.
- Force resetting of log level on `--verbosity`'s context closing to the hard-coded default.
- Use a dedicated `click_extra` logger for all internal messages, instead of sending them to the user-defined one.
- Aligns `click_extra` logger level to `--verbosity` option level.
- Set default logger of `--verbosity` to Python's global `root` logger, instead a local wrapped logger. Closes {issue}`318`.
- Allow user to provide a string as the default logger to `--verbosity` that will be used to fetch the global logger singleton of that name. Closes {issue}`318`.
- Only colorize the `%(levelname)s` field during log record formatting, not the `:` message separator.
- Prefix `INFO`-level log message with `info: ` prefix by default.
- Raise an error if multiple `--version` options are defined in the same command. Closes {issue}`317`.
- Remove dependency on `click-log`.
- Remove supports for `Pallets-Sphinx-Themes < 2.1.0`.
- Force closing of the context before stopping the execution flow, to make sure all callbacks are called.
- Fix rendering of GitHub-Flavored Markdown tables in canonical format.

## [3.10.0 (2023-04-04)](https://github.com/kdeldycke/click-extra/compare/v3.9.0...v3.10.0)

- Colorize help screens of subcommands spawned out of an `@extra_group`. Closes {issue}`479`.
- Remove deprecated `click_extra.platform`.

## [3.9.0 (2023-03-31)](https://github.com/kdeldycke/click-extra/compare/v3.8.3...v3.9.0)

- Allow `@color_option`, `@command`, `@config_option`, `@extra_command`, `@extra_group`, `@group`, `@help_option`, `@show_params_option`, `@table_format_option`, `@timer_option`, `@verbosity_option` and `@version_option` decorators to be used without parenthesis.
- Fix wrapping of Cloup decorators by `@extra_group`/`@extra_command` decorators. Closes {issue}`489`.
- Add main dependency on `furo` which is referenced in ANSI-aware Pygment styles.
- Move all documentation assets to `assets` subfolder.

## [3.8.3 (2023-02-25)](https://github.com/kdeldycke/click-extra/compare/v3.8.2...v3.8.3)

- Let `--version` option output system details when run on `python >= 3.10`.

## [3.8.2 (2023-02-20)](https://github.com/kdeldycke/click-extra/compare/v3.8.1...v3.8.2)

- Fix overlapping detection of `linux` and `wsl2` platforms.
- Renders platform groups in documentation in Mermaid format instead of Graphviz. Add new dependency on `sphinxcontrib-mermaid`, removed dependency on `graphviz`.
- Produce dependency graph in Mermaid instead of Graphviz.

## [3.8.1 (2023-02-15)](https://github.com/kdeldycke/click-extra/compare/v3.8.0...v3.8.1)

- Code, comments and documentation style change to conform to new QA workflows based on `ruff`.

## [3.8.0 (2023-01-24)](https://github.com/kdeldycke/click-extra/compare/v3.7.0...v3.8.0)

- Rename `click_extra.platform` to `click_extra.platforms`.
- Refactor platforms and their groups with dataclasses instead of string IDs.
- Add new `LINUX_LAYERS`, `ALL_WINDOWS`, `BSD_WITHOUT_MACOS`, `EXTRA_GROUPS` and `ALL_GROUPS` groups.
- Add new dependency on `graphviz`.
- Activate Graphviz extension in Sphinx.
- Let Sphinx produce the dependency graph from Graphviz file.
- Produce platform graph dynamically.
- Rename `docs.py` to `docs_update.py` and allow this module to be called directly.

## [3.7.0 (2023-01-03)](https://github.com/kdeldycke/click-extra/compare/v3.6.0...v3.7.0)

- Add support for new ANSI-capable lexers: `ansi-gap-console` and `ansi-gap-repl`.
- Auto-update table of supported lexers in documentation.
- Add test to search in Pygments' test data for REPL/terminal-like lexers, as candidates for ANSI-coloring.
- Depends on `importlib_metadata` for `Python < 3.8`.

## [3.6.0 (2022-12-28)](https://github.com/kdeldycke/click-extra/compare/v3.5.0...v3.6.0)

- Add new constants to group platforms by family.
- Add heuristics to recognize new platforms: IBM AIX, Cygwin, FreeBSD, GNU/Hurd, NetBSD, OpenBSD, Oracle Solaris, SunOS, Windows Subsystem for Linux v1 and v2.
- Document version option usage.
- Split version code to its own file and tests.
- Run tests on Python `3.12-dev`.

## [3.5.0 (2022-12-09)](https://github.com/kdeldycke/click-extra/compare/v3.4.1...v3.5.0)

- Print fully qualified class of options in `--show-params` output.
- Add new columns in `--show-params` table to show option specifications, configuration exclusion and exposed attribute.
- Rename `ignored_params` argument to `exclude_params` on the `ConfigOption` class.
- Blocking parameters from configuration files now requires the fully qualified ID. Which adds support for selectively blocking parameters at any subcommand level.

## [3.4.1 (2022-12-07)](https://github.com/kdeldycke/click-extra/compare/v3.4.0...v3.4.1)

- Fix highlighting of `+`-prefixed options in help screens. Closes {issue}`316`.
- Fix highlighting of hard-coded deprecated labels in option help.
- Document parameter introspection. Closes {issue}`319`.

## [3.4.0 (2022-12-01)](https://github.com/kdeldycke/click-extra/compare/v3.3.4...v3.4.0)

- Streamline setup of Sphinx extensions.
- Document `.. click:example::` and `.. click:run::` Sphinx extensions.

## [3.3.4 (2022-11-14)](https://github.com/kdeldycke/click-extra/compare/v3.3.3...v3.3.4)

- Fix some types.

## [3.3.3 (2022-11-14)](https://github.com/kdeldycke/click-extra/compare/v3.3.2...v3.3.3)

- Fix release workflow.

## [3.3.2 (2022-11-14)](https://github.com/kdeldycke/click-extra/compare/v3.3.1...v3.3.2)

- Remove use of deprecated `::set-output` directives and replace them by environment files.

## [3.3.1 (2022-11-11)](https://github.com/kdeldycke/click-extra/compare/v3.3.0...v3.3.1)

- Keep a copy of the table format ID in the context when set.

## [3.3.0 (2022-11-09)](https://github.com/kdeldycke/click-extra/compare/v3.2.5...v3.3.0)

- Use `tabulate` dependency instead of `cli-helpers` for all the table rendering utilities.
- Remove dependency on `cli-helpers`.
- Re-implement locally the `vertical` table rendering format from `cli-helpers`.
- Add new table rendering formats: `asciidoc`, `fancy_outline`, `heavy_grid`, `heavy_outline`, `latex_longtable`, `latex_raw`, `mixed_grid`, `mixed_outline`, `presto`, `pretty`, `unsafehtml` and `youtrack`.
- Remove `minimal` table rendering formats, which was an alias of `plain`.
- Add new `csv-excel`, `csv-excel-tab` and `csv-unix` formats based on Python defaults dialects.
- Remove `csv-tab` rendering format.
- Make `csv` format an alias of `csv-excel`.
- Deactivate number alignment and extra-spacing in table rendering by default.
- Remove tests on Pypy. Nobody asked for it and I need to speed up tests.

## [3.2.5 (2022-09-30)](https://github.com/kdeldycke/click-extra/compare/v3.2.4...v3.2.5)

- Fix argument's property getter in `--show-params`.
- Remove GitHub edit link workaround in documentation.

## [3.2.4 (2022-09-27)](https://github.com/kdeldycke/click-extra/compare/v3.2.3...v3.2.4)

- Add citation file.
- Fix type casting.

## [3.2.3 (2022-09-27)](https://github.com/kdeldycke/click-extra/compare/v3.2.2...v3.2.3)

- Increase type coverage.

## [3.2.2 (2022-09-26)](https://github.com/kdeldycke/click-extra/compare/v3.2.1...v3.2.2)

- Fix bad typing import.

## [3.2.1 (2022-09-26)](https://github.com/kdeldycke/click-extra/compare/v3.2.0...v3.2.1)

- Move some command utility from test machinery to `run` submodule.

## [3.2.0 (2022-09-24)](https://github.com/kdeldycke/click-extra/compare/v3.1.0...v3.2.0)

- New `--show-params` option to debug parameters defaults, values, environment variables and provenance.
- Rename `ignored_options` to `ignored_params` on `ConfigOption`.
- Highlight command's metavars, default values and deprecated flag in help.
- Finer highlighting of options, subcommands and their aliases in help screens.
- Fix highlight of dynamic metavars and secondary option in help screen.
- New custom `ExtraContext` which allows populating `meta` at instantiation.
- Use the `Formats` enum to encode for default configuration file extensions.
- Re-introduce `*.yml` as a possible extension for YAML files.

## [3.1.0 (2022-09-20)](https://github.com/kdeldycke/click-extra/compare/v3.0.1...v3.1.0)

- Add support for pattern matching to search for configuration file.
- Add a new `formats` option to specify which dialects the configuration file is written in, regardless of its name or file extension. Closes {issue}`197`.
- Set default configuration folder according each OS preferred location. Closes {issue}`211`.
- Add `roaming` and `force_posix` option to influence default application directory of configuration file.
- Add a `ignored_options` parameter to the configuration file instead of hard-coding them.
- Add dependency on `wcmatch`.
- Remove tests on deprecated `ubuntu-18.04`.
- Document preset options ovveriding. Closes {issue}`232`.
- Document configuration option pattern matching and default folder. Closes {issue}`197` and {issue}`211`.

## [3.0.1 (2022-08-07)](https://github.com/kdeldycke/click-extra/compare/v3.0.0...v3.0.1)

- Fix wrong dependency bump on `pytest-cov` produced by major release.

## [3.0.0 (2022-08-07)](https://github.com/kdeldycke/click-extra/compare/v2.1.3...v3.0.0)

- Make default extra features optional, so `click_extra` can act as a drop-in replacement for `click` and `cloup` (closes {issue}`173`):
  - Rename `click_extra.group` to `click_extra.extra_group`.
  - Rename `click_extra.command` to `click_extra.extra_command`.
  - Alias `click_extra.group` to `cloup.group`.
  - Alias `click_extra.command` to `cloup.group`.
- Use declarative `params=` argument to set defaults options on `extra_command` and `extra_group`.
- Move the implementation of options to classes.
- Hard-copy `version_option` code from `click` to allow for more flexibility. Addresses {issue}`176`.
- All custom options inherits from `ExtraOption` class.
- New `extra_option_at_end` to `extra_command` to force position of all extra options (on by default).
- Replace theme styles inherited from `click-log` by Python standard `logging` module. Adds `info` and removes `exception` styles.
- Add a tutorial in documentation.
- Add support for `.. click:example::` and `.. click:run::` directives in documentation.
- Add ANSI session and console lexers for Pygments.
- Add a Pygments filter to transform tokens into ANSI tokens.
- Add custom Pygment style to render ANSI tokens in `furo` theme.
- Add dependency on `pygments`, `pygments-ansi-color` and `Pallets-Sphinx-Themes`.
- Allow translation of short help in extra options.
- Add minimal type hints.
- Pre-compute test matrix to allow for a subset of jobs to fail if flagged as unstable.
- Run tests on `ubuntu-22.04` and `macos-12`.
- Remove tests on deprecated `macos-10.15`.

## [2.1.3 (2022-07-08)](https://github.com/kdeldycke/click-extra/compare/v2.1.2...v2.1.3)

- Do not render `None` cells in tables with `<null>` string.
- Disable workflow grouping and concurrency management.

## [2.1.2 (2022-06-02)](https://github.com/kdeldycke/click-extra/compare/v2.1.1...v2.1.2)

- Fix auto-mapping and recognition of all missing Click option types in config module. Closes {issue}`170`.
- Fix CI workflow grouping.

## [2.1.1 (2022-05-22)](https://github.com/kdeldycke/click-extra/compare/v2.1.0...v2.1.1)

- Fix compatibility with `cloup >= 0.14.0`.
- Group workflow jobs so new commits cancels in-progress execution triggered by previous commits.
- Run tests on early Python 3.11 releases.

## [2.1.0 (2022-04-22)](https://github.com/kdeldycke/click-extra/compare/v2.0.2...v2.1.0)

- Add a `highlight` utility to style substrings.
- Add `regex` dependency.

## [2.0.2 (2022-04-14)](https://github.com/kdeldycke/click-extra/compare/v2.0.1...v2.0.2)

- Fix and unittest derivation of configuration template and types from CLI
  options.
- Fix dependency requirements induced by overzealous automatic post-release
  version bump workflow.
- Replace `sphinx_tabs` by `sphinx-design`.
- Add edit link to documentation pages.

## [2.0.1 (2022-04-13)](https://github.com/kdeldycke/click-extra/compare/v2.0.0...v2.0.1)

- Fix mapping of file arguments in configuration files.
- Fix Sphinx documentation update and publishing.
- Run tests on `pypy-3.7`.

## [2.0.0 (2022-04-11)](https://github.com/kdeldycke/click-extra/compare/v1.9.0...v2.0.0)

- Add support for XML configuration file. Closes {issue}`122`.
- Add strict mode to fail on unrecognized configuration options.
- Support the `NO_COLOR` environment variable convention from
  [`no-color.org`](https://no-color.org).
- Recognize a subset of `(FORCE_)(CLI)(NO_)COLOR(S)(_FORCE)` variations as
  color-sensitive environment variables.
- Print version and environment details in logs at the `DEBUG` level.
- Add Sphinx-based documentation.
- Add a logo.
- Outsource documentation publishing to external workflow.

## [1.9.0 (2022-04-08)](https://github.com/kdeldycke/click-extra/compare/v1.8.0...v1.9.0)

- Add supports for `.ini` configuration files.
- Add supports for commented JSON configuration files.
- Fix identification of TOML and JSON configuration files.
- Fix leak of local environment variable update on `extend_env()` usage.
- Ignore `help` boolean in configuration files.
- Add new dependency on `mergedeep`.

## [1.8.0 (2022-04-03)](https://github.com/kdeldycke/click-extra/compare/v1.7.0...v1.8.0)

- Split the `print_cli_output` method to expose the simpler `format_cli` utility.

## [1.7.0 (2022-03-31)](https://github.com/kdeldycke/click-extra/compare/v1.6.4...v1.7.0)

- Refactor global logging management.
- Remove `click_extra.run.run` and rebase all run utilities around `subprocess.run`.
- Use the `tomllib` from the standard library starting with Python 3.11.

## [1.6.4 (2022-03-04)](https://github.com/kdeldycke/click-extra/compare/v1.6.3...v1.6.4)

- Fix extension of default environment variables.

## [1.6.3 (2022-03-04)](https://github.com/kdeldycke/click-extra/compare/v1.6.2...v1.6.3)

- Add support for environment variables to run utilities.

## [1.6.2 (2022-03-03)](https://github.com/kdeldycke/click-extra/compare/v1.6.1...v1.6.2)

- Temporarily skip displaying environment details in `--version` option results
  for `python >= 3.10`.
- Reactivate all tests on Python 3.10.

## [1.6.1 (2022-03-02)](https://github.com/kdeldycke/click-extra/compare/v1.6.0...v1.6.1)

- Expose some `cloup` versions of `click` utilities at the root of
  `click_extra`.

## [1.6.0 (2022-03-02)](https://github.com/kdeldycke/click-extra/compare/v1.5.0...v1.6.0)

- Allow `click_extra` to be imported as a drop-in replacement for `click`.
- Share the same set of default options between `click_extra.command` and
  `click_extra.group`.
- Document default help screen comparison between simple `click` CLI and
  enhanced `click-extra` CLI.

## [1.5.0 (2022-02-21)](https://github.com/kdeldycke/click-extra/compare/v1.4.1...v1.5.0)

- Add support for JSON configuration file.
- Search all supported formats in default location if configuration file not
  provided.
- Print configuration file default location in help screens.

## [1.4.1 (2022-02-13)](https://github.com/kdeldycke/click-extra/compare/v1.4.0...v1.4.1)

- Add new external workflow to modernize Python code.
- Use external workflow suite to manage changelog and build & publish packages
  on PyPi on release.
- Use external workflow to label sponsored issues and PRs.
- Replace local workflow by external one to label issues and PRs.
- Reuse externnal workflow to produce dependency graph.
- Remove dev dependencies on `check-wheel-contents`, `graphviz`, `pipdeptree`
  and `twine`.

## [1.4.0 (2022-01-08)](https://github.com/kdeldycke/click-extra/compare/v1.3.0...v1.4.0)

- Allow downloading of a remote config URL.
- Add new dependencies on `requests` and `pytest-httpserver`.
- Fix inference of config file top-level section name.
- Document usage of `click_extra.config.config_option`.
- Use external workflows for GitHub actions.
- Automate version and changelog management.

## [1.3.0 (2021-11-28)](https://github.com/kdeldycke/click-extra/compare/v1.2.2...v1.3.0)

- Add support for YAML configuration file. Closes #13.
- Auto-detect configuration file on loading.
- Add `pyyaml` dependency.

## [1.2.2 (2021-11-04)](https://github.com/kdeldycke/click-extra/compare/v1.2.1...v1.2.2)

- Evaluate format option dynamically at use to let third-party register new
  rendering formats.

## [1.2.1 (2021-11-04)](https://github.com/kdeldycke/click-extra/compare/v1.2.0...v1.2.1)

- Fix creation of post-release version bump PR on tagging.

## [1.2.0 (2021-11-04)](https://github.com/kdeldycke/click-extra/compare/v1.1.1...v1.2.0)

- Extend `cli-helper.TabularOutputFormatter` with new formats: `simple_grid`,
  `rounded_grid`, `double_grid`, `outline`, `simple_outline`, `rounded_outline`
  and `double_outline`. Address {issue}`astanin/python-tabulate#151`.
- Add a new `--table-format`/`-t` option to select table format rendering mode.
- Add new dependency on `cli-helper` and `tabulate`.
- Automate post-release version bump.

## [1.1.1 (2021-11-01)](https://github.com/kdeldycke/click-extra/compare/v1.1.0...v1.1.1)

- Fix printing of additional non-grouped default options in help screen.

## [1.1.0 (2021-10-28)](https://github.com/kdeldycke/click-extra/compare/v1.0.1...v1.1.0)

- Add a `--config`/`-C` option to load CLI configuration from a TOML file.

## [1.0.1 (2021-10-27)](https://github.com/kdeldycke/click-extra/compare/v1.0.0...v1.0.1)

- Re-release previous version with fixed dependency.

## [1.0.0 (2021-10-27)](https://github.com/kdeldycke/click-extra/compare/v0.0.1...v1.0.0)

- Add colorization of options, choices and metavars in help screens.
- Add `--color`/`--no-color` option flag (aliased to `--ansi`/`--no-ansi`).
- Add colored `--version` option.
- Add colored `--verbosity` option and logs.
- Add dependency on `click-log`.
- `--time`/`--no-time` flag to measure duration of command execution.
- Add platform recognition utilities.
- Add new conditional markers for `pytest`: `@skip_{linux,macos,windows}`,
  `@unless_{linux,macos,windows}`, `@destructive` and `@non_destructive`.

## [0.0.1 (2021-10-18)](https://github.com/kdeldycke/click-extra/compare/88b81e...v0.0.1)

- Initial public release.
