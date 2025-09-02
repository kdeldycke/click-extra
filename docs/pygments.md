# {octicon}`north-star` Pygments

Click Extra plugs into Pygments to allow for the rendering of ANSI codes in various terminal output.

````{important}
For these helpers to work, you need to install ``click_extra``'s additional dependencies from the ``pygments`` extra group:

```{code-block} shell-session
$ pip install click_extra[pygments]
```
````

## Integration

As soon as [`click-extra` is installed](install.md), all its additional components are automaticcaly registered to Pygments.

Here is a quick way to check the new plugins are visible to Pygments' regular API:

- Formatter:

  ```{code-block} ansi-pycon
  >>> from pygments.formatters import get_formatter_by_name
  >>> get_formatter_by_name("ansi-html")
  <click_extra.pygments.AnsiHtmlFormatter object at 0x1011ff1d0>
  ```

- Filter:

  ```{code-block} ansi-pycon
  >>> from pygments.filters import get_filter_by_name
  >>> get_filter_by_name("ansi-filter")
  <click_extra.pygments.AnsiFilter object at 0x103aaa790>
  ```

- Lexers:

  ```{code-block} ansi-pycon
  >>> from pygments.lexers import get_lexer_by_name
  >>> get_lexer_by_name("ansi-shell-session")
  <pygments.lexers.AnsiBashSessionLexer>
  ```

```{tip}
If `click-extra` is installed but you don't see these new components, you are probably running the snippets above in the wrong Python interpreter.

For instance, you may be running them in a virtual environment. In that case, make sure the virtual environment is activated, and you can `import click_extra` from it.
```

## ANSI HTML formatter

The new `ansi-html` formatter interpret ANSI Pygments tokens and renders them into HTML. It is also responsible for producing the corresponding CSS style to color the HTML elements.

````{warning}
This `ansi-html` formatter is designed to only work with the `ansi-color` lexer. These two components are the only one capable of producing ANSI tokens (`ansi-color`) and rendering them in HTML (`ansi-html`).

[`ansi-color` is implement by `pygments_ansi_color.AnsiColorLexer`](https://github.com/chriskuehl/pygments-ansi-color/blob/2ef0410763eff53f0af736c2f08ebd16fa4abb83/pygments_ansi_color/__init__.py#L203) on which Click Extra depends. So after Click Extra installation, `ansi-color` will be available to Pygments:

```{code-block} ansi-pycon
>>> from pygments.lexers import get_lexer_by_name
>>> get_lexer_by_name("ansi-color")
<pygments.lexers.AnsiColorLexer>
```
````

### Formatter usage

To test it, let's generate a `cowsay.ans` file that is full of ANSI colors:

```{code-block} ansi-shell-session
$ fortune | cowsay | lolcat --force > ./cowsay.ans
$ cat ./cowsay.ans
[38;5;154m [39m[38;5;154m_[39m[38;5;154m_[39m[38;5;148m_[39m[38;5;184m_[39m[38;5;184m_[39m[38;5;184m_[39m[38;5;184m_[39m[38;5;184m_[39m[38;5;184m_[39m[38;5;184m_[39m[38;5;184m_[39m[38;5;184m_[39m[38;5;184m_[39m[38;5;184m_[39m[38;5;178m_[39m[38;5;214m_[39m[38;5;214m_[39m[38;5;214m_[39m[38;5;214m_[39m[38;5;214m_[39m[38;5;214m_[39m[38;5;214m_[39m[38;5;214m_[39m[38;5;214m_[39m[38;5;208m_[39m[38;5;208m_[39m[38;5;208m_[39m[38;5;208m_[39m[38;5;208m_[39m[38;5;208m_[39m[38;5;208m_[39m[38;5;208m_[39m[38;5;208m [39m[38;5;208m[39m
[38;5;148m/[39m[38;5;184m [39m[38;5;184mR[39m[38;5;184me[39m[38;5;184ma[39m[38;5;184ml[39m[38;5;184mi[39m[38;5;184mt[39m[38;5;184my[39m[38;5;184m [39m[38;5;184mi[39m[38;5;184ms[39m[38;5;178m [39m[38;5;214mf[39m[38;5;214mo[39m[38;5;214mr[39m[38;5;214m [39m[38;5;214mp[39m[38;5;214me[39m[38;5;214mo[39m[38;5;214mp[39m[38;5;214ml[39m[38;5;208me[39m[38;5;208m [39m[38;5;208mw[39m[38;5;208mh[39m[38;5;208mo[39m[38;5;208m [39m[38;5;208ml[39m[38;5;208ma[39m[38;5;208mc[39m[38;5;208mk[39m[38;5;209m [39m[38;5;203m\[39m[38;5;203m[39m
[38;5;184m\[39m[38;5;184m [39m[38;5;184mi[39m[38;5;184mm[39m[38;5;184ma[39m[38;5;184mg[39m[38;5;184mi[39m[38;5;184mn[39m[38;5;184ma[39m[38;5;178mt[39m[38;5;214mi[39m[38;5;214mo[39m[38;5;214mn[39m[38;5;214m.[39m[38;5;214m [39m[38;5;214m [39m[38;5;214m [39m[38;5;214m [39m[38;5;214m [39m[38;5;208m [39m[38;5;208m [39m[38;5;208m [39m[38;5;208m [39m[38;5;208m [39m[38;5;208m [39m[38;5;208m [39m[38;5;208m [39m[38;5;208m [39m[38;5;208m [39m[38;5;209m [39m[38;5;203m [39m[38;5;203m [39m[38;5;203m [39m[38;5;203m/[39m[38;5;203m[39m
[38;5;184m [39m[38;5;184m-[39m[38;5;184m-[39m[38;5;184m-[39m[38;5;184m-[39m[38;5;184m-[39m[38;5;178m-[39m[38;5;214m-[39m[38;5;214m-[39m[38;5;214m-[39m[38;5;214m-[39m[38;5;214m-[39m[38;5;214m-[39m[38;5;214m-[39m[38;5;214m-[39m[38;5;214m-[39m[38;5;208m-[39m[38;5;208m-[39m[38;5;208m-[39m[38;5;208m-[39m[38;5;208m-[39m[38;5;208m-[39m[38;5;208m-[39m[38;5;208m-[39m[38;5;208m-[39m[38;5;208m-[39m[38;5;209m-[39m[38;5;203m-[39m[38;5;203m-[39m[38;5;203m-[39m[38;5;203m-[39m[38;5;203m-[39m[38;5;203m-[39m[38;5;203m [39m[38;5;203m[39m
[38;5;184m [39m[38;5;184m [39m[38;5;184m [39m[38;5;178m [39m[38;5;214m [39m[38;5;214m [39m[38;5;214m [39m[38;5;214m [39m[38;5;214m\[39m[38;5;214m [39m[38;5;214m [39m[38;5;214m [39m[38;5;214m^[39m[38;5;208m_[39m[38;5;208m_[39m[38;5;208m^[39m[38;5;208m[39m
[38;5;178m [39m[38;5;214m [39m[38;5;214m [39m[38;5;214m [39m[38;5;214m [39m[38;5;214m [39m[38;5;214m [39m[38;5;214m [39m[38;5;214m [39m[38;5;214m\[39m[38;5;208m [39m[38;5;208m [39m[38;5;208m([39m[38;5;208mo[39m[38;5;208mo[39m[38;5;208m)[39m[38;5;208m\[39m[38;5;208m_[39m[38;5;208m_[39m[38;5;208m_[39m[38;5;209m_[39m[38;5;203m_[39m[38;5;203m_[39m[38;5;203m_[39m[38;5;203m[39m
[38;5;214m [39m[38;5;214m [39m[38;5;214m [39m[38;5;214m [39m[38;5;214m [39m[38;5;214m [39m[38;5;214m [39m[38;5;208m [39m[38;5;208m [39m[38;5;208m [39m[38;5;208m [39m[38;5;208m [39m[38;5;208m([39m[38;5;208m_[39m[38;5;208m_[39m[38;5;208m)[39m[38;5;208m\[39m[38;5;209m [39m[38;5;203m [39m[38;5;203m [39m[38;5;203m [39m[38;5;203m [39m[38;5;203m [39m[38;5;203m [39m[38;5;203m)[39m[38;5;203m\[39m[38;5;203m/[39m[38;5;203m\[39m[38;5;203m[39m
[38;5;214m [39m[38;5;214m [39m[38;5;214m [39m[38;5;214m [39m[38;5;208m [39m[38;5;208m [39m[38;5;208m [39m[38;5;208m [39m[38;5;208m [39m[38;5;208m [39m[38;5;208m [39m[38;5;208m [39m[38;5;208m [39m[38;5;208m [39m[38;5;209m [39m[38;5;203m [39m[38;5;203m|[39m[38;5;203m|[39m[38;5;203m-[39m[38;5;203m-[39m[38;5;203m-[39m[38;5;203m-[39m[38;5;203mw[39m[38;5;203m [39m[38;5;203m|[39m[38;5;203m[39m
[38;5;214m [39m[38;5;208m [39m[38;5;208m [39m[38;5;208m [39m[38;5;208m [39m[38;5;208m [39m[38;5;208m [39m[38;5;208m [39m[38;5;208m [39m[38;5;208m [39m[38;5;208m [39m[38;5;209m [39m[38;5;203m [39m[38;5;203m [39m[38;5;203m [39m[38;5;203m [39m[38;5;203m|[39m[38;5;203m|[39m[38;5;203m [39m[38;5;203m [39m[38;5;203m [39m[38;5;203m [39m[38;5;203m [39m[38;5;198m|[39m[38;5;198m|[39m[38;5;198m[39m
```

We can run our formatter on that file:

```{code-block} python
:emphasize-lines: 10, 12
from pathlib import Path

from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import get_formatter_by_name

lexer = get_lexer_by_name("ansi-color")
formatter = get_formatter_by_name("ansi-html")

ansi_content = Path("./cowsay.ans").read_text()

print(highlight(ansi_content, lexer, formatter))
```

```{hint}
The `ansi-color` lexer parse raw ANSI codes and transform them into custom Pygments tokens, for the formatter to render.

[Pygments' `highlight()`](https://pygments.org/docs/api/#pygments.highlight) is the utility method tying the lexer and formatter together to generate the final output.
```

The code above prints the following HTML:

```{code-block} html
<div class="highlight">
 <pre>
      <span></span>
      <span class="-Color -Color-C154 -C-C154"> __</span>
      <span class="-Color -Color-C148 -C-C148">_</span>
      <span class="-Color -Color-C184 -C-C184">___________</span>
      <span class="-Color -Color-C178 -C-C178">_</span>
      <span class="-Color -Color-C214 -C-C214">_________</span>
      <span class="-Color -Color-C208 -C-C208">________ </span>
      <span class="-Color -Color-C148 -C-C148">/</span>
      <span class="-Color -Color-C184 -C-C184"> Reality is</span>
      <span class="-Color -Color-C178 -C-C178"> </span>
      <span class="-Color -Color-C214 -C-C214">for people</span>
      <span class="-Color -Color-C208 -C-C208"> who lack</span>
      …
   </pre>
</div>
```

And here is how to obtain the corresponding CSS style:

```{code-block} python
:emphasize-lines: 5
from pygments.formatters import get_formatter_by_name

formatter = get_formatter_by_name("ansi-html")

print(formatter.get_style_defs(".highlight"))
```

```{code-block} css
pre {
    line-height: 125%;
}

.highlight .hll {
    background-color: #ffffcc
}

.highlight {
    background: #f8f8f8;
}

.highlight .c {
    color: #3D7B7B;
    font-style: italic
}

/* Comment */
.highlight .err {
    border: 1px solid #FF0000
}

/* Error */
.highlight .o {
    color: #666666
}

/* Operator */
.highlight .-C-BGBlack {
    background-color: #000000
}

/* C.BGBlack */
.highlight .-C-BGBlue {
    background-color: #3465a4
}

/* C.BGBlue */
.highlight .-C-BGBrightBlack {
    background-color: #676767
}

/* C.BGBrightBlack */
.highlight .-C-BGBrightBlue {
    background-color: #6871ff
}

/* C.BGBrightBlue */
.highlight .-C-BGC0 {
    background-color: #000000
}

/* C.BGC0 */
.highlight .-C-BGC100 {
    background-color: #878700
}

/* C.BGC100 */
.highlight .-C-BGC101 {
    background-color: #87875f
}

/* C.BGC101 */
/* … */
```

```{caution}
The `ansi-color` lexer/`ansi-html` formatter combo can only render pure ANSI content. It cannot interpret the regular Pygments tokens produced by [the usual language lexers](https://pygments.org/languages/).

That's why we also maintain a collection of [ANSI-capable lexers for numerous languages](#ansi-language-lexers), as detailed below.
```

## ANSI filter

```{todo}
Write example and tutorial.
```

## ANSI language lexers

Some [languages supported by Pygments](https://pygments.org/languages/) are command lines or code, mixed with [generic output](#click_extra.pygments.DEFAULT_TOKEN_TYPE).

For example, the [`console` lexer can be used to highlight shell sessions](https://pygments.org/docs/terminal-sessions/). The general structure of the shell session will be highlighted by the `console` lexer, including the leading prompt. But the ANSI codes in the output will not be interpreted by `console` and will be rendered as plain text.

To fix that, Click Extra implements ANSI-capable lexers. These can parse both the language syntax and the ANSI codes in the output. So you can use the `ansi-console` lexer instead of `console`, and this `ansi-`-prefixed variant will highlight shell sessions with ANSI codes.

### Lexer variants

Here is the list of new ANSI-capable lexers and the [original lexers](https://pygments.org/languages/) they are based on:

<!-- lexer-table-start -->

| Original Lexer                                                                                             | Original IDs                                     | ANSI variants                                                   |
| ---------------------------------------------------------------------------------------------------------- | ------------------------------------------------ | --------------------------------------------------------------- |
| [`BashSessionLexer`](https://pygments.org/docs/lexers/#pygments.lexers.shell.BashSessionLexer)             | `console`, `shell-session`                       | `ansi-console`, `ansi-shell-session`                            |
| [`DylanConsoleLexer`](https://pygments.org/docs/lexers/#pygments.lexers.dylan.DylanConsoleLexer)           | `dylan-console`, `dylan-repl`                    | `ansi-dylan-console`, `ansi-dylan-repl`                         |
| [`ElixirConsoleLexer`](https://pygments.org/docs/lexers/#pygments.lexers.erlang.ElixirConsoleLexer)        | `iex`                                            | `ansi-iex`                                                      |
| [`ErlangShellLexer`](https://pygments.org/docs/lexers/#pygments.lexers.erlang.ErlangShellLexer)            | `erl`                                            | `ansi-erl`                                                      |
| [`GAPConsoleLexer`](https://pygments.org/docs/lexers/#pygments.lexers.algebra.GAPConsoleLexer)             | `gap-console`, `gap-repl`                        | `ansi-gap-console`, `ansi-gap-repl`                             |
| [`JuliaConsoleLexer`](https://pygments.org/docs/lexers/#pygments.lexers.julia.JuliaConsoleLexer)           | `jlcon`, `julia-repl`                            | `ansi-jlcon`, `ansi-julia-repl`                                 |
| [`MSDOSSessionLexer`](https://pygments.org/docs/lexers/#pygments.lexers.shell.MSDOSSessionLexer)           | `doscon`                                         | `ansi-doscon`                                                   |
| [`MatlabSessionLexer`](https://pygments.org/docs/lexers/#pygments.lexers.matlab.MatlabSessionLexer)        | `matlabsession`                                  | `ansi-matlabsession`                                            |
| [`OutputLexer`](https://pygments.org/docs/lexers/#pygments.lexers.special.OutputLexer)                     | `output`                                         | `ansi-output`                                                   |
| [`PostgresConsoleLexer`](https://pygments.org/docs/lexers/#pygments.lexers.sql.PostgresConsoleLexer)       | `postgres-console`, `postgresql-console`, `psql` | `ansi-postgres-console`, `ansi-postgresql-console`, `ansi-psql` |
| [`PowerShellSessionLexer`](https://pygments.org/docs/lexers/#pygments.lexers.shell.PowerShellSessionLexer) | `ps1con`, `pwsh-session`                         | `ansi-ps1con`, `ansi-pwsh-session`                              |
| [`PsyshConsoleLexer`](https://pygments.org/docs/lexers/#pygments.lexers.php.PsyshConsoleLexer)             | `psysh`                                          | `ansi-psysh`                                                    |
| [`PythonConsoleLexer`](https://pygments.org/docs/lexers/#pygments.lexers.python.PythonConsoleLexer)        | `pycon`, `python-console`                        | `ansi-pycon`, `ansi-python-console`                             |
| [`RConsoleLexer`](https://pygments.org/docs/lexers/#pygments.lexers.r.RConsoleLexer)                       | `rconsole`, `rout`                               | `ansi-rconsole`, `ansi-rout`                                    |
| [`RubyConsoleLexer`](https://pygments.org/docs/lexers/#pygments.lexers.ruby.RubyConsoleLexer)              | `irb`, `rbcon`                                   | `ansi-irb`, `ansi-rbcon`                                        |
| [`SqliteConsoleLexer`](https://pygments.org/docs/lexers/#pygments.lexers.sql.SqliteConsoleLexer)           | `sqlite3`                                        | `ansi-sqlite3`                                                  |
| [`TcshSessionLexer`](https://pygments.org/docs/lexers/#pygments.lexers.shell.TcshSessionLexer)             | `tcshcon`                                        | `ansi-tcshcon`                                                  |

<!-- lexer-table-end -->

### Lexers usage

Let's test one of these lexers. We are familiar with Python so we'll focus on the `pycon` Python console lexer.

First, we will generate some random art in an interactive Python shell:

```{code-block} pycon
>>> import itertools
>>> colors = [f"\033[3{i}m{{}}\033[0m" for i in range(1, 7)]
>>> rainbow = itertools.cycle(colors)
>>> letters = [next(rainbow).format(c) for c in "║▌█║ ANSI Art ▌│║▌"]
>>> art = "".join(letters)
>>> art
'\x1b[35m║\x1b[0m\x1b[36m▌\x1b[0m\x1b[31m█\x1b[0m\x1b[32m║\x1b[0m\x1b[33m \x1b[0m\x1b[34mA\x1b[0m\x1b[35mN\x1b[0m\x1b[36mS\x1b[0m\x1b[31mI\x1b[0m\x1b[32m \x1b[0m\x1b[33mA\x1b[0m\x1b[34mr\x1b[0m\x1b[35mt\x1b[0m\x1b[36m \x1b[0m\x1b[31m▌\x1b[0m\x1b[32m│\x1b[0m\x1b[33m║\x1b[0m\x1b[34m▌\x1b[0m'
```

The code block above is a typical Python console session. You have interactive prompt (`>>>`), pure Python code, and the output of these invocations. It is rendered here with Pygments' original `pycon` lexer.

You can see that the raw Python string `art` contain ANSI escape sequences (`\x1b[XXm`). When we print this string and give the results to Pygments, the ANSI codes are not interpreted and the output is rendered as-is:

```{code-block} pycon
>>> print(art)
[35m║[0m[36m▌[0m[31m█[0m[32m║[0m[33m [0m[34mA[0m[35mN[0m[36mS[0m[31mI[0m[32m [0m[33mA[0m[34mr[0m[35mt[0m[36m [0m[31m▌[0m[32m│[0m[33m║[0m[34m▌[0m
```

If you try to run the snippet above in your own Python console, you will see that the result of the `print(art)` is colored.

That's why you need Click Extra's lexers. If we switch to the new `ansi-pycon` lexer, the output is colored, replicating exactly what you are expecting in your console:

```{code-block} ansi-pycon
>>> print(art)
[35m║[0m[36m▌[0m[31m█[0m[32m║[0m[33m [0m[34mA[0m[35mN[0m[36mS[0m[31mI[0m[32m [0m[33mA[0m[34mr[0m[35mt[0m[36m [0m[31m▌[0m[32m│[0m[33m║[0m[34m▌[0m
```

```{seealso}
All these new lexers [can be used in Sphinx](https://kdeldycke.github.io/click-extra/sphinx.html#ansi-shell-sessions) out of the box, with [a bit of configuration](https://kdeldycke.github.io/click-extra/sphinx.html#setup).
```

### Lexer design

We can check how `pygments_ansi_color`'s `ansi-color` lexer transforms a raw string into ANSI tokens:

```{code-block} ansi-pycon
>>> from pygments.lexers import get_lexer_by_name
>>> ansi_lexer = get_lexer_by_name("ansi-color")
>>> tokens = ansi_lexer.get_tokens(art)
>>> tuple(tokens)
((Token.Color.Magenta, '║'), (Token.Text, ''), (Token.Color.Cyan, '▌'), (Token.Text, ''), (Token.Color.Red, '█'), (Token.Text, ''), (Token.Color.Green, '║'), (Token.Text, ''), (Token.Color.Yellow, ' '), (Token.Text, ''), (Token.Color.Blue, 'A'), (Token.Text, ''), (Token.Color.Magenta, 'N'), (Token.Text, ''), (Token.Color.Cyan, 'S'), (Token.Text, ''), (Token.Color.Red, 'I'), (Token.Text, ''), (Token.Color.Green, ' '), (Token.Text, ''), (Token.Color.Yellow, 'A'), (Token.Text, ''), (Token.Color.Blue, 'r'), (Token.Text, ''), (Token.Color.Magenta, 't'), (Token.Text, ''), (Token.Color.Cyan, ' '), (Token.Text, ''), (Token.Color.Red, '▌'), (Token.Text, ''), (Token.Color.Green, '│'), (Token.Text, ''), (Token.Color.Yellow, '║'), (Token.Text, ''), (Token.Color.Blue, '▌'), (Token.Text, '\n'))
```

See how the raw string is split into Pygments tokens, including the new `Token.Color` tokens. These tokens are then ready to be rendered by [our own `ansi-html` formatter](#ansi-html-formatter).

## `pygmentize` command line

Because they're properly registered to Pygments, all these new components can be invoked with the [`pygmentize` CLI](https://pygments.org/docs/cmdline/).

For example, here is how we can render the `cowsay.ans` file from the [example above](<>) into a standalone HTML file:

```{code-block} ansi-shell-session
$ pygmentize -f ansi-html -O full -o cowsay.html ./cowsay.ans
$ cat cowsay.html
```

```{code-block} html
:caption: `cowsay.html` file generated by `pygmentize` CLI
<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://www.w3.org/TR/html4/strict.dtd">
<!--
generated by Pygments <https://pygments.org/>
Copyright 2006-2023 by the Pygments team.
Licensed under the BSD license, see LICENSE for details.
-->
<html>
 <head>
  <title>
  </title>
  <meta content="text/html; charset=utf-8" http-equiv="content-type"/>
  <style type="text/css">
   /*
         generated by Pygments <https://pygments.org/>
         Copyright 2006-2023 by the Pygments team.
         Licensed under the BSD license, see LICENSE for details.
         */
         pre { line-height: 125%; }
         body { background: #f8f8f8; }
         body .c { color: #3D7B7B; font-style: italic } /* Comment */
         body .err { border: 1px solid #FF0000 } /* Error */
         body .o { color: #666666 } /* Operator */
         body .-Color-BGBlack { background-color: #000000 } /* Color.BGBlack */
         body .-Color-BGBlue { background-color: #3465a4 } /* Color.BGBlue */
         body .-Color-BGBrightBlack { background-color: #676767 } /* Color.BGBrightBlack */
         body .-Color-BGBrightBlue { background-color: #6871ff } /* Color.BGBrightBlue */
         body .-Color-BGCyan { background-color: #34e2e2 } /* Color.BGCyan */
         body .-Color-BGGreen { background-color: #8ae234 } /* Color.BGGreen */
         /* … */
  </style>
 </head>
 <body>
  <h2>
  </h2>
  <div class="highlight">
   <pre>
            <span></span>
            <span class="-Color -Color-C154"> __</span>
            <span class="-Color -Color-C148">_</span>
            <span class="-Color -Color-C184">___________</span>
            <span class="-Color -Color-C178">_</span>
            <span class="-Color -Color-C214">_________</span>
            <span class="-Color -Color-C208">________ </span>
            <span class="-Color -Color-C148">/</span>
            <span class="-Color -Color-C184"> Reality is</span>
            <span class="-Color -Color-C178"> </span>
            <span class="-Color -Color-C214">for people</span>
            <span class="-Color -Color-C208"> who lack</span>
            …
         </pre>
  </div>
 </body>
</html>
```

## `click_extra.pygments` API

```{eval-rst}
.. autoclasstree:: click_extra.pygments
   :strict:
```

```{eval-rst}
.. automodule:: click_extra.pygments
   :members:
   :undoc-members:
   :show-inheritance:
```
