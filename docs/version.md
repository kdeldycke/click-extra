# Version

Click Extra provides its own version option which, compared to [Click's built-in](https://click.palletsprojects.com/en/8.1.x/api/?highlight=version#click.version_option):

- adds [new variable](#variables) to compose your version string
- adds [colors](#colors)
- adds complete [environment information in JSON](#environment-information)
- works with [standalone scripts](#standalone-script)
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

```{eval-rst}
.. click:example::
      from click_extra import command, extra_version_option

      @command
      @extra_version_option(version="1.2.3")
      def cli():
         pass

.. click:run::
   result = invoke(cli, args=["--help"])
   assert "--version" in result.output

The default version message is the `same as Click's default <https://github.com/pallets/click/blob/b498906/src/click/decorators.py#L455>`_ (i.e. ``%(prog)s, version %(version)s``), but colored:

.. click:run::
   result = invoke(cli, args=["--version"])
   assert result.output == "\x1b[97mcli\x1b[0m, version \x1b[32m1.2.3\x1b[0m\n"
```

```{hint}
In this example I have hard-coded the version to `1.2.3` for the sake of demonstration. But in most case, you do not need to force it. By default, the version will be automattically fetched from the `__version__` attribute of the module where the command is defined.
```

## Variables

You can customize the version string with the following variables:

- `%(package_name)s`: the name of the package where the command is defined. Will return the base module ID (string before the first dot `.`). If the CLI is not packaged, it will return the Python script's filename.
- `%(version)s`: the version of the package where the command is defined. If the CLI is not packaged, the version string will be the one defined by the `__version__` variable in the Python script, or `None`.
- `%(prog_name)s`: the name of the program (i.e. the CLI's name).
- `%(env_info)s`: the environment information in JSON.

```{caution}
Click's built-in variables are recognized but deprecated:
- Click's `%(package)s` is aliased to Click Extra's `%(package_name)s`
- Click's `%(prog)s` is aliased to Click Extra's `%(prog_name)s`

A deprecation warning will be emitted when using Click's variables.
```

You can compose your own version string by passing the `message` argument:

```{eval-rst}
.. click:example::
      from click_extra import command, extra_version_option

      @command
      @extra_version_option(message="✨ %(prog_name)s v%(version)s - %(package_name)s")
      def my_own_cli():
         pass

.. click:run::
   from click_extra import __version__
   result = invoke(my_own_cli, args=["--version"])
   assert result.output == (
      "✨ \x1b[97mmy-own-cli\x1b[0m "
      f"v\x1b[32m{__version__}\x1b[0m - "
      "\x1b[97mclick_extra\x1b[0m\n"
   )
```

```{note}
Notice here how the `%(package_name)s` string takes the `click_extra` value. That's because this snippet of code is dynamiccaly executed by Sphinx in the context of Click Extra itself. And as a result, the `%(version)s` string takes the value of the current version of Click Extra (i.e.  `click_extra.__version__`).

You will not have this behavior once your get your CLI packaged: your CLI will properly inherits its metadata automatically from your package.
```

## Standalone script

The `--version` option works with standalone scripts.

Let's put this code in a file named `greet.py`:

```python
from click_extra import extra_command


@extra_command
def greet():
    print("Hello world")


if __name__ == "__main__":
    greet()
```

```shell-session
$ cat greet.py
from click_extra import extra_command


@extra_command
def greet():
    print("Hello world")


if __name__ == "__main__":
    greet()
```

Here is the result of the `--version` option:

```ansi-shell-session
$ python ./greet.py --version
[97mgreet.py[0m, version [32mNone[0m
```

Because the script is not packaged, the `%(package_name)s` is set to the script file name (`greet.py`) and `%(version)s` variable to `None`.

You can still define a `__version__` variable in your script to force the version string:

```python
from click_extra import extra_command


__version__ = "0.9.3-alpha"


@extra_command
def greet():
    print("Hello world")


if __name__ == "__main__":
    greet()
```

```ansi-shell-session
$ python ./greet.py --version
[97mgreet.py[0m, version [32m0.9.3-alpha[0m
```

## Colors

Each variable listed in the section above can be rendered in its own style. They all have dedicated parameters you can pass to the `extra_version_option` decorator:

| Parameter            | Description                               |
| -------------------- | ----------------------------------------- |
| `version_style`      | Style of the `%(version)s` variable.      |
| `package_name_style` | Style of the `%(package_name)s` variable. |
| `prog_name_style`    | Style of the `%(prog_name)s` variable.    |
| `env_info_style`     | Style of the `%(env_info)s` variable.     |
| `message_style`      | Default style of the rest of the message. |

Here is an example:

```{eval-rst}
.. click:example::
      from click_extra import command, extra_version_option, Style

      @command
      @extra_version_option(
         message="%(prog_name)s v%(version)s 🔥 %(package_name)s ( ͡❛ ͜ʖ ͡❛)",
         message_style=Style(fg="cyan"),
         prog_name_style=Style(fg="green", bold=True),
         version_style=Style(fg="bright_yellow", bg="red"),
         package_name_style=Style(fg="bright_blue", italic=True),
      )
      def cli():
         pass

.. click:run::
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

```{eval-rst}
.. click:example::
      from click_extra import command, extra_version_option

      @command
      @extra_version_option(
          version_style=None,
          package_name_style=None,
          prog_name_style=None,
          env_info_style=None,
          message_style=None,
      )
      def cli():
         pass

.. click:run::
   from click_extra import __version__
   result = invoke(cli, args=["--version"])
   assert result.output == f"cli, version {__version__}\n"
```

## Environment information

The `%(env_info)s` variable compiles all sorts of environment informations.

Here is how it looks like:

```{eval-rst}
.. click:example::
      from click_extra import command, extra_version_option

      @command
      @extra_version_option(message="%(env_info)s")
      def env_info_cli():
         pass

.. click:run::
   import re
   result = invoke(env_info_cli, args=["--version"])
   assert re.fullmatch(r"\x1b\[90m{'.+'}\x1b\[0m\n", result.output)
```

It's verbose but it's helpful for debugging and reporting of issues from end users.

```{important}
The JSON output is scrubbed out of identifiable information by default: current working directory, hostname, Python executable path, command-line arguments and username are replaced with `-`.
```

## Debug logs

When the `DEBUG` level is enabled, the version message will be printed to the `DEBUG` log:

```{eval-rst}
.. click:example::
      from click_extra import extra_command, VerbosityOption, ExtraVersionOption, echo

      @extra_command(
         params=[
            ExtraVersionOption(),
            VerbosityOption(),
         ]
      )
      def version_in_logs():
          echo("Standard operation")

.. click:run::
   import re
   from click_extra import __version__
   result = invoke(version_in_logs, ["--verbosity", "DEBUG"])
   assert re.search((
      r"\n\x1b\[34mdebug\x1b\[0m: "
      rf"\x1b\[97mversion-in-logs\x1b\[0m, version \x1b\[32m{__version__}\x1b\[0m"
      r"\n\x1b\[34mdebug\x1b\[0m: "
      r"\x1b\[90m{'.+'}\x1b\[0m\n"
   ), result.output)
```

```{hint}
If the message template does not contains the `%(env_info)s` variable, it will be automattically added to the log message.
```

```{attention}
This feature only works with the combination of `extra_command`, `ExtraVersionOption` and `VerbosityOption`.

Unless you assemble your own command with `extra_command`, or use the later with the default options, you won't see the version message in the logs.
```

## Get metadata values

You can get the uncolored, Python values used in the composition of the version message from the context:

```{eval-rst}
.. click:example::
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

.. click:run::
   result = invoke(version_metadata, ["--version"])

.. click:run::
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

```{eval-rst}
.. click:example::
    from click_extra import command, echo, pass_context, extra_version_option, ExtraVersionOption, search_params

    @command
    @extra_version_option
    @pass_context
    def template_rendering(ctx):
         # Search for a ``--version`` parameter.
         version_opt = search_params(ctx.command.params, ExtraVersionOption)
         version_string = version_opt.render_message()
         echo(f"Version string ~> {version_string}")

.. hint::
   To look for the ``--version`` parameter defined on the command, we rely on the `click_extra.search_params <parameters.md#click_extra.parameters.search_params>`_.

.. click:run::
   result = invoke(template_rendering, ["--version"])

.. click:run::
   import re
   from click_extra import __version__
   result = invoke(template_rendering)
   assert re.fullmatch((
      r"Version string ~> "
      rf"\x1b\[97mtemplate-rendering\x1b\[0m, version \x1b\[32m{__version__}\x1b\[0m\n"
   ), result.output)
```

That way you can collect the rendered (and colored) `version_string`, as if it was printed to the terminal by a call to `--version`, and use it in your own way.

Other internal methods to build-up and render the version string are [available in the API below](#click_extraversion-api).

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
