# {octicon}`versions` Version

Click Extra provides its own version option which, compared to [Click's built-in](https://click.palletsprojects.com/en/stable/api/?highlight=version#click.version_option):

- adds [new variable](#variables) to compose your version string
- adds [colors](#colors)
- adds complete [environment information in JSON](#environment-information)
- works with [standalone scripts](#standalone-script)
- use [format string syntax](https://docs.python.org/3/library/string.html#format-string-syntax)
- prints [details metadata in `DEBUG` logs](#debug-logs)
- expose [metadata in the context](#get-metadata-values)

## Defaults

Here is how the defaults looks like:

```{click:source}
:emphasize-lines: 5
import click
import click_extra

@click.command
@click_extra.version_option(version="1.2.3")
def cli():
    pass
```

```{click:run}
:emphasize-lines: 5
result = invoke(cli, args=["--help"])
assert "--version" in result.output
```

The default version message is the same as Click's default, but colored:

```{click:run}
result = invoke(cli, args=["--version"])
assert result.output == "\x1b[97mcli\x1b[0m, version \x1b[32m1.2.3\x1b[0m\n"
```

```{hint}
In the examples of this page the version is hard-coded to `1.2.3` for the sake of demonstration.

In most cases, you do not need to force it, as the version will be automatically [fetched from the package metadata](#variables) of the CLI or the [`__version__` attribute](#standalone-script) of the command.
```

## Variables

The message template is a [format string](https://docs.python.org/3/library/string.html#format-string-syntax), which {py:attr}`defaults to <click_extra.version.ExtraVersionOption.message>`:

```{code-block} python
f"{prog_name}, version {version}"
```

```{caution}
This is different from Click, which uses [the `%(prog)s, version %(version)s` template](https://github.com/pallets/click/blob/b498906/src/click/decorators.py#L455).

Click is based on [old-school `printf`-style formatting](https://docs.python.org/3/library/stdtypes.html#printf-style-string-formatting), which relies on variables of the `%(variable)s` form.

Click Extra uses [modern format string syntax](https://docs.python.org/3/library/string.html#format-string-syntax), with variables of the `{variable}` form, to provide a more flexible and powerful templating.
```

You can customize the message template with the following variables:

| Variable                                                                              | Description                                                                                                                                                                            |
| ------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| {py:attr}`{module} <click_extra.version.ExtraVersionOption.module>`                   | The [module object](https://docs.python.org/3/glossary.html#term-module) in which the command is implemented.                                                                          |
| {py:attr}`{module_name} <click_extra.version.ExtraVersionOption.module_name>`         | The [`__name__` of the module](https://docs.python.org/3/reference/datamodel.html#module.__name__) in which the command is implemented.                                                |
| {py:attr}`{module_file} <click_extra.version.ExtraVersionOption.module_file>`         | The [full path of the file](https://docs.python.org/3/reference/datamodel.html#module.__file__) in which the command is implemented.                                                   |
| {py:attr}`{module_version} <click_extra.version.ExtraVersionOption.module_version>`   | The string found in the local `__version__` variable of the module.                                                                                                                    |
| {py:attr}`{package_name} <click_extra.version.ExtraVersionOption.package_name>`       | The [name of the package](https://docs.python.org/3/reference/datamodel.html#module.__package__) in which the CLI is distributed.                                                      |
| {py:attr}`{package_version} <click_extra.version.ExtraVersionOption.package_version>` | The [version from the package metadata](https://docs.python.org/3/library/importlib.metadata.html?highlight=metadata%20version#distribution-versions) in which the CLI is distributed. |
| {py:attr}`{exec_name} <click_extra.version.ExtraVersionOption.exec_name>`             | User-friendly name of the executed CLI. Returns `{module_name}`, `{package_name}` or script's filename, in this order.                                                                 |
| {py:attr}`{version} <click_extra.version.ExtraVersionOption.version>`                 | Version of the CLI. Returns `{module_version}`, `{package_version}` or `None`, in this order. For [`.dev` versions](#development-versions), automatically appends the Git commit hash. |
| {py:attr}`{git_repo_path} <click_extra.version.ExtraVersionOption.git_repo_path>`     | The full path to the Git repository root directory, or `None` if not in a Git repository.                                                                                              |
| {py:attr}`{git_branch} <click_extra.version.ExtraVersionOption.git_branch>`           | The current Git branch name, or `None` if not in a Git repository or Git is not available.                                                                                             |
| {py:attr}`{git_long_hash} <click_extra.version.ExtraVersionOption.git_long_hash>`     | The full Git commit hash of the current `HEAD`, or `None` if not in a Git repository or Git is not available.                                                                          |
| {py:attr}`{git_short_hash} <click_extra.version.ExtraVersionOption.git_short_hash>`   | The short Git commit hash of the current `HEAD`, or `None` if not in a Git repository or Git is not available.                                                                         |
| {py:attr}`{git_date} <click_extra.version.ExtraVersionOption.git_date>`               | The commit date of the current `HEAD` in ISO format (`YYYY-MM-DD HH:MM:SS +ZZZZ`), or `None` if not in a Git repository or Git is not available.                                       |
| {py:attr}`{git_tag} <click_extra.version.ExtraVersionOption.git_tag>`                 | The Git tag pointing at `HEAD`, or `None` if `HEAD` is not at a tagged commit.                                                                                                         |
| {py:attr}`{git_tag_sha} <click_extra.version.ExtraVersionOption.git_tag_sha>`         | The full commit SHA that the current tag points at, or `None` if `HEAD` is not at a tagged commit.                                                                                     |
| {py:attr}`{prog_name} <click_extra.version.ExtraVersionOption.prog_name>`             | The display name of the program. Defaults to Click's `info_name`, but can be [overridden via `prog_name` on the command decorator](commands.md#version-fields).                        |
| {py:attr}`{env_info} <click_extra.version.ExtraVersionOption.env_info>`               | The [environment information](https://boltons.readthedocs.io/en/latest/ecoutils.html#boltons.ecoutils.get_profile) in JSON.                                                            |

```{note}
The ``git_*`` variables are evaluated at runtime by calling ``git``. They return ``None`` in environments where Git is not available (e.g., standalone Nuitka binaries, Docker containers without Git).

All ``git_*`` fields can be [pre-baked at build time](#pre-baking-git-metadata) by defining ``__<field>__`` dunder variables in the CLI module. Pre-baked values take priority over subprocess calls.
```

```{hint}
The `{version}` variable is resolved in this order:

1. A `__version__` variable defined alongside your CLI (see [standalone scripts](#standalone-script)).
2. A `__version__` variable in the parent package's `__init__.py` (for `__main__` entry points, e.g. Nuitka-compiled binaries).
3. The version from package metadata via [`importlib.metadata`](https://docs.python.org/3/library/importlib.metadata.html#distribution-versions) — this is the most common source for installed packages.
4. `None` if none of the above succeeds (e.g. unpackaged scripts without `__version__`).
```

```{error}
Some Click's built-in variables are not recognized:
- `%(package)s` should be replaced by `{package_name}`
- `%(prog)s` should be replaced by `{prog_name}`
- All other `%(variable)s` should be replaced by their `{variable}` counterpart
```

You can compose your own version string by passing the `message` argument:

```{click:source}
:emphasize-lines: 6
import click
import click_extra

@click.command
@click_extra.version_option(
    message="✨ {prog_name} v{version} - {package_name}",
    version="1.2.3",
)
def my_own_cli():
    pass
```

```{click:run}
result = invoke(my_own_cli, args=["--version"])
assert result.output == (
    "✨ \x1b[97mmy-own-cli\x1b[0m v\x1b[32m1.2.3\x1b[0m - \x1b[97mclick_extra.sphinx\x1b[0m\n"
)
```

```{caution}
This results reports the package name as `click_extra.sphinx` because we are running the example from the `click-extra` documentation build environment. This is just a quirk of the documentation setup and will not affect your own CLI.
```

## Overriding variables from the command

The [`version_fields` parameter on `@command` and `@group`](commands.md#version-fields) lets you override any template field without touching the default params list.

Fields can also be forced directly on the `ExtraVersionOption` instance via the [`params=` argument](commands.md#change-default-options):

```{click:source}
:emphasize-lines: 4-9
import click
from click_extra import ExtraVersionOption

@click.command(params=[
    ExtraVersionOption(
        prog_name="Acme CLI",
        version="42.0",
        message="{prog_name} {version} (branch: {git_branch})",
        git_branch="release/42",
    ),
])
def acme():
    pass
```

```{click:run}
result = invoke(acme, args=["--version"])
assert result.exit_code == 0
assert "Acme CLI" in result.output
assert "42.0" in result.output
assert "release/42" in result.output
```

## Standalone script

The `--version` option works with standalone scripts.

Let's put this code in a file named `greet.py`:

```{click:source}
:caption: `greet.py`
:linenos:
#!/usr/bin/env -S uv run --script
# /// script
# dependencies = ["click-extra"]
# ///

import click_extra


@click_extra.command
def greet():
    print("Hello world")


if __name__ == "__main__":
    greet()
```

Here is the result of the `--version` option:

```{click:run}
result = invoke(greet, args=["--version"])
assert result.output == "\x1b[97mgreet\x1b[0m, version \x1b[32mNone\x1b[0m\n"
```

Because the script is not packaged, the `{version}` variable is `None`.

But Click Extra recognize the `__version__` variable, to force it in your script:

```{click:source}
:caption: `greet.py`
:emphasize-lines: 9
:linenos:
#!/usr/bin/env -S uv run --script
# /// script
# dependencies = ["click-extra"]
# ///

import click_extra


__version__ = "0.9.3-alpha"


@click_extra.command
def greet():
    print("Hello world")


if __name__ == "__main__":
    greet()
```

```{click:run}
result = invoke(greet, args=["--version"])
assert result.output == "\x1b[97mgreet\x1b[0m, version \x1b[32m0.9.3-alpha\x1b[0m\n"
```

```{caution}
The `__version__` variable is [not an enforced Python standard](https://peps.python.org/pep-0396/#specification) and [more like a tradition](https://peps.python.org/pep-0008/#module-level-dunder-names).

It is supported by Click Extra as a convenience for script developers.
```

## Development versions

When the version string contains `.dev` (as in [PEP 440 development releases](https://peps.python.org/pep-0440/#developmental-releases)), Click Extra automatically appends the Git short commit hash as a [PEP 440 local version identifier](https://peps.python.org/pep-0440/#local-version-identifiers).

This lets you identify exactly which commit a development build was produced from:

```{click:source}
:emphasize-lines: 5
import click
import click_extra

__version__ = "1.2.3.dev0"

@click.command
@click_extra.version_option()
def dev_cli():
    pass
```

```{click:run}
import re
result = invoke(dev_cli, args=["--version"])
assert re.fullmatch(
    r"\x1b\[97mdev-cli\x1b\[0m, version \x1b\[32m1\.2\.3\.dev0(\+[a-f0-9]{4,40})?\x1b\[0m\n",
    result.output,
)
```

For example, a version like `1.2.3.dev0` becomes `1.2.3.dev0+6e59c8c1` during development. Release versions (without `.dev`) are never modified.

If Git is not available or the CLI is not running from a Git repository, the plain `.dev` version is returned as-is.

### Pre-baked versions

If the version string already contains a `+` (a [PEP 440 local version identifier](https://peps.python.org/pep-0440/#local-version-identifiers)), Click Extra assumes the hash was pre-baked at build time and returns the version as-is, without appending a second hash.

This is useful for CI pipelines or [Nuitka](https://nuitka.net) binaries where `git` is not available at runtime but the build step can inject the commit hash into `__version__` before compilation:

```{click:source}
:emphasize-lines: 5
import click
import click_extra

__version__ = "1.2.3.dev0+abc1234"

@click.command
@click_extra.version_option()
def prebaked_cli():
    pass
```

```{click:run}
result = invoke(prebaked_cli, args=["--version"])
assert result.output == "\x1b[97mprebaked-cli\x1b[0m, version \x1b[32m1.2.3.dev0+abc1234\x1b[0m\n"
```

```{hint}
Click Extra ships {func}`prebake_version() <click_extra.version.prebake_version>`, a utility to automate this injection. It parses a Python source file with {mod}`ast`, locates the `__version__` assignment, and appends a `+<local_version>` suffix in place. Call it in your build step before Nuitka/PyInstaller compilation.
```

### Version lifecycle

The version resolution adapts to the runtime environment:

| Scenario                          | `__version__` in source | Git available? | `{version}` output   |
| --------------------------------- | ----------------------- | -------------- | -------------------- |
| **Local dev** (from source)       | `1.0.0.dev0`            | Yes            | `1.0.0.dev0+abc1234` |
| **Nuitka binary** (pre-baked)     | `1.0.0.dev0+abc1234`    | No             | `1.0.0.dev0+abc1234` |
| **Nuitka binary** (not pre-baked) | `1.0.0.dev0`            | No             | `1.0.0.dev0`         |
| **Release**                       | `1.0.0`                 | —              | `1.0.0`              |

For Nuitka binaries, the recommended workflow is to inject the commit hash into `__version__` **before** compilation. [Repomatic](https://github.com/kdeldycke/repomatic) automates this via its `prebake-version` command.

### Pre-baking git metadata

All `git_*` template fields support pre-baking. If the CLI module defines a `__<field>__` dunder variable with a non-empty string value, that value is used instead of calling `git` at runtime. This is the recommended approach for compiled binaries (Nuitka, PyInstaller) where `git` is unavailable.

The supported dunders are:

| Dunder variable      | Template field     | Subprocess fallback                               |
| -------------------- | ------------------ | ------------------------------------------------- |
| `__git_branch__`     | `{git_branch}`     | `git rev-parse --abbrev-ref HEAD`                 |
| `__git_long_hash__`  | `{git_long_hash}`  | `git rev-parse HEAD`                              |
| `__git_short_hash__` | `{git_short_hash}` | `git rev-parse --short HEAD`                      |
| `__git_date__`       | `{git_date}`       | `git show -s --format=%ci HEAD`                   |
| `__git_tag__`        | `{git_tag}`        | `git describe --tags --exact-match HEAD`          |
| `__git_tag_sha__`    | `{git_tag_sha}`    | `git rev-list -1 <tag>` (if `{git_tag}` resolves) |

To pre-bake a value, declare the dunder with an empty string placeholder in your `__init__.py`:

```{code-block} python
:caption: `mypackage/__init__.py`

__version__ = "1.0.0.dev0"
__git_branch__ = ""
__git_short_hash__ = ""
```

Then inject values at build time using {func}`prebake_dunder() <click_extra.version.prebake_dunder>`:

```{code-block} python
from pathlib import Path
from click_extra.version import prebake_dunder

prebake_dunder(Path("mypackage/__init__.py"), "__git_branch__", "main")
prebake_dunder(Path("mypackage/__init__.py"), "__git_short_hash__", "abc1234")
```

{func}`prebake_dunder() <click_extra.version.prebake_dunder>` only replaces empty strings, so running it twice is safe (idempotent). It preserves the quoting style and surrounding file content.

{func}`discover_package_init_files() <click_extra.version.discover_package_init_files>` can auto-discover `__init__.py` paths from `[project.scripts]` in `pyproject.toml`, so you don't need to hardcode paths in your build scripts.

### CLI usage

The `click-extra prebake` command exposes these utilities from the command line, without writing Python:

```{code-block} shell-session
$ # Bake __version__ and all git fields in one pass
$ click-extra prebake all

$ # Only inject Git hash into __version__
$ click-extra prebake version
$ click-extra prebake version --hash abc1234

$ # Set a specific field (double underscores added automatically)
$ click-extra prebake field git_tag_sha abc123def456...
$ click-extra prebake field git_branch main --module mypackage/__init__.py
```

All subcommands auto-discover target files from `[project.scripts]` in `pyproject.toml`. Use `--module` to target a specific file instead.

## Colors

Each variable listed in the section above can be rendered in its own style. They all have dedicated parameters you can pass to the `version_option` decorator:

| Parameter               | Description                             | Default Style                                |
| ----------------------- | --------------------------------------- | -------------------------------------------- |
| `message_style`         | Style of the whole message.             | `None`{l=python}                             |
| `module_style`          | Style for `{module}` variable.          | `None`{l=python}                             |
| `module_name_style`     | Style for `{module_name}` variable.     | `default_theme.invoked_command`{l=python}    |
| `module_file_style`     | Style for `{module_file}` variable.     | `None`{l=python}                             |
| `module_version_style`  | Style for `{module_version}` variable.  | `Style(fg="green")`{l=python}                |
| `package_name_style`    | Style for `{package_name}` variable.    | `default_theme.invoked_command`{l=python}    |
| `package_version_style` | Style for `{package_version}` variable. | `Style(fg="green")`{l=python}                |
| `exec_name_style`       | Style for `{exec_name}` variable.       | `default_theme.invoked_command`{l=python}    |
| `version_style`         | Style for `{version}` variable.         | `Style(fg="green")`{l=python}                |
| `git_repo_path_style`   | Style for `{git_repo_path}` variable.   | `Style(fg="bright_black")`{l=python}         |
| `git_branch_style`      | Style for `{git_branch}` variable.      | `Style(fg="cyan")`{l=python}                 |
| `git_long_hash_style`   | Style for `{git_long_hash}` variable.   | `Style(fg="yellow")`{l=python}               |
| `git_short_hash_style`  | Style for `{git_short_hash}` variable.  | `Style(fg="yellow")`{l=python}               |
| `git_date_style`        | Style for `{git_date}` variable.        | `Style(fg="bright_black")`{l=python}         |
| `git_tag_style`         | Style for `{git_tag}` variable.         | `Style(fg="cyan")`{l=python}                 |
| `git_tag_sha_style`     | Style for `{git_tag_sha}` variable.     | `Style(fg="yellow")`{l=python}               |
| `prog_name_style`       | Style for `{prog_name}` variable.       | `default_theme.invoked_command`{l=python}    |
| `env_info_style`        | Style for `{env_info}` variable.        | `Style(fg="bright_black")`{l=python}         |

Here is an example:

```{click:source}
:emphasize-lines: 7-10
import click
from click_extra import version_option, Style

@click.command
@version_option(
    message="{prog_name} v{version} 🔥 {package_name} ( ͡❛ ͜ʖ ͡❛)",
    message_style=Style(fg="cyan"),
    prog_name_style=Style(fg="green", bold=True),
    version_style=Style(fg="bright_yellow", bg="red"),
    package_name_style=Style(fg="bright_blue", italic=True),
    version="1.2.3",
)
def cli():
    pass
```

```{click:run}
result = invoke(cli, args=["--version"])
assert result.output == (
    "\x1b[32m\x1b[1mcli\x1b[0m\x1b[36m "
    "v\x1b[0m\x1b[93m\x1b[41m1.2.3\x1b[0m\x1b[36m 🔥 "
    "\x1b[0m\x1b[94m\x1b[3mclick_extra.sphinx\x1b[0m\x1b[36m ( ͡❛\u202f͜ʖ ͡❛)\x1b[0m\n"
)
```

```{hint}
The [`Style()` helper is defined by Cloup](https://cloup.readthedocs.io/en/stable/autoapi/cloup/styling/index.html#cloup.styling.Style).
```

You can pass `None` to any of the style parameters to disable styling for the corresponding variable:

```{click:source}
:emphasize-lines: 6-8
import click
from click_extra import version_option

@click.command
@version_option(
    message_style=None,
    version_style=None,
    prog_name_style=None,
    version="1.2.3",
)
def cli():
    pass
```

```{click:run}
result = invoke(cli, args=["--version"])
assert result.output == f"cli, version 1.2.3\n"
```

## Environment information

The `{env_info}` variable compiles all sorts of environment information.

Here is how it looks like:

```{click:source}
:emphasize-lines: 5
import click
from click_extra import version_option

@click.command
@version_option(message="{env_info}")
def env_info_cli():
    pass
```

```{click:run}
import re
result = invoke(env_info_cli, args=["--version"])
assert re.fullmatch(r"\x1b\[90m{'.+'}\x1b\[0m\n", result.output)
```

It's verbose but it's helpful for debugging and reporting of issues from end users.

```{important}
The JSON output is scrubbed out of identifiable information by default: current working directory, hostname, Python executable path, command-line arguments and username are replaced with `-`.
```

Another trick consist in picking into the content of `{env_info}` to produce highly customized version strings. This can be done because `{env_info}` is kept as a `dict`:

```{click:source}
:emphasize-lines: 6
import click
from click_extra import version_option

@click.command
@version_option(
    message="{prog_name} {version}, from {module_file} (Python {env_info[python][version]})",
    version="1.2.3",
)
def custom_env_info():
    pass
```

```{click:run}
import re
result = invoke(custom_env_info, args=["--version"])
assert re.fullmatch((
    r"\x1b\[97mcustom-env-info\x1b\[0m \x1b\[32m1.2.3\x1b\[0m, "
    r"from .+ \(Python \x1b\[90m3\.\d+\.\d+ .+\x1b\[0m\)\n"
), result.output)
```

## Debug logs

When the `DEBUG` level is enabled, all available variables will be printed in the log:

```{click:source}
:emphasize-lines: 5-6
import click
from click_extra import version_option, verbosity_option, echo

@click.command
@version_option(version="1.2.3")
@verbosity_option
def version_in_logs():
    echo("Standard operation")
```

Which is great to see how each variable is populated and styled:

```{click:run}
import re
result = invoke(version_in_logs, ["--verbosity", "DEBUG"])
assert "\n\x1b[34mdebug\x1b[0m: Version string template variables:\n" in result.output
```

## Get metadata values

You can get the uncolored, Python values used in the composition of the version message from the context:

```{click:source}
:emphasize-lines: 8-11
import click
from click_extra import echo, pass_context, version_option

@click.command
@version_option(version="1.2.3")
@pass_context
def version_metadata(ctx):
    version = ctx.meta["click_extra.version"]
    package_name = ctx.meta["click_extra.package_name"]
    prog_name = ctx.meta["click_extra.prog_name"]
    env_info = ctx.meta["click_extra.env_info"]

    echo(f"version = {version}")
    echo(f"package_name = {package_name}")
    echo(f"prog_name = {prog_name}")
    echo(f"env_info = {env_info}")
```

```{click:run}
invoke(version_metadata, ["--version"])
```

```{click:run}
import re
result = invoke(version_metadata)
assert re.fullmatch((
    r"version = 1.2.3\n"
    r"package_name = click_extra.sphinx\n"
    r"prog_name = version-metadata\n"
    r"env_info = {'.+'}\n"
), result.output)
```

```{hint}
These variables are presented in their original Python type. If most of these variables are strings, others like `env_info` retains their original `dict` type.
```

```{note}
Metadata values in `ctx.meta` are **lazily evaluated**: a field like `env_info` or `git_long_hash` is only computed the first time you access it. If your command only reads `ctx.meta["click_extra.version"]`, the expensive Git subprocess calls and environment profiling are never executed.
```

## Template rendering

You can render the version string manually by calling the option's internal methods:

```{click:source}
:emphasize-lines: 9-10
import click
from click_extra import echo, pass_context, version_option, ExtraVersionOption, search_params

@click.command
@version_option(version="1.2.3")
@pass_context
def template_rendering(ctx):
    # Search for a ``--version`` parameter.
    version_opt = search_params(ctx.command.params, ExtraVersionOption)
    version_string = version_opt.render_message()
    echo(f"Version string ~> {version_string}")
```

```{hint}
To fetch the `--version` parameter defined on the command, we rely on the [`click_extra.search_params`](parameters.md#click_extra.parameters.search_params).
```

```{click:run}
invoke(template_rendering, ["--version"])
```

```{click:run}
import re
result = invoke(template_rendering)
assert re.fullmatch((
    r"Version string ~> "
    r"\x1b\[97mtemplate-rendering\x1b\[0m, version \x1b\[32m1.2.3\x1b\[0m\n"
), result.output)
```

That way you can collect the rendered `version_string`, as if it was printed to the terminal by a call to `--version`, and use it in your own way.

Other internal methods to build-up and render the version string are [available in the API below](#click-extra-version-api).

<a name="click-extra-version-api"></a>

## `click_extra.version` API

```{eval-rst}
.. autoclasstree:: click_extra.version
   :strict:

.. automodule:: click_extra.version
   :members:
   :undoc-members:
   :show-inheritance:
```
