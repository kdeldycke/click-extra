# Sphinx extensions

[Sphinx](https://www.sphinx-doc.org) is the best way to document your Python CLI. Click Extra provides several utilities to improve the quality of life of maintainers.

````{important}
For these helpers to work, you need to install `click_extra`'s additional dependencies from the `sphinx` extra group:

```{code-block} shell-session
$ pip install click_extra[sphinx]
```
````

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

## `click` directives

Click Extra adds two new directives:

- `click:example` to display any Click-based Python code blocks in Sphinx
- `click:run` to invoke the CLI defined above, and display the results as if was executed in a terminmal

Thanks to these, you can directly demonstrate the usage of your CLI in your documentation. You no longer have to maintain screenshots of you CLIs. Or copy and paste their outputs to keep them in sync with the latest revision. Click Extra will do that job for you.

These directives supports both [MyST Markdown](https://myst-parser.readthedocs.io) and [reStructuredText](https://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html) syntax.

## Usage

Here is how to define a simple Click-based CLI with the `click:example` directive:

``````{tab-set}
`````{tab-item} MyST Markdown
:sync: myst
````{code-block} markdown
:emphasize-lines: 1
```{click:example}
from click_extra import echo, extra_command, option, style

@extra_command
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
.. click:example::

    from click_extra import echo, extra_command, option, style

    @extra_command
    @option("--name", prompt="Your name", help="The person to greet.")
    def hello_world(name):
        """Simple program that greets NAME."""
        echo(f"Hello, {style(name, fg='red')}!")
```
`````
``````

After defining the CLI source code in the `click:example` directive above, you can invoke it with the `click:run` directive.

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

```{click:example}
from click_extra import echo, extra_command, option, style

@extra_command
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
    \x1b[94m\x1b[1m\x1b[4mUsage:\x1b[0m \x1b[97mhello-world\x1b[0m \x1b[36m\x1b[2m[OPTIONS]\x1b[0m

      Simple program that greets NAME.

    \x1b[94m\x1b[1m\x1b[4mOptions:\x1b[0m
      \x1b[36m--name\x1b[0m \x1b[36m\x1b[2mTEXT\x1b[0m               The person to greet.
      \x1b[36m--time\x1b[0m / \x1b[36m--no-time\x1b[0m        Measure and print elapsed execution time."""
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

Which renders in Sphinx like it was executed in a terminal block:

```{click:run}
result = invoke(hello_world, args=["--name", "Joe"])
assert result.output == 'Hello, \x1b[31mJoe\x1b[0m!\n'
```

```{tip}
`click:example` and `click:run` directives works well with standard vanilla `click`-based CLIs.

In the example above, we choose to import our CLI primitives from the `click-extra` module instead, to demonstrate the coloring of terminal session outputs, as `click-extra` provides [fancy coloring of help screens](colorize.md) by default.
```

```{seealso}
Click Extra's own documentation extensively use `click:example` and `click:run` directives. [Look around
in its Markdown source files](https://github.com/kdeldycke/click-extra/tree/main/docs) for advanced examples and
inspiration.
```

## Options

You can pass options to both the `click:example` and `click:run` directives to customize their behavior:

| Option | Description | Example |
|--------|-------------|---------|
| [`:linenos:`](https://www.sphinx-doc.org/en/master/usage/restructuredtext/directives.html#directive-option-code-block-linenos) | Display line numbers. | `:linenos:` |
| [`:lineno-start:`](https://www.sphinx-doc.org/en/master/usage/restructuredtext/directives.html#directive-option-code-block-lineno-start) | Specify the starting line number. | `:lineno-start: 10` |
| [`:emphasize-lines:`](https://www.sphinx-doc.org/en/master/usage/restructuredtext/directives.html#directive-option-code-block-emphasize-lines) | Highlight specific lines. | `:emphasize-lines: 2,4-6` |
| [`:force:`](https://www.sphinx-doc.org/en/master/usage/restructuredtext/directives.html#directive-option-code-block-force) | Ignore minor errors on highlighting. | `:force:` |
| [`:caption:`](https://www.sphinx-doc.org/en/master/usage/restructuredtext/directives.html#directive-option-code-block-caption) | Set a caption for the code block. | `:caption: My Code Example` |
| [`:name:`](https://www.sphinx-doc.org/en/master/usage/restructuredtext/directives.html#directive-option-code-block-name) | Set a name for the code block (useful for cross-referencing). | `:name: example-1` |
| [`:class:`](https://www.sphinx-doc.org/en/master/usage/restructuredtext/directives.html#directive-option-code-block-class) | Set a CSS class for the code block. | `:class: highlight` |
| [`:dedent:`](https://www.sphinx-doc.org/en/master/usage/restructuredtext/directives.html#directive-option-code-block-dedent) | Specify the number of spaces to remove from the beginning of each line. | `:dedent: 4` |
| [`:language:`](https://www.sphinx-doc.org/en/master/usage/restructuredtext/directives.html#directive-option-literalinclude-language) | Specify the programming language for syntax highlighting. This can be used as an alternative to [passing the language as an argument](#syntax-highlight-language). | `:language: sql` |
| `:show-source:`/`:hide-source:` | Flags to force the source code within the directive to be rendered or not. | `:show-source:` or `:hide-source:` |
| `:show-results:`/`:hide-results:` | Flags to force the results of the CLI invocation to be rendered or not. | `:show-results:` or `:hide-results:` |

### `code-block` options

Because the `click:example` and `click:run` directives produces code blocks, they inherits the [same options as the Sphinx `code-block` directive](https://www.sphinx-doc.org/en/master/usage/restructuredtext/directives.html#directive-code-block).

For example, you can highlight some lines of with the `:emphasize-lines:` option, display line numbers with the `:linenos:` option, and set a caption with the `:caption:` option:

``````{tab-set}
`````{tab-item} MyST Markdown
:sync: myst
````{code-block} markdown
:emphasize-lines: 2-4
```{click:example}
:caption: A magnificent ✨ Hello World CLI!
:linenos:
:emphasize-lines: 4,7
from click_extra import echo, extra_command, option, style

@extra_command
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
.. click:example::
   :caption: A magnificent ✨ Hello World CLI!
   :linenos:
   :emphasize-lines: 4,7

   from click_extra import echo, extra_command, option, style

   @extra_command
   @option("--name", prompt="Your name", help="The person to greet.")
   def hello_world(name):
       """Simple program that greets NAME."""
       echo(f"Hello, {style(name, fg='red')}!")
```
`````
``````

Which renders to:

```{click:example}
:caption: A magnificent ✨ Hello World CLI!
:linenos:
:emphasize-lines: 4,7
from click_extra import echo, extra_command, option, style

@extra_command
@option("--name", prompt="Your name", help="The person to greet.")
def hello_world(name):
    """Simple program that greets NAME."""
    echo(f"Hello, {style(name, fg='red')}!")
```

### Display options

You can also control the display of the source code and the results of the CLI invocation with the `:show-source:`/`:hide-source:` and `:show-results:`/`:hide-results:` options.

By default:
- `click:example` displays the source code of the CLI, but does not display the results (because it is not executed). This is equivalent to having both `:show-source:` and `:hide-results:` options.
- `click:run` displays the results of the CLI invocation, but does not display the source code. This is equivalent to having both `:hide-source:` and `:show-results:` options.

But you can override this behavior by explicitly setting the options. Let's say [you only want to display the result](https://github.com/kdeldycke/click-extra/issues/719) of the CLI invocation, without showing the source code defining that CLI. Then you can add `:hide-source:` to the `click:example` directive:

``````{tab-set}
`````{tab-item} MyST Markdown
:sync: myst
````{code-block} markdown
:emphasize-lines: 2
```{click:example}
:hide-source:
from click_extra import echo, extra_command, style

@extra_command
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
.. click:example::
   :hide-source:

   from click_extra import echo, extra_command, style

   @extra_command
   def simple_print():
       echo(f"Just a {style('string', fg='blue')} to print.")

.. click:run::

   invoke(simple_print)
```
`````
``````

Which only renders the `click:run` directive, as the `click:example` doesn't display anything:

```{click:example}
:hide-source:
from click_extra import echo, extra_command, style

@extra_command
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

   assert result.exit_code == 0, "CLI execution failed"
   assert not result.stderr, "Found error messages in <stderr>"
```
`````
``````

In this particular mode the `click:run` produced two code blocks, one for the source code, and one for the results of the invocation:

```{click:run}
:show-source:
result = invoke(simple_print)

assert result.exit_code == 0, "CLI execution failed"
assert not result.stderr, "Found error messages in <stderr>"
```

```{hint}
`:show-results:`/`:hide-results:` options have no effect on the `click:example` directive and will be ignored. That's because this directive does not execute the CLI: it only displays its source code.
```

## Inline tests

The `click:run` directive can also be used to embed tests in your documentation.

You can write tests in your documentation, and they will be executed at build time. This allows you to catch regressions early, and ensure that your documentation is always up-to-date with the latest version of your CLI, in the spirit of [`doctest`](https://docs.python.org/3/library/doctest.html) and [Docs as Tests](https://www.docsastests.com/docs-as-tests/concept/2024/01/09/intro-docs-as-tests.html).

For example, here is a simple CLI:

``````{tab-set}
`````{tab-item} MyST Markdown
:sync: myst
````{code-block} markdown
```{click:example}
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
.. click:example::

   from click import echo, command

   @command
   def yo_cli():
       echo("Yo!")
```
`````
``````

Let's put the code above in a `click:example` directive. And then put the following Python code into a `click:run` block:

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

```{click:example}
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

```{hint}
The CLI runner used by `click:run` is a custom version [derived from the original `click.testing.CliRunner`](https://click.palletsprojects.com/en/stable/api/#click.testing.CliRunner).

It is [called `ExtraCliRunner`](testing.md#click_extra.testing.ExtraCliRunner) and is patched so you can refine your tests by inspecting both `<stdout>` and `<stderr>` independently. It also provides an additional `<output>` stream which simulates what the user sees in its terminal.
```

## ANSI shell sessions

Sphinx extensions from Click Extra automaticcaly integrates the [new ANSI-capable lexers for Pygments](pygments.md#lexers).

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

## Legacy mixed syntax: MyST + reStructuredText

Before MyST was fully integrated into Sphinx, many projects used a mixed syntax setup with MyST and reStructuredText. If you are maintaining such a project or need to ensure compatibility with older documentation, you can use these legacy Sphinx snippets.

This rely on MyST's ability to embed reStructuredText within MyST documents, via the [`{eval-rst}` directive](https://myst-parser.readthedocs.io/en/latest/syntax/roles-and-directives.html#how-directives-parse-content).

So instead of using the `{click:example}` and `{click:run}` MyST directive, you can wrap your reStructuredText code blocks with `{eval-rst}`:

````{code-block} markdown
:emphasize-lines: 1
```{eval-rst}
.. click:example::

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
.. click:example::

   from click import echo, command

   @command
   def yo_cli():
       echo("Yo!")

.. click:run::

    invoke(yo_cli)
```

````{warning}
CLI states and references are lost as soon as an `{eval-rst}` block ends. So a `.. click:example::` directive needs to have all its associated `.. click:run::` calls within the same rST block.

If not, you are likely to encounter execution tracebacks such as:
```pytb
  File ".../click-extra/docs/sphinx.md:372", line 1, in <module>
NameError: name 'yo_cli' is not defined
```
````

## Syntax highlight language

By default, code blocks produced by the directives are automatically highlighted with these languages:
- `click:example`: [`python`](https://pygments.org/docs/lexers/#pygments.lexers.python.PythonLexer)
- `click:run`: [`ansi-shell-session`](pygments.md#lexer-variants)

If for any reason you want to override these defaults, you can pass the language as an optional parameter to the directive.

Let's say you have a CLI that is only printing SQL queries in its output:

```{click:example}
:emphasize-lines: 6
from click_extra import echo, extra_command, option

@extra_command
@option("--name")
def sql_output(name):
    sql_query = f"SELECT * FROM users WHERE name = '{name}';"
    echo(sql_query)
```

Then you can force the SQL Pygments highlighter on its output by passing the [short name of that lexer (i.e. `sql`)](https://pygments.org/docs/lexers/#pygments.lexers.sql.SqlLexer) as the first argument to the directive:

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

See how the output (i.e. the second line above) is now rendered with the `sql` Pygments lexer, which is more appropriate for SQL queries. But of course it also parse and renders the whole block as if it is SQL code, which mess up the rendering of the first line, as it is a shell command.

In fact, if you look at Sphinx logs, you will see that a warning has been raised because of that:

```{code-block} text
.../docs/sphinx.md:257: WARNING: Lexing literal_block "$ sql-output --name Joe\nSELECT * FROM users WHERE name = 'Joe';" as "sql" resulted in an error at token: '$'. Retrying in relaxed mode. [misc.highlighting_failure]
```

```{hint}
Alternatively, you can force syntax highlight with the `:language:` option, which takes precedence over the default language of the directive.
```

## `click_extra.sphinx` API

```{eval-rst}
.. autoclasstree:: click_extra.sphinx
   :strict:
```

```{eval-rst}
.. automodule:: click_extra.sphinx
   :members:
   :undoc-members:
   :show-inheritance:
```
