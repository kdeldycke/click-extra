# Version

Click Extra provides its own version option which, compared to [Click's built-in](https://click.palletsprojects.com/en/stable/api/?highlight=version#click.version_option):

- adds [new variable](#variables) to compose your version string
- adds [colors](#colors)
- adds complete [environment information in JSON](#environment-information)
- works with [standalone scripts](#standalone-script)
- use [format string syntax](https://docs.python.org/3/library/string.html#format-string-syntax)
- prints [details metadata in `DEBUG` logs](#debug-logs)
- expose [metadata in the context](#get-metadata-values)

```{hint}
To prevent any confusion, and to keep on [the promise of drop-in replacement](commands.md#drop-in-replacement), Click Extra's version option is prefixed with `extra_`:
   - the vanilla Click's `version_option` is aliased as `click_extra.version_option`
   - Click Extra's own `version_option` is available as [`click_extra.extra_version_option`](click_extra.md#click_extra.extra_version_option)
   - Click Extra adds a [`@extra_version_option` decorator](click_extra.md#click_extra.extra_version_option) which is based on [`click_extra.ExtraVersionOption` class](#click_extra.version.ExtraVersionOption)
```

## Defaults

Here is how the defaults looks like:

```{click:example}
:emphasize-lines: 4
from click_extra import command, extra_version_option

@command
@extra_version_option(version="1.2.3")
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
In this example I have hard-coded the version to `1.2.3` for the sake of demonstration. In most cases, you do not need to force it. By default, the version will be automatically fetched from the `__version__` attribute of the module where the command is defined.
```

## Variables

The message template is a [format string](https://docs.python.org/3/library/string.html#format-string-syntax), which [defaults to](#click_extra.version.ExtraVersionOption.message):

```{code-block} python
f"{prog_name}, version {version}"
```

```{important}
This is different from Click, which uses [the `%(prog)s, version %(version)s` template](https://github.com/pallets/click/blob/b498906/src/click/decorators.py#L455).

Click is based on [old-school `printf`-style formatting](https://docs.python.org/3/library/stdtypes.html#printf-style-string-formatting), which relies on variables of the `%(variable)s` form.

Click Extra uses [modern format string syntax](https://docs.python.org/3/library/string.html#format-string-syntax), with variables of the `{variable}` form, to provide a more flexible and powerful templating.
```

You can customize the message template with the following variables:

| Variable                                                                       | Description                                                                                                                                                                            |
| ------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`{module}`](#click_extra.version.ExtraVersionOption.module)                   | The [module object](https://docs.python.org/3/glossary.html#term-module) in which the command is implemented.                                                                          |
| [`{module_name}`](#click_extra.version.ExtraVersionOption.module_name)         | The [`__name__` of the module](https://docs.python.org/3/reference/import.html#name__) in which the command is implemented.                                                            |
| [`{module_file}`](#click_extra.version.ExtraVersionOption.module_file)         | The [full path of the file](https://docs.python.org/3/reference/import.html#file__) in which the command is implemented.                                                               |
| [`{module_version}`](#click_extra.version.ExtraVersionOption.module_version)   | The string found in the local `__version__` variable of the module.                                                                                                                    |
| [`{package_name}`](#click_extra.version.ExtraVersionOption.package_name)       | The [name of the package](https://docs.python.org/3/reference/import.html#package__) in which the CLI is distributed.                                                                  |
| [`{package_version}`](#click_extra.version.ExtraVersionOption.package_version) | The [version from the package metadata](https://docs.python.org/3/library/importlib.metadata.html?highlight=metadata%20version#distribution-versions) in which the CLI is distributed. |
| [`{exec_name}`](#click_extra.version.ExtraVersionOption.exec_name)             | User-friendly name of the executed CLI. Returns `{module_name}`, `{package_name}` or script's filename, in this order.                                                                 |
| [`{version}`](#click_extra.version.ExtraVersionOption.version)                 | Version of the CLI. Returns `{module_version}`, `{package_version}` or `None`, in this order.                                                                                          |
| [`{git_repo_path}`](#click_extra.version.ExtraVersionOption.git_repo_path)     | The full path to the Git repository root directory, or `None` if not in a Git repository.                                                                                              |
| [`{git_branch}`](#click_extra.version.ExtraVersionOption.git_branch)           | The current Git branch name, or `None` if not in a Git repository or Git is not available.                                                                                             |
| [`{git_long_hash}`](#click_extra.version.ExtraVersionOption.git_long_hash)     | The full Git commit hash of the current `HEAD`, or `None` if not in a Git repository or Git is not available.                                                                           |
| [`{git_short_hash}`](#click_extra.version.ExtraVersionOption.git_short_hash)   | The short Git commit hash of the current `HEAD`, or `None` if not in a Git repository or Git is not available.                                                                          |
| [`{git_date}`](#click_extra.version.ExtraVersionOption.git_date)               | The commit date of the current `HEAD` in ISO format (`YYYY-MM-DD HH:MM:SS +ZZZZ`), or `None` if not in a Git repository or Git is not available.                                       |
| [`{prog_name}`](#click_extra.version.ExtraVersionOption.prog_name)             | The name of the program, from Click's point of view.                                                                                                                                   |
| [`{env_info}`](#click_extra.version.ExtraVersionOption.env_info)               | The [environment information](https://boltons.readthedocs.io/en/latest/ecoutils.html#boltons.ecoutils.get_profile) in JSON.                                                            |

```{caution}
Some Click's built-in variables are not recognized:
- `%(package)s` should be replaced by `{package_name}`
- `%(prog)s` should be replaced by `{prog_name}`
- All other `%(variable)s` should be replaced by their `{variable}` counterpart
```

You can compose your own version string by passing the `message` argument:

```{click:example}
:emphasize-lines: 4
from click_extra import command, extra_version_option

@command
@extra_version_option(message="✨ {prog_name} v{version} - {package_name}")
def my_own_cli():
    pass
```

```{click:run}
from click_extra import __version__
result = invoke(my_own_cli, args=["--version"])
assert result.output == (
    "✨ \x1b[97mmy-own-cli\x1b[0m "
    f"v\x1b[32m{__version__}\x1b[0m - "
    "\x1b[97mclick_extra\x1b[0m\n"
)
```

```{note}
Notice here how the `{package_name}` string takes the `click_extra` value. That's because this snippet of code is dynamiccaly executed by Sphinx in the context of Click Extra itself. And as a result, the `{version}` string takes the value of the current version of Click Extra (i.e.  `click_extra.__version__`).

You will not have this behavior once your get your CLI packaged: your CLI will properly inherits its metadata automatically from your package.
```

## Standalone script

The `--version` option works with standalone scripts.

Let's put this code in a file named `greet.py`:

```{code-block} python
:caption: `greet.py`
from click_extra import extra_command


@extra_command
def greet():
    print("Hello world")


if __name__ == "__main__":
    greet()
```

Here is the result of the `--version` option:

```{code-block} ansi-shell-session
$ python ./greet.py --version
[97mgreet.py[0m, version [32mNone[0m
```

Because the script is not packaged, the `{package_name}` is set to the script file name (`greet.py`) and `{version}` variable to `None`.

But Click Extra recognize a `__version__` variable. So you can force the version string in your script:

```{code-block} python
:caption: `greet.py`
:emphasize-lines: 4
from click_extra import extra_command


__version__ = "0.9.3-alpha"


@extra_command
def greet():
    print("Hello world")


if __name__ == "__main__":
    greet()
```

```{code-block} ansi-shell-session
$ python ./greet.py --version
[97mgreet.py[0m, version [32m0.9.3-alpha[0m
```

```{caution}
The `__version__` variable is [not an enforced Python standard](https://peps.python.org/pep-0396/#specification) and [more like a tradition](https://peps.python.org/pep-0008/#module-level-dunder-names).

It is supported by Click Extra as a convenience for script developers.
```

## Colors

Each variable listed in the section above can be rendered in its own style. They all have dedicated parameters you can pass to the `extra_version_option` decorator:

| Parameter                 | Description                                 | Default Style |
| ------------------------- | ------------------------------------------- | ------------- |
| `message_style`           | Style of the whole message.               | `None` |
| `module_style`            | Style for `{module}` variable.           | `None` |
| `module_name_style`       | Style for `{module_name}` variable.      | `default_theme.invoked_command` |
| `module_file_style`       | Style for `{module_file}` variable.      | `None` |
| `module_version_style`    | Style for `{module_version}` variable.   | `Style(fg="green")` |
| `package_name_style`      | Style for `{package_name}` variable.     | `default_theme.invoked_command` |
| `package_version_style`   | Style for `{package_version}` variable.  | `Style(fg="green")` |
| `exec_name_style`         | Style for `{exec_name}` variable.        | `default_theme.invoked_command` |
| `version_style`           | Style for `{version}` variable.          | `Style(fg="green")` |
| `git_repo_path_style`     | Style for `{git_repo_path}` variable.    | `Style(fg="bright_black")` |
| `git_branch_style`        | Style for `{git_branch}` variable.       | `Style(fg="cyan")` |
| `git_long_hash_style`     | Style for `{git_long_hash}` variable.    | `Style(fg="yellow")` |
| `git_short_hash_style`    | Style for `{git_short_hash}` variable.   | `Style(fg="yellow")` |
| `git_date_style`          | Style for `{git_date}` variable.         | `Style(fg="bright_black")` |
| `prog_name_style`         | Style for `{prog_name}` variable.        | `default_theme.invoked_command` |
| `env_info_style`          | Style for `{env_info}` variable.         | `Style(fg="bright_black")` |

Here is an example:

```{click:example}
:emphasize-lines: 6-9
from click_extra import command, extra_version_option, Style

@command
@extra_version_option(
    message="{prog_name} v{version} 🔥 {package_name} ( ͡❛ ͜ʖ ͡❛)",
    message_style=Style(fg="cyan"),
    prog_name_style=Style(fg="green", bold=True),
    version_style=Style(fg="bright_yellow", bg="red"),
    package_name_style=Style(fg="bright_blue", italic=True),
)
def cli():
    pass
```

```{click:run}
from click_extra import __version__
result = invoke(cli, args=["--version"])
assert result.output == (
    "\x1b[32m\x1b[1mcli\x1b[0m\x1b[36m "
    f"v\x1b[0m\x1b[93m\x1b[41m{__version__}\x1b[0m\x1b[36m 🔥 "
    "\x1b[0m\x1b[94m\x1b[3mclick_extra\x1b[0m\x1b[36m ( ͡❛\u202f͜ʖ ͡❛)\x1b[0m\n"
)
```

```{hint}
The [`Style()` helper is defined by Cloup](https://cloup.readthedocs.io/en/stable/autoapi/cloup/styling/index.html#cloup.styling.Style).
```

You can pass `None` to any of the style parameters to disable styling for the corresponding variable:

```{click:example}
:emphasize-lines: 5-7
from click_extra import command, extra_version_option

@command
@extra_version_option(
    message_style=None,
    version_style=None,
    prog_name_style=None,
)
def cli():
    pass
```

```{click:run}
from click_extra import __version__
result = invoke(cli, args=["--version"])
assert result.output == f"cli, version {__version__}\n"
```

## Environment information

The `{env_info}` variable compiles all sorts of environment information.

Here is how it looks like:

```{click:example}
:emphasize-lines: 4
from click_extra import command, extra_version_option

@command
@extra_version_option(message="{env_info}")
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

```{click:example}
:emphasize-lines: 5
from click_extra import command, extra_version_option

@command
@extra_version_option(
    message="{prog_name} {version}, from {module_file} (Python {env_info[python][version]})"
)
def custom_env_info():
    pass
```

```{click:run}
import re
from click_extra import __version__
result = invoke(custom_env_info, args=["--version"])
assert re.fullmatch((
    rf"\x1b\[97mcustom-env-info\x1b\[0m \x1b\[32m{__version__}\x1b\[0m, "
    r"from .+ \(Python \x1b\[90m3\.\d+\.\d+ .+\x1b\[0m\)\n"
), result.output)
```

## Debug logs

When the `DEBUG` level is enabled, all available variables will be printed in the log:

```{click:example}
:emphasize-lines: 4-5
from click_extra import command, verbosity_option, extra_version_option, echo

@command
@extra_version_option
@verbosity_option
def version_in_logs():
    echo("Standard operation")
```

Which is great to see how each variable is populated and styled:

```{click:run}
import re
from click_extra import __version__
result = invoke(version_in_logs, ["--verbosity", "DEBUG"])
assert "\n\x1b[34mdebug\x1b[0m: Version string template variables:\n" in result.output
```

## Get metadata values

You can get the uncolored, Python values used in the composition of the version message from the context:

```{click:example}
:emphasize-lines: 7-10
from click_extra import command, echo, pass_context, extra_version_option

@command
@extra_version_option
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
from click_extra import __version__
result = invoke(version_metadata)
assert re.fullmatch((
    rf"version = {__version__}\n"
    r"package_name = click_extra\n"
    r"prog_name = version-metadata\n"
    r"env_info = {'.+'}\n"
), result.output)
```

```{hint}
These variables are presented in their original Python type. If most of these variables are strings, others like `env_info` retains their original `dict` type.
```

## Template rendering

You can render the version string manually by calling the option's internal methods:

```{click:example}
:emphasize-lines: 8-9
from click_extra import command, echo, pass_context, extra_version_option, ExtraVersionOption, search_params

@command
@extra_version_option
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
from click_extra import __version__
result = invoke(template_rendering)
assert re.fullmatch((
    r"Version string ~> "
    rf"\x1b\[97mtemplate-rendering\x1b\[0m, version \x1b\[32m{__version__}\x1b\[0m\n"
), result.output)
```

That way you can collect the rendered `version_string`, as if it was printed to the terminal by a call to `--version`, and use it in your own way.

Other internal methods to build-up and render the version string are [available in the API below](#click-extra-version-api).

## `click_extra.version` API

```{eval-rst}
.. autoclasstree:: click_extra.version
   :strict:
```

```{eval-rst}
.. automodule:: click_extra.version
   :members:
   :undoc-members:
   :show-inheritance:
```
