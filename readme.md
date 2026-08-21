<p align="center">
  <a href="https://github.com/kdeldycke/click-extra/">
    <img src="https://raw.githubusercontent.com/kdeldycke/click-extra/main/docs/assets/logo-banner.svg" alt="Click Extra">
  </a>
</p>

[![Last release](https://img.shields.io/pypi/v/click-extra.svg)](https://pypi.org/project/click-extra/)
[![Python versions](https://img.shields.io/pypi/pyversions/click-extra.svg)](https://pypi.org/project/click-extra/)
[![Downloads](https://static.pepy.tech/badge/click-extra/month)](https://pepy.tech/projects/click-extra)
[![Unittests status](https://img.shields.io/github/actions/workflow/status/kdeldycke/click-extra/tests.yaml?branch=main&label=%F0%9F%94%AC%20Tests)](https://github.com/kdeldycke/click-extra/actions/workflows/tests.yaml?query=branch%3Amain)
[![Documentation status](https://img.shields.io/github/actions/workflow/status/kdeldycke/click-extra/docs.yaml?branch=main&label=%F0%9F%93%9A%20Docs)](https://github.com/kdeldycke/click-extra/actions/workflows/docs.yaml?query=branch%3Amain)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.7116050.svg)](https://doi.org/10.5281/zenodo.7116050)

## What is Click Extra?

It should be easy to write a good CLI in Python. [Click](https://click.palletsprojects.com) makes it so. But there are still hundreds of tweaks to implement by yourself to have a user-friendly CLI.

Click Extra is a **ready-to-use wrapper around Click** to make your CLI look good and behave well. It is a drop-in replacement with good defaults that saves lots of boilerplate code and frustration by making all parts working together.

It also comes with [workarounds and patches](https://kdeldycke.github.io/click-extra/upstream.html) that have not reached upstream yet (or are unlikely to).

## Who is this for?

Anyone building a CLI who doesn't have time to assemble the pieces from scratch:

- You use Click and want professional defaults without the boilerplate.
- You're a security researcher turning a proof-of-concept into a presentable tool to hand off, demo, or attach to an advisory.
- You're a DevOps engineer or sysadmin whose one-off script grew into a team tool and needs `--help`, `--verbose`, `--config`, and colored output.

Click Extra's defaults-first design means one decorator gets you there. See the [30-second quick start](https://kdeldycke.github.io/click-extra/tutorial.html#from-script-to-cli-in-30-seconds).

## Demo

You can try Click Extra right now in your terminal, without installing any dependency or virtual env [thanks to `uvx`](https://docs.astral.sh/uv/guides/tools/):

```shell-session
$ uvx click-extra
```

This is a great way to play with Click Extra and check that it runs fine on your system, and renders properly in your terminal.

## Example

It transforms this vanilla `click` CLI:

![click CLI help screen](https://raw.githubusercontent.com/kdeldycke/click-extra/main/docs/assets/hello-click-screen.svg)

Into this:

![click-extra CLI help screen](https://raw.githubusercontent.com/kdeldycke/click-extra/main/docs/assets/hello-click-extra-screen.svg)

And here is the entire diff between the two. Click Extra proxies the whole `click` namespace, so aliasing it back leaves every decorator and call untouched:

```diff
-import click
+import click_extra as click
```

The colors, and every option below `--name`, come from that one line. Both screens above are captured from the [tutorial](https://kdeldycke.github.io/click-extra/tutorial.html)'s own live examples.

## Features

### Help screens and theming

- [Colorized help screens](https://kdeldycke.github.io/click-extra/colorize.html): options, choices, metavars, arguments, defaults, ranges, required labels, environment variables, subcommands and aliases all get distinct styles. Option names referenced in descriptions and docstrings are [highlighted automatically](https://kdeldycke.github.io/click-extra/colorize.html#cross-reference-highlighting)
- [Theme system](https://kdeldycke.github.io/click-extra/theme.html) with seven built-in themes ([`dark`, `light`, `dracula`, `monokai`, `nord`, `solarized_dark`, and a monochrome `manpage`](https://kdeldycke.github.io/click-extra/theme.html#built-in-themes)), here recoloring the same help screen:
  ![The same help screen under the dark and dracula themes](https://raw.githubusercontent.com/kdeldycke/click-extra/main/docs/assets/theme-gallery-screen.svg)
- [User-defined themes and partial overrides loaded from the CLI's `--config` file](https://kdeldycke.github.io/click-extra/theme.html#themes-from-your-config-file) (`[tool.<cli>.themes.<name>]`), scoped per invocation so concurrent runs don't bleed into each other
- [`--theme` flag](https://kdeldycke.github.io/click-extra/theme.html#the-theme-option) on every command, with case-insensitive validation against the live registry
- [`CLICK_EXTRA_THEME`](https://kdeldycke.github.io/click-extra/theme.html#environment-variables) exported once from a shell profile themes every Click Extra CLI on the machine, with a per-CLI `<CLI>_THEME` taking precedence over it
- [`--theme=auto`](https://kdeldycke.github.io/click-extra/theme.html#automatic-background-detection) reads the terminal's own background to pick between the dark and light palettes, from `CLITHEME`, `COLORFGBG`, or an opt-in [OSC 11 query](https://kdeldycke.github.io/click-extra/theme.html#querying-the-terminal-directly)
- `-h`/`--help` option names (see [rant on other inconsistencies](https://blog.craftyguy.net/cmdline-help/))
- Built-in [`help` subcommand](https://kdeldycke.github.io/click-extra/commands.html#help-subcommand) with a `--search` mode for groups
- [Usage examples](https://kdeldycke.github.io/click-extra/commands.html#examples) declared as `examples=[("description", "command")]` on any command, rendered in the help screen, the man page and every machine-readable format

### Standard options on every CLI

Listed in the order they show up in a `--help` screen:

- [`--time`/`--no-time`](https://kdeldycke.github.io/click-extra/execution.html#timer) to measure command execution duration
- `--color[=WHEN]` tri-state flag (`auto`/`always`/`never`) with a hidden `--no-color` alias, recognizing `NO_COLOR` ([no-color.org](https://no-color.org)), `FORCE_COLOR`, `CLICOLOR`, and `LLM` environment variables
- [`--params`](https://kdeldycke.github.io/click-extra/parameters.html#params-option) to debug parameter defaults, values, environment variables and provenance
- [`--table-format`](https://kdeldycke.github.io/click-extra/table.html#table-formats) to switch between 40+ table-rendering styles, from terminal grids to machine-readable `json`, `yaml`, `toml`, `csv` and `xml` (uses [`print_table()`](https://kdeldycke.github.io/click-extra/table.html) and [`serialize_data()`](https://kdeldycke.github.io/click-extra/table.html#data-serialization))
- [Colored `--verbosity` LEVEL and logs](https://kdeldycke.github.io/click-extra/logging.html), plus `-v`/`--verbose` repetition for incremental bumping
- [`--tree`](https://kdeldycke.github.io/click-extra/tree.html) to print the whole hierarchy of nested subcommands with their descriptions, aliases and deprecations:
  ![Nested subcommands printed as a tree](https://raw.githubusercontent.com/kdeldycke/click-extra/main/docs/assets/command-tree-screen.svg)
- [`--man`](https://kdeldycke.github.io/click-extra/man-page.html#reading-a-manual) to typeset the command's manual and page it, the way `man` does, for a CLI that ships no man page at all
- [`--help-format`](https://kdeldycke.github.io/click-extra/machine-readable.html) to render the command as JSON, Markdown, a man page or a [Carapace](https://carapace.sh) spec, for the readers that are programs rather than people: one option carrying a format, not one flag per format
- [Colored `--version`](https://kdeldycke.github.io/click-extra/version.html) with [template variables](https://kdeldycke.github.io/click-extra/version.html#variables) for git metadata (branch, hash, date, tag) and [pre-baking](https://kdeldycke.github.io/click-extra/version.html#pre-baking-git-metadata) for compiled binaries (Nuitka, PyInstaller)

Two more options are one decorator away, for a CLI that wants them:

- [`--jobs`](https://kdeldycke.github.io/click-extra/execution.html#parallel-jobs) for parallel-execution worker counts
- `--telemetry`/`--no-telemetry` flag to opt-in/out of tracking code, recognizing `DO_NOT_TRACK` from [consoledonottrack.com](https://consoledonottrack.com)

And every CLI gets these on top:

- Global `show_envvar` option to display all environment variables in help screens
- Global `show_choices` to activate selection of choices on user input prompts
- Auto-generation and normalization of environment variables for all options

### CLI wrapper

- [CLI wrapper](https://kdeldycke.github.io/click-extra/wrap.html) (`click-extra wrap`) applies help colorization, themes, and config loading to any Click CLI without modifying its source code:
  ![Flask's help screen rendered through the wrapper](https://raw.githubusercontent.com/kdeldycke/click-extra/main/docs/assets/wrap-flask-help-screen.svg)
- [`--params` mode](https://kdeldycke.github.io/click-extra/wrap.html#introspecting-external-clis) to introspect any external Click CLI's parameters, restricted to the columns you care about:
  ![Flask's parameters listed by the wrapper](https://raw.githubusercontent.com/kdeldycke/click-extra/main/docs/assets/wrap-flask-params-screen.svg)
- That same inventory in any [machine-readable format](https://kdeldycke.github.io/click-extra/machine-readable.html#any-click-cli), for a script that has to consume another CLI's interface:
  ![Flask's parameters exported as JSON](https://raw.githubusercontent.com/kdeldycke/click-extra/main/docs/assets/wrap-flask-json-screen.svg)
- [`--help-format carapace`](https://kdeldycke.github.io/click-extra/carapace.html#the-wrap-help-format-carapace-mode) to export any Click CLI's [Carapace](https://carapace.sh) completion spec, for identical completions in Bash, Zsh, Fish, Nushell, PowerShell, Elvish and Xonsh, with `--install` putting it where Carapace looks (and `--help-format man --install` doing the same for a man page):
  ![A Carapace completion spec generated from Flask](https://raw.githubusercontent.com/kdeldycke/click-extra/main/docs/assets/wrap-carapace-screen.svg)
- [`--man` mode](https://kdeldycke.github.io/click-extra/man-page.html#reading-a-manual) to read the manual of a CLI that never wrote one
- [`--help-format` mode](https://kdeldycke.github.io/click-extra/machine-readable.html#any-click-cli) to describe any Click CLI as JSON, Markdown, a man page or a Carapace spec: usage line, option groups, subcommands and all, with no cooperation from the target
- [`--tree` mode](https://kdeldycke.github.io/click-extra/tree.html#foreign-clis) to print any external Click CLI's subcommand hierarchy without running it
- [User-defined themes via `--config`](https://kdeldycke.github.io/click-extra/wrap.html#custom-themes-via-config) work transparently through the wrapper, so users can theme third-party CLIs from their own `pyproject.toml`

### Configuration

- [Multi-format configuration file](https://kdeldycke.github.io/click-extra/config.html) loader for:
  - `TOML`
  - `YAML`
  - `JSON`, `JSON5`, `JSONC` and `HJSON`
  - `INI`, with extended interpolation, multi-level sections and non-native types (`list`, `set`, …)
  - `XML`
  - `plist`, in both its XML and binary variants
- Automatic [`pyproject.toml` integration](https://kdeldycke.github.io/click-extra/config.html#dotted-keys): the CLI reads its `[tool.<cli>]` section from the user's project file, including a CWD-aware walk that skips unrelated `pyproject.toml` files
- [Inference of the configuration file structure](https://kdeldycke.github.io/click-extra/config.html#standalone-option) from your CLI's options, with optional [dataclass schema typing](https://kdeldycke.github.io/click-extra/config.html#schema-only-configuration) so values arrive parsed and validated
- Remote loading of [configuration from URLs](https://kdeldycke.github.io/click-extra/config.html#remote-url)
- Optional [strict validation](https://kdeldycke.github.io/click-extra/config.html#strictness) of configuration with `--validate-config`
- [Extension hook](https://kdeldycke.github.io/click-extra/config.html#extending-validation) (`ConfigValidator`) for user-defined sub-trees whose keys are *data* rather than CLI flags (per-plugin overrides, matrix axes, user-defined IDs), with rooted `ValidationError` reporting
- Respect the [default application path](https://kdeldycke.github.io/click-extra/config.html#default-folder) on each platform (XDG spec. on Linux)
- [Glob search patterns](https://kdeldycke.github.io/click-extra/config.html#search-pattern) for configuration files
- A `--no-config` option to disable configuration file loading
- Respect of `Prompt` > `CLI` > `Environment` > `Config` > `Defaults` [precedence](https://kdeldycke.github.io/click-extra/config.html#precedence)

### Types and parameters

- [`EnumChoice`](https://kdeldycke.github.io/click-extra/types.html#enumchoice) — `click.Choice` subclass with proper `Enum` rendering, case-insensitive matching, alias support, and pluggable [choice sources](https://kdeldycke.github.io/click-extra/types.html#choice-source)
- [Click parameter introspection](https://kdeldycke.github.io/click-extra/parameters.html#introspecting-parameters) and a [shared parameter structure](https://kdeldycke.github.io/click-extra/parameters.html#parameter-structure) used by both `--params` and the config loader

### Performance and structure

- [Lazy-loading of subcommands](https://kdeldycke.github.io/click-extra/commands.html#lazily-loading-subcommands) from module paths to speed up CLI startup time
- [Composition with third-party Click CLIs](https://kdeldycke.github.io/click-extra/commands.html#third-party-commands-composition) (`wrap_other_commands`)

### Documentation tooling

- [`click-extra screenshot`](https://kdeldycke.github.io/click-extra/screenshots.html) captures any CLI's colored output as an SVG image or a self-contained HTML block, and the window it is drawn in is yours to set: [terminal preset](https://kdeldycke.github.io/click-extra/screenshots.html#terminal-presets), [light or dark chrome](https://kdeldycke.github.io/click-extra/screenshots.html#light-and-dark-chrome), gradient backdrop, caption, line numbers, transparency, credit line, border, shadow, corner radius and margins. Every capture in this readme is one, rewritten on each documentation build, and a pair of them can be [switched on the reader's own color scheme](https://kdeldycke.github.io/click-extra/screenshots.html#github-integration):
  ![A CLI help screen captioned, numbered and left see-through on a gradient backdrop](https://raw.githubusercontent.com/kdeldycke/click-extra/main/docs/assets/styled-window-screen.svg)
- [`click:source` and `click:run` Sphinx directives](https://kdeldycke.github.io/click-extra/sphinx.html#click-directives) in MyST Markdown and reStructuredText to document CLI source code and their execution
- [`python:source`, `python:run`, `python:render`, `python:render-myst`, `python:render-rst`](https://kdeldycke.github.io/click-extra/sphinx.html#python-directives) — the same machinery for arbitrary Python, with a `render*` family that parses the captured output as live document content (replaces the `docs_update.py` + marker-region pattern)
- [Inline testing of CLI examples](https://kdeldycke.github.io/click-extra/sphinx.html#inline-tests) in documentation: every `click:run` block runs at build time and assertions fail the build
- Render [GitHub alerts](https://kdeldycke.github.io/click-extra/sphinx.html) into MyST admonitions in both Sphinx and MkDocs
- [ANSI-capable Pygments lexers](https://kdeldycke.github.io/click-extra/pygments.html#ansi-language-lexers) for shell session and console output, with [24-bit true-color rendering](https://kdeldycke.github.io/click-extra/pygments.html#true-color-24-bit) on by default
- [`AnsiHtmlFormatter`](https://kdeldycke.github.io/click-extra/pygments.html#ansi-html-formatter) for HTML output of ANSI-colored text
- [MkDocs plugin](https://kdeldycke.github.io/click-extra/mkdocs.html) for ANSI color rendering in code blocks

### Testing

- [`CliRunner`](https://kdeldycke.github.io/click-extra/testing.html) — `click.testing.CliRunner` subclass that captures `stdout` and `stderr` separately and preserves ANSI codes for assertion against colored output
- [pytest fixtures](https://kdeldycke.github.io/click-extra/pytest.html#fixtures) (`invoke`, `runner`, `create_config`) and ready-made regex helpers (`default_options_uncolored_help`, `default_debug_*`) for click-extra-aware test suites

### Upstream

- [Fixes 100+ bugs and addresses missing features](https://kdeldycke.github.io/click-extra/upstream.html) across Click, Cloup, Pygments, tabulate, MyST-Parser, Furo, and unmaintained `click-contrib` packages
- Drop-in replacement for [Click](https://click.palletsprojects.com) and [Cloup](https://github.com/janluke/cloup): every `from click_extra import …` and `@click_extra.command` works as a transparent superset. Cloup provides option groups, constraints, subcommand sections, aliases, and `Did you mean <subcommand>?` suggestions; click-extra adds everything above on top.

## Used in

Check these projects to get real-life examples of `click-extra` usage.

### CLIs built on it

- ![GitHub stars](https://img.shields.io/github/stars/kdeldycke/meta-package-manager?label=%E2%AD%90&style=flat-square) [Meta Package Manager](https://github.com/kdeldycke/meta-package-manager) - A unifying CLI for multiple package managers.
- ![GitHub stars](https://img.shields.io/github/stars/kdeldycke/mail-deduplicate?label=%E2%AD%90&style=flat-square) [Mail Deduplicate](https://github.com/kdeldycke/mail-deduplicate) - A CLI to deduplicate similar emails.
- ![GitHub stars](https://img.shields.io/github/stars/kdeldycke/repomatic?label=%E2%AD%90&style=flat-square) [repomatic](https://github.com/kdeldycke/repomatic) - Automate repository maintenance, releases and CI/CD workflows.
- ![GitHub stars](https://img.shields.io/github/stars/couchbaselabs/agent-catalog?label=%E2%AD%90&style=flat-square) [agent-catalog](https://github.com/couchbaselabs/agent-catalog) - Couchbase agent catalog.
- ![GitHub stars](https://img.shields.io/github/stars/SkwalExe/octo-logo?label=%E2%AD%90&style=flat-square) [octo-logo](https://github.com/SkwalExe/octo-logo) - Simple logos for complex projects.
- ![GitHub stars](https://img.shields.io/github/stars/Project-Muteki/besta-tools?label=%E2%AD%90&style=flat-square) [besta-tools](https://github.com/Project-Muteki/besta-tools) - Tools for Besta devices and Besta RTOS proprietary formats.

### Documentation rendered with it

These pull `click-extra[sphinx]` or `click-extra[mkdocs]` for GitHub alerts, ANSI-colored code blocks and live CLI examples, and build their own command line on something else:

- ![GitHub stars](https://img.shields.io/github/stars/ankitects/anki?label=%E2%AD%90&style=flat-square) [Anki](https://github.com/ankitects/anki) - A smart spaced repetition flashcard program.
- ![GitHub stars](https://img.shields.io/github/stars/jazzband/pip-tools?label=%E2%AD%90&style=flat-square) [pip-tools](https://github.com/jazzband/pip-tools) - A set of tools to keep your pinned Python dependencies fresh.
- ![GitHub stars](https://img.shields.io/github/stars/callowayproject/bump-my-version?label=%E2%AD%90&style=flat-square) [bump-my-version](https://github.com/callowayproject/bump-my-version) - A CLI updating every version string in a project.
- ![GitHub stars](https://img.shields.io/github/stars/litestar-org/sqlspec?label=%E2%AD%90&style=flat-square) [SQLSpec](https://github.com/litestar-org/sqlspec) - A query mapper for Python.
- ![GitHub stars](https://img.shields.io/github/stars/kdeldycke/extra-platforms?label=%E2%AD%90&style=flat-square) [Extra Platforms](https://github.com/kdeldycke/extra-platforms) - Detect architectures, platforms, shells, terminals and CI systems, grouped by family.

Feel free to send a PR to add your project in either list if you are relying on Click Extra in any way.
