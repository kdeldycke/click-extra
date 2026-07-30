# {octicon}`command-palette` CLI

The `click-extra` package ships a CLI of the same name. It doubles as a live demo of the framework's rendering features and as a toolbox of documentation and testing utilities. It comes with the package itself (see [installation](install.md)) or as a [standalone binary](binaries.md).

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
