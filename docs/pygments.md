# {octicon}`file-code` Pygments

This package ships a set of Pygments components that make terminal-style content first-class in any Pygments pipeline:

- A lexer ([`ansi-color`](#ansi-html-formatter)) that parses raw ANSI/ECMA-48 escape sequences: text attributes (bold, faint, italic, underline, blink, reverse, strikethrough, overline), the standard 16 named colors, the [256-color indexed palette](#color-palette-swatch), [24-bit RGB](#bit-true-color), and [OSC 8 hyperlinks](#osc-8-hyperlinks).
- An HTML formatter ([`ansi-html`](#ansi-html-formatter)) that renders those tokens as styled `<span>`{l=html} elements and OSC 8 hyperlinks as `<a>`{l=html} tags. Works in CSS-class mode or [`noclasses=True` inline-style mode](#inline-styles-self-contained-html).
- [ANSI-aware variants](#ansi-language-lexers) of every shell-session and REPL lexer Pygments ships (`ansi-shell-session`, `ansi-pycon`, `ansi-rb`, …) so terminal output embedded in code blocks renders with its colors instead of as raw escape codes.
- A filter ([`ansi-filter`](#ansi-filter)) that intercepts `Generic.Output` tokens from any session lexer and re-lexes them through `ansi-color`. This is the seam used by the ANSI session lexers, but you can also attach it to your own lexer.

These are plain Pygments entry points: once [installed](#install), they are usable from [`pygmentize`](#pygmentize-command-line), `pygments.highlight()`, and any tool that consumes Pygments (Sphinx, MkDocs, Hexo, mdBook, Jekyll, GitHub-flavored Markdown renderers that use Pygments, …).

## Install

The Pygments components ship as an optional extra to keep the base install lean:

```{code-block} shell-session
$ pip install click_extra[pygments]
```

You do not need to use Click, the Click Extra CLI, or the Sphinx/MkDocs integrations to use any of these components: the `pygments` extra pulls in only Pygments and its prerequisites. The package name (`click_extra`) is a historical artifact of where these components first lived; the Pygments components are stable, independent, and have no Click dependency at runtime.

## Integration

Installing the package automatically registers all components with Pygments through standard `pygments.lexers`, `pygments.filters`, and `pygments.formatters` entry points.

Quick check that the new plugins are visible to Pygments' regular API:

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

After Click Extra installation, `ansi-color` will be available to Pygments:

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
      <span class="-Ansi-C154 -Ansi -Ansi-C154"> __</span>
      <span class="-Ansi-C148 -Ansi -Ansi-C148">_</span>
      <span class="-Ansi-C184 -Ansi -Ansi-C184">___________</span>
      <span class="-Ansi-C178 -Ansi -Ansi-C178">_</span>
      <span class="-Ansi-C214 -Ansi -Ansi-C214">_________</span>
      <span class="-Ansi-C208 -Ansi -Ansi-C208">________ </span>
      <span class="-Ansi-C148 -Ansi -Ansi-C148">/</span>
      <span class="-Ansi-C184 -Ansi -Ansi-C184"> Reality is</span>
      <span class="-Ansi-C178 -Ansi -Ansi-C178"> </span>
      <span class="-Ansi-C214 -Ansi -Ansi-C214">for people</span>
      <span class="-Ansi-C208 -Ansi -Ansi-C208"> who lack</span>
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
.highlight .-Ansi-BGBlack {
    background-color: #000000
}

/* Ansi.BGBlack */
.highlight .-Ansi-BGBlue {
    background-color: #3465a4
}

/* Ansi.BGBlue */
.highlight .-Ansi-BGC0 {
    background-color: #000000
}

/* Ansi.BGC0 */
.highlight .-Ansi-Red {
    color: #ef2929
}

/* Ansi.Red */
.highlight .-Ansi-Bold {
    font-weight: bold
}

/* Ansi.Bold */
/* … */
```

```{caution}
The `ansi-color` lexer/`ansi-html` formatter combo can only render pure ANSI content. It cannot interpret the regular Pygments tokens produced by [the usual language lexers](https://pygments.org/languages/).

That's why we also maintain a collection of [ANSI-capable lexers for numerous languages](#ansi-language-lexers), as detailed below.
```

### Inline styles (self-contained HTML)

For HTML output that does not depend on an external stylesheet, pass `noclasses=True` to the formatter. Pygments then converts every token's CSS class into an inline `style="..."`{l=html} attribute:

```{python:run}
:show-source:
:emphasize-lines: 7
:emphasize-result-lines: 1
:language: html
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import get_formatter_by_name


lexer = get_lexer_by_name("ansi-color")
formatter = get_formatter_by_name("ansi-html", noclasses=True)

print(highlight("\x1b[1;31mError:\x1b[0m file not found\n", lexer, formatter))
```

This mode is the right pick when embedding output in emails, static reports, or any context where shipping a separate stylesheet is impractical. It pairs naturally with the [24-bit true-color mode](#bit-true-color), which is itself inline-style based.

## ANSI filter

The `AnsiFilter` is a Pygments filter that intercepts tokens of a specific type (by default `Generic.Output`) and re-lexes their content through `AnsiColorLexer`. This is the glue that makes the [ANSI language lexers](#ansi-language-lexers) work: a session lexer like `BashSessionLexer` splits input into prompts (`Generic.Prompt`) and output (`Generic.Output`), then the `AnsiFilter` transforms the output tokens into colored `Token.Ansi.*` tokens.

A short example showing how the filter transforms a token stream. The source highlight points to the `filter()` call; the result highlight points to the line where the styled `Token.Ansi.Bold.Red` token replaces the original `Generic.Output`:

```{python:run}
:show-source:
:emphasize-lines: 12
:emphasize-result-lines: 2
from pygments.token import Generic

from click_extra.pygments import AnsiFilter


filt = AnsiFilter()

# Simulate what a session lexer produces: a prompt token and an output
# token containing ANSI escape codes.
stream = [
    (Generic.Prompt, "$ "),
    (Generic.Output, "\x1b[1;31mError:\x1b[0m file not found\n"),
]

for token_type, value in filt.filter(None, stream):
    print(f"  {token_type!s:30} {value!r}")
```

The prompt token passes through unchanged, the output token is split into styled `Token.Ansi.*` tokens, which `AnsiHtmlFormatter` then renders with CSS classes (or inline styles, see [below](#inline-styles-self-contained-html)).

You can attach `AnsiFilter` to any custom lexer that emits `Generic.Output`:

```{code-block} python
:emphasize-lines: 6
from pygments.lexers import get_lexer_by_name
from click_extra.pygments import AnsiFilter


lexer = get_lexer_by_name("docker")  # or any lexer of yours
lexer.add_filter(AnsiFilter())
```

Pass `token_type="Generic.Error"` (or any other token type) to redirect the filter at a different stream.

## ANSI language lexers

Some [languages supported by Pygments](https://pygments.org/languages/) are command lines or code, mixed with {py:data}`generic output <click_extra.pygments.DEFAULT_TOKEN_TYPE>`.

For example, the [`console` lexer can be used to highlight shell sessions](https://pygments.org/docs/terminal-sessions/). The general structure of the shell session will be highlighted by the `console` lexer, including the leading prompt. But the ANSI codes in the output will not be interpreted by `console` and will be rendered as plain text.

To fix that, this package implements ANSI-capable lexers. These can parse both the language syntax and the ANSI codes in the output. So you can use the `ansi-console` lexer instead of `console`, and this `ansi-`-prefixed variant will highlight shell sessions with ANSI codes.

### Lexer variants

Here is the list of new ANSI-capable lexers and the [original lexers](https://pygments.org/languages/) they are based on:

```{python:render}
from click_extra.pygments import LEXER_MAP
from click_extra.table import TableFormat, render_table

rows = []
for orig_lexer, ansi_lexer in sorted(
    LEXER_MAP.items(), key=lambda i: i[0].__qualname__
):
    rows.append([
        f"[`{orig_lexer.__qualname__}`](https://pygments.org/docs/lexers/#"
        f"{orig_lexer.__module__}.{orig_lexer.__qualname__})",
        ", ".join(f"`{a}`" for a in sorted(orig_lexer.aliases)),
        ", ".join(f"`{a}`" for a in sorted(ansi_lexer.aliases)),
    ])

print(
    render_table(
        rows,
        table_format=TableFormat.GITHUB,
        headers=["Original Lexer", "Original IDs", "ANSI variants"],
        colalign=["left", "left", "left"],
    )
)
```

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
Because they are registered as standard Pygments entry points, these lexers also work out of the box with any tool that drives Pygments through `get_lexer_by_name()` — including [Sphinx](sphinx.md#ansi-shell-sessions), [MkDocs](mkdocs.md), Hexo, mdBook, Jekyll, and similar.
```

### Lexer design

We can check how the `ansi-color` lexer transforms a raw string into ANSI tokens:

```{code-block} ansi-pycon
>>> from pygments.lexers import get_lexer_by_name
>>> ansi_lexer = get_lexer_by_name("ansi-color")
>>> tokens = ansi_lexer.get_tokens(art)
>>> tuple(tokens)
((Token.Ansi.Magenta, '║'), (Token.Text, ''), (Token.Ansi.Cyan, '▌'), (Token.Text, ''), (Token.Ansi.Red, '█'), (Token.Text, ''), (Token.Ansi.Green, '║'), (Token.Text, ''), (Token.Ansi.Yellow, ' '), (Token.Text, ''), (Token.Ansi.Blue, 'A'), (Token.Text, ''), (Token.Ansi.Magenta, 'N'), (Token.Text, ''), (Token.Ansi.Cyan, 'S'), (Token.Text, ''), (Token.Ansi.Red, 'I'), (Token.Text, ''), (Token.Ansi.Green, ' '), (Token.Text, ''), (Token.Ansi.Yellow, 'A'), (Token.Text, ''), (Token.Ansi.Blue, 'r'), (Token.Text, ''), (Token.Ansi.Magenta, 't'), (Token.Text, ''), (Token.Ansi.Cyan, ' '), (Token.Text, ''), (Token.Ansi.Red, '▌'), (Token.Text, ''), (Token.Ansi.Green, '│'), (Token.Text, ''), (Token.Ansi.Yellow, '║'), (Token.Text, ''), (Token.Ansi.Blue, '▌'), (Token.Text, '\n'))
```

See how the raw string is split into Pygments tokens, including the `Token.Ansi` tokens. These tokens are then ready to be rendered by [our own `ansi-html` formatter](#ansi-html-formatter).

## `pygmentize` command line

Because they're properly registered to Pygments, all these new components can be invoked with the [`pygmentize` CLI](https://pygments.org/docs/cmdline/).

For example, here is how we can render the `cowsay.ans` file from the [example above](#formatter-usage) into a standalone HTML file:

```{code-block} ansi-shell-session
$ pygmentize -f ansi-html -O full -o cowsay.html ./cowsay.ans
$ cat cowsay.html
```

```{code-block} html
:caption: `cowsay.html` file generated by `pygmentize` CLI
<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://www.w3.org/TR/html4/strict.dtd">
<html>
 <head>
  <style type="text/css">
         pre { line-height: 125%; }
         body { background: #f8f8f8; }
         body .-Ansi-BGBlack { background-color: #000000 } /* Ansi.BGBlack */
         body .-Ansi-BGBlue { background-color: #3465a4 } /* Ansi.BGBlue */
         body .-Ansi-Red { color: #ef2929 } /* Ansi.Red */
         body .-Ansi-Bold { font-weight: bold } /* Ansi.Bold */
         /* … */
  </style>
 </head>
 <body>
  <div class="highlight">
   <pre>
            <span></span>
            <span class="-Ansi-C154 -Ansi -Ansi-C154"> __</span>
            <span class="-Ansi-C148 -Ansi -Ansi-C148">_</span>
            <span class="-Ansi-C184 -Ansi -Ansi-C184">___________</span>
            …
         </pre>
  </div>
 </body>
</html>
```

## 24-bit true color

The `ansi-color` lexer accepts `SGR 38;2;r;g;b` and `48;2;r;g;b` (24-bit RGB) sequences and can render them either quantized to the 256-color palette (default) or as raw RGB inline styles. The difference is most visible on a smooth gradient:

````{python:render}
import colorsys

from pygments import highlight

from click_extra.pygments import AnsiColorLexer, AnsiHtmlFormatter

steps = []
for i in range(64):
    r, g, b = (round(c * 255) for c in colorsys.hsv_to_rgb(i / 64, 1, 1))
    steps.append(f"\x1b[38;2;{r};{g};{b}m█")
gradient = "".join(steps) + "\x1b[0m"

formatter = AnsiHtmlFormatter(nowrap=True)
quantized = highlight(gradient, AnsiColorLexer(), formatter)
truecolor = highlight(gradient, AnsiColorLexer(true_color=True), formatter)

# Wrap each ``<pre>`` in ``<div class="highlight">`` so the Pygments stylesheet's
# ``.highlight .-Ansi-*`` rules scope correctly to the quantized row. The true-color
# row carries inline styles and renders identically with or without the wrapper.
print("```{raw} html")
print("<p><strong>Default (quantized to 256 colors):</strong></p>")
print(
    f'<div class="highlight"><pre style="font-size: 1.1em; line-height: 1">'
    f"{quantized}</pre></div>"
)
print("<p><strong>Opt-in 24-bit true color:</strong></p>")
print(
    f'<div class="highlight"><pre style="font-size: 1.1em; line-height: 1">'
    f"{truecolor}</pre></div>"
)
print("```")
````

The first row bands visibly where adjacent gradient steps collapse onto the same 256-color palette entry. The second row preserves all 64 distinct hex values.

### When each mode fits

The default (quantization) works for nearly all terminal output: the 6×6×6 cube and 24-step grayscale ramp are visually close, the resulting CSS is small, and it stays compatible with Furo's dark-mode stylesheet swap. Smooth gradients (`lolcat`-style output, `bat` themes with custom palettes, terminal recordings of TUI applications) are where the approximation becomes noticeable, and where the opt-in 24-bit mode pays off.

### How to opt in

Pass `true_color=True` to the lexer:

```{python:run}
:emphasize-lines: 10
:emphasize-result-lines: 2
:show-source:
from click_extra.pygments import AnsiColorLexer


text = "\x1b[38;2;255;165;0morange\x1b[0m"

# Default: quantize to nearest 256-color palette entry.
quantized = list(AnsiColorLexer().get_tokens(text))

# Opt-in: preserve raw RGB hex.
truecolor = list(AnsiColorLexer(true_color=True).get_tokens(text))

print(f"quantized: {quantized}")
print(f"truecolor: {truecolor}")
```

The flag also flows through `AnsiFilter` and the [ANSI language lexers](#ansi-language-lexers):

```{code-block} python
:emphasize-lines: 3
from pygments.lexers import get_lexer_by_name

lexer = get_lexer_by_name("ansi-shell-session", true_color=True)
```

### How it renders

When true-color tokens reach `AnsiHtmlFormatter`, they are rendered as inline `<span style="color: #rrggbb">`{l=html} / `<span style="background-color: #rrggbb">`{l=html} tags. Other token components on the same span (bold, italic, named colors, palette indices) keep their CSS-class rendering, so a bold-orange-on-blue span ends up as nested `<span class="-Ansi-Bold"><span style="color: #ffa500"><span style="background-color: #004488">…</span></span></span>`{l=html}.

The CSS classes for the quantized rendering resolve through the Pygments stylesheet; the true-color spans carry their colors as inline `style="color: #rrggbb"`{l=html} attributes and render identically regardless of stylesheet.

```{warning}
Inline styles bypass the Pygments stylesheet entirely. Furo's dark-mode CSS swap cannot recolor them, but this matches how the 256-color palette already works (its hex values are baked into the stylesheet at generation time). ANSI colors are absolute by design: a red `\e[31m` should look red regardless of theme.
```

```{seealso}
Pygments has tracked 24-bit terminal rendering for years without a built-in HTML path: see [pygments/pygments#849](https://github.com/pygments/pygments/issues/849) (closed without a 24-bit formatter) and [pygments/pygments#1644](https://github.com/pygments/pygments/issues/1644) (subclassing the HTML formatter to add ANSI inline styles is fragile across releases). The `pygments-ansi-color` project hits the same architectural wall: see [chriskuehl/pygments-ansi-color#5](https://github.com/chriskuehl/pygments-ansi-color/issues/5) (256-color rendering breaks with `noclasses=True`, the inline-style mode), [chriskuehl/pygments-ansi-color#31](https://github.com/chriskuehl/pygments-ansi-color/issues/31), and [chriskuehl/pygments-ansi-color#33](https://github.com/chriskuehl/pygments-ansi-color/issues/33).
```

## OSC 8 hyperlinks

Terminal hyperlinks ([OSC 8](https://gist.github.com/egmontkob/eb114294efbcd5adb1944c9f3cb5feda)) in CLI output are rendered as clickable HTML `<a>` tags.
Tools like [Rich](https://rich.readthedocs.io/) and modern CLI frameworks emit these sequences to make URLs clickable in terminals that support them.

The `AnsiColorLexer` parses the OSC 8 escape sequences and the `AnsiHtmlFormatter` converts them into proper HTML links, preserving any ANSI color styling on the link text.
Only URLs with safe schemes (`http`, `https`, `mailto`, `ftp`, `ftps`) are rendered as links.
All other OSC sequences (like window title changes) are silently stripped.

## 256-color palette swatch

A live proof that the full 256-color indexed palette renders correctly through the pipeline. Each cell sets foreground and background to the same index, producing a solid color block; the second column of each pair is bold.

```{click:source}
:hide-source:
from click_extra.cli import demo
```

```{click:run}
result = invoke(demo, args=["palette"], env={"FORCE_COLOR": "1"})
assert result.exit_code == 0
assert "\x1b[38;5;" in result.output
```

The same swatch can be reproduced from any Python script — the output above is captured from `click-extra palette`, but the underlying ANSI text is what `pygmentize -l ansi-color -f ansi-html` consumes:

```{code-block} python
swatch = "\x1b[38;5;{0};48;5;{0}m\u2588\x1b[1m\u2588\x1b[m"
ansi_text = "".join(swatch.format(i) for i in range(256))
```

```{seealso}
This package's own CLI ships several other demo subcommands (`colors`, `styles`, `8color`, `gradient`) under [Colors and styles](colorize.md#colors-and-styles): they are useful as ready-made ANSI fixtures even if you do not use the CLI itself.
```

## `click_extra.pygments` API

```{eval-rst}
.. autoclasstree:: click_extra.pygments
   :strict:

.. automodule:: click_extra.pygments
   :members:
   :undoc-members:
   :show-inheritance:
```
