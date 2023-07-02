# Version

Click Extra provides its own version option which, compared to [Click's built-in](https://click.palletsprojects.com/en/8.1.x/api/?highlight=version#click.version_option):

- adds [new variable](#variables) to compose your version string
- adds [colors](#colors)
- adds complete [environment information in JSON](#environment-information)
- prints [details metadata in `DEBUG` logs](#debug-logs)
- expose [metadata in the context](#get-metadata-values)

## Defaults

Here is how the defaults looks like:

```{eval-rst}
.. click:example::
      from click_extra import command, version_option

      @command
      @version_option(version="1.2.3")
      def cli():
         pass

Here I have hard-coded the version to ``1.2.3`` for the sake of the example, but by default, the version will be automattically fetched from the ``__version__`` attribute of the module where the command is defined.

.. click:run::
   result = invoke(cli, args=["--help"])
   assert "--version" in result.output

The default version message is ``%(prog)s, version %(version)s`` (`like Click's own default <https://github.com/pallets/click/blob/b498906/src/click/decorators.py#L455>`_), but is colored:

.. click:run::
   result = invoke(cli, args=["--version"])
   assert result.output == "\x1b[97mcli\x1b[0m, version \x1b[32m1.2.3\x1b[0m\n"
```

## Variables

You can customize the version string with the following variables:

- `%(version)s`: the version of the package where the command is defined
- `%(package_name)s`: the name of the package where the command is defined
- `%(prog_name)s`: the name of the program (i.e. the CLI's name)
- `%(env_info)s`: the environment information in JSON

```{caution}
Click's built-in variables are recognized but deprecated:
- Click's `%(package)s` is aliased to Click Extra's `%(package_name)s`
- Click's `%(prog)s` is aliased to Click Extra's `%(prog_name)s`

A deprecation warning will be emitted when using Click's variables.
```

You can compose your own version string by passing the `message` argument:

```{eval-rst}
.. click:example::
      from click_extra import command, version_option

      @command
      @version_option(message="%(prog_name)s v%(version)s - %(package_name)s")
      def my_own_cli():
         pass

.. click:run::
   from click_extra import __version__
   result = invoke(my_own_cli, args=["--version"])
   assert result.output == (
      "\x1b[97mmy-own-cli\x1b[0m "
      f"v\x1b[32m{__version__}\x1b[0m - "
      "\x1b[97mclick_extra\x1b[0m\n"
   )
```

```{note}
Notice here how the `%(package_name)s` string takes the value of the current package name, i.e. `click_extra`, because that is the Python package this snippet of code is defined in. Consequently, the `%(version)s` string takes the value of the current version of Click Extra (i.e.  `click_extra.__version__`).

Once your CLI gets packaged in its own module, its metadata will be fetched automatically so you don't have to manage them manually.
```

## Colors

Each variable listed in the section above can be rendered in its own style. They all have dedicated parameters you can pass to the `version_option` decorator:

| Parameter | Description |
| --- | --- |
| `version_style` | Style of the `%(version)s` variable. |
| `package_name_style` | Style of the `%(package_name)s` variable. |
| `prog_name_style` | Style of the `%(prog_name)s` variable. |
| `env_info_style` | Style of the `%(env_info)s` variable. |
| `message_style` | Default style of the rest of the message. |

Here is an example:

```{eval-rst}
.. click:example::
      from click_extra import command, version_option, Style

      @command
      @version_option(
         message="%(prog_name)s v%(version)s - %(package_name)s",
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
      f"v\x1b[0m\x1b[93m\x1b[41m{__version__}\x1b[0m\x1b[36m - "
      "\x1b[0m\x1b[94m\x1b[3mclick_extra\x1b[0m\n"
   )
```

```{hint}
The [`Style()` helper is defined by Cloup](https://cloup.readthedocs.io/en/stable/autoapi/cloup/styling/index.html#cloup.styling.Style).
```

You can pass `None` to any of the style parameters to disable styling for the corresponding variable:

```{eval-rst}
.. click:example::
      from click_extra import command, version_option

      @command
      @version_option(
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
      from click_extra import command, version_option

      @command
      @version_option(message="%(env_info)s")
      def my_own_cli():
         pass

.. click:run::
   result = invoke(my_own_cli, args=["--version"])
```

It's verbose but it's helpful for debugging and reporting of issues from end users.

```{important}
The JSON output is scrubbed out of identifiable information by default: current working directory, hostname, Python executable path, command-line arguments and username are replaced with `-`.
```

## Debug logs

When the `DEBUG` level is enabled, the version message will be printed to the `DEBUG` log:

```{eval-rst}
.. click:example::
      from click_extra import extra_command, VerbosityOption, VersionOption, echo

      @extra_command(params=[
          VersionOption(),
          VerbosityOption(),
      ])
      def version_in_logs():
          echo("Standard operation")

.. click:run::
   result = invoke(version_in_logs, ["--verbosity", "DEBUG"])
```

```{hint}
If the message template does not contains the `%(env_info)s` variable, it will be automattically added to the log message.
```

```{attention}
This feature only works with the combination of `extra_command`, `VersionOption` and `VerbosityOption`.

Unless you assemble your own command with `extra_command`, or use the later with the default options, you won't see the version message in the logs.
```

## Get metadata values

You can get the values used in the composition of the version message from the context:

```{eval-rst}
.. click:example::
    from click_extra import command, echo, pass_context, version_option

    @command
    @version_option
    @pass_context
    def version_command(ctx):
        version = ctx.meta["click_extra.version"]
        package_name = ctx.meta["click_extra.package_name"]
        prog_name = ctx.meta["click_extra.prog_name"]
        env_info = ctx.meta["click_extra.env_info"]

        echo(f"version = {version}")
        echo(f"package_name = {package_name}")
        echo(f"prog_name = {prog_name}")
        echo(f"env_info = {env_info}")

.. click:run::
   result = invoke(version_command, ["--version"])

.. click:run::
   result = invoke(version_command)
```

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
