# {octicon}`download` Installation

```{sidebar}
[![Packaging status](https://repology.org/badge/vertical-allrepos/python%3Aclick-extra.svg)](https://repology.org/project/python%3Aclick-extra/versions)
```

Click Extra is [distributed on PyPi](https://pypi.org/project/click-extra/).

So you can install the latest stable release with your favorite package manager [like `pip`](https://pip.pypa.io):

```{code-block} shell-session
$ pip install click-extra
```

## Demo CLI

You can try Click Extra right now in your terminal, without installing any dependency or virtual env [thanks to `uvx`](https://docs.astral.sh/uv/guides/tools/):

`````{tab-set}
````{tab-item} Latest version
```shell-session
$ uvx --from click-extra -- click-extra-demo
```
````

````{tab-item} Specific version
```shell-session
$ uvx --from click-extra@7.2.0 -- click-extra-demo
```
````

````{tab-item} Development version
```shell-session
$ uvx --from git+https://github.com/kdeldycke/click-extra -- click-extra-demo
```
````

````{tab-item} Local version
```shell-session
$ uvx --from file:///Users/me/code/click-extra -- click-extra-demo
```
````
`````

This will download `click-extra` (the package), and run `click-extra-demo`, a demo CLI included in the package.

The `click-extra-demo` CLI showcases various features of Click Extra, such as enhanced help formatting, colored output, and more.

By default it will display the help message of the demo application:

```{code-block} shell-session
$ uvx --from click-extra -- click-extra-demo
Installed 16 packages in 14ms
Usage: click-extra [OPTIONS] COMMAND [ARGS]...
```

And so you can explore the various possibilities of the demo application, like showing the current version:

```{code-block} shell-session
$ uvx --from click-extra -- click-extra-demo --version
Installed 16 packages in 14ms
demo, version 7.2.0
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

### Configuration file formats

- [YAML configuration files](config.md#yaml) support:

  ```{code-block} shell-session
  $ pip install click-extra[yaml]
  ```

- [XML configuration files](config.md#xml) support:

  ```{code-block} shell-session
  $ pip install click-extra[xml]
  ```

- [JSON5 configuration files](config.md#json5) support:

  ```{code-block} shell-session
  $ pip install click-extra[json5]
  ```

- [JSONC configuration files](config.md#jsonc) support:

  ```{code-block} shell-session
  $ pip install click-extra[jsonc]
  ```

- [HJSON configuration files](config.md#hjson) support:

  ```{code-block} shell-session
  $ pip install click-extra[hjson]
  ```

### For Pygments

Register new [ANSI-capable formatter, filter and lexers](pygments.md):

```{code-block} shell-session
$ pip install click-extra[pygments]
```

### For Sphinx

Register new [`click:source` and `click:run` directives](sphinx.md):

```{code-block} shell-session
$ pip install click-extra[sphinx]
```

### For Pytest

Activate new [fixtures and utilities](pytest.md) for testing Click CLIs:

```{code-block} shell-session
$ pip install click-extra[pytest]
```