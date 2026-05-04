# {octicon}`download` Installation

```{sidebar}
[![Packaging status](https://repology.org/badge/vertical-allrepos/python%3Aclick-extra.svg)](https://repology.org/project/python%3Aclick-extra/versions)
```

Click Extra is [distributed on PyPI](https://pypi.org/project/click-extra/).

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
[`pipx`](https://pipx.pypa.io/stable/how-to/install-pipx/) is a great way to install the demo CLI globally:

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

## Python compatibility

The table below shows which Python versions each `click-extra` release range supports, derived from the `Programming Language :: Python :: 3.X` classifiers across all release tags. Releases prior to `4.9.0` did not declare explicit Python classifiers and are not represented.

<!-- python-compat-start -->

| `click-extra`       | Released   | `3.9` | `3.10` | `3.11` | `3.12` | `3.13` | `3.14` |
| :------------------ | :--------- | :---: | :----: | :----: | :----: | :----: | :----: |
| `6.2.x` → `7.x`     | 2025-11-04 |  ❌   |   ✅   |   ✅   |   ✅   |   ✅   |   ✅   |
| `6.0.1` → `6.1.x`   | 2025-10-08 |  ❌   |   ❌   |   ✅   |   ✅   |   ✅   |   ✅   |
| `5.x` → `6.0.0`     | 2025-05-13 |  ❌   |   ❌   |   ✅   |   ✅   |   ✅   |   ❌   |
| `4.11.x` → `4.15.x` | 2024-10-08 |  ❌   |   ✅   |   ✅   |   ✅   |   ✅   |   ❌   |
| `4.9.x` → `4.10.x`  | 2024-07-25 |  ✅   |   ✅   |   ✅   |   ✅   |   ❌   |   ❌   |

<!-- python-compat-end -->

## Click compatibility

Click Extra wraps Click, so the two are tightly coupled and the matrix of supported Click versions matters as much as the Python one. The table below shows which Click versions each `click-extra` release range accepts at install time, derived from the `click` runtime dependency specifier in `pyproject.toml` across all release tags. The `8.1` and `8.2` columns are minor-grouped (✅ means at least one patch in that minor is accepted); the `8.3` columns are split per patch since `click-extra` releases pin distinct `8.3.x` floors that matter at install time.

<!-- click-compat-start -->

| `click-extra`       | Released   | Spec       | `8.1` | `8.2` | `8.3.0` | `8.3.1` | `8.3.3` |
| :------------------ | :--------- | :--------- | :---: | :---: | :-----: | :-----: | :-----: |
| `7.15.x`            | 2026-05-03 | `>=8.3.1`  |  ❌   |  ❌   |   ❌    |   ✅    |   ✅    |
| `7.14.1`            | 2026-04-26 | `>=8.1`    |  ✅   |  ✅   |   ✅    |   ✅    |   ✅    |
| `7.14.0`            | 2026-04-24 | `>=8.3.3`  |  ❌   |  ❌   |   ❌    |   ❌    |   ✅    |
| `7.0.x` → `7.13.x`  | 2025-11-17 | `>=8.3.1`  |  ❌   |  ❌   |   ❌    |   ✅    |   ✅    |
| `6.x`               | 2025-09-25 | `>=8.3.0`  |  ❌   |  ❌   |   ✅    |   ✅    |   ✅    |
| `5.x`               | 2025-05-13 | `~=8.2.x`  |  ❌   |  ✅   |   ❌    |   ❌    |   ❌    |
| `4.9.x` → `4.15.x`  | 2024-07-25 | `~=8.1.x`  |  ✅   |  ❌   |   ❌    |   ❌    |   ❌    |

<!-- click-compat-end -->

```{note}
`7.14.1` is the only release with relaxed Click bounds (`>=8.1`): it temporarily widened compatibility to ease pinning across downstreams that hadn't yet bumped to Click `8.3`. `7.15.0` re-tightened the floor to `8.3.1` once Click `8.3` adoption stabilized. `7.14.0` is the strictest floor on record (`>=8.3.3`), pulled in to match a specific Click parameter-name fix; `7.14.1` immediately relaxed it.
```

## Default dependencies

This is a graph of the default, main dependencies of the Python package:

```mermaid assets/dependencies.mmd
:align: center
```

## Extra dependencies

By default, Click Extra supports TOML [configuration files](config.md#toml) and all standard [table formats](table.md#table-formats). Optional extras unlock additional features:

````{list-table}
:header-rows: 1
:widths: 10 40 50
* - Extra
  - Install command
  - Unlocks
* - `hjson`
  - ```{code-block} shell-session
    $ pip install click-extra[hjson]
    ```
  - - [HJSON](config.md#hjson) config files: `--config app.hjson`
    - [`hjson` table format](table.md#table-formats): `--table-format hjson`
* - `json5`
  - ```{code-block} shell-session
    $ pip install click-extra[json5]
    ```
  - - [JSON5](config.md#json5) config files: `--config app.json5`
* - `jsonc`
  - ```{code-block} shell-session
    $ pip install click-extra[jsonc]
    ```
  - - [JSONC](config.md#jsonc) config files: `--config app.jsonc`
* - `toml`
  - ```{code-block} shell-session
    $ pip install click-extra[toml]
    ```
  - - [`toml` table format](table.md#table-formats): `--table-format toml`
* - `xml`
  - ```{code-block} shell-session
    $ pip install click-extra[xml]
    ```
  - - [XML](config.md#xml) config files: `--config app.xml`
    - [`xml` table format](table.md#table-formats): `--table-format xml`
* - `yaml`
  - ```{code-block} shell-session
    $ pip install click-extra[yaml]
    ```
  - - [YAML](config.md#yaml) config files: `--config app.yaml`
    - [`yaml` table format](table.md#table-formats): `--table-format yaml`
* - `mkdocs`
  - ```{code-block} shell-session
    $ pip install click-extra[mkdocs]
    ```
  - - [ANSI color rendering](mkdocs.md) in MkDocs code blocks
* - `pygments`
  - ```{code-block} shell-session
    $ pip install click-extra[pygments]
    ```
  - - [ANSI-capable formatter, filter and lexers](pygments.md) for Pygments
* - `sphinx`
  - ```{code-block} shell-session
    $ pip install click-extra[sphinx]
    ```
  - - [`click:source` and `click:run` directives](sphinx.md) for live CLI documentation
* - `pytest`
  - ```{code-block} shell-session
    $ pip install click-extra[pytest]
    ```
  - - [Fixtures and utilities](pytest.md) for testing Click CLIs
````

````{tip}
Install all extras at once with:

```{code-block} shell-session
$ pip install click-extra[hjson,json5,jsonc,mkdocs,toml,xml,yaml,pygments,sphinx,pytest]
```
````
