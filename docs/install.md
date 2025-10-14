# {octicon}`download` Installation

## With `pip`

This package is
[available on PyPi](https://pypi.python.org/pypi/click-extra), so you
can install the latest stable release and its dependencies with a simple `pip`
call:

```{code-block} shell-session
$ pip install click-extra
```

See also
[pip installation instructions](https://pip.pypa.io/en/stable/installing/).

## Main dependencies

This is a graph of the default, main dependencies of the Python package:

```mermaid assets/dependencies.mmd
:align: center
```

## Extra dependencies

For additional features, you may need to install extra dependencies:

- To add support for [YAML configuration files](config.md#yaml):

  ```{code-block} shell-session
  $ pip install click-extra[yaml]
  ```

- To add support for [XML configuration files](config.md#xml):

  ```{code-block} shell-session
  $ pip install click-extra[xml]
  ```

- To add support for [JSON5 configuration files](config.md#json5):

  ```{code-block} shell-session
  $ pip install click-extra[json5]
  ```

- To add support for [JSONC configuration files](config.md#jsonc):

  ```{code-block} shell-session
  $ pip install click-extra[jsonc]
  ```

- To add support for [HJSON configuration files](config.md#hjson):

  ```{code-block} shell-session
  $ pip install click-extra[hjson]
  ```

- To register new [ANSI-capable formatter, filter and lexers for Pygments](pygments.md):

  ```{code-block} shell-session
  $ pip install click-extra[pygments]
  ```

- To add new [`click:example` and `click:run` directives for Sphinx](sphinx.md):

  ```{code-block} shell-session
  $ pip install click-extra[sphinx]
  ```

- To use [fixtures and utilities for testing Click CLIs with Pytest](pytest.md):

  ```{code-block} shell-session
  $ pip install click-extra[pytest]
  ```