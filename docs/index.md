---
hide-toc: true
---

```{include} ../readme.md
```

% XXX Furo doesn't support icons in toctree entries natively.
% CSS workaround in _static/custom.css, see: https://github.com/pradyunsg/furo/discussions/921

```{toctree}
:maxdepth: 2
:hidden:
install
tutorial
```

```{toctree}
:caption: The click-extra CLI
:maxdepth: 2
:hidden:
cli
wrap
binaries
```

```{toctree}
:caption: Building a CLI
:maxdepth: 2
:hidden:
commands
decorators
types
context
multicall
```

```{toctree}
:caption: Configuration
:maxdepth: 2
:hidden:
config
envvar
```

```{toctree}
:caption: Colors and output
:maxdepth: 2
:hidden:
colorize
theme
styling
table
spinner
```

```{toctree}
:caption: Runtime behavior
:maxdepth: 2
:hidden:
logging
execution
version
telemetry
```

```{toctree}
:caption: Introspection and export
:maxdepth: 2
:hidden:
parameters
machine-readable
tree
carapace
```

```{toctree}
:caption: Testing
:maxdepth: 2
:hidden:
testing
pytest
test-suite
```

```{toctree}
:caption: Documentation tooling
:maxdepth: 2
:hidden:
screenshots
snippets
man-page
sphinx
mkdocs
myst-docstrings
pygments
```

```{toctree}
:caption: Comparisons
:maxdepth: 2
:hidden:
typer
benchmark
```

```{toctree}
:caption: Development
:maxdepth: 2
:hidden:
contributing
packaging
API <click_extra>
tests
genindex
modindex
changelog
upstream
todolist
code-of-conduct
license
GitHub repository <https://github.com/kdeldycke/click-extra>
Funding <https://github.com/sponsors/kdeldycke>
```
