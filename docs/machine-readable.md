# {octicon}`file-code` Machine-readable help

CLIs are increasingly read by something other than a person: a script wiring two tools together, a package manager, a language model deciding which flag to pass. All of them start from `--help`, and `--help` is the worst possible source. It is written for a human at a terminal: it wraps to a width, carries ANSI styling, and expresses structure as *layout*, so a reader has to recover the option list from column alignment and guess where a description ends.

None of that parsing is necessary. The structure was there before it was formatted, and Click Extra hands it over directly.

`click_extra.command_doc` extracts a command once, into a `CommandDoc`, and renders that model several ways. Every command gets a `--help-format FORMAT` option reaching them, and [`click-extra wrap`](#any-click-cli) does the same for a CLI whose author never heard of Click Extra.

| A program wants to know                                                   | Ask for                                                           | Documented in               |
| ------------------------------------------------------------------------- | ----------------------------------------------------------------- | --------------------------- |
| What does this command do, and what does it accept?                       | `--help-format json`, `--help-format markdown`                    | this page                   |
| What are the parameters, their types, and where did each value come from? | [`--params`](parameters.md#params-option)                         | [Parameters](parameters.md) |
| What is the resolved configuration, as a file I can edit and replay?      | [`--export-config FORMAT`](config.md#exporting-the-configuration) | [Configuration](config.md)  |
| What subcommands exist?                                                   | `--help-format json-full`, or [`--tree`](tree.md) for a person    | [Command tree](tree.md)     |
| How do I complete this in a shell?                                        | `--help-format carapace`                                          | [Carapace](carapace.md)     |

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

## The `--help-format` option

One option carrying a format, rather than a flag per format. A CLI's option list is the most expensive real estate in its help screen, and every reader pays for it whether or not they will ever export anything: a family of `--help-json`, `--help-markdown` and `--help-carapace` flags would widen the label column of every screen, forever. Here a new format costs a registry entry and nothing on screen.

### JSON

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

### Markdown

The same command, in what a language model reads most comfortably:

```{click:run}
result = invoke(weather, args=["--help-format", "markdown"])
assert result.exit_code == 0
assert result.output.startswith("# weather\n")
assert "## Synopsis" in result.output
assert "- `CITY`: Name of the city to report on." in result.output
```

### The format list

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

## Installing the artifacts

Two of these renderings are *installed* rather than read: a man page under a `man` directory, a Carapace spec under Carapace's. For those, the wrapper takes a destination instead of printing to stdout:

```{code-block} shell-session
$ click-extra wrap --help-format man --install -- flask
/home/me/.local/share/man/man1/flask.1
/home/me/.local/share/man/man1/flask-run.1
$ click-extra wrap --help-format carapace --install -- flask
/home/me/.config/carapace/specs/flask.yaml
```

`--install` means the same thing for both: put this where its consumer looks for it, honoring `XDG_DATA_HOME` and `XDG_CONFIG_HOME`. `--output-dir DIR` writes it somewhere else instead. Both are refused for the other formats, which are documents nothing goes looking for: a shell redirection is the whole story there.

## Any Click CLI

A CLI that has never heard of Click Extra gets the same treatment through the [wrapper](wrap.md): it is loaded and walked from the outside, so an agent is not limited to the tools whose authors thought about it.

```{code-block} shell-session
$ click-extra wrap --help-format json -- flask run
$ click-extra wrap --help-format markdown -- flask
```

```{click:source}
:hide-source:
from click_extra.cli import demo
```

The parameter inventory comes out the same way, in any [structured format](table.md#table-formats), values keeping their native types:

```{click:run}
result = invoke(demo, args=["wrap", "--params", "--table-format", "json", "--", "flask", "run"])
assert result.exit_code == 0
assert '"run.port"' in result.output
assert '"Default": 5000' in result.output
```

Pair it with `--columns` to hand a consumer only the fields it reads:

```{click:run}
:screenshot: wrap-flask-json-screen
:screenshot-columns: auto
result = invoke(demo, args=["wrap", "--params", "--table-format", "json", "--columns", "id,spec,envvars,default", "--", "flask", "routes"])
assert result.exit_code == 0
assert '"routes.sort"' in result.output
assert '"FLASK_ROUTES_SORT"' in result.output
```

Where `--params` describes the parameters, `--help-format` describes the command itself: its usage line, description, option groups, subcommands and examples. The target cooperates with neither, and needs to know nothing about Click Extra:

```{click:run}
import json

result = invoke(demo, args=["wrap", "--help-format", "json", "--", "flask", "run"])
assert result.exit_code == 0

doc = json.loads(result.output)
assert doc["name"] == "flask run"
assert "development server" in doc["description"]
options = [opt for group in doc["option_groups"] for opt in group["options"]]
assert any("--port" in opt["names"] for opt in options)
```

## Feeding a CLI to an agent

Three things are worth knowing before wiring any of this into a tool or a model.

**Hand a model Markdown, not JSON.** Both carry the same content, and JSON is the right answer for code that indexes fields. But a model reads prose better than it reads a nested object, and pays fewer tokens for it: no quoting, no punctuation scaffolding, and headings it already knows how to skim.

**Descend, do not dump.** The plain formats name a command's children without expanding them, so an agent answering a question about one leaf spends its context on that leaf rather than on a tree it will not read. Reach for `-full` when the whole surface is the point (generating documentation, diffing two releases), not by default. On a large CLI the difference is the whole budget.

**Two lookalikes that answer different questions.** `--help-format json` describes the *interface*: what the command is, what it accepts, what it documents. [`--params`](parameters.md#params-option) describes the *state* of one invocation: every parameter's resolved value and where it came from, be that a flag, an environment variable, a configuration file or a default. An agent picking flags wants the first. An agent debugging why a run behaved a certain way wants the second.

Neither requires the target to cooperate: [`click-extra wrap`](#any-click-cli) extracts both from a CLI that knows nothing about Click Extra.

## `click_extra.command_doc` API

```{eval-rst}
.. autoclasstree:: click_extra.command_doc
   :strict:

.. automodule:: click_extra.command_doc
   :no-index:
   :members:
   :undoc-members:
   :show-inheritance:
```
