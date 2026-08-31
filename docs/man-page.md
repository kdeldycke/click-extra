# {octicon}`repo` Man-page

`click_extra.command_doc` extracts a command once, into a `CommandDoc`, and renders that model several ways. This page covers the man page: reading one, shipping one, and the `man-pages(7)` layout each section is built to. [Machine-readable help](machine-readable.md) covers the rest.

## Generating man pages

Every man-page section is produced mechanically by `click_extra.command_doc` from the command itself. It works on any Click command *object* (no `console_scripts` entry point required) and walks the command tree, discovering subcommands dynamically, into one roff page per command. Literal tokens (command and option names) are set bold and replaceable tokens (metavars, operands) italic, following the [literal and replaceable slots](theme.md#literal-and-replaceable-slots) split; Click's `\b` no-rewrap marker becomes a roff `.nf` / `.fi` block.

## Reading a manual

The `@man_option` decorator adds a `--man` flag that typesets the command's manual and sends it to the pager, the way `man` itself does. A CLI gets a manual to read whether or not anyone ever shipped one for it:

```{click:source}
import click

from click_extra import help_format_option, man_option

@click.command
@man_option
@help_format_option
@click.option("--name", help="Who to greet.")
def greet(name):
    """Greet someone."""
    click.echo(f"Hello, {name}!")
```

`@man_option` and `@help_format_option` are siblings: a plain Click command takes either or both, and a Click Extra one gets them among its [default options](commands.md#default-options).

```{code-block} shell-session
$ greet --man
GREET(1)                        General Commands Manual                       GREET(1)

NAME
       greet - Greet someone.

SYNOPSIS
       greet [OPTIONS]
...
```

Typesetting goes through `groff` or `mandoc`, whichever is installed. Where neither is (Windows, a slim container), the roff source is printed instead with a warning naming what to install: something on screen beats an error, and the source still carries every word.

Under [`--accessible`](colorize.md#accessible-flag) the pager is bypassed and the bold-and-underline overstrike is stripped, since a screen reader voices `N\x08NA\x08AM\x08ME\x08E` rather than skipping it.

## Shipping a manual

`--man` reads; `--help-format man` emits the roff source a packager installs. The two are one question apart: do you want to read the manual, or to ship it?

```{click:run}
result = invoke(greet, args=["--help-format", "man"])
assert result.exit_code == 0
assert '.TH "GREET" "1"' in result.output
assert "greet \\- Greet someone." in result.output
```

The quickest way to produce a man page is `wrap --help-format man`: `click-extra wrap --help-format man -- SCRIPT` resolves the target, loads the Click command, and prints its roff page to stdout without running it. Trailing arguments drill into subcommands (`click-extra wrap --help-format man -- flask run`). With uvx nothing needs to be installed up front:

```{code-block} shell-session
$ uvx --from click-extra --with flask click-extra wrap --help-format man -- flask > flask.1
```

### Multiple pages

For multi-command CLIs, `--output-dir DIR` writes the whole command tree as one `.1` file per (sub)command into `DIR` (created if missing). The output replaces stdout, so this is the right form for a release pipeline or a distributor's build phase:

```{code-block} shell-session
$ uvx --from click-extra --with flask click-extra wrap --help-format man --output-dir /tmp/man -- flask
/tmp/man/flask.1
/tmp/man/flask-run.1
/tmp/man/flask-routes.1
/tmp/man/flask-shell.1
```

`--output-dir` (and `--help-format`) must appear *before* SCRIPT, since arguments after SCRIPT navigate into nested subcommands. Mixing `--output-dir` with a SUBCOMMAND argument is rejected: the flag always emits the whole tree of SCRIPT.

### Target resolution

`SCRIPT` is accepted in five forms, tried in this order. The example above uses the first; the others reach the same Click command from a different starting point:

1. A `console_scripts` entry point exposed by an installed package, the form shown above (`flask` ships one in the `flask` distribution).

2. A local project directory, resolved from its `pyproject.toml` (`[project.scripts]`) or `setup.cfg` (`console_scripts`) entry point. Its package is added to `sys.path`, though its dependencies are not installed (see [Dependencies of the wrapped CLI](wrap.md#dependencies-of-the-wrapped-cli)):

   ```{code-block} shell-session
   $ click-extra wrap --help-format man -- ../my-project > my-project.1
   ```

3. `module:function` notation pointing straight at a Click command object. Useful when the entry point is a wrapper rather than the command itself, or when the command isn't exposed as a console script at all:

   ```{code-block} shell-session
   $ uvx --from click-extra --with flask click-extra wrap --help-format man -- flask.cli:cli > flask.1
   ```

4. A `.py` file path. The file is imported in place, with no install step required, which is the right hook for source trees that don't ship a Python build system (Autotools, Meson, Bazel):

   ```{code-block} shell-session
   $ click-extra wrap --help-format man -- path/to/my_cli.py > my_cli.1
   ```

5. A bare Python module name invocable via `python -m`. The resolver imports the module and picks up the Click command from its top-level attributes:

   ```{code-block} shell-session
   $ click-extra wrap --help-format man -- my_package.cli > my_package.1
   ```

`wrap` resolves SCRIPT the [same way](wrap.md#script-resolution) in every mode, so any of these forms works whether you run, introspect (`--params`), or document (`--help-format man`) the target.

### Programmatic API

Three entry points cover the Python API, from one-shot rendering up to writing the whole tree. Dates honor `SOURCE_DATE_EPOCH` for reproducible builds:

1. `render_manpage(cli)` returns one page's roff as a string. Use it when you want to pipe to `groff` or post-process the output before writing it:

   ```python
   from click_extra import render_manpage

   print(render_manpage(cli))
   ```

2. `render_manpages(cli)` returns a `{filename: roff}` mapping covering the whole command tree. Use it when you need to filter, rename, or splice pages before writing them:

   ```python
   from pathlib import Path
   from click_extra import render_manpages

   for filename, roff in render_manpages(cli).items():
       Path("man", filename).write_text(roff)
   ```

3. `write_manpages(cli, target_dir)` writes one `.1` file per command directly to disk: the build-system hook. A Debian package wires it into `debian/rules` from its `override_dh_installman`:

   ```{code-block} makefile
   override_dh_installman:
   	python -c "from myapp.cli import cli; from click_extra import write_manpages; write_manpages(cli, 'debian/tmp/manpages')"
   	dh_installman -O--buildsystem=pybuild
   ```

### Sphinx integration

A project already building its documentation with the `click_extra.sphinx` extension emits the same pages from that build, with one `click_extra_manpages` entry in `conf.py`. See [from a Sphinx build](#from-a-sphinx-build).

### Index

The list below is auto-generated by the [`click-extra-manpages` directive](#click-extra-manpages-directive): one link per (sub)command declared in this project's `click_extra_manpages` config, pointing at the HTML sibling rendered alongside the docs.

````{code-block} markdown
:caption: Directive call
```{click-extra-manpages}
```
````

```{click-extra-manpages}
```

## From a Sphinx build

The Sphinx extension can render the roff man page tree of any Click CLI alongside the HTML build, so a project's docs site, release pipeline, and downstream packagers all share a single generator. Add one or more entries to `click_extra_manpages` in `conf.py`:

```{code-block} python
:caption: `conf.py`
extensions = ["click_extra.sphinx"]

click_extra_manpages = [
    {
        "script": "my_pkg.cli:my_cli",   # required
        "prog_name": "my-cli",            # optional, defaults to the resolved command's name
        "output_dir": "man",              # optional, defaults to "man"
        "render_html": True,              # optional, defaults to True
    },
]
```

On every HTML build, the hook resolves each `script` with the same scanner as the [`click-extra wrap --help-format man`](#generating-man-pages) CLI and writes one `.1` file per (sub)command into `<outdir>/<output_dir>/`, mirroring what `click-extra wrap --help-format man --output-dir DIR -- SCRIPT` produces from the command line. An empty (or absent) list keeps the hook silent: no man pages, no warnings.

Only HTML-family builders (`html`, `dirhtml`, `singlehtml`) trigger the hook. Other builders (`linkcheck`, `man`, `epub`, `coverage`) skip it: roff in their output trees would be redundant or confusing.

The generator honors `SOURCE_DATE_EPOCH` for reproducible builds and inherits every option-group and Cloup-aware rendering rule documented in the [layout reference](#layout).

### HTML siblings

Browsers download `.1` files rather than render them, so each emitted page is also passed through a roff → HTML renderer when one is available. The result lands next to the source as `<page>.<section>.html` (like `my-cli.1.html`).

The hook tries [`mandoc -Thtml`](https://mandoc.bsd.lv) first, then `groff -Thtml -mandoc`, picking whichever it finds on `PATH`. mandoc is preferred for its semantic anchors: every section and option gets a stable `id`, which makes deep-linking work. If neither renderer is installed, the build still produces the `.1` files and logs a single info-level notice, which `render_html: False` suppresses.

A typical CI container ships one or the other: Debian and Ubuntu have `groff` in `build-essential`, BSDs and recent macOS images ship `mandoc`. To pin the renderer on GitHub Actions, install it explicitly:

```{code-block} yaml
:caption: `.github/workflows/docs.yaml`
- name: Install mandoc
  run: sudo apt-get install --yes mandoc
```

### Cross-linking from prose

To make the standard `:manpage:` role link to the HTML siblings the hook emits, set Sphinx's [`manpages_url`](https://www.sphinx-doc.org/en/master/usage/configuration.html#confval-manpages_url) to the matching path:

```{code-block} python
:caption: `conf.py`
manpages_url = "man/{page}.{section}.html"
```

With that in place, `` :manpage:`my-cli(1)` `` in any docstring or `.md` file resolves to `man/my-cli.1.html` in the rendered docs. The same template covers every subcommand page, since `{page}` matches the full hyphenated name the generator produces (`my-cli`, `my-cli-build`, `my-cli-build-all`).

Leaving `manpages_url` unset is fine. The role still renders as styled text; only the hyperlink target is missing.

### `click-extra-manpages` directive

For a discoverable landing page, drop the `click-extra-manpages` directive anywhere in the docs. It walks `click_extra_manpages` and emits a bullet list with one entry per (sub)command in each declared tree, linked to the HTML sibling produced by the hook:

````{code-block} markdown
```{click-extra-manpages}
```
````

The directive takes no arguments. URLs are computed relative to the enclosing page's actual published location, not its source docname, so the same call resolves correctly on a top-level page, on a page nested under a subdirectory, and under any HTML-family builder: `dirhtml` publishes each page one directory deeper, as `<docname>/index.html` rather than `<docname>.html`, while `singlehtml` folds every document into one page at the build root, so its links need no directory traversal at all. When `click_extra_manpages` is empty, the directive renders nothing.

A live instance of the directive ships in [the index above](#index): the list there is what this project's own `click_extra_manpages` entry produces at build time.

## Layout

Unix tools are conventionally documented with the section layout of [`man-pages(7)`](https://man7.org/linux/man-pages/man7/man-pages.7.html): a one-line `NAME`, a `SYNOPSIS`, a prose `DESCRIPTION`, an itemized `OPTIONS` list, then `ENVIRONMENT`, `FILES`, and `EXIT STATUS`. A Click Extra command already carries everything those sections need. This page documents one small CLI top-to-bottom in that order, with each section backed by output rendered live from the running command.

```{click:source}
from click_extra import Choice, argument, command, echo, option


@command(context_settings={"show_envvar": True})
@argument("city", help="Name of the city to report on.")
@option(
    "--units",
    type=Choice(["celsius", "fahrenheit"]),
    default="celsius",
    help="Temperature scale to display.",
)
def weather(city, units):
    """Report the current temperature for a city."""
    echo(f"{city}: 21 degrees {units}.")
```

### `NAME`

A man page opens with a single `name - one-line description` line, the one `apropos` and `whatis` index. Click has no dedicated slot for it: the equivalent is the program name paired with the first line of the command's docstring, which Click also uses as the command's short help. For this CLI the pairing reads:

```text
weather - report the current temperature for a city
```

### `SYNOPSIS`

The `Usage:` line is the synopsis. Click Extra styles its tokens along the same typographic split a man page draws between **bold** literal text and *italic* replaceable text, documented in [literal and replaceable slots](theme.md#literal-and-replaceable-slots): the literal command name `weather` against the replaceable `CITY` operand and the `[OPTIONS]` placeholder.

Click prints the synopsis as the first line of the help screen. The rest of that screen, dissected in the two sections below, supplies the `DESCRIPTION` and the `OPTIONS` list:

```{click:run}
from boltons.strutils import strip_ansi

result = invoke(weather, args=["--help"])
assert result.exit_code == 0
plain = strip_ansi(result.output)
# SYNOPSIS: the usage line.
assert "Usage: weather [OPTIONS] CITY" in plain
# DESCRIPTION: the docstring, plus the itemized operand.
assert "Report the current temperature for a city." in plain
assert "Positional arguments:" in plain
# OPTIONS: the itemized option, its choice metavar, and its env var.
assert "--units [celsius|fahrenheit]" in plain
assert "WEATHER_UNITS" in plain
```

### `DESCRIPTION`

The `DESCRIPTION` explains what the program does and, in prose, what its operands mean. Click Extra sources it from the command's docstring, rendered just under the synopsis above: "Report the current temperature for a city." The `CITY` operand is the city to report on.

When an argument carries a `help=` string, Click Extra also itemizes operands in a dedicated `Positional arguments:` block (the `CITY` entry above). That is a structured take on operands that goes beyond what `man-pages(7)` prescribes, which keeps their meaning in the prose description rather than in a list.

### `OPTIONS`

The `OPTIONS` section is the formal, per-item description of each option, rendered as the `Options:` block above. Every entry pairs the option's literal name (`--units`) and its replaceable metavar (`[celsius|fahrenheit]`) with the help text and a trailing bracket field carrying the option's environment variable and default. Click Extra injects its own options into the same section (`--config`, `--verbosity`, `--version`, `--help`, …), so a CLI built on it gets a complete, conventional options section without extra work.

Each option group becomes a `.SS` subsection of `OPTIONS`, which is the same split the `--help` screen draws. Click Extra's own options are grouped, so `OPTIONS` always carries the four subsections they are sorted into. A CLI adding groups of its own with `@option_group` gets them first, and the options it leaves ungrouped gather between the two under an `Other options` heading:

```{click:source}
from click_extra import command, option, option_group


@command
@option_group(
    "Location",
    option("--city", help="City to report on."),
    option("--country", help="Two-letter country code."),
)
@option("--fahrenheit", is_flag=True, help="Report in the Fahrenheit scale.")
def forecast(city, country, fahrenheit):
    """Report a multi-day forecast."""
```

```{click:run}
result = invoke(forecast, args=["--help-format", "man"])
assert result.exit_code == 0
assert '.SS "Location"' in result.output
assert '.SS "Other options"' in result.output
```

### `ENVIRONMENT`

The `ENVIRONMENT` section lists the variables that change the program's behavior. Click Extra derives one per option from the command name (the `WEATHER_` prefix here) and surfaces it in the help screen's bracket field (`[env var: WEATHER_UNITS; …]` above) when `show_envvar` is enabled. The variable is live: setting it feeds the option, ranked below the command line but above the default in the [precedence chain](config.md#precedence).

```{click:run}
result = invoke(weather, args=["Paris"], env={"WEATHER_UNITS": "fahrenheit"})
assert result.exit_code == 0
assert "fahrenheit" in result.output
assert "celsius" not in result.output
```

`--params` prints the full mapping at once: every parameter, the environment variable it reads, its default, its resolved value, and the source that value came from.

```{click:run}
from boltons.strutils import strip_ansi

result = invoke(weather, args=["--params"])
assert result.exit_code == 0
assert "WEATHER_UNITS" in strip_ansi(result.stdout)
```

### `FILES`

The `FILES` section documents the files a program reads. Click Extra's `--config` option resolves a per-platform search path, shown as its default in the `OPTIONS` block above: the [application directory](config-discovery.md#default-folder) for `weather` followed by a glob over every supported format (`*.toml`, `*.yaml`, `*.json`, `*.ini`, `*.xml`, and `pyproject.toml`). See [the configuration guide](config.md) for the search order and the precedence rules that govern which file wins.

### `EXIT STATUS`

The `EXIT STATUS` section documents the process return codes. Click Extra inherits Click's conventional scheme:

| Code | Meaning                                                                                          |
| ---- | ------------------------------------------------------------------------------------------------ |
| `0`  | Success.                                                                                         |
| `1`  | A runtime error, or an aborted prompt (`Ctrl-C`, a declined confirmation).                       |
| `2`  | A usage error: unknown option, invalid value, missing operand, or an unparsable `--config` file. |

A successful run returns `0`:

```{click:run}
result = invoke(weather, args=["Paris"])
assert result.exit_code == 0
assert result.output == "Paris: 21 degrees celsius.\n"
```

An invalid choice is a usage error, so the command exits `2`:

```{click:run}
result = invoke(weather, args=["--units", "kelvin", "Paris"])
assert result.exit_code == 2
```

## Other renderings

A man page is one of several ways the same extracted command renders. The others, and the `--help-format` option reaching all of them, are documented in [machine-readable help](machine-readable.md): JSON and Markdown for a tool or a model to read, a [Carapace spec](carapace.md) for a shell to complete from.
