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

For additional features, and to facilitate integration of Click CLIs with third-party tools, you may need to install extra dependencies:

- [For Pygments](pygments.md):

  ```{code-block} shell-session
  $ pip install click-extra[pygments]
  ```

- [For Sphinx](sphinx.md):

  ```{code-block} shell-session
  $ pip install click-extra[sphinx]
  ```

- [For Pytest](pytest.md):

  ```{code-block} shell-session
  $ pip install click-extra[pytest]
  ```