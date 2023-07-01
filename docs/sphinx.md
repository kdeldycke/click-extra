# Sphinx extensions

[Sphinx](https://www.sphinx-doc.org) is the best way to document your Python CLI. Click Extra provides several utilities to improve the quality of life of maintainers.

## Setup

Once [Click Extra is installed](install.md), you can enable its [extensions](https://www.sphinx-doc.org/en/master/usage/configuration.html#confval-extensions) in your Sphinx's `conf.py`:

```python
extensions = ["click_extra.sphinx", ...]
```

## Click directives

Click Extra adds two new directives:

- `.. click:example::` to display any Click-based Python code blocks in Sphinx (and renders like `.. code-block:: python`)
- `.. click:run::` to invoke the CLI defined above, and display the results as if was executed in a terminmal (within a `.. code-block:: ansi-shell-session`)

Thanks to these, you can directly demonstrate the usage of your CLI in your documentation. You no longer have to maintain screenshots of you CLIs. Or copy and paste their outputs to keep them in sync with the latest revision. Click Extra will do that job for you.

```{hint}
These directives are [based on the official `Pallets-Sphinx-Themes`](https://github.com/pallets/pallets-sphinx-themes/blob/main/src/pallets_sphinx_themes/themes/click/domain.py) from Click's authors, but augmented with support for ANSI coloring. That way you can show off your user-friendly CLI in all its glory. 🌈
```

```{seealso}
Click Extra's own documentation extensively use `.. click:example::` and `.. click:run::` directives. [Look around
in its Markdown source files](https://github.com/kdeldycke/click-extra/tree/main/docs) for advanced examples and
inspiration.
```

### Usage

Here is how to define a simple Click-based CLI with the `.. click:example::` directive:

``````{tab-set}
`````{tab-item} Markdown (MyST)
:sync: myst
```{attention}
As you can see in the example below, these Click directives are not recognized as-is by the MyST parser, so you need to wrap them in `{eval-rst}` blocks.
```

````markdown
```{eval-rst}
.. click:example::
    from click_extra import echo, extra_command, option, style

    @extra_command
    @option("--name", prompt="Your name", help="The person to greet.")
    def hello_world(name):
        """Simple program that greets NAME."""
        echo(f"Hello, {style(name, fg='red')}!")
```
````

Thanks to the `.. click:run::` directive, we can invoke this CLI with its `--help` option:

````markdown
```{eval-rst}
.. click:run::
    invoke(hello_world, args=["--help"])
```
````

````{warning}
CLI states and references are lost as soon as an `{eval-rst}` block ends. If you need to run a `.. click:example::` definition multiple times, all its `.. click:run::` calls must happens within the same rST block.

A symptom of that issue is the execution failing with tracebacks such as:
```pytb
Exception occurred:
  File "<docs>", line 1, in <module>
NameError: name 'hello_world' is not defined
```
````
`````

`````{tab-item} reStructuredText
:sync: rst

```rst
.. click:example::
    from click_extra import echo, extra_command, option, style

    @extra_command
    @option("--name", prompt="Your name", help="The person to greet.")
    def hello_world(name):
        """Simple program that greets NAME."""
        echo(f"Hello, {style(name, fg='red')}!")
```

Thanks to the `.. click:run::` directive, we can invoke this CLI with its `--help` option:

```rst
.. click:run::
    invoke(hello_world, args=["--help"])
```
`````
``````

Placed in your Sphinx documentation, the two blocks above renders to:

```{eval-rst}
.. click:example::
    from click_extra import echo, extra_command, option, style

    @extra_command
    @option("--name", prompt="Your name", help="The person to greet.")
    def hello_world(name):
        """Simple program that greets NAME."""
        echo(f"Hello, {style(name, fg='red')}!")

.. click:run::
    from textwrap import dedent
    result = invoke(hello_world, args=["--help"])
    assert result.stdout.startswith(dedent(
        """\
        \x1b[94m\x1b[1m\x1b[4mUsage:\x1b[0m \x1b[97mhello-world\x1b[0m \x1b[36m\x1b[2m[OPTIONS]\x1b[0m

          Simple program that greets NAME.

        \x1b[94m\x1b[1m\x1b[4mOptions:\x1b[0m
          \x1b[36m--name\x1b[0m \x1b[36m\x1b[2mTEXT\x1b[0m               The person to greet.
          \x1b[36m--time\x1b[0m / \x1b[36m--no-time\x1b[0m        Measure and print elapsed execution time."""
    ))

This is perfect for documentation, as it shows both the source code of the CLI and its results.

See for instance how the CLI code is properly rendered as a Python code block with syntax highlighting. And how the invocation of that CLI renders into a terminal session with ANSI coloring of output.

You can then invoke that CLI again with its ``--name`` option:

.. code-block:: rst

    .. click:run::
        invoke(hello_world, args=["--name", "Joe"])

Which renders in Sphinx like it was executed in a terminal block:

.. click:run::
    result = invoke(hello_world, args=["--name", "Joe"])
    assert result.output == 'Hello, \x1b[31mJoe\x1b[0m!\n'
```

```{tip}
`.. click:example::` and `.. click:run::` directives works well with standard vanilla `click`-based CLIs.

In the example above, we choose to import our CLI primitives from the `click-extra` module instead, to demonstrate the coloring of terminal session outputs, as `click-extra` provides [fancy coloring of help screens](colorize.md) by default.
```

### Inline tests

The `.. click:run::` directive can also be used to embed tests in your documentation.

These blocks are Python code executed at build time, so you can use them to validate the behavior of your CLI. This allow you to catch regressions, outdated documentation or changes in terminal output.

For example, here is a simple CLI:

```{eval-rst}
.. click:example::
    from click_extra import echo, extra_command, option, style

    @extra_command
    @option("--name", prompt="Your name", help="The person to greet.")
    def hello_world(name):
        """Simple program that greets NAME."""
        echo(f"Hello, {style(name, fg='red')}!")

If we put this CLI code in a ``.. click:example::`` directive, we can associate it with the following ``.. click:run::`` block:

.. code-block:: rst

    .. click:run::
        result = invoke(hello_world, args=["--help"])

        assert result.exit_code == 0, "CLI execution failed"
        assert not result.stderr, "error message in <stderr>"
        assert "--show-params" in result.stdout, "--show-params not found in help screeen"

See how we collect the ``result`` of the ``invoke`` command, and inspect the ``exit_code``, ``stderr`` and ``stdout`` of the CLI with ``assert`` statements.

If for any reason our CLI changes and its help screen is no longer what we expect, the test will fail and the documentation build will break with a message similar to:

.. code-block:: pytb

    Exception occurred:
    File "<docs>", line 5, in <module>
    AssertionError: --show-params not found in help screeen

Having your build fails when something unexpected happens is a great signal to catch regressions early.

On the other hand, if the build succeed, the ``.. click:run::`` block will render as usual with the result of the invocation:

.. click:run::
    result = invoke(hello_world, args=["--help"])

    assert result.exit_code == 0, "CLI execution failed"
    assert not result.stderr, "error message in <stderr>"
    assert "--show-params" in result.stdout, "--show-params not found in help screeen"
```

```{tip}
In a way, you can consider this kind of inline tests as like [doctests](https://docs.python.org/3/library/doctest.html), but for Click CLIs.

Look around in the sources of Click Extra's documentation for more examples of inline tests.
```

```{hint}
The CLI runner used by `.. click:run::` is a custom version [derived from the original `click.testing.CliRunner`](https://click.palletsprojects.com/en/8.1.x/api/#click.testing.CliRunner).

It is [called `ExtraCliRunner`](testing.md#click_extra.testing.ExtraCliRunner) and is patched so you can refine your tests by inspecting both `<stdout>` and `<stderr>` independently. It also provides an additional `<output>` stream which simulates what the user sees in its terminal.
```

## ANSI shell sessions

Sphinx extensions from Click Extra automaticcaly integrates the [new ANSI-capable lexers for Pygments](https://kdeldycke.github.io/click-extra/pygments.html#lexers).

This allows you to render colored shell sessions in code blocks by referring to the `ansi-` prefixed lexers:

``````{tab-set}

`````{tab-item} Markdown (MyST)
:sync: myst

````markdown
```ansi-shell-session
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
```rst
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

```ansi-shell-session
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
