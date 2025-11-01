# {octicon}`download` Installation

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