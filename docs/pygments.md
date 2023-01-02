# Pygments extensions

Click Extra extends Pygments to allow for the rendering of ANSI codes in terminal outputs.

## Setup

As soon as [`click-extra` is installed](install.md), all its additionnal lexers, styles and filters will be automaticcaly registered to Pygments.

## Lexers

Click Extra adds new lexers capable of parsing ANSI code in various shell-like sessions. I.e. command lines or code, including a prompt, interspersed with output.

| Original Lexer                                                                                             | Original IDs                                     | ANSI variants                                                   |
| ---------------------------------------------------------------------------------------------------------- | ------------------------------------------------ | --------------------------------------------------------------- |
| [`BashSessionLexer`](https://pygments.org/docs/lexers/#pygments.lexers.shell.BashSessionLexer)             | `console`, `shell-session`                       | `ansi-console`, `ansi-shell-session`                            |
| [`DylanConsoleLexer`](https://pygments.org/docs/lexers/#pygments.lexers.dylan.DylanConsoleLexer)           | `dylan-console`, `dylan-repl`                    | `ansi-dylan-console`, `ansi-dylan-repl`                         |
| [`ElixirConsoleLexer`](https://pygments.org/docs/lexers/#pygments.lexers.erlang.ElixirConsoleLexer)        | `iex`                                            | `ansi-iex`                                                      |
| [`ErlangShellLexer`](https://pygments.org/docs/lexers/#pygments.lexers.erlang.ErlangShellLexer)            | `erl`                                            | `ansi-erl`                                                      |
| [`GAPConsoleLexer`](https://pygments.org/docs/lexers/#pygments.lexers.algebra.GAPConsoleLexer)             | `gap`                                            | `ansi-gap`                                                      |
| [`JuliaConsoleLexer`](https://pygments.org/docs/lexers/#pygments.lexers.julia.JuliaConsoleLexer)           | `jlcon`, `julia-repl`                            | `ansi-jlcon`, `ansi-julia-repl`                                 |
| [`MSDOSSessionLexer`](https://pygments.org/docs/lexers/#pygments.lexers.shell.MSDOSSessionLexer)           | `doscon`                                         | `ansi-doscon`                                                   |
| [`MatlabSessionLexer`](https://pygments.org/docs/lexers/#pygments.lexers.matlab.MatlabSessionLexer)        | `matlabsession`                                  | `ansi-matlabsession`                                            |
| [`OutputLexer`](https://pygments.org/docs/lexers/#pygments.lexers.special.OutputLexer)                     | `output`                                         | `ansi-output`                                                   |
| [`PostgresConsoleLexer`](https://pygments.org/docs/lexers/#pygments.lexers.sql.PostgresConsoleLexer)       | `psql`, `postgresql-console`, `postgres-console` | `ansi-psql`, `ansi-postgresql-console`, `ansi-postgres-console` |
| [`PowerShellSessionLexer`](https://pygments.org/docs/lexers/#pygments.lexers.shell.PowerShellSessionLexer) | `pwsh-session`, `ps1con`                         | `ansi-pwsh-session`, `ansi-ps1con`                              |
| [`PsyshConsoleLexer`](https://pygments.org/docs/lexers/#pygments.lexers.php.PsyshConsoleLexer)             | `psysh`                                          | `ansi-psysh`                                                    |
| [`PythonConsoleLexer`](https://pygments.org/docs/lexers/#pygments.lexers.python.PythonConsoleLexer)        | `pycon`                                          | `ansi-pycon`                                                    |
| [`RConsoleLexer`](https://pygments.org/docs/lexers/#pygments.lexers.r.RConsoleLexer)                       | `rconsole`, `rout`                               | `ansi-rconsole`, `ansi-rout`                                    |
| [`RubyConsoleLexer`](https://pygments.org/docs/lexers/#pygments.lexers.ruby.RubyConsoleLexer)              | `rbcon`, `irb`                                   | `ansi-rbcon`, `ansi-irb`                                        |
| [`SqliteConsoleLexer`](https://pygments.org/docs/lexers/#pygments.lexers.sql.SqliteConsoleLexer)           | `sqlite3`                                        | `ansi-sqlite3`                                                  |
| [`TcshSessionLexer`](https://pygments.org/docs/lexers/#pygments.lexers.shell.TcshSessionLexer)             | `tcshcon`                                        | `ansi-tcshcon`                                                  |

To check the new lexers are properly register by Pygments:

```ansi-pycon
>>> from pygments import lexers
>>> ansi_lexer = lexers.get_lexer_by_name('ansi-shell-session')
>>> ansi_lexer
<pygments.lexers.AnsiBashSessionLexer>
```

Let's test the lexer. But first, we will generate some random art:

```ansi-pycon
>>> import itertools
>>> colors = [f"\033[3{i}m{{}}\033[0m" for i in range(1, 7)]
>>> rainbow = itertools.cycle(colors)
>>> letters = [next(rainbow).format(c) for c in "║▌█║ ANSI Art ▌│║▌"]
>>> art = "".join(letters)
>>> art
'\x1b[35m║\x1b[0m\x1b[36m▌\x1b[0m\x1b[31m█\x1b[0m\x1b[32m║\x1b[0m\x1b[33m \x1b[0m\x1b[34mA\x1b[0m\x1b[35mN\x1b[0m\x1b[36mS\x1b[0m\x1b[31mI\x1b[0m\x1b[32m \x1b[0m\x1b[33mA\x1b[0m\x1b[34mr\x1b[0m\x1b[35mt\x1b[0m\x1b[36m \x1b[0m\x1b[31m▌\x1b[0m\x1b[32m│\x1b[0m\x1b[33m║\x1b[0m\x1b[34m▌\x1b[0m'
>>> print(art)
[35m║[0m[36m▌[0m[31m█[0m[32m║[0m[33m [0m[34mA[0m[35mN[0m[36mS[0m[31mI[0m[32m [0m[33mA[0m[34mr[0m[35mt[0m[36m [0m[31m▌[0m[32m│[0m[33m║[0m[34m▌[0m
```

We can now see how the new lexers transforms a raw strings into ANSI tokens:

```ansi-pycon
>>> tokens = ansi_lexer.get_tokens(art)
>>> tuple(tokens)
((Token.Color.Magenta, '║'), (Token.Text, ''), (Token.Color.Cyan, '▌'), (Token.Text, ''), (Token.Color.Red, '█'), (Token.Text, ''), (Token.Color.Green, '║'), (Token.Text, ''), (Token.Color.Yellow, ' '), (Token.Text, ''), (Token.Color.Blue, 'A'), (Token.Text, ''), (Token.Color.Magenta, 'N'), (Token.Text, ''), (Token.Color.Cyan, 'S'), (Token.Text, ''), (Token.Color.Red, 'I'), (Token.Text, ''), (Token.Color.Green, ' '), (Token.Text, ''), (Token.Color.Yellow, 'A'), (Token.Text, ''), (Token.Color.Blue, 'r'), (Token.Text, ''), (Token.Color.Magenta, 't'), (Token.Text, ''), (Token.Color.Cyan, ' '), (Token.Text, ''), (Token.Color.Red, '▌'), (Token.Text, ''), (Token.Color.Green, '│'), (Token.Text, ''), (Token.Color.Yellow, '║'), (Token.Text, ''), (Token.Color.Blue, '▌'), (Token.Text, '\n'))
```

```{seealso}
All these new lexers [can be used in Sphinx](https://kdeldycke.github.io/click-extra/sphinx.html#ansi-shell-sessions) with [a bit of configuration](https://kdeldycke.github.io/click-extra/sphinx.html#setup).
```

## Filters

```{todo}
Write example and tutorial.
```

## Formatters

```{todo}
Write example and tutorial.
```

## Styles

```{todo}
Write example and tutorial.
```

## `click_extra.pygments` API

```{eval-rst}
.. automodule:: click_extra.pygments
   :members:
   :undoc-members:
   :show-inheritance:
```
