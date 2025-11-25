# {octicon}`download` Installation

## Demo application

You can try Click Extra right now in your terminal, without installing any dependency or virtual env [thanks to `uvx`](https://docs.astral.sh/uv/guides/tools/):

`````{tab-set}
````{tab-item} Latest version
```shell-session
$ uvx -- click-extra
```
````

````{tab-item} Specific version
```shell-session
$ uvx -- click-extra@7.0.0
```
````

````{tab-item} Development version
```shell-session
$ uvx --from git+https://github.com/kdeldycke/click-extra -- click-extra
```
````
`````

This will download `click-extra`, the package, and run `click-extra`, a demo CLI application included in the package.

The `click-extra` demo application showcases various features of Click Extra, such as enhanced help formatting, colored output, and more.

So by default it will display the help message of the demo application:

```{code-block} shell-session
$ uvx -- click-extra
Installed 16 packages in 14ms
Usage: click-extra [OPTIONS] COMMAND [ARGS]...
```

Which is the same as running it with the `--help` option:

```{code-block} shell-session
$ uvx -- click-extra --help
Installed 16 packages in 14ms
Usage: click-extra [OPTIONS] COMMAND [ARGS]...
```

And so you can explore the various possibilities of the demo application, like showing the current version:

```{code-block} shell-session
$ uvx -- click-extra --help
Installed 16 packages in 14ms
Click Extra Demo Application Version 7.0.0
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
'7.1.1'
>>>
```

## With `pip`

This package is [available on PyPi](https://pypi.python.org/pypi/click-extra), so you can install the latest stable release and its dependencies with a simple `pip` call:

```{code-block} shell-session
$ pip install click-extra
```

See also [pip installation instructions](https://pip.pypa.io/en/stable/installing/).

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

Register new [`click:example` and `click:run` directives](sphinx.md):

```{code-block} shell-session
$ pip install click-extra[sphinx]
```

### For Pytest

Activate new [fixtures and utilities](pytest.md) for testing Click CLIs:

```{code-block} shell-session
$ pip install click-extra[pytest]
```