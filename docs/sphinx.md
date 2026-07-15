# {octicon}`book` Sphinx

[Sphinx](https://www.sphinx-doc.org) is the best way to document your Python CLI. Click Extra provides several utilities to improve the quality of life of maintainers.

````{important}
For these helpers to work, you need to install `click_extra`'s additional dependencies from the `sphinx` extra group:

```{code-block} shell-session
$ pip install click_extra[sphinx]
```
````

```{seealso}
To capture a CLI's output as a static image for a README, slide, or any surface that cannot run Sphinx, see [CLI screenshots](screenshots.md).
```

## Setup

Once [Click Extra is installed](install.md), you can enable its [extensions](https://www.sphinx-doc.org/en/master/usage/configuration.html#confval-extensions) in your Sphinx's `conf.py`:

```{code-block} python
:caption: `conf.py`
:emphasize-lines: 3
extensions = [
    ...
    "click_extra.sphinx",
]
```

This unlocks the always-on features: the ANSI-capable Pygments HTML formatter and the GitHub-flavored alert (`> [!NOTE]`, `> [!WARNING]`, ...) → MyST/reST admonition converter. The `click:*` and `python:*` directive families are disabled by default and require an explicit opt-in described below.

```{danger}
**Build-time code execution.** Every `click:*` and `python:*` directive runs its body with the same privileges as the Sphinx process: full filesystem access, full network access, and full access to the build environment's secrets (`GITHUB_TOKEN`, `READTHEDOCS_TOKEN`, etc.). The runner namespace is unrestricted: there is no sandbox.

This is intentional: build-time execution is the whole point of those directives. But it means the same trust boundary I'd apply to a `Makefile` or `conftest.py` applies here:

- Only run `sphinx-build` against source I trust.
- Do not auto-build documentation from unverified pull requests in CI without an isolated, secret-free environment.
- Treat any `print` call inside `python:render*` whose output incorporates untrusted data as a content-injection sink. reST in particular allows `.. raw:: html` and `.. include:: /path/to/file`, both of which can read local files or inject HTML into the rendered page.

The risk profile is identical to other build-time-execution extensions like `jupyter-sphinx`, `myst-nb`, and `sphinx-exec-code`.
```

````{important}
**Opt-in required.** Both directive families are **disabled by default**. A project that adds `click_extra.sphinx` to its `extensions` list gets the always-on features automatically, but does *not* gain build-time code execution unless the maintainer explicitly turns it on. Add this to `conf.py`:

```python
click_extra_enable_exec_directives = True
```

Without it, `click:source`, `click:run`, `python:source`, `python:run`, `python:render`, `python:render-myst`, and `python:render-rst` are not registered with Sphinx. Documents that reference them get an "Unknown directive" warning and the directive body is never executed. This way a transitive import of `click_extra.sphinx`, or a maintainer who installs the extension purely for ANSI-aware code blocks, cannot be tricked into running attacker-supplied Python by a doc-only pull request.
````

```{tip}
I recommend using one of these themes, which works well with Click Extra:

- ![GitHub stars](https://img.shields.io/github/stars/pradyunsg/furo?label=%E2%AD%90&style=flat-square) [Furo](https://github.com/pradyunsg/furo) - Which has been [fixed to support Click Extra](https://github.com/pradyunsg/furo/pull/657) as of `2023.05.20`.
- ![GitHub stars](https://img.shields.io/github/stars/lepture/shibuya?label=%E2%AD%90&style=flat-square) [Shibuya](https://github.com/lepture/shibuya) - Which is [explicitly supporting Click Extra](https://shibuya.lepture.com/extensions/click-extra/) as of `2025.9.22`.
```

```{seealso}
Using MkDocs instead of Sphinx? See the [MkDocs integration](mkdocs.md).
```

## `click:*` directives

Click Extra adds two new directives:

| Directive      | Purpose                                                                                            |
| -------------- | -------------------------------------------------------------------------------------------------- |
| `click:source` | Define and show the source code of a Click CLI in Sphinx.                                          |
| `click:run`    | Invoke the CLI defined above, and display the results as if it was executed in a terminal session. |

Thanks to these, you can directly demonstrate the usage of your CLI in your documentation. You no longer have to maintain screenshots of you CLIs. Or copy and paste their outputs to keep them in sync with the latest revision. Click Extra will do that job for you.

These directives supports both [MyST Markdown](https://myst-parser.readthedocs.io) and [reStructuredText](https://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html) syntax.

### Usage

Here is how to define a simple Click-based CLI with the `click:source` directive:

``````{tab-set}
`````{tab-item} MyST Markdown
:sync: myst
````{code-block} markdown
:emphasize-lines: 1
```{click:source}
from click_extra import echo, command, option, style

@command
@option("--name", prompt="Your name", help="The person to greet.")
def hello_world(name):
    """Simple program that greets NAME."""
    echo(f"Hello, {style(name, fg='red')}!")
```
````
`````

`````{tab-item} reStructuredText
:sync: rst
```{code-block} rst
:emphasize-lines: 1
.. click:source::

    from click_extra import echo, command, option, style

    @command
    @option("--name", prompt="Your name", help="The person to greet.")
    def hello_world(name):
        """Simple program that greets NAME."""
        echo(f"Hello, {style(name, fg='red')}!")
```
`````
``````

After defining the CLI source code in the `click:source` directive above, you can invoke it with the `click:run` directive.

The `click:run` directive expects a Python code block that uses the `invoke` function. This function is specifically designed to run Click-based CLIs and handle their execution and output.

Here is how we invoke our example with a `--help` option:

``````{tab-set}
`````{tab-item} MyST Markdown
:sync: myst
````{code-block} markdown
:emphasize-lines: 1
```{click:run}
invoke(hello_world, args=["--help"])
```
````
`````

`````{tab-item} reStructuredText
:sync: rst
```{code-block} rst
:emphasize-lines: 1
.. click:run::

    invoke(hello_world, args=["--help"])
```
`````
``````

Placed in your Sphinx documentation, the two blocks above renders to:

```{click:source}
from click_extra import echo, command, option, style

@command
@option("--name", prompt="Your name", help="The person to greet.")
def hello_world(name):
    """Simple program that greets NAME."""
    echo(f"Hello, {style(name, fg='red')}!")
```

```{click:run}
from textwrap import dedent
result = invoke(hello_world, args=["--help"])
print(repr(result.stdout))
assert result.stdout.startswith(dedent(
    """\
    \x1b[94m\x1b[4mUsage:\x1b[0m \x1b[97m\x1b[1mhello-world\x1b[0m \x1b[36m\x1b[2m\x1b[3m[OPTIONS]\x1b[0m

      Simple program that greets NAME.

    \x1b[94m\x1b[4mOptions:\x1b[0m
      \x1b[36m\x1b[1m--name\x1b[0m \x1b[36m\x1b[2m\x1b[3mTEXT\x1b[0m                  The person to greet.
      \x1b[36m\x1b[1m--time\x1b[0m / \x1b[36m\x1b[1m--no-time\x1b[0m           Measure and print elapsed execution time."""
))
```

This is perfect for documentation, as it shows both the source code of the CLI and its results.

Notice how the CLI code is properly rendered as a Python code block with syntax highlighting. And how the invocation of that CLI renders into a terminal session with ANSI coloring of output.

You can then invoke that CLI again with its `--name` option:

``````{tab-set}
`````{tab-item} MyST Markdown
:sync: myst
````{code-block} markdown
:emphasize-lines: 2
```{click:run}
invoke(hello_world, args=["--name", "Joe"])
```
````
`````

`````{tab-item} reStructuredText
:sync: rst
```{code-block} rst
:emphasize-lines: 3
.. click:run::

    invoke(hello_world, args=["--name", "Joe"])
```
`````
``````

Which renders in Sphinx as if it was executed in a terminal code block:

```{click:run}
result = invoke(hello_world, args=["--name", "Joe"])
assert "Hello, " in result.output
assert "Joe" in result.output
```

```{hint}
`click:source` and `click:run` directives works well with standard vanilla `click`-based CLIs.

In the example above, we choose to import our CLI primitives from the `click-extra` module instead, to demonstrate the coloring of terminal session outputs, as `click-extra` provides [fancy coloring of help screens](colorize.md) by default.
```

```{tip}
Need to run arbitrary Python that isn't a Click CLI? See [`python:run`](#python-directives) and the rest of the `python:*` family for general-purpose build-time execution and live-content generation.
```

```{seealso}
Click Extra's own documentation extensively use `click:source` and `click:run` directives. [Look around in its Markdown source files](https://github.com/kdeldycke/click-extra/tree/main/docs) for advanced examples and inspiration.
```

### Options

You can pass options to both the `click:source` and `click:run` directives to customize their behavior:

| Option                                                                                                                                         | Description                                                                                                                                                        | Example                              |
| ---------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------ |
| [`:linenos:`](https://www.sphinx-doc.org/en/master/usage/restructuredtext/directives.html#directive-option-code-block-linenos)                 | Display line numbers.                                                                                                                                              | `:linenos:`                          |
| [`:lineno-start:`](https://www.sphinx-doc.org/en/master/usage/restructuredtext/directives.html#directive-option-code-block-lineno-start)       | Specify the starting line number.                                                                                                                                  | `:lineno-start: 10`                  |
| [`:emphasize-lines:`](https://www.sphinx-doc.org/en/master/usage/restructuredtext/directives.html#directive-option-code-block-emphasize-lines) | Highlight specific lines in the source block.                                                                                                                      | `:emphasize-lines: 2,4-6`            |
| `:emphasize-result-lines:`                                                                                                                     | Highlight specific lines in the captured output block. Same syntax as `:emphasize-lines:`. Only applies to `click:run`; ignored by `click:source`.                 | `:emphasize-result-lines: 1,3`       |
| [`:force:`](https://www.sphinx-doc.org/en/master/usage/restructuredtext/directives.html#directive-option-code-block-force)                     | Ignore minor errors on highlighting.                                                                                                                               | `:force:`                            |
| [`:caption:`](https://www.sphinx-doc.org/en/master/usage/restructuredtext/directives.html#directive-option-code-block-caption)                 | Set a caption for the code block.                                                                                                                                  | `:caption: My Code Example`          |
| [`:name:`](https://www.sphinx-doc.org/en/master/usage/restructuredtext/directives.html#directive-option-code-block-name)                       | Set a name for the code block (useful for cross-referencing).                                                                                                      | `:name: example-1`                   |
| [`:class:`](https://www.sphinx-doc.org/en/master/usage/restructuredtext/directives.html#directive-option-code-block-class)                     | Set a CSS class for the code block.                                                                                                                                | `:class: highlight`                  |
| [`:dedent:`](https://www.sphinx-doc.org/en/master/usage/restructuredtext/directives.html#directive-option-code-block-dedent)                   | Specify the number of spaces to remove from the beginning of each line.                                                                                            | `:dedent: 4`                         |
| [`:language:`](https://www.sphinx-doc.org/en/master/usage/restructuredtext/directives.html#directive-option-literalinclude-language)           | Specify the programming language for syntax highlighting. This can be used as an alternative to [passing the language as an argument](#syntax-highlight-language). | `:language: sql`                     |
| `:show-source:`/`:hide-source:`                                                                                                                | Flags to force the source code within the directive to be rendered or not.                                                                                         | `:show-source:` or `:hide-source:`   |
| `:show-results:`/`:hide-results:`                                                                                                              | Flags to force the results of the CLI invocation to be rendered or not. Only applies to `click:run`. Is silently ignored in `click:source`.                        | `:show-results:` or `:hide-results:` |
| `:show-prompt:`/`:hide-prompt:`                                                                                                                | TODO                                                                                                                                                               | TODO                                 |

#### `code-block` options

Because the `click:source` and `click:run` directives produces code blocks, they inherits the [same options as the Sphinx `code-block` directive](https://www.sphinx-doc.org/en/master/usage/restructuredtext/directives.html#directive-code-block).

For example, you can highlight some lines of with the `:emphasize-lines:` option, display line numbers with the `:linenos:` option, and set a caption with the `:caption:` option:

``````{tab-set}
`````{tab-item} MyST Markdown
:sync: myst
````{code-block} markdown
:emphasize-lines: 2-4
```{click:source}
:caption: A magnificent ✨ Hello World CLI!
:linenos:
:emphasize-lines: 4,7
from click_extra import echo, command, option, style

@command
@option("--name", prompt="Your name", help="The person to greet.")
def hello_world(name):
    """Simple program that greets NAME."""
    echo(f"Hello, {style(name, fg='red')}!")
```
````
`````

`````{tab-item} reStructuredText
:sync: rst
```{code-block} rst
:emphasize-lines: 2-4
.. click:source::
   :caption: A magnificent ✨ Hello World CLI!
   :linenos:
   :emphasize-lines: 4,7

   from click_extra import echo, command, option, style

   @command
   @option("--name", prompt="Your name", help="The person to greet.")
   def hello_world(name):
       """Simple program that greets NAME."""
       echo(f"Hello, {style(name, fg='red')}!")
```
`````
``````

Which renders to:

```{click:source}
:caption: A magnificent ✨ Hello World CLI!
:linenos:
:emphasize-lines: 4,7
from click_extra import echo, command, option, style

@command
@option("--name", prompt="Your name", help="The person to greet.")
def hello_world(name):
    """Simple program that greets NAME."""
    echo(f"Hello, {style(name, fg='red')}!")
```

#### Display options

You can also control the display of the source code and the results of the CLI invocation with the `:show-source:`/`:hide-source:` and `:show-results:`/`:hide-results:` options.

By default:

- `click:source` displays the source code of the CLI. Because its content is not executed, no results are displayed. This is equivalent to having both `:show-source:` and `:hide-results:` options.
- `click:run` displays the results of the CLI invocation, but does not display the source code. This is equivalent to having both `:hide-source:` and `:show-results:` options.

But you can override this behavior by explicitly setting the options. Let's say [you only want to display the result](https://github.com/kdeldycke/click-extra/issues/719) of the CLI invocation, without showing the source code defining that CLI. Then you can add `:hide-source:` to the `click:source` directive:

``````{tab-set}
`````{tab-item} MyST Markdown
:sync: myst
````{code-block} markdown
:emphasize-lines: 2
```{click:source}
:hide-source:
from click_extra import echo, command, style

@command
def simple_print():
    echo(f"Just a {style('string', fg='blue')} to print.")
```

```{click:run}
invoke(simple_print)
```
````
`````

`````{tab-item} reStructuredText
:sync: rst
```{code-block} rst
:emphasize-lines: 2
.. click:source::
   :hide-source:

   from click_extra import echo, command, style

   @command
   def simple_print():
       echo(f"Just a {style('string', fg='blue')} to print.")

.. click:run::

   invoke(simple_print)
```
`````
``````

Which only renders the `click:run` directive, as the `click:source` doesn't display anything:

```{click:source}
:hide-source:
from click_extra import echo, command, style

@command
def simple_print():
    echo(f"Just a {style('string', fg='blue')} to print.")
```

```{click:run}
invoke(simple_print)
```

If you want to display the source code used to invoke the CLI in addition to its results, you can add the `:show-source:` option to the `click:run` directive:

``````{tab-set}
`````{tab-item} MyST Markdown
:sync: myst
````{code-block} markdown
:emphasize-lines: 2
```{click:run}
:show-source:
result = invoke(simple_print)

# Some inline tests.
assert result.exit_code == 0, "CLI execution failed"
assert not result.stderr, "Found error messages in <stderr>"
```
````
`````

`````{tab-item} reStructuredText
:sync: rst
```{code-block} rst
:emphasize-lines: 2
.. click:run::
   :show-source:

   result = invoke(simple_print)

   # Some inline tests.
   assert result.exit_code == 0, "CLI execution failed"
   assert not result.stderr, "Found error messages in <stderr>"
```
`````
``````

In this particular mode the `click:run` produced two code blocks, one for the source code, and one for the results of the invocation:

```{click:run}
:show-source:
result = invoke(simple_print)

# Some inline tests.
assert result.exit_code == 0, "CLI execution failed"
assert not result.stderr, "Found error messages in <stderr>"
```

```{caution}
`:show-results:`/`:hide-results:` options have no effect on the `click:source` directive and will be ignored. That's because this directive does not execute the CLI: it only displays its source code.
```

### Standalone `click:run` blocks

You can also use the `click:run` directive without a preceding `click:source` block. This is useful when you want to demonstrate the usage of a CLI defined elsewhere, for example in your package's source code.

In the example below, we import the `click_extra.cli.demo` function, which is defined in the [`click_extra/cli.py`](https://github.com/kdeldycke/click-extra/blob/main/click_extra/cli.py) source file. There is no need to redefine the CLI in a `click:source` block beforehand:

``````{tab-set}
`````{tab-item} MyST Markdown
:sync: myst
````{code-block} markdown
```{click:run}
from click_extra.cli import demo
invoke(demo, args=["--version"])
```
````
`````

`````{tab-item} reStructuredText
:sync: rst
```{code-block} rst
.. click:run::

   from click_extra.cli import demo
   invoke(demo, args=["--version"])
```
`````
``````

And the execution of that CLI renders just fine:

```{click:run}
from click_extra.cli import demo
invoke(demo, args=["--version"])
```

### Capture mode

`click:run` and `click:tree` execute the documented CLI through Click's test runner. On Click `8.4` and later, the output is captured at the file-descriptor level (Click's `capture="fd"` mode), so a CLI that writes through its `stdout` descriptor, such as one re-opening `sys.stdout.fileno()` to force UTF-8 output, renders normally instead of aborting the build with `io.UnsupportedOperation`.

Select the capture mode with the `click_extra_run_capture` value in `conf.py`:

```{code-block} python
:caption: `conf.py`
click_extra_run_capture = "fd"  # "fd" (default) or "sys"
```

Set it to `"sys"` to use Click's legacy in-memory capture, which exposes no file descriptor. On Click releases older than `8.4` the value is ignored, as the `capture` parameter does not exist.

### Inline tests

The `click:run` directive can also be used to embed tests in your documentation.

You can write tests in your documentation, and they will be executed at build time. This allows you to catch regressions early, and ensure that your documentation is always up-to-date with the latest version of your CLI, in the spirit of [`doctest`](https://docs.python.org/3/library/doctest.html) and [Docs as Tests](https://www.docsastests.com/docs-as-tests/concept/2024/01/09/intro-docs-as-tests.html).

For example, here is a simple CLI:

``````{tab-set}
`````{tab-item} MyST Markdown
:sync: myst
````{code-block} markdown
```{click:source}
from click import echo, command

@command
def yo_cli():
    echo("Yo!")
```
````
`````

`````{tab-item} reStructuredText
:sync: rst
```{code-block} rst
.. click:source::

   from click import echo, command

   @command
   def yo_cli():
       echo("Yo!")
```
`````
``````

Let's put the code above in a `click:source` directive. And then put the following Python code into a `click:run` block:

``````{tab-set}
`````{tab-item} MyST Markdown
:sync: myst
````{code-block} markdown
:emphasize-lines: 6
```{click:run}
result = invoke(yo_cli, args=["--help"])

assert result.exit_code == 0, "CLI execution failed"
assert not result.stderr, "Found error messages in <stderr>"
assert "Usage: yo-cli [OPTIONS]" in result.stdout, "Usage line not found in help screen"
```
````
`````

`````{tab-item} reStructuredText
:sync: rst
```{code-block} rst
:emphasize-lines: 7
.. click:run::

   result = invoke(yo_cli, args=["--help"])

   assert result.exit_code == 0, "CLI execution failed"
   assert not result.stderr, "Found error messages in <stderr>"
   assert "Usage: yo-cli [OPTIONS]" in result.stdout, "Usage line not found in help screen"
```
`````
``````

See how we collect here the `result` of the `invoke` command, and separately inspect the `exit_code`, `stderr` and `stdout` of with `assert` statements.

If for any reason our CLI changes and its help screen is no longer what we expect, the test will fail and the documentation build will break with a message similar to:

```{code-block} text
:emphasize-lines: 22
Versions
========

* Platform:         darwin; (macOS-15.5-arm64-64bit)
* Python version:   3.11.11 (CPython)
* Sphinx version:   8.2.3
* Docutils version: 0.21.2
* Jinja2 version:   3.1.6
* Pygments version: 2.19.2

Loaded Extensions
=================

(...)
* myst_parser (4.0.1)
* click_extra.sphinx (5.1.0)

Traceback
=========

      File "(...)/click-extra/docs/sphinx.md:197", line 5, in <module>
    AssertionError: Usage line not found in help screen

The full traceback has been saved in:
/var/folders/gr/1frk79j52flczzs2rrpfnkl80000gn/T/sphinx-err-5l6axu9g.log
```

Having your build fails when something unexpected happens is a great signal to catch regressions early.

On the other hand, if the build succeed, the `click:run` block will render as usual with the result of the invocation:

```{click:source}
:hide-source:
from click import echo, command

@command
def yo_cli():
    echo("Yo!")
```

```{click:run}
:emphasize-lines: 2
result = invoke(yo_cli, args=["--help"])

assert result.exit_code == 0, "CLI execution failed"
assert not result.stderr, "Found error messages in <stderr>"
assert "Usage: yo-cli [OPTIONS]" in result.stdout, "Usage line not found in help screen"
```

### Syntax highlight language

By default, code blocks produced by the directives are automatically highlighted with these languages:

- `click:source`: [`python`](https://pygments.org/docs/lexers/#pygments.lexers.python.PythonLexer)
- `click:run`: [`ansi-shell-session`](pygments.md#lexer-variants)

If for any reason you want to override these defaults, you can pass the language as an optional parameter to the directive.

Let's say you have a CLI that is only printing SQL queries in its output:

```{click:source}
:emphasize-lines: 6
from click_extra import echo, command, option

@command
@option("--name")
def sql_output(name):
    sql_query = f"SELECT * FROM users WHERE name = '{name}';"
    echo(sql_query)
```

Then you can force the SQL Pygments highlighter on its output by passing the [short name of that lexer (`sql`)](https://pygments.org/docs/lexers/#pygments.lexers.sql.SqlLexer) as the first argument to the directive:

````{code-block} markdown
:emphasize-lines: 1
```{click:run} sql
invoke(sql_output, args=["--name", "Joe"])
```
````

And renders to:

```{click:run} sql
:emphasize-lines: 2
invoke(sql_output, args=["--name", "Joe"])
```

See how the output (the second line above) is now rendered with the `sql` Pygments lexer, which is more appropriate for SQL queries. But of course it also parse and renders the whole block as if it is SQL code, which mess up the rendering of the first line, as it is a shell command.

In fact, if you look at Sphinx logs, you will see that a warning has been raised because of that:

```{code-block} text
.../docs/sphinx.md:257: WARNING: Lexing literal_block "$ sql-output --name Joe\nSELECT * FROM users WHERE name = 'Joe';" as "sql" resulted in an error at token: '$'. Retrying in relaxed mode. [misc.highlighting_failure]
```

```{hint}
Alternatively, you can force syntax highlight with the `:language:` option, which takes precedence over the default language of the directive.
```

### CLI reference tree

The `click:tree` directive walks a Click command group at build time and expands into a full CLI reference page: a summary table on top, then one `--help` capture per command, nested by depth. It is meant to replace per-project hand-rolled scripts that generate the same scaffolding (a summary table, anchors, one `click:run` per command) by hand.

The required argument is a Python expression evaluated in the per-document runner namespace; it must resolve to a {py:class}`click.Command`. The optional body is Python preamble that runs in the same namespace before the expression is evaluated, so you can either rely on a prior `click:source` import or inline the import in the directive's body.

Here is a small recipe CLI to demonstrate:

```{click:source}
from click_extra import echo, command, group, option

@group()
def kitchen():
    """Manage kitchen tools and recipes."""

@kitchen.command()
@option("--minutes", type=int, default=5)
def boil(minutes):
    """Boil water for tea."""
    echo(f"Boiling for {minutes} minutes.")

@kitchen.group()
def pantry():
    """Inspect pantry contents."""

@pantry.command()
def jars():
    """List jars on the shelf."""
    echo("Olives, honey, pickles.")

@pantry.command()
@option("--fruit", default="apple")
def count(fruit):
    """Count fruits in the basket."""
    echo(f"Three {fruit}s.")
```

A single `click:tree` invocation expands into a summary table plus one `--help` capture for `kitchen`, `kitchen boil`, `kitchen pantry`, `kitchen pantry count`, and `kitchen pantry jars`:

````{code-block} markdown
```{click:tree} kitchen
:root-label: kitchen --help
```
````

Which renders as:

```{click:tree} kitchen
:root-label: kitchen --help
```

#### Tree options

| Option             | Description                                                                                                        | Default                                                                        |
| ------------------ | ------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------ |
| `:max-depth:`      | Maximum recursion depth into nested groups.                                                                        | `10`                                                                           |
| `:heading-offset:` | Shift all generated headings down by N levels. Override when the auto-detected depth is wrong for the page layout. | Surrounding section depth (root nested one level below the enclosing section). |
| `:anchor-prefix:`  | Slug prefix for every generated anchor.                                                                            | Slug of the CLI name.                                                          |
| `:label-prefix:`   | Display prefix for the command labels in the table and headings.                                                   | The CLI name.                                                                  |
| `:root-label:`     | Heading text for the root `--help` block.                                                                          | `"Help screen"`                                                                |
| `:no-table:`       | Skip the summary table.                                                                                            | Table is rendered.                                                             |
| `:no-root:`        | Skip the root `--help` block.                                                                                      | Root block is rendered.                                                        |

#### Inline import in the directive body

If the CLI lives in your package, you can skip the seed `click:source` block and import directly in the body:

````{code-block} markdown
```{click:tree} demo
from click_extra.cli import demo
```
````

The rendered output is identical to the kitchen example above: a summary table and one `--help` block per (sub)command. The only difference is where the CLI comes from: a package import instead of a preceding `click:source` block.

```{note}
`click:tree` is currently MyST-only because the expanded scaffolding uses MyST's `(label)=` anchor syntax and pipe tables. An rST equivalent would emit `.. _label:` targets and `list-table::` directives instead; it has not been implemented yet.
```

### Configuration reference

The `click:config` directive documents a CLI's [`config_schema`](config.md) at build time: a summary table linking each option to its section, then one heading per option with its docstring, type, default, and a TOML example pinned to the default value. Like `click:tree`, it replaces per-project hand-rolled generators that produce the same reference from the schema dataclass by hand.

The required argument is a Python expression evaluated in the per-document runner namespace. It accepts either a {py:class}`click.Command` whose `config_schema` is wired (the schema is pulled off its `ConfigOption`), or a schema dataclass directly. The optional body is Python preamble, same as `click:tree`.

Click Extra's own CLI declares a `config_schema`, so a single invocation documents its `[tool.click-extra]` section:

````{code-block} markdown
```{click:config} demo
from click_extra.cli import demo
```
````

Which renders as:

```{click:config} demo
from click_extra.cli import demo
```

#### Config options

| Option             | Description                                                                                                        | Default                                                                           |
| ------------------ | ------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------- |
| `:heading-offset:` | Shift all generated headings down by N levels. Override when the auto-detected depth is wrong for the page layout. | Surrounding section depth (options nested one level below the enclosing section). |
| `:section:`        | TOML table header shown in the per-option examples. An explicitly empty value suppresses the header.               | `tool.{cli-name}` when the argument is a CLI; no header for a bare schema.        |
| `:no-table:`       | Skip the summary table.                                                                                            | Table is rendered.                                                                |
| `:no-examples:`    | Skip the TOML example blocks.                                                                                      | Examples are rendered.                                                            |

Option metadata comes from the `schema_field_infos()` introspection helper, which is also part of the public API for CLIs that render their own configuration reference (a `show-config` table, say): dotted kebab-case keys, type annotations, defaults from a pristine schema instance, and attribute docstrings. Docstrings are parsed as the host document's markup, and their first paragraph doubles as the option's summary in the table.

```{caution}
Attribute docstrings are recovered from the schema's source file. A schema defined inline in a `click:source` block was born in an `exec` call, has no source file, and therefore documents its options without descriptions. Import the schema from a real module instead, as in the example above.
```

```{note}
`click:config` is currently MyST-only: place it in a `.md` document with `myst_parser` enabled. Like `click:tree`, an rST equivalent has not been implemented yet.
```

## `python:*` directives

Click Extra also adds five general-purpose Python execution directives, registered under a separate `python` domain (distinct from Sphinx's built-in `py` domain for documenting API objects):

| Directive            | Purpose                                                                                                                                                                                                                              |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `python:source`      | Define and show a Python source block, executed silently. Use it to teach readers what a snippet looks like and to seed imports/variables for follow-up blocks.                                                                      |
| `python:run`         | Execute a Python block and render its captured `stdout` in a code block. Output language defaults to `text`; override with `:language:` for structured output (`json`, `html`, `yaml`, etc.).                                        |
| `python:render`      | Execute a Python block and parse its captured `stdout` as **live document content** using the host file's parser. Generated tables, headings, admonitions, and cross-references become first-class document nodes, not a code block. |
| `python:render-myst` | Execute a Python block and parse its captured `stdout` as MyST, regardless of host. Lets a `.rst` document embed MyST-generated content.                                                                                             |
| `python:render-rst`  | Execute a Python block and parse its captured `stdout` as reST, regardless of host. Lets a `.md` document embed reST-generated content.                                                                                              |

These complement the Click directives: `click:run` is for showing simulated CLI sessions; `python:run` is for showing arbitrary Python output; the `python:render*` family is for **inline content generation**, replacing the regenerator-script + marker-region pattern many projects use to keep auto-tables in sync.

```{hint}
This project eats its own dog food: the [ANSI lexer table in `pygments.md`](pygments.md#lexer-variants) is rendered live at build time by an inline [`python:render`](#python-directives) block that imports `LEXER_MAP` and prints a Markdown table. Read [the exact source lines on GitHub](https://github.com/kdeldycke/click-extra/blob/0cac18fdaa8770ac03a33a8e8969c2556fde674e/docs/pygments.md?plain=1#L243-L264) for a real-world example of replacing a regenerator script with a one-block inline build-time computation.
```

### Pick the right `render`

| Directive            | Parser used for captured stdout           | When to use                                    |
| -------------------- | ----------------------------------------- | ---------------------------------------------- |
| `python:render`      | Whatever parser owns the host source file | Generated markup matches the host file format. |
| `python:render-myst` | MyST, regardless of host                  | Embed MyST-generated content in a `.rst` host. |
| `python:render-rst`  | reST, regardless of host                  | Embed reST-generated content in a `.md` host.  |

`python:render` reuses the host state machine, so cross-references and Sphinx-aware roles resolve naturally. The forced-parser variants (`render-myst`, `render-rst`) parse into a fresh sub-document and graft the resulting nodes back into the page.

### `python:render`: docs as code

```{tip}
The strongest use case is replacing a `docs/docs_update.py` script that walks an in-process registry, renders Markdown, and rewrites a region of a `.md` file between `<!-- start -->` / `<!-- end -->` markers. With `python:render`, the same code lives inline in the page itself and runs at build time. The rendered HTML is always current because the source-of-truth registry is queried on every build.
```

Render the live list of Python's built-in modules as a Markdown table, executed by Sphinx at build time:

``````{tab-set}
`````{tab-item} MyST Markdown
:sync: myst
````{code-block} markdown
```{python:render}
import sys
print("| Module | Type |")
print("|--------|------|")
for name in sorted(sys.builtin_module_names)[:5]:
    print(f"| `{name}` | built-in |")
```
````
`````

`````{tab-item} reStructuredText
:sync: rst
```{code-block} rst
.. python:render::

    import sys
    print("| Module | Type |")
    print("|--------|------|")
    for name in sorted(sys.builtin_module_names)[:5]:
        print(f"| `{name}` | built-in |")
```
`````
``````

Renders as a real HTML `<table>` (output truncated to 5 entries):

```{python:render}
import sys

print("| Module | Type |")
print("|--------|------|")
for name in sorted(sys.builtin_module_names)[:5]:
    print(f"| `{name}` | built-in |")
```

### Cross-format rendering

`python:render-myst` and `python:render-rst` let a host file embed content authored in the other markup. This page is MyST, but the following block prints reST and parses it as such:

```{python:render-rst}
print(".. note::")
print()
print("   A persimmon must be very ripe to eat raw.")
```

In an rST host, `python:render-myst` provides the symmetric path: print MyST and have it parsed as MyST regardless of the surrounding `.rst` file.

### Namespace persistence

Like `click:source` / `click:run`, the Python runner holds a per-document namespace, so consecutive blocks share imports and variables:

```{python:source}
from textwrap import dedent

GREETING = "hello, sphinx"
```

```{python:run}
print(dedent(GREETING).upper())
```

The `python:source` block ran silently to seed `dedent` and `GREETING`; the subsequent `python:run` referenced both.

### Shared options

`python:run` and the `python:render*` directives accept the same option spec as `click:run`. Defaults match: results shown, source hidden, so an inline `import` line in a `python:run` block runs silently and stays out of the rendered output.

| Option                              | Effect                                                                   | Default |
| ----------------------------------- | ------------------------------------------------------------------------ | ------- |
| `:show-source:` / `:hide-source:`   | Render the directive's source block, or omit it.                         | hidden  |
| `:show-results:` / `:hide-results:` | Render the captured output block, or omit it.                            | shown   |
| `:linenos:`                         | Display line numbers in both blocks.                                     | off     |
| `:lineno-start:`                    | Starting line number when `:linenos:` is on. Applies to source.          | 1       |
| `:emphasize-lines:`                 | Highlight lines in the source block. Syntax: `1,3-5`.                    | none    |
| `:emphasize-result-lines:`          | Highlight lines in the result block. Same syntax as `:emphasize-lines:`. | none    |
| `:language:`                        | Override the Pygments lexer used to render the result block.             | `text`  |
| `:caption:`                         | Set a caption on the rendered code block.                                | none    |
| `:name:`                            | Anchor name for cross-referencing.                                       | none    |
| `:class:`                           | Extra CSS class on the rendered block.                                   | none    |
| `:dedent:`                          | Strip N leading spaces from every line of the source.                    | 0       |
| `:force:`                           | Suppress minor highlighting errors.                                      | off     |

```{seealso}
Some related projects for build-time Python execution:

- [`sphinx-exec-code`](https://sphinx-exec-code.readthedocs.io/): single `exec_code` directive; supports external `:filename:` and inline `#hide:` / `#skip:` markers; fresh interpreter per block.
- [`jupyter-sphinx`](https://jupyter-sphinx.readthedocs.io/): runs Python in a real Jupyter kernel; rich outputs (matplotlib, widgets).
- [`MyST-NB`](https://myst-nb.readthedocs.io/): executes `.ipynb` and code-cell `.md`; `glue` / `eval` roles inject computed values into prose.
- [`sphinx-jinja`](https://github.com/tardyp/sphinx-jinja): Jinja2 templates with Python context, output parsed as reST/MyST. Closest analogue for the docs-as-code pattern without `exec`.
```

(matrix-directives)=

## The `matrix` directive

The `matrix` directive renders a package's release compatibility matrix for a given axis. Unlike the `click:*` and `python:*` families, it runs a fixed generator rather than user-supplied Python, so it carries no execution surface and is registered without the `click_extra_enable_exec_directives` opt-in. Two axes are built in:

- `{matrix} python` renders the interpreter matrix (release ranges × Python versions).
- `{matrix} <distribution>` (like `{matrix} click`) renders a dependency matrix (release ranges × that dependency's versions).

The generated table lives **in the source**, kept current by the offline updater described below, so it shows up in the raw Markdown (and in pull-request diffs) and the HTML build needs no git access (it works on a shallow clone). There are two ways to write it, both refreshed by the same `refresh-directives` command:

- **A directive fence**, ```` ```{matrix} python ```` … ```` ``` ````, rendered by Sphinx. Simplest on a docs-only page, but GitHub shows the fenced block as a code block. An empty fence falls back to generating from the git tags at build time, so a freshly authored block renders before its first refresh.
- **A comment marker region**, `<!-- matrix python -->` … `<!-- matrix-end -->`, with the raw table between the markers. Being plain Markdown, it renders as a real table on **GitHub** and PyPI as well as in Sphinx. Options go in the start comment as `key=value` pairs and bare flags: `<!-- matrix click show-spec -->`. `install.md`'s tables use this form so they render everywhere.

The examples below use the directive fence; the marker form takes the same axis and options.

### The `python` axis

This project uses it for the [Python compatibility table in `install.md`](install.md#python-compatibility). You write the block with just its axis and options:

````{code-block} markdown
```{matrix} python
:package: click-extra

| `click-extra`       | Released   | `3.7` | `3.8` | `3.9` | `3.10` | `3.11` | `3.12` | `3.13` | `3.14` |
| :------------------ | :--------- | :---: | :---: | :---: | :----: | :----: | :----: | :----: | :----: |
| `6.2.x` → `8.x`     | 2025-11-04 |  ❌   |  ❌   |  ❌   |   ✅   |   ✅   |   ✅   |   ✅   |   ✅   |
| `6.0.x` → `6.1.x`   | 2025-10-08 |  ❌   |  ❌   |  ❌   |   ❌   |   ✅   |   ✅   |   ✅   |   ✅   |
| `5.0.x` → `6.0.x`   | 2025-05-13 |  ❌   |  ❌   |  ❌   |   ❌   |   ✅   |   ✅   |   ✅   |   ❌   |
| `4.11.x` → `4.15.x` | 2024-10-08 |  ❌   |  ❌   |  ❌   |   ✅   |   ✅   |   ✅   |   ✅   |   ❌   |
| `4.9.x` → `4.10.x`  | 2024-07-25 |  ❌   |  ❌   |  ✅   |   ✅   |   ✅   |   ✅   |   ❌   |   ❌   |
| `4.0.x` → `4.8.x`   | 2023-05-08 |  ❌   |  ✅   |  ✅   |   ✅   |   ✅   |   ✅   |   ❌   |   ❌   |
| `0.0.x` → `3.10.x`  | 2021-10-18 |  ✅   |  ✅   |  ✅   |   ✅   |   ✅   |   ❌   |   ❌   |   ❌   |
```
````

and the updater fills in the table below the options, regenerated from every `vMAJOR.MINOR.PATCH` tag (reading the declared Python support from the `Programming Language :: Python :: X.Y` classifiers in `pyproject.toml`, falling back to `requires-python`, Poetry's `python = "..."`, then `setup.py`'s `python_requires`). Consecutive releases that agree are grouped into one row, and a floor-only declaration is capped at the latest Python released while the range was current:

````{code-block} markdown
```{matrix} python
:package: click-extra

| `click-extra`       | Released   | `3.7` | `3.8` | `3.9` | `3.10` | `3.11` | `3.12` | `3.13` | `3.14` |
| :------------------ | :--------- | :---: | :---: | :---: | :----: | :----: | :----: | :----: | :----: |
| `6.2.x` → `8.x`     | 2025-11-04 |  ❌   |  ❌   |  ❌   |   ✅   |   ✅   |   ✅   |   ✅   |   ✅   |
| `6.0.x` → `6.1.x`   | 2025-10-08 |  ❌   |  ❌   |  ❌   |   ❌   |   ✅   |   ✅   |   ✅   |   ✅   |
| `5.0.x` → `6.0.x`   | 2025-05-13 |  ❌   |  ❌   |  ❌   |   ❌   |   ✅   |   ✅   |   ✅   |   ❌   |
| `4.11.x` → `4.15.x` | 2024-10-08 |  ❌   |  ❌   |  ❌   |   ✅   |   ✅   |   ✅   |   ✅   |   ❌   |
| `4.9.x` → `4.10.x`  | 2024-07-25 |  ❌   |  ❌   |  ✅   |   ✅   |   ✅   |   ✅   |   ❌   |   ❌   |
| `4.0.x` → `4.8.x`   | 2023-05-08 |  ❌   |  ✅   |  ✅   |   ✅   |   ✅   |   ✅   |   ❌   |   ❌   |
| `0.0.x` → `3.10.x`  | 2021-10-18 |  ✅   |  ✅   |  ✅   |   ✅   |   ✅   |   ❌   |   ❌   |   ❌   |
```
````

### A dependency axis

`{matrix} <distribution>` tracks a runtime dependency instead. For each release range it reads that distribution's requirement specifier (PEP 621, Poetry, or `setup.py`) and marks ✅ / ❌ for each column version with [`packaging`](https://packaging.pypa.io). Columns are auto-derived: a minor series stays a single `X.Y` column unless an open (`>=`) floor pins a specific patch, in which case it splits into `X.Y.0` plus that floor; the right edge is the version resolved in `uv.lock`. Add `:show-spec:` for a `Spec` column with each range's raw specifier. This project uses it for the [Click compatibility table](install.md#click-compatibility):

````{code-block} markdown
```{matrix} click
:package: click-extra
:show-spec:

| `click-extra`       | Released   | Spec      | `8.0` | `8.1` | `8.2` | `8.3.0` | `8.3.1` | `8.3.3` | `8.4.0` | `8.4.1` | `8.4.2` |
| :------------------ | :--------- | :-------- | :---: | :---: | :---: | :-----: | :-----: | :-----: | :-----: | :-----: | :-----: |
| `8.x`               | 2026-06-22 | `>=8.3.1` |  ❌   |  ❌   |  ❌   |   ❌    |   ✅    |   ✅    |   ✅    |   ✅    |   ✅    |
| `7.17.x` → `7.20.x` | 2026-05-25 | `>=8.4.1` |  ❌   |  ❌   |  ❌   |   ❌    |   ❌    |   ❌    |   ❌    |   ✅    |   ✅    |
| `7.15.x` → `7.16.x` | 2026-05-03 | `>=8.3.1` |  ❌   |  ❌   |  ❌   |   ❌    |   ✅    |   ✅    |   ✅    |   ✅    |   ✅    |
| `7.14.1`            | 2026-04-26 | `>=8.1`   |  ❌   |  ✅   |  ✅   |   ✅    |   ✅    |   ✅    |   ✅    |   ✅    |   ✅    |
| `7.14.0`            | 2026-04-24 | `>=8.3.3` |  ❌   |  ❌   |  ❌   |   ❌    |   ❌    |   ✅    |   ✅    |   ✅    |   ✅    |
| `7.0.x` → `7.13.x`  | 2025-11-17 | `>=8.3.1` |  ❌   |  ❌   |  ❌   |   ❌    |   ✅    |   ✅    |   ✅    |   ✅    |   ✅    |
| `6.x`               | 2025-09-25 | `>=8.3.0` |  ❌   |  ❌   |  ❌   |   ✅    |   ✅    |   ✅    |   ✅    |   ✅    |   ✅    |
| `5.x`               | 2025-05-13 | `~=8.2.0` |  ❌   |  ❌   |  ✅   |   ❌    |   ❌    |   ❌    |   ❌    |   ❌    |   ❌    |
| `4.9.x` → `4.15.x`  | 2024-07-25 | `~=8.1.4` |  ❌   |  ✅   |  ❌   |   ❌    |   ❌    |   ❌    |   ❌    |   ❌    |   ❌    |
| `1.7.x` → `4.8.x`   | 2022-03-31 | `^8.1.1`  |  ❌   |  ✅   |  ✅   |   ✅    |   ✅    |   ✅    |   ✅    |   ✅    |   ✅    |
| `0.0.x` → `1.6.x`   | 2021-10-18 | `^8.0.2`  |  ✅   |  ✅   |  ✅   |   ✅    |   ✅    |   ✅    |   ✅    |   ✅    |   ✅    |
```
````

### Options

| Option            | Effect                                                                           | Default                |
| ----------------- | -------------------------------------------------------------------------------- | ---------------------- |
| `:package:`       | Header column label, rendered in backticks.                                      | repository folder name |
| `:path:`          | Git working tree to walk, absolute or relative to the documented project's root. | project's git root     |
| `:version-floor:` | Drop release rows below this package version.                                    | none (all tags)        |
| `:tag-pattern:`   | Regex selecting release tags.                                                    | `^v\d+\.\d+\.\d+$`     |
| `:python-floor:`  | (`python` axis) Drop Python `X.Y` columns below this version.                    | none (all columns)     |
| `:show-spec:`     | (dependency axis) Add a `Spec` column with each range's raw specifier.           | off                    |

The `:path:` option makes the directive reusable across repositories: point it at a sibling checkout to render another package's matrix.

### Keeping the tables current

The embedded tables are refreshed offline, formatter-style, by the `refresh-directives` command (which needs the sphinx extra):

```{code-block} shell-session
$ click-extra refresh-directives docs/
```

It walks the given Markdown files or directories, regenerates each matrix block's table (both the `{matrix}` directive fences and the `<!-- matrix … -->` marker regions) from that block's axis, options, and the project's git tags, and rewrites the block in place. Only blocks that already exist are refreshed: nothing is added. Pass `--check` to write nothing and exit non-zero when a block is stale, so a CI job or pre-commit hook can fail on an out-of-date matrix. The same logic is importable as `click_extra.sphinx.matrix.update_matrix_blocks(paths, check=...)`. A block whose generation fails (missing git binary, non-repository `:path:`, no matching data) is left untouched, so a transient failure never wipes a good table.

```{note}
Only the updater (and the empty-block fallback) needs the release tags, since it is the part that shells out to `git`. Run it wherever the full tag history is available. The HTML build renders the embedded table verbatim and needs no git access, so shallow clones and read-only build hosts render the matrix fine.
```

## Man pages

The Sphinx extension can render the roff man page tree of any Click CLI alongside the HTML build, so a project's docs site, release pipeline, and downstream packagers all share a single generator. Add one or more entries to `click_extra_manpages` in `conf.py`:

```{code-block} python
:caption: `conf.py`
extensions = ["click_extra.sphinx"]

click_extra_manpages = [
    {
        "script": "my_pkg.cli:my_cli",   # required
        "prog_name": "my-cli",            # optional, defaults to the resolved command's name
        "output_dir": "man",              # optional, defaults to "man"
        "render_html": True,              # optional, defaults to True
    },
]
```

On every HTML build, the hook resolves each `script` with the same scanner as the [`click-extra wrap --man`](man-page.md#generating-man-pages) CLI and writes one `.1` file per (sub)command into `<outdir>/<output_dir>/`, mirroring what `click-extra wrap --man --output-dir DIR -- SCRIPT` produces from the command line. An empty (or absent) list keeps the hook silent: no man pages, no warnings.

Only HTML-family builders (`html`, `dirhtml`, `singlehtml`) trigger the hook. Other builders (`linkcheck`, `man`, `epub`, `coverage`) skip it: roff in their output trees would be redundant or confusing.

The generator honors `SOURCE_DATE_EPOCH` for reproducible builds and inherits every option-group and Cloup-aware rendering rule documented in the [man-page reference](man-page.md#layout).

### HTML siblings

Browsers download `.1` files rather than render them, so each emitted page is also passed through a roff → HTML renderer when one is available. The result lands next to the source as `<page>.<section>.html` (like `my-cli.1.html`).

The hook tries [`mandoc -Thtml`](https://mandoc.bsd.lv) first, then `groff -Thtml -mandoc`, picking whichever it finds on `PATH`. mandoc is preferred for its semantic anchors: every section and option gets a stable `id`, which makes deep-linking work. If neither renderer is installed, the build still produces the `.1` files and logs a single info-level notice, which `render_html: False` suppresses.

A typical CI container ships one or the other: Debian and Ubuntu have `groff` in `build-essential`, BSDs and recent macOS images ship `mandoc`. To pin the renderer on GitHub Actions, install it explicitly:

```{code-block} yaml
:caption: `.github/workflows/docs.yaml`
- name: Install mandoc
  run: sudo apt-get install --yes mandoc
```

### Cross-linking from prose

To make the standard `:manpage:` role link to the HTML siblings the hook emits, set Sphinx's [`manpages_url`](https://www.sphinx-doc.org/en/master/usage/configuration.html#confval-manpages_url) to the matching path:

```{code-block} python
:caption: `conf.py`
manpages_url = "man/{page}.{section}.html"
```

With that in place, `` :manpage:`my-cli(1)` `` in any docstring or `.md` file resolves to `man/my-cli.1.html` in the rendered docs. The same template covers every subcommand page, since `{page}` matches the full hyphenated name the generator produces (`my-cli`, `my-cli-build`, `my-cli-build-all`).

Leaving `manpages_url` unset is fine. The role still renders as styled text; only the hyperlink target is missing.

### `click-extra-manpages` directive

For a discoverable landing page, drop the `click-extra-manpages` directive anywhere in the docs. It walks `click_extra_manpages` and emits a bullet list with one entry per (sub)command in each declared tree, linked to the HTML sibling produced by the hook:

````{code-block} markdown
```{click-extra-manpages}
```
````

The directive takes no arguments. URLs are computed relative to the enclosing document, so the same call works on a top-level page and on a page nested under a subdirectory. When `click_extra_manpages` is empty, the directive renders nothing.

A live instance of the directive ships at the bottom of the [man-page reference](man-page.md#index): the list there is what this project's own `click_extra_manpages` entry produces at build time.

## GitHub alerts

Click Extra's Sphinx extension automatically converts [GitHub-flavored Markdown alerts](https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax#alerts) into [MyST admonitions](https://myst-parser.readthedocs.io/en/latest/syntax/admonitions.html).

This allows you to write documentation that renders correctly both on GitHub and in your Sphinx-generated documentation.

### Setup

To use GitHub alerts, you need to enable the [`colon_fence` extension](https://myst-parser.readthedocs.io/en/latest/syntax/optional.html#code-fences-using-colons) in your Sphinx configuration:

```{code-block} python
:caption: `conf.py`
:emphasize-lines: 6
extensions = [
    ...
    "click_extra.sphinx",
]

myst_enable_extensions = ["colon_fence"]
```

### Supported alert types

GitHub supports five alert types, all of which are replaced behind the scenes with their corresponding MyST admonitions:

````{list-table}
:header-rows: 1
:widths: 10 30 30 30
* - Type
  - GitHub syntax
  - MyST syntax
  - Rendered
* - Note
  - ```markdown
    > [!NOTE]
    > Useful information.
    ```
  - ```markdown
    :::{note}
    Useful information.
    :::
    ```
  - ```{note}
    Useful information.
    ```
* - Tip
  - ```markdown
    > [!TIP]
    > Helpful advice.
    ```
  - ```markdown
    :::{tip}
    Helpful advice.
    :::
    ```
  - ```{tip}
    Helpful advice.
    ```
* - Important
  - ```markdown
    > [!IMPORTANT]
    > Key information.
    ```
  - ```markdown
    :::{important}
    Key information.
    :::
    ```
  - ```{important}
    Key information.
    ```
* - Warning
  - ```markdown
    > [!WARNING]
    > Potential issues.
    ```
  - ```markdown
    :::{warning}
    Potential issues.
    :::
    ```
  - ```{warning}
    Potential issues.
    ```
* - Caution
  - ```markdown
    > [!CAUTION]
    > Negative consequences.
    ```
  - ```markdown
    :::{caution}
    Negative consequences.
    :::
    ```
  - ```{caution}
    Negative consequences.
    ```
````

### Usage

Write alerts using GitHub's blockquote syntax:

```{code-block} markdown
> [!NOTE]
> This is a note that will render as an admonition in Sphinx.

> [!WARNING]
> Reader discretion is strongly advised.
```

These will render in Sphinx as:

> [!NOTE]
> This is a note that will render as an admonition in Sphinx.

> [!WARNING]
> Reader discretion is strongly advised.

### Rules

Playing with alerts on various GitHub websites, I reverse-engineered the following specifications:

- Alert type must be in uppercase: `[!TIP]`, not `[!tip]`.
- No spaces in the directive: `[! NOTE]`, `[!NOTE ]` or `[ !NOTE]` are invalid.
- Must be the first thing in the blockquote: `> Hello [!NOTE] This is a note.` is interpreted as a normal blockquote, not an alert.
- Only the first line of the blockquote is parsed for the alert type: subsequent lines are considered part of the alert content.
- The alert content can span multiple lines, as long as they are part of the same blockquote.
- Empty blockquotes are ignored: `> [!TIP]` without any content is not rendered.
- Nested blockquotes are supported: the alert content can contain other blockquotes, lists, code blocks, etc.

### Nested alerts

GitHub alerts support nested content, including other blockquotes, lists, code blocks, and even nested alerts. This allows for complex documentation structures that render correctly both on GitHub and in Sphinx.

You can include various Markdown elements inside an alert:

````{code-block} markdown
> [!NOTE]
> This alert contains:
> - A bullet list
> - With multiple items
>
> And a code block:
> ```python
> print("Hello, world!")
> ```
````

Which renders as:

> [!NOTE]
> This alert contains:
>
> - A bullet list
> - With multiple items
>
> And a code block:
>
> ```python
> print("Hello, world!")
> ```

You can nest alerts within alerts for hierarchical information:

```{code-block} markdown
> [!WARNING]
> Be careful with this operation.
>
> > [!TIP]
> > If you encounter issues, try restarting the service.
```

Which renders as:

> [!WARNING]
> Be careful with this operation.
>
> > [!TIP]
> > If you encounter issues, try restarting the service.

You can also mix GitHub alerts with MyST directives inside container directives:

`````{code-block} markdown
````{note}
> [!TIP]
> First alert.

```{warning}
Nested MyST warning.
```

> [!CAUTION]
> Second alert after nested directive.
````
`````

````{note}
> [!TIP]
> First alert.

```{warning}
Nested MyST warning.
```

> [!CAUTION]
> Second alert after nested directive.
````

For more complex documentation, you can combine multiple nested elements such as blockquotes, numbered lists, nested alerts, and code blocks:

````{code-block} markdown
> [!IMPORTANT]
> Before proceeding, ensure you have:
>
> 1. Backed up your data
> 2. Reviewed the changelog
>
> > This is important context that applies to all the steps above.
>
> > [!CAUTION]
> > This action cannot be undone.
>
> ```bash
> $ make backup
> ```
````

Which renders as:

> [!IMPORTANT]
> Before proceeding, ensure you have:
>
> 1. Backed up your data
> 2. Reviewed the changelog
>
> > This is important context that applies to all the steps above.
>
> > [!CAUTION]
> > This action cannot be undone.
>
> ```bash
> $ make backup
> ```

## ANSI shell sessions

Sphinx extensions from Click Extra automaticcaly integrates the [new ANSI-capable lexers for Pygments](pygments.md#ansi-language-lexers).

This allows you to render colored shell sessions in code blocks by referring to the `ansi-` prefixed lexers:

``````{tab-set}
`````{tab-item} MyST Markdown
:sync: myst
````{code-block} markdown
:emphasize-lines: 1
```{code-block} ansi-shell-session
$ # Print ANSI foreground colors.
$ for i in {0..255}; do \
>     printf '\e[38;5;%dm%3d ' $i $i \
>     (((i+3) % 18)) || printf '\e[0m\n' \
> done
[38;5;0m  0 [38;5;1m  1 [38;5;2m  2 [38;5;3m  3 [38;5;4m  4 [38;5;5m  5 [38;5;6m  6 [38;5;7m  7 [38;5;8m  8 [38;5;9m  9 [38;5;10m 10 [38;5;11m 11 [38;5;12m 12 [38;5;13m 13 [38;5;14m 14 [38;5;15m 15 [0m
[38;5;16m 16 [38;5;17m 17 [38;5;18m 18 [38;5;19m 19 [38;5;20m 20 [38;5;21m 21 [38;5;22m 22 [38;5;23m 23 [38;5;24m 24 [38;5;25m 25 [38;5;26m 26 [38;5;27m 27 [38;5;28m 28 [38;5;29m 29 [38;5;30m 30 [38;5;31m 31 [38;5;32m 32 [38;5;33m 33 [0m
[38;5;34m 34 [38;5;35m 35 [38;5;36m 36 [38;5;37m 37 [38;5;38m 38 [38;5;39m 39 [38;5;40m 40 [38;5;41m 41 [38;5;42m 42 [38;5;43m 43 [38;5;44m 44 [38;5;45m 45 [38;5;46m 46 [38;5;47m 47 [38;5;48m 48 [38;5;49m 49 [38;5;50m 50 [38;5;51m 51 [0m
[38;5;52m 52 [38;5;53m 53 [38;5;54m 54 [38;5;55m 55 [38;5;56m 56 [38;5;57m 57 [38;5;58m 58 [38;5;59m 59 [38;5;60m 60 [38;5;61m 61 [38;5;62m 62 [38;5;63m 63 [38;5;64m 64 [38;5;65m 65 [38;5;66m 66 [38;5;67m 67 [38;5;68m 68 [38;5;69m 69 [0m
[38;5;70m 70 [38;5;71m 71 [38;5;72m 72 [38;5;73m 73 [38;5;74m 74 [38;5;75m 75 [38;5;76m 76 [38;5;77m 77 [38;5;78m 78 [38;5;79m 79 [38;5;80m 80 [38;5;81m 81 [38;5;82m 82 [38;5;83m 83 [38;5;84m 84 [38;5;85m 85 [38;5;86m 86 [38;5;87m 87 [0m
[38;5;88m 88 [38;5;89m 89 [38;5;90m 90 [38;5;91m 91 [38;5;92m 92 [38;5;93m 93 [38;5;94m 94 [38;5;95m 95 [38;5;96m 96 [38;5;97m 97 [38;5;98m 98 [38;5;99m 99 [38;5;100m100 [38;5;101m101 [38;5;102m102 [38;5;103m103 [38;5;104m104 [38;5;105m105 [0m
[38;5;106m106 [38;5;107m107 [38;5;108m108 [38;5;109m109 [38;5;110m110 [38;5;111m111 [38;5;112m112 [38;5;113m113 [38;5;114m114 [38;5;115m115 [38;5;116m116 [38;5;117m117 [38;5;118m118 [38;5;119m119 [38;5;120m120 [38;5;121m121 [38;5;122m122 [38;5;123m123 [0m
[38;5;124m124 [38;5;125m125 [38;5;126m126 [38;5;127m127 [38;5;128m128 [38;5;129m129 [38;5;130m130 [38;5;131m131 [38;5;132m132 [38;5;133m133 [38;5;134m134 [38;5;135m135 [38;5;136m136 [38;5;137m137 [38;5;138m138 [38;5;139m139 [38;5;140m140 [38;5;141m141 [0m
[38;5;142m142 [38;5;143m143 [38;5;144m144 [38;5;145m145 [38;5;146m146 [38;5;147m147 [38;5;148m148 [38;5;149m149 [38;5;150m150 [38;5;151m151 [38;5;152m152 [38;5;153m153 [38;5;154m154 [38;5;155m155 [38;5;156m156 [38;5;157m157 [38;5;158m158 [38;5;159m159 [0m
[38;5;160m160 [38;5;161m161 [38;5;162m162 [38;5;163m163 [38;5;164m164 [38;5;165m165 [38;5;166m166 [38;5;167m167 [38;5;168m168 [38;5;169m169 [38;5;170m170 [38;5;171m171 [38;5;172m172 [38;5;173m173 [38;5;174m174 [38;5;175m175 [38;5;176m176 [38;5;177m177 [0m
[38;5;178m178 [38;5;179m179 [38;5;180m180 [38;5;181m181 [38;5;182m182 [38;5;183m183 [38;5;184m184 [38;5;185m185 [38;5;186m186 [38;5;187m187 [38;5;188m188 [38;5;189m189 [38;5;190m190 [38;5;191m191 [38;5;192m192 [38;5;193m193 [38;5;194m194 [38;5;195m195 [0m
[38;5;196m196 [38;5;197m197 [38;5;198m198 [38;5;199m199 [38;5;200m200 [38;5;201m201 [38;5;202m202 [38;5;203m203 [38;5;204m204 [38;5;205m205 [38;5;206m206 [38;5;207m207 [38;5;208m208 [38;5;209m209 [38;5;210m210 [38;5;211m211 [38;5;212m212 [38;5;213m213 [0m
[38;5;214m214 [38;5;215m215 [38;5;216m216 [38;5;217m217 [38;5;218m218 [38;5;219m219 [38;5;220m220 [38;5;221m221 [38;5;222m222 [38;5;223m223 [38;5;224m224 [38;5;225m225 [38;5;226m226 [38;5;227m227 [38;5;228m228 [38;5;229m229 [38;5;230m230 [38;5;231m231 [0m
[38;5;232m232 [38;5;233m233 [38;5;234m234 [38;5;235m235 [38;5;236m236 [38;5;237m237 [38;5;238m238 [38;5;239m239 [38;5;240m240 [38;5;241m241 [38;5;242m242 [38;5;243m243 [38;5;244m244 [38;5;245m245 [38;5;246m246 [38;5;247m247 [38;5;248m248 [38;5;249m249 [0m
[38;5;250m250 [38;5;251m251 [38;5;252m252 [38;5;253m253 [38;5;254m254 [38;5;255m255
```
````
`````

`````{tab-item} reStructuredText
:sync: rst
```{code-block} rst
:emphasize-lines: 1
.. code-block:: ansi-shell-session

    $ # Print ANSI foreground colors.
    $ for i in {0..255}; do \
    >     printf '\e[38;5;%dm%3d ' $i $i \
    >     (((i+3) % 18)) || printf '\e[0m\n' \
    > done
    [38;5;0m  0 [38;5;1m  1 [38;5;2m  2 [38;5;3m  3 [38;5;4m  4 [38;5;5m  5 [38;5;6m  6 [38;5;7m  7 [38;5;8m  8 [38;5;9m  9 [38;5;10m 10 [38;5;11m 11 [38;5;12m 12 [38;5;13m 13 [38;5;14m 14 [38;5;15m 15 [0m
    [38;5;16m 16 [38;5;17m 17 [38;5;18m 18 [38;5;19m 19 [38;5;20m 20 [38;5;21m 21 [38;5;22m 22 [38;5;23m 23 [38;5;24m 24 [38;5;25m 25 [38;5;26m 26 [38;5;27m 27 [38;5;28m 28 [38;5;29m 29 [38;5;30m 30 [38;5;31m 31 [38;5;32m 32 [38;5;33m 33 [0m
    [38;5;34m 34 [38;5;35m 35 [38;5;36m 36 [38;5;37m 37 [38;5;38m 38 [38;5;39m 39 [38;5;40m 40 [38;5;41m 41 [38;5;42m 42 [38;5;43m 43 [38;5;44m 44 [38;5;45m 45 [38;5;46m 46 [38;5;47m 47 [38;5;48m 48 [38;5;49m 49 [38;5;50m 50 [38;5;51m 51 [0m
    [38;5;52m 52 [38;5;53m 53 [38;5;54m 54 [38;5;55m 55 [38;5;56m 56 [38;5;57m 57 [38;5;58m 58 [38;5;59m 59 [38;5;60m 60 [38;5;61m 61 [38;5;62m 62 [38;5;63m 63 [38;5;64m 64 [38;5;65m 65 [38;5;66m 66 [38;5;67m 67 [38;5;68m 68 [38;5;69m 69 [0m
    [38;5;70m 70 [38;5;71m 71 [38;5;72m 72 [38;5;73m 73 [38;5;74m 74 [38;5;75m 75 [38;5;76m 76 [38;5;77m 77 [38;5;78m 78 [38;5;79m 79 [38;5;80m 80 [38;5;81m 81 [38;5;82m 82 [38;5;83m 83 [38;5;84m 84 [38;5;85m 85 [38;5;86m 86 [38;5;87m 87 [0m
    [38;5;88m 88 [38;5;89m 89 [38;5;90m 90 [38;5;91m 91 [38;5;92m 92 [38;5;93m 93 [38;5;94m 94 [38;5;95m 95 [38;5;96m 96 [38;5;97m 97 [38;5;98m 98 [38;5;99m 99 [38;5;100m100 [38;5;101m101 [38;5;102m102 [38;5;103m103 [38;5;104m104 [38;5;105m105 [0m
    [38;5;106m106 [38;5;107m107 [38;5;108m108 [38;5;109m109 [38;5;110m110 [38;5;111m111 [38;5;112m112 [38;5;113m113 [38;5;114m114 [38;5;115m115 [38;5;116m116 [38;5;117m117 [38;5;118m118 [38;5;119m119 [38;5;120m120 [38;5;121m121 [38;5;122m122 [38;5;123m123 [0m
    [38;5;124m124 [38;5;125m125 [38;5;126m126 [38;5;127m127 [38;5;128m128 [38;5;129m129 [38;5;130m130 [38;5;131m131 [38;5;132m132 [38;5;133m133 [38;5;134m134 [38;5;135m135 [38;5;136m136 [38;5;137m137 [38;5;138m138 [38;5;139m139 [38;5;140m140 [38;5;141m141 [0m
    [38;5;142m142 [38;5;143m143 [38;5;144m144 [38;5;145m145 [38;5;146m146 [38;5;147m147 [38;5;148m148 [38;5;149m149 [38;5;150m150 [38;5;151m151 [38;5;152m152 [38;5;153m153 [38;5;154m154 [38;5;155m155 [38;5;156m156 [38;5;157m157 [38;5;158m158 [38;5;159m159 [0m
    [38;5;160m160 [38;5;161m161 [38;5;162m162 [38;5;163m163 [38;5;164m164 [38;5;165m165 [38;5;166m166 [38;5;167m167 [38;5;168m168 [38;5;169m169 [38;5;170m170 [38;5;171m171 [38;5;172m172 [38;5;173m173 [38;5;174m174 [38;5;175m175 [38;5;176m176 [38;5;177m177 [0m
    [38;5;178m178 [38;5;179m179 [38;5;180m180 [38;5;181m181 [38;5;182m182 [38;5;183m183 [38;5;184m184 [38;5;185m185 [38;5;186m186 [38;5;187m187 [38;5;188m188 [38;5;189m189 [38;5;190m190 [38;5;191m191 [38;5;192m192 [38;5;193m193 [38;5;194m194 [38;5;195m195 [0m
    [38;5;196m196 [38;5;197m197 [38;5;198m198 [38;5;199m199 [38;5;200m200 [38;5;201m201 [38;5;202m202 [38;5;203m203 [38;5;204m204 [38;5;205m205 [38;5;206m206 [38;5;207m207 [38;5;208m208 [38;5;209m209 [38;5;210m210 [38;5;211m211 [38;5;212m212 [38;5;213m213 [0m
    [38;5;214m214 [38;5;215m215 [38;5;216m216 [38;5;217m217 [38;5;218m218 [38;5;219m219 [38;5;220m220 [38;5;221m221 [38;5;222m222 [38;5;223m223 [38;5;224m224 [38;5;225m225 [38;5;226m226 [38;5;227m227 [38;5;228m228 [38;5;229m229 [38;5;230m230 [38;5;231m231 [0m
    [38;5;232m232 [38;5;233m233 [38;5;234m234 [38;5;235m235 [38;5;236m236 [38;5;237m237 [38;5;238m238 [38;5;239m239 [38;5;240m240 [38;5;241m241 [38;5;242m242 [38;5;243m243 [38;5;244m244 [38;5;245m245 [38;5;246m246 [38;5;247m247 [38;5;248m248 [38;5;249m249 [0m
    [38;5;250m250 [38;5;251m251 [38;5;252m252 [38;5;253m253 [38;5;254m254 [38;5;255m255
```
`````
``````

In Sphinx, the snippet above renders to:

```{code-block} ansi-shell-session
$ # Print ANSI foreground colors.
$ for i in {0..255}; do \
>     printf '\e[38;5;%dm%3d ' $i $i \
>     (((i+3) % 18)) || printf '\e[0m\n' \
> done
[38;5;0m  0 [38;5;1m  1 [38;5;2m  2 [38;5;3m  3 [38;5;4m  4 [38;5;5m  5 [38;5;6m  6 [38;5;7m  7 [38;5;8m  8 [38;5;9m  9 [38;5;10m 10 [38;5;11m 11 [38;5;12m 12 [38;5;13m 13 [38;5;14m 14 [38;5;15m 15 [0m
[38;5;16m 16 [38;5;17m 17 [38;5;18m 18 [38;5;19m 19 [38;5;20m 20 [38;5;21m 21 [38;5;22m 22 [38;5;23m 23 [38;5;24m 24 [38;5;25m 25 [38;5;26m 26 [38;5;27m 27 [38;5;28m 28 [38;5;29m 29 [38;5;30m 30 [38;5;31m 31 [38;5;32m 32 [38;5;33m 33 [0m
[38;5;34m 34 [38;5;35m 35 [38;5;36m 36 [38;5;37m 37 [38;5;38m 38 [38;5;39m 39 [38;5;40m 40 [38;5;41m 41 [38;5;42m 42 [38;5;43m 43 [38;5;44m 44 [38;5;45m 45 [38;5;46m 46 [38;5;47m 47 [38;5;48m 48 [38;5;49m 49 [38;5;50m 50 [38;5;51m 51 [0m
[38;5;52m 52 [38;5;53m 53 [38;5;54m 54 [38;5;55m 55 [38;5;56m 56 [38;5;57m 57 [38;5;58m 58 [38;5;59m 59 [38;5;60m 60 [38;5;61m 61 [38;5;62m 62 [38;5;63m 63 [38;5;64m 64 [38;5;65m 65 [38;5;66m 66 [38;5;67m 67 [38;5;68m 68 [38;5;69m 69 [0m
[38;5;70m 70 [38;5;71m 71 [38;5;72m 72 [38;5;73m 73 [38;5;74m 74 [38;5;75m 75 [38;5;76m 76 [38;5;77m 77 [38;5;78m 78 [38;5;79m 79 [38;5;80m 80 [38;5;81m 81 [38;5;82m 82 [38;5;83m 83 [38;5;84m 84 [38;5;85m 85 [38;5;86m 86 [38;5;87m 87 [0m
[38;5;88m 88 [38;5;89m 89 [38;5;90m 90 [38;5;91m 91 [38;5;92m 92 [38;5;93m 93 [38;5;94m 94 [38;5;95m 95 [38;5;96m 96 [38;5;97m 97 [38;5;98m 98 [38;5;99m 99 [38;5;100m100 [38;5;101m101 [38;5;102m102 [38;5;103m103 [38;5;104m104 [38;5;105m105 [0m
[38;5;106m106 [38;5;107m107 [38;5;108m108 [38;5;109m109 [38;5;110m110 [38;5;111m111 [38;5;112m112 [38;5;113m113 [38;5;114m114 [38;5;115m115 [38;5;116m116 [38;5;117m117 [38;5;118m118 [38;5;119m119 [38;5;120m120 [38;5;121m121 [38;5;122m122 [38;5;123m123 [0m
[38;5;124m124 [38;5;125m125 [38;5;126m126 [38;5;127m127 [38;5;128m128 [38;5;129m129 [38;5;130m130 [38;5;131m131 [38;5;132m132 [38;5;133m133 [38;5;134m134 [38;5;135m135 [38;5;136m136 [38;5;137m137 [38;5;138m138 [38;5;139m139 [38;5;140m140 [38;5;141m141 [0m
[38;5;142m142 [38;5;143m143 [38;5;144m144 [38;5;145m145 [38;5;146m146 [38;5;147m147 [38;5;148m148 [38;5;149m149 [38;5;150m150 [38;5;151m151 [38;5;152m152 [38;5;153m153 [38;5;154m154 [38;5;155m155 [38;5;156m156 [38;5;157m157 [38;5;158m158 [38;5;159m159 [0m
[38;5;160m160 [38;5;161m161 [38;5;162m162 [38;5;163m163 [38;5;164m164 [38;5;165m165 [38;5;166m166 [38;5;167m167 [38;5;168m168 [38;5;169m169 [38;5;170m170 [38;5;171m171 [38;5;172m172 [38;5;173m173 [38;5;174m174 [38;5;175m175 [38;5;176m176 [38;5;177m177 [0m
[38;5;178m178 [38;5;179m179 [38;5;180m180 [38;5;181m181 [38;5;182m182 [38;5;183m183 [38;5;184m184 [38;5;185m185 [38;5;186m186 [38;5;187m187 [38;5;188m188 [38;5;189m189 [38;5;190m190 [38;5;191m191 [38;5;192m192 [38;5;193m193 [38;5;194m194 [38;5;195m195 [0m
[38;5;196m196 [38;5;197m197 [38;5;198m198 [38;5;199m199 [38;5;200m200 [38;5;201m201 [38;5;202m202 [38;5;203m203 [38;5;204m204 [38;5;205m205 [38;5;206m206 [38;5;207m207 [38;5;208m208 [38;5;209m209 [38;5;210m210 [38;5;211m211 [38;5;212m212 [38;5;213m213 [0m
[38;5;214m214 [38;5;215m215 [38;5;216m216 [38;5;217m217 [38;5;218m218 [38;5;219m219 [38;5;220m220 [38;5;221m221 [38;5;222m222 [38;5;223m223 [38;5;224m224 [38;5;225m225 [38;5;226m226 [38;5;227m227 [38;5;228m228 [38;5;229m229 [38;5;230m230 [38;5;231m231 [0m
[38;5;232m232 [38;5;233m233 [38;5;234m234 [38;5;235m235 [38;5;236m236 [38;5;237m237 [38;5;238m238 [38;5;239m239 [38;5;240m240 [38;5;241m241 [38;5;242m242 [38;5;243m243 [38;5;244m244 [38;5;245m245 [38;5;246m246 [38;5;247m247 [38;5;248m248 [38;5;249m249 [0m
[38;5;250m250 [38;5;251m251 [38;5;252m252 [38;5;253m253 [38;5;254m254 [38;5;255m255
```

## Legacy MyST + reStructuredText syntax

Before MyST was fully integrated into Sphinx, many projects used a mixed syntax setup with MyST and reStructuredText. If you are maintaining such a project or need to ensure compatibility with older documentation, you can use these legacy Sphinx snippets.

This rely on MyST's ability to embed reStructuredText within MyST documents, via the [`{eval-rst}` directive](https://myst-parser.readthedocs.io/en/latest/syntax/roles-and-directives.html#how-directives-parse-content).

So instead of using the `{click:source}` and `{click:run}` MyST directive, you can wrap your reStructuredText code blocks with `{eval-rst}`:

````{code-block} markdown
:emphasize-lines: 1
```{eval-rst}
.. click:source::

   from click import echo, command

   @command
   def yo_cli():
       echo("Yo!")

.. click:run::

    invoke(yo_cli)
```
````

Which renders to:

```{eval-rst}
.. click:source::

   from click import echo, command

   @command
   def yo_cli():
       echo("Yo!")

.. click:run::

    invoke(yo_cli)
```

````{warning}
CLI states and references are lost as soon as an `{eval-rst}` block ends. So a `.. click:source::` directive needs to have all its associated `.. click:run::` calls within the same rST block.

If not, you are likely to encounter execution tracebacks such as:
```pytb
  File ".../click-extra/docs/sphinx.md:372", line 1, in <module>
NameError: name 'yo_cli' is not defined
```
````

## `click_extra.sphinx` API

```{eval-rst}
.. autoclasstree:: click_extra.sphinx
   :strict:

.. automodule:: click_extra.sphinx
   :no-index:
   :members:
   :undoc-members:
   :show-inheritance:
```
