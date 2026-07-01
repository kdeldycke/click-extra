<p align="center">
  <a href="https://github.com/kdeldycke/click-extra/">
    <img src="https://raw.githubusercontent.com/kdeldycke/click-extra/v8.2.0/docs/assets/logo-banner.svg" alt="Click Extra">
  </a>
</p>

[![Last release](https://img.shields.io/pypi/v/click-extra.svg)](https://pypi.org/project/click-extra/)
[![Python versions](https://img.shields.io/pypi/pyversions/click-extra.svg)](https://pypi.org/project/click-extra/)
[![Downloads](https://static.pepy.tech/badge/click-extra/month)](https://pepy.tech/projects/click-extra)
[![Unittests status](https://img.shields.io/github/actions/workflow/status/kdeldycke/click-extra/tests.yaml?branch=main&label=%F0%9F%94%AC%20Tests)](https://github.com/kdeldycke/click-extra/actions/workflows/tests.yaml?query=branch%3Amain)
[![Coverage status](https://codecov.io/gh/kdeldycke/click-extra/graph/badge.svg?token=PMEcGfrVEs)](https://codecov.io/gh/kdeldycke/click-extra)
[![Documentation status](https://img.shields.io/github/actions/workflow/status/kdeldycke/click-extra/docs.yaml?branch=main&label=%F0%9F%93%9A%20Docs)](https://github.com/kdeldycke/click-extra/actions/workflows/docs.yaml?query=branch%3Amain)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.7116050.svg)](https://doi.org/10.5281/zenodo.7116050)

## What is Click Extra?

It should be easy to write a good CLI in Python. [Click](https://click.palletsprojects.com) makes it so. But there is still hundrends of tweaks to implement by yourself to have a user-friendly CLI.

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

![click CLI help screen](https://raw.githubusercontent.com/kdeldycke/click-extra/v8.2.0/docs/assets/click-help-screen.png)

Into this:

![click-extra CLI help screen](https://raw.githubusercontent.com/kdeldycke/click-extra/v8.2.0/docs/assets/click-extra-screen.png)

To understand how we ended up with the result above, [go read the tutorial](https://kdeldycke.github.io/click-extra/tutorial.html).

## Features

### Configuration

- [Multi-format configuration file](https://kdeldycke.github.io/click-extra/config.html) loader for:
  - `TOML`
  - `YAML`
  - `JSON`, `JSON5`, `JSONC` and `HJSON`
  - `INI`, with extended interpolation, multi-level sections and non-native types (`list`, `set`, …)
  - `XML`
- Automatic [`pyproject.toml` integration](https://kdeldycke.github.io/click-extra/config.html#dotted-keys): the CLI reads its `[tool.<cli>]` section from the user's project file, including a CWD-aware walk that skips unrelated `pyproject.toml` files
- [Inference of the configuration file structure](https://kdeldycke.github.io/click-extra/config.html#standalone-option) from your CLI's options, with optional [dataclass schema typing](https://kdeldycke.github.io/click-extra/config.html#schema-only-configuration) so values arrive parsed and validated
- Remote loading of [configuration from URLs](https://kdeldycke.github.io/click-extra/config.html#remote-url)
- Optional [strict validation](https://kdeldycke.github.io/click-extra/config.html#strictness) of configuration with `--validate-config`
- [Extension hook](https://kdeldycke.github.io/click-extra/config.html#extending-validation) (`ConfigValidator`) for user-defined sub-trees whose keys are *data* rather than CLI flags (per-plugin overrides, matrix axes, user-defined IDs), with rooted `ValidationError` reporting
- Respect the [default application path](https://kdeldycke.github.io/click-extra/config.html#default-folder) on each platform (XDG spec. on Linux)
- [Glob search patterns](https://kdeldycke.github.io/click-extra/config.html#search-pattern) for configuration files
- A `--no-config` option to disable configuration file loading
- Respect of `Prompt` > `CLI` > `Environment` > `Config` > `Defaults` [precedence](https://kdeldycke.github.io/click-extra/config.html#precedence)

### Help screens and theming

- [Colorized help screens](https://kdeldycke.github.io/click-extra/colorize.html): options, choices, metavars, arguments, defaults, ranges, required labels, environment variables, subcommands and aliases all get distinct styles. Option names referenced in descriptions and docstrings are [highlighted automatically](https://kdeldycke.github.io/click-extra/colorize.html#cross-reference-highlighting)
- [Theme system](https://kdeldycke.github.io/click-extra/theme.html) with seven built-in themes ([`dark`, `light`, `dracula`, `monokai`, `nord`, `solarized_dark`, and a monochrome `manpage`](https://kdeldycke.github.io/click-extra/theme.html#built-in-themes))
- [User-defined themes and partial overrides loaded from the CLI's `--config` file](https://kdeldycke.github.io/click-extra/theme.html#themes-from-your-config-file) (`[tool.<cli>.themes.<name>]`), scoped per invocation so concurrent runs don't bleed into each other
- [`--theme` flag](https://kdeldycke.github.io/click-extra/theme.html#the-theme-option) on every command, with case-insensitive validation against the live registry
- `-h`/`--help` option names (see [rant on other inconsistencies](https://blog.craftyguy.net/cmdline-help/))
- Built-in [`help` subcommand](https://kdeldycke.github.io/click-extra/commands.html#help-subcommand) with a `--search` mode for groups

### Standard options on every CLI

- [Colored `--version`](https://kdeldycke.github.io/click-extra/version.html) with [template variables](https://kdeldycke.github.io/click-extra/version.html#variables) for git metadata (branch, hash, date, tag) and [pre-baking](https://kdeldycke.github.io/click-extra/version.html#pre-baking-git-metadata) for compiled binaries (Nuitka, PyInstaller)
- [Colored `--verbosity` LEVEL and logs](https://kdeldycke.github.io/click-extra/logging.html), plus `-v`/`--verbose` repetition for incremental bumping
- [`--show-params`](https://kdeldycke.github.io/click-extra/parameters.html#show-params-option) to debug parameter defaults, values, environment variables and provenance
- [`--time`/`--no-time`](https://kdeldycke.github.io/click-extra/execution.html#timer) to measure command execution duration
- [`--table-format`](https://kdeldycke.github.io/click-extra/table.html#table-formats) to switch between 40+ table-rendering styles (uses [`print_table()`](https://kdeldycke.github.io/click-extra/table.html) and [`serialize_data()`](https://kdeldycke.github.io/click-extra/table.html#data-serialization))
- [`--jobs`](https://kdeldycke.github.io/click-extra/execution.html#parallel-jobs) for parallel-execution worker counts
- `--telemetry`/`--no-telemetry` flag to opt-in/out of tracking code
- `--color[=WHEN]` tri-state flag (`auto`/`always`/`never`) with a hidden `--no-color` alias, recognizing `NO_COLOR` ([no-color.org](https://no-color.org)), `FORCE_COLOR`, `CLICOLOR`, and `LLM` environment variables
- Recognition of `DO_NOT_TRACK` from [consoledonottrack.com](https://consoledonottrack.com) for telemetry
- Global `show_envvar` option to display all environment variables in help screens
- Global `show_choices` to activate selection of choices on user input prompts
- Auto-generation and normalization of environment variables for all options

### Types and parameters

- [`EnumChoice`](https://kdeldycke.github.io/click-extra/types.html#enumchoice) — `click.Choice` subclass with proper `Enum` rendering, case-insensitive matching, alias support, and pluggable [choice sources](https://kdeldycke.github.io/click-extra/types.html#choice-source)
- [Click parameter introspection](https://kdeldycke.github.io/click-extra/parameters.html#introspecting-parameters) and a [shared parameter structure](https://kdeldycke.github.io/click-extra/parameters.html#parameter-structure) used by both `--show-params` and the config loader

### CLI wrapper

- [CLI wrapper](https://kdeldycke.github.io/click-extra/wrap.html) (`click-extra wrap`) applies help colorization, themes, and config loading to any Click CLI without modifying its source code
- [`show-params` subcommand](https://kdeldycke.github.io/click-extra/wrap.html#introspecting-external-clis) to introspect any external Click CLI's parameters
- [User-defined themes via `--config`](https://kdeldycke.github.io/click-extra/wrap.html#custom-themes-via-config) work transparently through the wrapper, so users can theme third-party CLIs from their own `pyproject.toml`

### Performance and structure

- [Lazy-loading of subcommands](https://kdeldycke.github.io/click-extra/commands.html#lazily-loading-subcommands) from module paths to speed up CLI startup time
- [Composition with third-party Click CLIs](https://kdeldycke.github.io/click-extra/commands.html#third-party-commands-composition) (`wrap_other_commands`)

### Documentation tooling

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

Check these projects to get real-life examples of `click-extra` usage:

- ![GitHub stars](https://img.shields.io/github/stars/kdeldycke/meta-package-manager?label=%E2%AD%90&style=flat-square) [Meta Package Manager](https://github.com/kdeldycke/meta-package-manager)
  \- A unifying CLI for multiple package managers.
- ![GitHub stars](https://img.shields.io/github/stars/kdeldycke/mail-deduplicate?label=%E2%AD%90&style=flat-square) [Mail Deduplicate](https://github.com/kdeldycke/mail-deduplicate) - A
  CLI to deduplicate similar emails.
- ![GitHub stars](https://img.shields.io/github/stars/Sprocket-Security/fireproxng?label=%E2%AD%90&style=flat-square) [fireproxng](https://github.com/Sprocket-Security/fireproxng) - A rewrite of the fireprox tool.
- ![GitHub stars](https://img.shields.io/github/stars/couchbaselabs/agent-catalog?label=%E2%AD%90&style=flat-square) [agent-catalog](https://github.com/couchbaselabs/agent-catalog) - Couchbase agent catalog.
- ![GitHub stars](https://img.shields.io/github/stars/hugolundin/badger?label=%E2%AD%90&style=flat-square) [badger-proxy](https://github.com/hugolundin/badger) - An mDNS-based reverse
  proxy for naming services on a local network.

Feel free to send a PR to add your project in this list if you are relying on Click Extra in any way.
