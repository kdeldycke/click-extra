# {octicon}`command-palette` CLI

The `click-extra` package ships a CLI of the same name. It doubles as a live demo of the framework's rendering features and as a toolbox of documentation and testing utilities. It comes with the package itself (see [installation](install.md)) or as a [standalone binary](binaries.md).

A crash of the CLI's own code ends with a [bug report](bug-report.md) for the issue form of Click Extra. A subcommand that runs the code of another project, like [`wrap`](wrap.md), shows the traceback of the error instead.

Everything below is rendered at build time from the actual command tree, so this reference cannot drift from the code.

## Commands

```{click:tree} demo
from click_extra.cli import demo
```

## Configuration

The CLI reads its defaults from the `[tool.click-extra]` section of the nearest `pyproject.toml`, through click-extra's own [configuration machinery](config.md). The reference below is rendered live from its configuration schema:

```{click:config} demo
from click_extra.cli import demo
```

The schema leaves out two parts of the section, which the sections below cover.

### Themes

Each `[tool.click-extra.themes.<name>]` table declares a help-screen theme for `--theme`. A table named after a built-in theme overrides the slots it sets, and a table with any other name adds a theme. See [themes from your config file](theme.md#themes-from-your-config-file).

### Default subcommand

The reserved `_default_subcommands` key names the subcommand that runs when `click-extra` gets no subcommand on the command line. See [default subcommands](config.md#default-subcommands).
