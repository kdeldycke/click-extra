# {octicon}`download` Installation

```{sidebar}
[![Packaging status](https://repology.org/badge/vertical-allrepos/python%3Aclick-extra.svg)](https://repology.org/project/python%3Aclick-extra/versions)
```

## Quick start

Click Extra is [distributed on PyPI](https://pypi.org/project/click-extra/).

So you can install the latest stable release with your favorite package manager [like `uv`](https://docs.astral.sh/uv/):

```{code-block} shell-session
$ uv pip install click-extra
```

## Demo CLI

You can try Click Extra right now in your terminal, without installing any dependency or virtual env [thanks to `uvx`](https://docs.astral.sh/uv/guides/tools/). This downloads and runs `click-extra`, a demo CLI included in the package:

`````{tab-set}
````{tab-item} Latest release
```shell-session
$ uvx click-extra
```

```{click:run}
from click_extra.cli import demo
result = invoke(demo, args=["--help"])
assert result.exit_code == 0
assert "Usage:" in result.output
```
````

````{tab-item} Specific version
```shell-session
$ uvx click-extra@10.3.0
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

The demo CLI showcases various features of Click Extra, such as enhanced help formatting, colored output, and more. The help screen in the *Latest release* tab is rendered at build time, so it always matches the current code. The [CLI reference](cli.md) documents every command with its live help screen.

And so you can explore the various possibilities of the demo application, like showing the current version:

```shell-session
$ uvx click-extra --version
```

This is a great way to play with Click Extra and check that it runs fine on your system, and renders properly in your terminal.

The demo CLI is also compiled into [standalone executables](#binaries) for Linux, macOS, and Windows, so you can try it without Python or `uv`.

## Try the library

Now that you have tried the demo application, you can also try the library itself in an interactive Python shell without installing anything on your system:

```{code-block} shell-session
$ uvx --with click-extra python
Installed 8 packages in 5ms
Python 3.14.0 free-threading build (main, Oct 28 2025, 11:52:40) [Clang 20.1.4 ] on darwin
Type "help", "copyright", "credits" or "license" for more information.
>>> from click_extra import echo, style
>>> echo(style("Hello, World!", fg="green"))
Hello, World!
>>>
```

## Installation methods

`````{tab-set}
:orientation: vertical
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

````{tab-item} pip
You can install the latest stable release and its dependencies with a simple `pip` call:

```{code-block} shell-session
$ python -m pip install click-extra
```

If you have difficulties to use `pip`, see
[`pip`'s own installation instructions](https://pip.pypa.io/en/stable/installation/).
````

````{tab-item} pipx
[`pipx`](https://pipx.pypa.io/stable/how-to/install-pipx.html) is a great way to install the demo CLI globally:

```{code-block} shell-session
$ pipx install click-extra
```
````

````{tab-item} Arch Linux
Arch Linux users install [`python-click-extra`](https://aur.archlinux.org/packages/python-click-extra) from the AUR, with the helper of their choice:

```{code-block} shell-session
$ paru -S python-click-extra
```

The package needs `python-click` `8.5.1` or newer.
````

````{tab-item} GNU Guix
GNU Guix users install [`python-click-extra`](https://packages.guix.gnu.org/packages/python-click-extra/) with [`guix install`](https://guix.gnu.org/manual/en/html_node/Invoking-guix-package.html):

```{code-block} shell-session
$ guix install python-click-extra
```
````

````{tab-item} MacPorts
MacPorts splits [`py-click-extra`](https://ports.macports.org/port/py-click-extra/) into one port per Python version, like `py313-click-extra` for Python 3.13. Install the one matching your Python with [`port install`](https://guide.macports.org/#using.port.install):

```{code-block} shell-session
$ sudo port install py313-click-extra
```
````

````{tab-item} openSUSE Tumbleweed
openSUSE Tumbleweed ships one package per Python version, like `python313-click-extra` for Python 3.13. Install it with [`zypper`](https://doc.opensuse.org/documentation/leap/reference/html/book-reference/cha-sw-cl.html):

```{code-block} shell-session
$ sudo zypper install python313-click-extra
```
````
`````

## Support envelope

Each compatibility table below keeps the [support envelope](python-directives.md#the-support-envelope) of its own axis. Across the three tables, these are obsolete, even where a table still shows them:

<!-- envelope python click cloup -->

- `click-extra` releases before `8.0.0` (2026-06-22)
- Python versions before `3.10` (2021-10-04)
- `click` versions before `8.3.1` (2025-11-15)
- `cloup` versions before `3.0.7` (2025-03-15)

<!-- envelope-end -->

## Python compatibility

Each cell holds one of three states:

- ✅: the release declares support for that Python.
- ❌: the `requires-python` of the release rules that Python out.
- `–`: the release neither claimed nor forbade that Python, usually because that Python was not out yet when the release declared its requirements.

See [three states, two sources](python-directives.md#three-states-two-sources). The table keeps the [support envelope](python-directives.md#the-support-envelope) of its axis, so the oldest releases drop off as the oldest Python the latest release supports moves up.

<!-- matrix python -->

| `click-extra` ↴ \\ Python → | `3.15` | `3.14` | `3.13` | `3.12` | `3.11` | `3.10` | `3.9` | `3.8` | `3.7` |
| :-------------------------- | :----: | :----: | :----: | :----: | :----: | :----: | :---: | :---: | :---: |
| `10.x`                      |   ✅   |   ✅   |   ✅   |   ✅   |   ✅   |   ❌   |  ❌   |  ❌   |  ❌   |
| `9.3.2` → `9.5.x`           |   ✅   |   ✅   |   ✅   |   ✅   |   ✅   |   ✅   |  ❌   |  ❌   |  ❌   |
| `6.2.x` → `9.3.1`           |   –    |   ✅   |   ✅   |   ✅   |   ✅   |   ✅   |  ❌   |  ❌   |  ❌   |
| `6.0.1` → `6.1.x`           |   –    |   ✅   |   ✅   |   ✅   |   ✅   |   ❌   |  ❌   |  ❌   |  ❌   |
| `5.0.x` → `6.0.0`           |   –    |   –    |   ✅   |   ✅   |   ✅   |   ❌   |  ❌   |  ❌   |  ❌   |
| `4.11.x` → `4.15.x`         |   –    |   –    |   ✅   |   ✅   |   ✅   |   ✅   |  ❌   |  ❌   |  ❌   |
| `4.9.x` → `4.10.x`          |   –    |   –    |   –    |   ✅   |   ✅   |   ✅   |  ✅   |  ❌   |  ❌   |
| `4.0.x` → `4.8.x`           |   –    |   –    |   –    |   ✅   |   ✅   |   ✅   |  ✅   |  ✅   |  ❌   |
| `0.0.x` → `3.10.x`          |   –    |   –    |   –    |   –    |   ✅   |   ✅   |  ✅   |  ✅   |  ✅   |

<!-- matrix-end -->

## Click compatibility

Click Extra wraps Click, so the two are tightly coupled and the matrix of supported Click versions matters as much as the Python one.

<!-- matrix click -->

| `click-extra` ↴ \\ `click` → | `8.5.1` | `8.5.0` | `8.4.2` ← `8.4.1` | `8.4.0` ← `8.3.1` |
| :--------------------------- | :-----: | :-----: | :---------------: | :---------------: |
| `10.x`                       |   ✅    |   ✅    |        ❌         |        ❌         |
| `9.x`                        |    –    |   ✅    |        ✅         |        ❌         |
| `8.x`                        |    –    |   ✅    |        ✅         |        ✅         |

<!-- matrix-end -->

## Cloup compatibility

Click Extra's commands and groups subclass those of [Cloup](https://github.com/janluke/cloup), which subclass Click's, and its option groups extend Cloup's. Cloup is therefore the other dependency whose supported range matters.

<!-- matrix cloup -->

| `click-extra` ↴ \\ `cloup` → | `4.0.0` | `3.1.x` ← `3.0.7` |
| :--------------------------- | :-----: | :---------------: |
| `10.x`                       |   ✅    |        ❌         |
| `6.0.x` → `9.5.x`            |   ✅    |        ✅         |

<!-- matrix-end -->

## Binaries

Standalone executables of the demo CLI's latest release are available as direct downloads for several platforms and architectures:

| Platform ↴ \\ Architecture → | `arm64`                                                                                                                                     | `x64`                                                                                                                                   |
| :--------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------ | :-------------------------------------------------------------------------------------------------------------------------------------- |
| **Linux**                    | [Download `click-extra-linux-arm64.bin`](https://github.com/kdeldycke/click-extra/releases/latest/download/click-extra-linux-arm64.bin)     | [Download `click-extra-linux-x64.bin`](https://github.com/kdeldycke/click-extra/releases/latest/download/click-extra-linux-x64.bin)     |
| **macOS**                    | [Download `click-extra-macos-arm64.bin`](https://github.com/kdeldycke/click-extra/releases/latest/download/click-extra-macos-arm64.bin)     | [Download `click-extra-macos-x64.bin`](https://github.com/kdeldycke/click-extra/releases/latest/download/click-extra-macos-x64.bin)     |
| **Windows**                  | [Download `click-extra-windows-arm64.exe`](https://github.com/kdeldycke/click-extra/releases/latest/download/click-extra-windows-arm64.exe) | [Download `click-extra-windows-x64.exe`](https://github.com/kdeldycke/click-extra/releases/latest/download/click-extra-windows-x64.exe) |

Binaries of all past releases, with their VirusTotal analyses, are cataloged on the [binaries page](binaries.md).

## Release verification

Every binary is signed with a [build provenance attestation](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations) at release time. After downloading one, verify it with the [`gh` CLI](https://cli.github.com):

```shell-session
$ gh attestation verify click-extra-linux-x64.bin --repo kdeldycke/click-extra --signer-repo kdeldycke/repomatic
```

`--signer-repo kdeldycke/repomatic` is required because the release runs from [repomatic](https://github.com/kdeldycke/repomatic)'s reusable release workflow, whose signing identity is `kdeldycke/repomatic`.

The PyPI distributions carry their own [PEP 740](https://peps.python.org/pep-0740/) attestations, visible and verifiable on the [PyPI project page](https://pypi.org/project/click-extra/).

## Man pages

The demo CLI has a [`--man`](man-page.md#reading-a-manual) option, which typesets its manual and pages it, the way `man` does:

```{code-block} shell-session
$ click-extra --man
```

To get the roff source instead, ask for the `man` rendering of `--help-format`:

```{code-block} shell-session
$ click-extra --help-format man
```

The full command tree is also pre-rendered as static `.1` files:

- Bundled with the latest release as [`click-extra-manpages.tar.gz`](https://github.com/kdeldycke/click-extra/releases/latest/download/click-extra-manpages.tar.gz). Extract it, then copy the `.1` files of its `man/` folder to `${MANPATH%%:*}/man1/` (typically `/usr/local/share/man/man1/`).
- Rendered as HTML pages on the documentation site, listed in the [man page index](man-page.md#index).

Packagers can regenerate them from source as part of their build phase:

```{code-block} shell-session
$ click-extra wrap --help-format man --output-dir /usr/share/man/man1/ -- click_extra.cli:demo
```

The generator honors `SOURCE_DATE_EPOCH` for reproducible builds. See [shipping a manual](man-page.md#shipping-a-manual) for the other invocation forms.

(extra-dependencies)=

## Extra dependencies

By default, Click Extra reads the [configuration formats enabled by default](config-formats.md) and renders all standard [table formats](table.md#table-formats). Optional extras unlock additional features:

````{list-table}
:header-rows: 1
:widths: 10 40 50
* - Extra
  - Install command
  - Unlocks
* - `hjson`
  - ```{code-block} shell-session
    $ uv pip install 'click-extra[hjson]'
    ```
  - - [HJSON](config-formats.md#hjson) config files: `--config app.hjson`
    - [`hjson` table format](table.md#table-formats): `--table-format hjson`
* - `json5`
  - ```{code-block} shell-session
    $ uv pip install 'click-extra[json5]'
    ```
  - - [JSON5](config-formats.md#json5) config files: `--config app.json5`
* - `toml`
  - ```{code-block} shell-session
    $ uv pip install 'click-extra[toml]'
    ```
  - - [`toml` table format](table.md#table-formats): `--table-format toml`
    - [TOML export](config.md#exporting-the-configuration): `--export-config toml`
* - `yaml`
  - ```{code-block} shell-session
    $ uv pip install 'click-extra[yaml]'
    ```
  - - [YAML](config-formats.md#yaml) config files: `--config app.yaml`
    - [`yaml` table format](table.md#table-formats): `--table-format yaml`
* - `carapace`
  - ```{code-block} shell-session
    $ uv pip install 'click-extra[carapace]'
    ```
  - - [Carapace completion spec export](carapace.md): `wrap --help-format carapace`
* - `mkdocs`
  - ```{code-block} shell-session
    $ uv pip install 'click-extra[mkdocs]'
    ```
  - - [ANSI color rendering](mkdocs.md) in MkDocs code blocks
* - `pygments`
  - ```{code-block} shell-session
    $ uv pip install 'click-extra[pygments]'
    ```
  - - [ANSI-capable formatter, filter and lexers](pygments.md) for Pygments
* - `sphinx`
  - ```{code-block} shell-session
    $ uv pip install 'click-extra[sphinx]'
    ```
  - - [`click:source` and `click:run` directives](sphinx.md) for live CLI documentation
* - `pytest`
  - ```{code-block} shell-session
    $ uv pip install 'click-extra[pytest]'
    ```
  - - [Fixtures and utilities](pytest.md) for testing Click CLIs
````

````{tip}
Install all extras at once with:

```{code-block} shell-session
$ uv pip install 'click-extra[all]'
```
````
