# {octicon}`repo` Man-page

`click_extra.man_page` extracts a command once, into a `CommandDoc`, and renders that same model several ways. A man page is one of them; [Markdown, JSON and a Carapace spec](#machine-readable-formats) are the others, for readers that are programs rather than people.

## Generating man pages

Every man-page section is produced mechanically by `click_extra.man_page` from the command itself. It works on any Click command *object* (no `console_scripts` entry point required) and walks the command tree, discovering subcommands dynamically, into one roff page per command. Literal tokens (command and option names) are set bold and replaceable tokens (metavars, operands) italic, following the [literal and replaceable slots](theme.md#literal-and-replaceable-slots) split; Click's `\b` no-rewrap marker becomes a roff `.nf` / `.fi` block.

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

The quickest way to produce a man page is `wrap --man`: `click-extra wrap --man -- SCRIPT` resolves the target, loads the Click command, and prints its roff page to stdout without running it. Trailing arguments drill into subcommands (`click-extra wrap --man -- flask run`). With uvx nothing needs to be installed up front:

```{code-block} shell-session
$ uvx --from click-extra --with flask click-extra wrap --man -- flask > flask.1
```

### Multiple pages

For multi-command CLIs, `--output-dir DIR` writes the whole command tree as one `.1` file per (sub)command into `DIR` (created if missing). The output replaces stdout, so this is the right form for a release pipeline or a distributor's build phase:

```{code-block} shell-session
$ uvx --from click-extra --with flask click-extra wrap --man --output-dir /tmp/man -- flask
/tmp/man/flask.1
/tmp/man/flask-run.1
/tmp/man/flask-routes.1
/tmp/man/flask-shell.1
```

`--output-dir` (and `--man`) must appear *before* SCRIPT, since arguments after SCRIPT navigate into nested subcommands. Mixing `--output-dir` with a SUBCOMMAND argument is rejected: the flag always emits the whole tree of SCRIPT.

### Target resolution

`SCRIPT` is accepted in five forms, tried in this order. The example above uses the first; the others reach the same Click command from a different starting point:

1. A `console_scripts` entry point exposed by an installed package, the form shown above (`flask` ships one in the `flask` distribution).

2. A local project directory, resolved from its `pyproject.toml` (`[project.scripts]`) or `setup.cfg` (`console_scripts`) entry point. Its package is added to `sys.path`, though its dependencies are not installed (see [Dependencies of the wrapped CLI](wrap.md#dependencies-of-the-wrapped-cli)):

   ```{code-block} shell-session
   $ click-extra wrap --man -- ../my-project > my-project.1
   ```

3. `module:function` notation pointing straight at a Click command object. Useful when the entry point is a wrapper rather than the command itself, or when the command isn't exposed as a console script at all:

   ```{code-block} shell-session
   $ uvx --from click-extra --with flask click-extra wrap --man -- flask.cli:cli > flask.1
   ```

4. A `.py` file path. The file is imported in place, with no install step required, which is the right hook for source trees that don't ship a Python build system (Autotools, Meson, Bazel):

   ```{code-block} shell-session
   $ click-extra wrap --man -- path/to/my_cli.py > my_cli.1
   ```

5. A bare Python module name invocable via `python -m`. The resolver imports the module and picks up the Click command from its top-level attributes:

   ```{code-block} shell-session
   $ click-extra wrap --man -- my_package.cli > my_package.1
   ```

`wrap` resolves SCRIPT the [same way](wrap.md#script-resolution) in every mode, so any of these forms works whether you run, introspect (`--params`), or document (`--man`) the target.

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

Projects already using the `click_extra.sphinx` extension can publish the same pages alongside their HTML docs with a single `click_extra_manpages` entry in `conf.py`: see [Man pages](sphinx.md#man-pages). The Sphinx hook reuses `write_manpages` under the hood and optionally renders a browser-viewable HTML sibling next to each `.1` so the standard [`:manpage:`](https://www.sphinx-doc.org/en/master/usage/restructuredtext/roles.html#role-manpage) role can link to them.

### Index

The list below is auto-generated by the [`click-extra-manpages` directive](sphinx.md#click-extra-manpages-directive): one link per (sub)command declared in this project's `click_extra_manpages` config, pointing at the HTML sibling rendered alongside the docs.

````{code-block} markdown
:caption: Directive call
```{click-extra-manpages}
```
````

```{click-extra-manpages}
```

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

The `OPTIONS` section is the formal, per-item description of each option, rendered as the `Options:` block above. Every entry pairs the option's literal name (`--units`) and its replaceable metavar (`[celsius|fahrenheit]`) with the help text and a trailing bracket field carrying the option's environment variable and default. Click Extra injects its own options into the same list (`--config`, `--verbosity`, `--version`, `--help`, …), so a CLI built on it gets a complete, conventional options section without extra work.

When a CLI sorts its options into groups with `@option_group`, each group becomes a `.SS` subsection of `OPTIONS`; the options left ungrouped, including the ones Click Extra injects, gather under a trailing `Other options` heading. This is the same split the `--help` screen draws:

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

The `FILES` section documents the files a program reads. Click Extra's `--config` option resolves a per-platform search path, shown as its default in the `OPTIONS` block above: the [application directory](config.md#default-folder) for `weather` followed by a glob over every supported format (`*.toml`, `*.yaml`, `*.json`, `*.ini`, `*.xml`, and `pyproject.toml`). See [the configuration guide](config.md) for the search order and the precedence rules that govern which file wins.

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

## Machine-readable formats

A `--help` screen is written for a person: it wraps to the terminal, carries ANSI styling, and flattens the structure the command actually has. A tool reading that screen has to parse a layout; the structure was there all along, one extraction away.

Every command gets a `--help-format` option, which renders it through one of the backends of the same `CommandDoc` the man page comes from:

```{click:run}
import json

result = invoke(weather, args=["--help-format", "json"])
assert result.exit_code == 0

doc = json.loads(result.output)
assert doc["name"] == "weather"
assert doc["arguments"] == [
    {"metavar": "CITY", "help": "Name of the city to report on."}
]
options = [opt for group in doc["option_groups"] for opt in group["options"]]
units = next(opt for opt in options if "--units" in opt["names"])
assert units["metavar"] == "[celsius|fahrenheit]"
assert units["help"] == "Temperature scale to display."
```

The same command as Markdown, which is what a language model reads most comfortably:

```{click:run}
result = invoke(weather, args=["--help-format", "markdown"])
assert result.exit_code == 0
assert result.output.startswith("# weather\n")
assert "## Synopsis" in result.output
assert "- `CITY`: Name of the city to report on." in result.output
```

The available formats:

| Format          | What it renders                                                                             |
| --------------- | ------------------------------------------------------------------------------------------- |
| `carapace`      | A [Carapace completion spec](carapace.md) (YAML), which doubles as a command-and-flag tree. |
| `json`          | This command as a JSON object, its direct subcommands listed by name.                       |
| `json-full`     | Every command of the tree, under a `commands` array.                                        |
| `man`           | This command as a man page: the roff source [`--man`](#reading-a-manual) typesets to read.  |
| `markdown`      | This command as a Markdown document, one section per topic.                                 |
| `markdown-full` | Every command of the tree as one Markdown document.                                         |

```{note}
The plain and `-full` variants differ in how much they hand over at once. A plain render describes one command and *names* its children, so a reader descends one level at a time rather than pulling a whole tree into a context window to answer a question about one leaf. The `-full` variants are for the opposite job: generating documentation, or diffing a CLI's whole surface between two releases.
```

Whatever `--color` says, these renderings carry no ANSI codes: they are meant to be piped into a parser, which has no use for escape sequences. `--help` remains the colorized human view.

### Installing the artifacts

Two of these renderings are *installed* rather than read: a man page under a `man` directory, a Carapace spec under Carapace's. For those, the wrapper takes a destination instead of printing to stdout:

```{code-block} shell-session
$ click-extra wrap --help-format man --install -- flask
/home/me/.local/share/man/man1/flask.1
/home/me/.local/share/man/man1/flask-run.1
$ click-extra wrap --help-format carapace --install -- flask
/home/me/.config/carapace/specs/flask.yaml
```

`--install` means the same thing for both: put this where its consumer looks for it, honoring `XDG_DATA_HOME` and `XDG_CONFIG_HOME`. `--output-dir DIR` writes it somewhere else instead. Both are refused for the other formats, which are documents nothing goes looking for: a shell redirection is the whole story there.

### Any Click CLI

The wrapper applies the same treatment to a CLI that has never heard of Click Extra. It is loaded and walked from the outside, so no cooperation from its author is required:

```{code-block} shell-session
$ click-extra wrap --help-format json -- flask run
$ click-extra wrap --help-format markdown -- flask
```

For parameter-level detail (types, defaults, provenance, environment variables), [`--params`](parameters.md#params-option) covers ground `--help-format` does not, and speaks the same [structured formats](table.md#table-formats).

## Examples

A command can carry usage examples, as `(description, command)` pairs. They render in an `Examples:` section of the help screen, in the man page's `EXAMPLES` section, and in every format above:

```{click:source}
from click_extra import command, echo, option


@command(
    examples=[
        ("Report the temperature in Fahrenheit", "forecast --units fahrenheit Oslo"),
        ("Report tomorrow's forecast", "forecast --day tomorrow Oslo"),
    ]
)
@option("--units", default="celsius", help="Temperature scale to display.")
def forecast(units):
    """Report the forecast for a city."""
    echo(f"Sunny, in {units}.")
```

```{click:run}
from boltons.strutils import strip_ansi

result = invoke(forecast, args=["--help"])
assert result.exit_code == 0
plain = strip_ansi(result.output)
assert "Examples:" in plain
assert "$ forecast --units fahrenheit Oslo" in plain
```

The command lines are emitted verbatim rather than wrapped: an example exists to be copied. Option names, subcommands and CLI names inside them are highlighted by the same pass that highlights them everywhere else on the screen, which is why the assertion above strips the styling before matching.

They reach the machine-readable renderings as structured entries, not as prose to be parsed back out:

```{click:run}
import json

result = invoke(forecast, args=["--help-format", "json"])
assert result.exit_code == 0
assert json.loads(result.output)["examples"][0] == {
    "description": "Report the temperature in Fahrenheit",
    "command": "forecast --units fahrenheit Oslo",
}
```

A malformed pair raises `TypeError` at command construction, so a typo surfaces on import rather than on the first `--help` a user runs.

## `click_extra.man_page` API

```{eval-rst}
.. autoclasstree:: click_extra.man_page
   :strict:

.. automodule:: click_extra.man_page
   :members:
   :undoc-members:
   :show-inheritance:
```
