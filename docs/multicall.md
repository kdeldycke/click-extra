# {octicon}`command-palette` Multicall binaries

Some of the oldest tools on Unix are one file answering to many names: `bzip2`, `bunzip2` and `bzcat` are the same binary, `vim` and `view` differ by default options, and [BusyBox](https://busybox.net/about.html) multiplexes hundreds of applets behind symlinks pointing at a single executable. The behavior is selected by the *invocation name*: the `argv[0]` the process starts under, which a symlink or a hard link is free to change without touching the file itself.

{class}`~click_extra.multicall.MulticallGroup` brings the pattern to Click Extra: a group that, when invoked under the name of one of its subcommands, skips the group entirely and behaves exactly like that subcommand as a standalone binary. Neither [Click](https://click.palletsprojects.com) nor [Cloup](https://cloup.readthedocs.io) ships anything comparable, and on the Rust side [clap has had first-class multicall since 3.2](https://docs.rs/clap/latest/clap/_cookbook/multicall_busybox/), which this design borrows from.

## Declaring a multicall group

Use {func}`~click_extra.decorators.multicall_group` in place of {func}`~click_extra.decorators.group`; subcommands are declared the usual way:

```{click:source}
from click_extra import argument, echo, multicall_group, option

@multicall_group()
def kitchen():
    """A multicall kitchen appliance."""

@kitchen.command()
@option("--temperature", default="180")
@argument("dishes", nargs=-1)
def bake(temperature, dishes):
    """Bake dishes in the oven."""
    echo(f"Baking at {temperature} degrees: {', '.join(dishes) or 'nothing'}.")

@kitchen.command()
@option("--hours", default="2")
@argument("bottles", nargs=-1)
def chill(hours, bottles):
    """Chill bottles in the fridge."""
    echo(f"Chilling for {hours} hours: {', '.join(bottles) or 'nothing'}.")
```

Invoked under its own name, the CLI is a regular group:

```{click:run}
from boltons.strutils import strip_ansi

result = invoke(kitchen, args=["--help"])
assert result.exit_code == 0
help_screen = strip_ansi(result.stdout)
assert "bake" in help_screen
assert "chill" in help_screen
assert "personalities" in help_screen

result = invoke(kitchen, args=["bake", "--temperature", "200", "pie"])
assert result.exit_code == 0
assert "Baking at 200 degrees: pie." in result.stdout
```

Invoked under the name of one of its subcommands, it *is* that subcommand. {class}`~click_extra.testing.CliRunner` simulates the invocation name with its `prog_name` parameter, which stands in for the symlink below:

```{click:run}
from boltons.strutils import strip_ansi

result = invoke(kitchen, args=["--help"], prog_name="bake")
assert result.exit_code == 0
help_screen = strip_ansi(result.stdout)
assert help_screen.startswith("Usage: bake [OPTIONS] [DISHES]...")
assert "--temperature" in help_screen
assert "--verbosity" in help_screen
assert "chill" not in help_screen
```

The personality is not the subcommand wearing a different name: it is a standalone command carrying the group's options merged into the subcommand's. All of them parse in one flat pass, in any order, with no subcommand token in sight:

```{click:run}
result = invoke(kitchen, args=["--verbosity", "INFO", "--temperature", "200", "pie"], prog_name="bake")
assert result.exit_code == 0
assert "Baking at 200 degrees: pie." in result.stdout

result = invoke(kitchen, args=["pie", "--temperature", "200"], prog_name="bake")
assert result.exit_code == 0
assert "Baking at 200 degrees: pie." in result.stdout

result = invoke(kitchen, args=[], prog_name="chill")
assert result.exit_code == 0
assert "Chilling for 2 hours: nothing." in result.stdout
```

On a real system the name comes from `argv[0]`: create a symlink (or a hard link) next to the entry point, on your `$PATH`, bearing the subcommand's name:

```bash
ln -s "$(which kitchen)" "$(dirname "$(which kitchen)")/bake"
bake --temperature 200 pie
```

An invocation name matching no personality is not an error: it falls through to regular group behavior. That is also what keeps the feature inert under test runners and interpreters, where `argv[0]` is the runner's own binary. On Windows, entry points are `.exe` shims and the suffix is stripped before matching, so a `bake.exe` wrapper still dispatches.

## Personalities with preset options

A personality maps to a *sequence of tokens*, not just a subcommand: the first token names the subcommand, and the rest is prepended to the user's arguments. That is how `bzcat` can be `bzip2 --decompress --stdout`, or `view` a `vim` that starts read-only:

```{click:source}
from click_extra import argument, echo, multicall_group, option

@multicall_group(personalities={"quick-chill": ("chill", "--hours", "1")})
def fridge():
    """Multicall fridge with a preset personality."""

@fridge.command()
@option("--hours", default="2")
@argument("bottles", nargs=-1)
def chill(hours, bottles):
    """Chill bottles in the fridge."""
    echo(f"Chilling for {hours} hours: {', '.join(bottles) or 'nothing'}.")
```

```{click:run}
result = invoke(fridge, args=["sparkling-water"], prog_name="quick-chill")
assert result.exit_code == 0
assert "Chilling for 1 hours: sparkling-water." in result.stdout
```

An explicit `personalities` mapping is exhaustive: only the names it declares dispatch, and the identity mapping every subcommand would otherwise get is dropped. Declare them all if you want them all.

## Listing the personalities

The auto-injected `personalities` subcommand enumerates every name the binary answers to, next to the command line each one invokes:

```{click:run}
from boltons.strutils import strip_ansi

result = invoke(fridge, args=["personalities"])
assert result.exit_code == 0
listing = strip_ansi(result.stdout)
assert "quick-chill" in listing
assert "chill --hours 1" in listing
```

It renders through the usual table machinery, so `--table-format` applies. Pass `personalities_command=False` to `@multicall_group()` to suppress it, or register your own `personalities` subcommand to replace it.

## The invocation-name hook

For custom dispatch logic that does not fit the group machinery, every command exposes the name it was invoked under in `ctx.meta`, under the {data}`click_extra.context.INVOCATION_NAME` key. It equals Click's root `info_name`: the entry-point script name, the symlink name in personality mode, or an explicit `prog_name` override:

```{click:source}
from click_extra import command, context, echo, pass_context

@command
@pass_context
def appliance(ctx):
    """Adapt its behavior to the name it was invoked under."""
    invoked_as = ctx.meta[context.INVOCATION_NAME]
    if invoked_as == "toaster":
        echo("Browning bread.")
    else:
        echo(f"Running as {invoked_as}.")
```

```{click:run}
result = invoke(appliance, args=[], prog_name="toaster")
assert result.exit_code == 0
assert "Browning bread." in result.stdout

result = invoke(appliance, args=[])
assert result.exit_code == 0
assert "Running as appliance." in result.stdout
```

## Behavior notes

A personality is a genuine standalone binary, with the consequences that follow:

- **The group's callback does not run.** The personality has no parent context. A group whose callback performs setup must fold that setup into the subcommands, or stay a plain group.
- **Namespaces follow the personality name.** Configuration is read from the personality's own app dir (a `bake` invocation reads what a standalone `bake` binary would, not the group's `kitchen` directory), and the auto-generated environment variables carry the personality prefix (`BAKE_TEMPERATURE`). A `kitchen bake` invocation keeps the group's namespaces.
- **Completion is keyed on the program name.** Each personality needs its own shell-completion registration (a `_{NAME}_COMPLETE` variable, or its own [carapace](carapace.md) spec); the group's spec does not cover them.
- **Eager options answer to the personality.** `--help`, `--version`, `--params`, `--man` and their siblings render for the personality alone: `bake --version` names `bake`.
