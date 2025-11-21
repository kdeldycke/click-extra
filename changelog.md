# Changelog

## [7.1.0 (2025-11-21)](https://github.com/kdeldycke/click-extra/compare/v7.0.1...v7.1.0)

- Add support for aliases in `EnumChoice` type.
- Register pre-configured `render_table()` utility in the context when `table_format` is set, in the same spirit as `print_table()`.

## [7.0.1 (2025-11-18)](https://github.com/kdeldycke/click-extra/compare/v7.0.0...v7.0.1)

- Restore support for `@extra_command`, `@extra_group` and `@extra_version_option`, but mark them as deprecated.

## [7.0.0 (2025-11-17)](https://github.com/kdeldycke/click-extra/compare/v6.2.0...v7.0.0)

- Allow parent directories search for configuration files. Adds `search_parents` argument on `@config_file`. Closes {issue}`651`.
- Allow fine-tuning of configuration file format pattern matching. Replaces `formats` argument on `@config_file` by `file_format_patterns`.
- Adds `search_pattern_flags` and `file_pattern_flags` arguments on `@config_file` to allow user to tweak pattern matching behavior.
- Use `|` as separator for multiple file patterns instead of `{,}` syntax. Replace `glob.BRACE` by `glob.SPLIT` for search pattern flags. Force `glob.SPLIT` for file pattern flags.
- Remove `glob.IGNORECASE` flag to make case-sensitivity determined by the underlying platform at runtime.
- Force `glob.NODIR` for search pattern flags to speed up search.
- Rename `click_extra.config.Formats` enum to `click_extra.config.ConfigFormat`. Expose it at the root `click_extra` module.
- Eat our own dog food: add a `click-extra` CLI to run self-tests.
- Override base decorators and classes with Click Extra's own variants:
  - `@command` now points to what was `@extra_command`.
  - `@group` now points to what was `@extra_group`.
  - `Option` class now points to `click_extra.Option`, which is a subclass of `cloup.Option`.
  - `Argument` class now points to `click_extra.Argument`, which is a subclass of `cloup.Argument`.
  - `@option` now instantiates `click_extra.Option` by default.
  - `@argument` now instantiates `click_extra.Argument` by default.
  - `@version_option` now points to what was `@extra_version_option`.
  - Now if you want to use the previous aliases to Click's and Cloup's originals, import them directly from `click` or `cloup` instead of `click_extra`, which makes origination clearer.
- Remove `@extra_command`, `@extra_group` and `@extra_version_option`.
- Remove `no_redefined` argument in `click_extra.pytest.command_decorators()` method.
- Validates that classes passed to the `cls` parameter of decorators are subclasses of the expected base classes.
- Normalize the default value of `EnumChoice` parameters to their string choice representation in help screens.
- Run tests on Python `3.14t` and `3.15t` free-threaded variants.

## [6.2.0 (2025-11-04)](https://github.com/kdeldycke/click-extra/compare/v6.1.0...v6.2.0)

- Add new `EnumChoice` type for fine-tunable Enum-based choices. Expose `EnumChoice` and `ChoiceSource` at the root `click_extra` module.
- Relax dependencies to support Python 3.10. Closes {issue}`1385`.
- Re-introduce `tomli` dependency for Python 3.10 users.
- Skip tests on intermediate Python versions (`3.11`, `3.12` and `3.13`) to reduce CI load.

## [6.1.0 (2025-10-28)](https://github.com/kdeldycke/click-extra/compare/v6.0.3...v6.1.0)

- Add support for JSON5, JSONC and HJSON configuration files.
- YAML and XML configuration support is now optional. You need to install the `click_extra[yaml]` and `click_extra[xml]` extra dependency groups to enable it.
- Add new `@lazy_group` decorator and `LazyGroup` class to create groups that only load their subcommands when invoked. Closes {issue}`1332`.
- Move all custom types to `click_extra._types` module.
- Avoid importing all types at runtime to reduce startup time.
- Upgrade tests runs from `macos-13` to `macos-15-intel`, and from `macos-15` to `macos-26`.
- Use `astral-sh/setup-uv` action to install `uv`.

## [6.0.3 (2025-10-13)](https://github.com/kdeldycke/click-extra/compare/v6.0.2...v6.0.3)

- Fix `regex_fullmatch_line_by_line` to accept compiled regex patterns as well as string patterns.

## [6.0.2 (2025-10-11)](https://github.com/kdeldycke/click-extra/compare/v6.0.1...v6.0.2)

- Add a new `regex_fullmatch_line_by_line` utility to compare a wall of text against a regex, line by line, and raise a custom `RegexLineMismatch` exception on the first mismatch.

## [6.0.1 (2025-10-08)](https://github.com/kdeldycke/click-extra/compare/v6.0.0...v6.0.1)

- Fix `@config_option` to accept `Path` objects as default value. Closes {issue}`1356`.
- Add official support of Python 3.14.
- Run tests on Python 3.15-dev.

## [6.0.0 (2025-09-25)](https://github.com/kdeldycke/click-extra/compare/v5.1.1...v6.0.0)

- Add new variables for version string template: `{git_repo_path}`, `{git_branch}`, `{git_long_hash}`, `{git_short_hash}` and `{git_date}`.
- Add a new `--no-config` option on  `@extra_command` and `@extra_group` to disable configuration files. Closes {issue}`750`.
- Add `--table-format` option by default on `@extra_command` and `@extra_group`.
- Let `--table-format` and `--no-color` affect the rendering of `--show-params` table.
- Swap `Class` and `Spec.` columns in `--show-params` output.
- Remove the `-C` short option associated with `--config`.
- Remove the `-t` short option associated with `--table-format`.
- Classify table formats into two categories: markup formats and plain-text formats.
- Rename all table format identifiers to use dashes instead of underscores:
  - `double_grid` → `double-grid`
  - `double_outline` → `double-outline`
  - `fancy_grid` → `fancy-grid`
  - `fancy_outline` → `fancy-outline`
  - `heavy_grid` → `heavy-grid`
  - `heavy_outline` → `heavy-outline`
  - `latex_booktabs` → `latex-booktabs`
  - `latex_longtable` → `latex-longtable`
  - `latex_raw` → `latex-raw`
  - `mixed_grid` → `mixed-grid`
  - `mixed_outline` → `mixed-outline`
  - `rounded_grid` → `rounded-grid`
  - `rounded_outline` → `rounded-outline`
  - `simple_grid` → `simple-grid`
  - `simple_outline` → `simple-outline`
- Fix display in `--show-params` for parameters sharing the same name.
- Fix detection in the `--version` option of the module in which the user's CLI is implemented.
- Rename `click_extra.tabulate` namespace to `click_extra.table`.
- Expose `click._utils.UNSET` and `click.logging.LogLevel` at the root `click_extra` module.
- Replace unmaintained `mergedeep` dependency by `deepmerge`.
- Remove maximum capped version of all dependencies (relax all `~=` specifiers to `>=`). This gives more freedom to downstream and upstream packagers. Document each minimal version choice.
- Add unit tests for Sphinx extension.
- Render GitHub-Flavored Markdown admonitions in Sphinx.

## [5.1.1 (2025-08-24)](https://github.com/kdeldycke/click-extra/compare/v5.1.0...v5.1.1)

- Relax Click dependency to account for yanked release. Closes {issue}`1307`.

## [5.1.0 (2025-08-01)](https://github.com/kdeldycke/click-extra/compare/v5.0.2...v5.1.0)

- Add support for MyST Markdown syntax for `click:example` and `click:run` Sphinx directives.
- Add support for all `code-block` options to `click:example` and `click:run`: `:linenos:`, `:lineno-start:`, `:emphasize-lines:`, `:force:`, `:caption:`, `:name:`, `:class:` and `:dedent:`.
- Add new `:show-source:`/`:hide-source:`, `:show-results:`/`:hide-results:` and `:language:` options to `click:example` and `click:run`. Closes {issue}`719`.
- Support non-string choices in colored help screens. Closes {issue}`1284`.
- Replace `LOG_LEVELS` mapping with `LogLevel` enum.
- Remove `DEFAULT_LEVEL_NAME` constants.
- Fix rendering of default values in `--show-params` output.
- Fix reconciliation of flags' environment variables.
- Force requirement on `cloup >= 3.0.7`.
- Be more informative when error is found in `click:example` and `click:run` Sphinx directives by displaying the path of the original document and the line number of the error.

## [5.0.2 (2025-05-31)](https://github.com/kdeldycke/click-extra/compare/v5.0.1...v5.0.2)

- Set `ExtraCommand` default `prog_name` to CLI's `name` to avoid it to be named `python -m <module_name>` if invoked out of a module.
- Tweak exit code rendering of CLI runs.

## [5.0.1 (2025-05-28)](https://github.com/kdeldycke/click-extra/compare/v5.0.0...v5.0.1)

- Fix highlighting of deprecated messages.
- Use ASCII characters instead of unicode for prompt rendering in messages.

## [5.0.0 (2025-05-13)](https://github.com/kdeldycke/click-extra/compare/v4.15.0...v5.0.0)

- Upgrade to Click 8.2.0.
- Add support for custom deprecated messages on commands and parameters.
- Remove `ExtraOption.get_help_default()` and rely on new `Option.get_help_extra()`.
- Remove dependency on `pallets-sphinx-themes`.
- Drop supports for Python 3.10.
- Add `windows-11-arm` to the test matrix.
- Remove tests on `ubuntu-22.04-arm`, `ubuntu-22.04` and `windows-2022` to keep matrix small.

## [4.15.0 (2025-03-05)](https://github.com/kdeldycke/click-extra/compare/v4.14.2...v4.15.0)

- Regroup all envronment variables-related code.
- Rename `extend_envvars()` to `merge_envvar_ids()` and allow it to merge arbitrary-nested structures. Normalize names to uppercase on Windows.
- Rename `normalize_envvar()` to `clean_envvar_id()`.
- Rename `all_envvars()` to `param_envvar_ids()`.
- Rename `auto_envvar()` to `param_auto_envvar_id()`.
- Remove unused `normalize` parameter on `all_envvars()`.
- Add missing line returns in `render_cli_run()`.
- Prefix all types with capital-`T`.

## [4.14.2 (2025-02-23)](https://github.com/kdeldycke/click-extra/compare/v4.14.1...v4.14.2)

- Extract rendering part of the `print_cli_run()` helper to `render_cli_run()`.
- Remove unused `click_extra.testing.run_cmd`.
- Relax requirement on `extra-platforms`.
- Add tests on `windows-2025`. Remove tests on `windows-2019`.

## [4.14.1 (2025-02-02)](https://github.com/kdeldycke/click-extra/compare/v4.14.0...v4.14.1)

- Fix upload of Python package to GitHub release on tagging.

## [4.14.0 (2025-02-01)](https://github.com/kdeldycke/click-extra/compare/v4.13.2...v4.14.0)

- Add a new `--verbose` option on `@extra_command` and `@extra_group` to increase the verbosity level for each additional repetition.
- Add new `@verbose_option` pre-configured decorator.
- Reassign the short `-v` option from `--verbosity` to `--verbose`.
- Improve logging documentation.
- Align `ExtraStreamHandler` behavior to `logging.StreamHandler`.
- Move `stream_handler_class` and `formatter_class` arguments from `new_extra_logger` to `extraBasicConfig`.
- Add new `file_handler_class` argument to `extraBasicConfig`.
- Fix upload of Python package to GitHub release on tagging.
- Remove dependency on `pytest-cases`.

## [4.13.2 (2025-01-28)](https://github.com/kdeldycke/click-extra/compare/v4.13.1...v4.13.2)

- Re-release to fix Github publishing.
- Reactivates some color tests on Windows.

## [4.13.1 (2025-01-28)](https://github.com/kdeldycke/click-extra/compare/v4.13.0...v4.13.1)

- Re-release to fix Github publishing.

## [4.13.0 (2025-01-27)](https://github.com/kdeldycke/click-extra/compare/v4.12.0...v4.13.0)

- Revamps logging helpers and aligns them with Python's `logging` module.
- Remove `extra_basic_config`.
- Adds new `extraBasicConfig`, and aligns it with Python's `basicConfig`.
- Replace `ExtraLogFormatter` with `ExtraFormatter`.
- Replace `ExtraLogHandler` with `ExtraStreamHandler`.
- Add new `new_extra_logger` helper.
- Rewrite the logging documentation with all use-cases and custom configuration examples. Closes {issue}`989`.
- Removes old platforms page from documentation.

## [4.12.0 (2025-01-20)](https://github.com/kdeldycke/click-extra/compare/v4.11.7...v4.12.0)

- Remove Click Extra's own implementation of `HelpOption` class now that fixes have reached Click's upstream.
- Redefine `@help_option` decorator to default to `--help`/`-h` options.
- Add more logging examples in documentation.
- Add tests on `ubuntu-24.04-arm` and `ubuntu-22.04-arm`.
- Use `uv` to install specific versions of Python.

## [4.11.7 (2024-11-30)](https://github.com/kdeldycke/click-extra/compare/v4.11.6...v4.11.7)

- Remove support for comments in JSON configuration files. Remove dependency on unmaintained `commentjson`. Closes [`click-extra#1152`](https://github.com/kdeldycke/click-extra/issues/1152).

## [4.11.6 (2024-11-28)](https://github.com/kdeldycke/click-extra/compare/v4.11.5...v4.11.6)

- Make `--timer` option eager so it can jumps the queue of processing order.
- Fix configuration of help option generated by the `help_option_names` context setting. Closes [`mail-deduplicate#762`](https://github.com/kdeldycke/mail-deduplicate/issues/762).
- Fix eagerness of help option generated by `help_option_names`. Refs [`click#2811`](https://github.com/pallets/click/pull/2811).
- Display generated help option in `--show-params` results.
- Force UTF-8 encoding everywhere.

## [4.11.5 (2024-11-18)](https://github.com/kdeldycke/click-extra/compare/v4.11.4...v4.11.5)

- Allow `replace_content()` utility method to replace any content found after the start tag.

## [4.11.4 (2024-11-14)](https://github.com/kdeldycke/click-extra/compare/v4.11.3...v4.11.4)

- Ignore hidden options when coloring help screen.

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
- Document `click:example` and `click:run` Sphinx extensions.

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
- Document preset options overriding. Closes {issue}`232`.
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
- Add support for `click:example` and `click:run` directives in documentation.
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
