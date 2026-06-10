# {octicon}`repo` Man-page

## Generating man pages

Every man-page section is produced mechanically by `click_extra.man_page` from the command itself. It works on any Click command *object* (no `console_scripts` entry point required) and walks the command tree, discovering subcommands dynamically, into one roff page per command. Literal tokens (command and option names) are set bold and replaceable tokens (metavars, operands) italic, following the [literal and replaceable slots](theme.md#literal-and-replaceable-slots) split; Click's `\b` no-rewrap marker becomes a roff `.nf` / `.fi` block.

The `@man_option` decorator adds a `--man` flag that prints a command's man page and exits:

```{click:source}
import click

from click_extra import man_option

@click.command
@man_option
@click.option("--name", help="Who to greet.")
def greet(name):
    """Greet someone."""
    click.echo(f"Hello, {name}!")
```

```{click:run}
result = invoke(greet, args=["--man"])
assert result.exit_code == 0
assert '.TH "GREET" "1"' in result.output
assert "greet \\- Greet someone." in result.output
```

The quickest way to produce a man page is the `man` subcommand: `click-extra man SCRIPT` resolves the target, loads the Click command, and prints its roff page to stdout. Trailing arguments drill into subcommands (`click-extra man flask run`). With uvx nothing needs to be installed up front:

```{code-block} shell-session
$ uvx --from click-extra --with flask click-extra man flask > flask.1
```

### Multiple pages

For multi-command CLIs, `--output-dir DIR` writes the whole command tree as one `.1` file per (sub)command into `DIR` (created if missing). The output replaces stdout, so this is the right form for a release pipeline or a distributor's build phase:

```{code-block} shell-session
$ uvx --from click-extra --with flask click-extra man --output-dir /tmp/man flask
/tmp/man/flask.1
/tmp/man/flask-run.1
/tmp/man/flask-routes.1
/tmp/man/flask-shell.1
```

`--output-dir` must appear *before* SCRIPT, since arguments after SCRIPT navigate into nested subcommands. Mixing `--output-dir` with a SUBCOMMAND argument is rejected: the flag always emits the whole tree of SCRIPT.

### Target resolution

`SCRIPT` is accepted in four forms, tried in this order. The example above uses the first; the others reach the same Click command from a different starting point:

1. A `console_scripts` entry point exposed by an installed package, the form shown above (`flask` ships one in the `flask` distribution).

2. `module:function` notation pointing straight at a Click command object. Useful when the entry point is a wrapper rather than the command itself, or when the command isn't exposed as a console script at all:

   ```{code-block} shell-session
   $ uvx --from click-extra --with flask click-extra man flask.cli:cli > flask.1
   ```

3. A `.py` file path. The file is imported in place, with no install step required, which is the right hook for source trees that don't ship a Python build system (Autotools, Meson, Bazel):

   ```{code-block} shell-session
   $ click-extra man path/to/my_cli.py > my_cli.1
   ```

4. A bare Python module name invocable via `python -m`. The resolver imports the module and picks up the Click command from its top-level attributes:

   ```{code-block} shell-session
   $ click-extra man my_package.cli > my_package.1
   ```

The same resolver is shared with [`wrap`](wrap.md#script-resolution) and `show-params`, so any of these forms works with all three subcommands.

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
result = invoke(forecast, args=["--man"])
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

`--show-params` prints the full mapping at once: every parameter, the environment variable it reads, its default, its resolved value, and the source that value came from.

```{click:run}
from boltons.strutils import strip_ansi

result = invoke(weather, args=["--show-params"])
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

## `click_extra.man_page` API

```{eval-rst}
.. automodule:: click_extra.man_page
   :members:
   :undoc-members:
   :show-inheritance:
```
