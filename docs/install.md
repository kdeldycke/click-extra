# {octicon}`download` Installation

```{sidebar}
[![Packaging status](https://repology.org/badge/vertical-allrepos/python%3Aclick-extra.svg)](https://repology.org/project/python%3Aclick-extra/versions)
```

Click Extra is [distributed on PyPi](https://pypi.org/project/click-extra/).

So you can install the latest stable release with your favorite package manager [like `pip`](https://pip.pypa.io):

```{code-block} shell-session
$ pip install click-extra
```

## Installation methods

`````{tab-set}

````{tab-item} uv
Easiest way is to [install `uv`](https://docs.astral.sh/uv/getting-started/installation/), then add `click-extra` to your project:

```{code-block} shell-session
$ uv add click-extra
```

Or to install the demo CLI system-wide with [`uv tool`](https://docs.astral.sh/uv/guides/tools/#installing-tools):

```{code-block} shell-session
$ uv tool install click-extra
```
````

````{tab-item} pipx
[`pipx`](https://pipx.pypa.io/stable/installation/) is a great way to install the demo CLI globally:

```{code-block} shell-session
$ pipx install click-extra
```
````

````{tab-item} pip
You can install the latest stable release and its dependencies with a simple `pip` call:

```{code-block} shell-session
$ python -m pip install click-extra
```

If you have difficulties to use `pip`, see
[`pip`'s own installation instructions](https://pip.pypa.io/en/stable/installation/).
````
`````

## Demo CLI

You can try Click Extra right now in your terminal, without installing any dependency or virtual env [thanks to `uvx`](https://docs.astral.sh/uv/guides/tools/):

`````{tab-set}
````{tab-item} Latest version
```shell-session
$ uvx click-extra
```
````

````{tab-item} Specific version
```shell-session
$ uvx click-extra@7.2.0
```
````

````{tab-item} Development version
```shell-session
$ uvx --from git+https://github.com/kdeldycke/click-extra -- click-extra
```
````

````{tab-item} Local version
```shell-session
$ uvx --from file:///Users/me/code/click-extra -- click-extra
```
````
`````

This will download and run `click-extra`, a demo CLI included in the package.

The demo CLI showcases various features of Click Extra, such as enhanced help formatting, colored output, and more.

By default it will display the help message of the demo application:

```{code-block} shell-session
$ uvx click-extra
Installed 16 packages in 14ms
Usage: click-extra [OPTIONS] COMMAND [ARGS]...
```

And so you can explore the various possibilities of the demo application, like showing the current version:

```{code-block} shell-session
$ uvx click-extra --version
Installed 16 packages in 14ms
Click Extra demo, version 7.2.0
```

This is a great way to play with Click Extra and check that it runs fine on your system, and renders properly in your terminal.

## Try the library

Now that you have tried the demo application, you can also try the library itself in an interactive Python shell without installing anything on your system:

```{code-block} shell-session
$ uvx --with click-extra python
Installed 3 packages in 5ms
Python 3.14.0 free-threading build (main, Oct 28 2025, 11:52:40) [Clang 20.1.4 ] on darwin
Type "help", "copyright", "credits" or "license" for more information.
>>> import click_extra
>>> click_extra.__version__
'7.2.0'
>>>
```

## Default dependencies

This is a graph of the default, main dependencies of the Python package:

```mermaid assets/dependencies.mmd
:align: center
```

## Extra dependencies

For additional features, you may need to install extra dependencies.

### Data formats

These extras add support for additional [configuration file formats](config.md#formats) and [table output formats](table.md#table-formats):

- [HJSON](config.md#hjson) configuration files and [`hjson` table format](table.md#table-formats):

  ```{code-block} shell-session
  $ pip install click-extra[hjson]
  ```

- [JSON5](config.md#json5) configuration files:

  ```{code-block} shell-session
  $ pip install click-extra[json5]
  ```

- [JSONC](config.md#jsonc) configuration files:

  ```{code-block} shell-session
  $ pip install click-extra[jsonc]
  ```

- [`toml` table format](table.md#table-formats) output (TOML [configuration files](config.md#toml) are supported by default):

  ```{code-block} shell-session
  $ pip install click-extra[toml]
  ```

- [XML](config.md#xml) configuration files and [`xml` table format](table.md#table-formats):

  ```{code-block} shell-session
  $ pip install click-extra[xml]
  ```

- [YAML](config.md#yaml) configuration files and [`yaml` table format](table.md#table-formats):

  ```{code-block} shell-session
  $ pip install click-extra[yaml]
  ```

### For Pygments

Register new [ANSI-capable formatter, filter and lexers](pygments.md):

```{code-block} shell-session
$ pip install click-extra[pygments]
```

### For Sphinx

Register new [`click:source` and `click:run` directives](sphinx.md) for live CLI documentation:

```{code-block} shell-session
$ pip install click-extra[sphinx]
```

### For Pytest

Activate new [fixtures and utilities](pytest.md) for testing Click CLIs:

```{code-block} shell-session
$ pip install click-extra[pytest]
```