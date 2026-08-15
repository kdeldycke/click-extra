# {octicon}`device-camera` CLI screenshots

click-extra produces colored terminal output, and inside this Sphinx documentation the [`click:run`](sphinx.md) directive executes each CLI and renders its real output at build time, so these pages need no screenshots. A README on GitHub or PyPI, a slide, a social post or a page of your own cannot run code, and those surfaces need a capture instead. click-extra ships the command that produces one, as an image or as HTML.

## The `screenshot` command

`click-extra screenshot` runs a CLI, captures its colored output and writes it out. Point it at any command, with `--` separating your CLI's own options from the ones above:

```shell-session
$ click-extra screenshot --output cli-help.svg -- my-cli --help
```

### Two formats, two surfaces

The extension of `--output` picks what gets written, and the two are not interchangeable:

| Format  | Text is                          | Goes where                                                    | Needs                  |
| :------ | :------------------------------- | :------------------------------------------------------------ | :--------------------- |
| `.svg`  | a picture                        | a surface that strips inline HTML: a README on GitHub or PyPI | the `screenshot` extra |
| `.html` | selectable, searchable, copyable | a page you own: your site, a blog post, a slide deck          | nothing                |

So the choice is really made for you. GitHub and PyPI render an image and drop inline styling, which leaves a README no option but SVG. Everywhere you control the markup, HTML is the better artifact: a reader can select a flag out of the help screen and paste it into their terminal, and search finds it.

Only SVG needs Rich:

```shell-session
$ uv pip install "click-extra[screenshot]"
```

HTML is built on {func}`click_extra.styling.ansi_to_html`, which ships with the package, so it is always available:

```shell-session
$ click-extra screenshot --output cli-help.html -- my-cli --help
```

That writes a standalone document. Add `--fragment` to get the bare `<pre>` instead, styled inline so it needs no stylesheet from the page you paste it into.

```{click:run}
from click_extra.cli import screenshot_cmd
result = invoke(screenshot_cmd, args=["--help"])
assert result.exit_code == 0
assert "--columns" in result.stdout
assert "--merge-stderr" in result.stdout
```

Three things it settles that a general-purpose capture tool leaves to you:

- Colors, which a command strips on its own the moment its output is a pipe rather than a terminal. The capture runs under {func}`click_extra.color.forced_color`, setting the `FORCE_COLOR` lever both Click's and Rich's color systems obey and clearing any `NO_COLOR` the environment carries.
- Width, where `--columns` pins what the command wraps to *and* what the image is drawn at. Let those two disagree and the rendered lines overrun the image.
- `stderr`, which stays out of the capture unless `--merge-stderr` asks for it. That is what keeps a wrapper's build chatter out of the picture with no shell redirection to remember.

The SVG renderer sits behind a one-function seam ({func}`click_extra.screenshot._rich_svg`), so Rich can be swapped for another engine without touching the capture, the CLI, or the pass described below.

```{note}
HTML carries two limitations SVG does not. An [OSC 8 hyperlink](https://gist.github.com/egmontkob/eb114294efbcd5adb1944c9f3cb5feda) loses its URL and keeps its visible text, and the eight base ANSI colors render as their CSS names, so the browser's palette decides their exact shade rather than the terminal's. Neither shows up on a help screen, which is why the format is worth having anyway.
```

### The captures on this page

Here is the command turned on click-extra itself, whose [bundled CLI](cli.md) doubles as a live demo of the rendering features. Each image below was produced by the line printed under it, run from a checkout.

`gradient` puts 24-bit ramps next to their 256-color quantized equivalents, so the stepping the smaller palette introduces is there to see:

![Color gradients rendered in 24-bit and quantized to 256 colors](assets/color-gradient-screen.svg)

```shell-session
$ click-extra screenshot --output docs/assets/color-gradient-screen.svg --prompt "click-extra gradient" -- uv run --frozen -- click-extra gradient
```

`styles` crosses every color with every text style. Its table wants far more than 80 columns, so the capture is taken at the width it actually needs:

![Every color rendered under each text style](assets/text-styles-screen.svg)

```shell-session
$ click-extra screenshot --output docs/assets/text-styles-screen.svg --columns 160 --head 14 --prompt "click-extra styles" -- uv run --frozen -- click-extra styles
```

`themes` renders a sample help screen under each built-in palette, and this capture keeps the first of them:

![Sample CLI help screen captured under the dark theme](assets/theme-gallery-screen.svg)

```shell-session
$ click-extra screenshot --output docs/assets/theme-gallery-screen.svg --head 16 --prompt "click-extra themes" -- uv run --frozen -- click-extra themes
```

`--prompt` is what makes each image show the bare `click-extra …` a reader would type, while `uv run --frozen --` is what actually ran: the plumbing that reaches a checkout's copy of the CLI is not worth picturing. `--head` bounds the two long ones, and the `[...]` marker admits that the rest was cut.

The before/after pair opening the [readme](https://github.com/kdeldycke/click-extra#example) takes the other route. Those two screens already exist as live [`click:run`](sphinx.md#committed-captures) blocks in the [tutorial](tutorial.md), so rather than shoot them again, the blocks maintain them: a `:screenshot:` option writes each image on every documentation build, which is what keeps the readme's front page in step with the code nobody thought to re-check.

Reach for the command when the CLI you want to picture has no live block, and for the directive when it does.

Whichever route, a full click-extra help screen carries `--table-format`, whose choice list is a single 463-character line. Click never wraps an option's own term, so the renderer folds it across six rows, exactly as a terminal would.

### Why a capture needs hardening

A renderer places a run of same-styled characters with an `x` offset, then leans on `textLength` to hold that run to an exact width. The padding separating two columns lives *inside* the run, as spaces preceding the text. A column therefore lands where it belongs only if the glyphs are the exact width the renderer assumed, which asks two things of whoever opens the file: honor `textLength`, and resolve the font the source names (Rich names Fira Code and links it from a CDN, which a browser blocks inside an `<img>`).

A web browser does both. Little else does. `librsvg`, and through it `rsvg-convert` and ImageMagick, ignores `textLength` outright; a file manager, a git client or a thumbnailer commonly falls back to a proportional font. Either way every glyph sitting behind padding slides out of its column and neighbouring words collide.

{func}`click_extra.screenshot.harden_svg` strips that padding and advances `x` by as many cells, so each run starts on its own column and a renderer only has to draw glyphs, not match metrics. Browsers are unaffected, since `textLength` is rewritten to the width of what remains. Every capture this command writes goes through it.

### Keeping a capture honest

Once committed, an image goes stale the first time the CLI's help changes, and nothing about it complains. `tests/test_screenshots.py` reads the SVG back, rebuilds the terminal text from the glyph coordinates, and compares it to what the command prints today, failing on the first line that diverged. Re-running the command above is then all it takes to refresh the picture.

## Other tools

The wider landscape splits by need: a regenerable static image, an animated demo, or a quick hand-made shot. None of them applies the hardening pass above, so their SVGs want a browser to render faithfully.

```{tip}
A tool that captures a command by reading its piped output sees a non-interactive stream, and click-extra strips colors there by default, like any CLI that respects a non-TTY `stdout`. Export `FORCE_COLOR=1` in the capture environment (`FORCE_COLOR=1 my-cli --help`) to keep them. A tool that allocates a real pseudo-terminal (a PTY) receives colors on its own, with no environment variable needed.
```

| Tool                                                                                                                         | Output            | Runs your command? | Install        | Diffable source | Best for                           |
| :--------------------------------------------------------------------------------------------------------------------------- | :---------------- | :----------------- | :------------- | :-------------- | :--------------------------------- |
| [`rich-codex`](https://ewels.github.io/rich-codex/)                                                                          | SVG, PNG          | Yes                | `uvx` (Python) | Yes             | Scanning Markdown for commands     |
| [`freeze`](https://github.com/charmbracelet/freeze)                                                                          | SVG, PNG, WebP    | Yes (`--execute`)  | Go binary      | Yes             | Static shots without a Python tool |
| [`vhs`](https://github.com/charmbracelet/vhs)                                                                                | GIF, MP4, WebM    | Scripted `.tape`   | Go binary      | No              | Reproducible animated demos        |
| [`asciinema`](https://asciinema.org) + [`agg`](https://github.com/asciinema/agg)                                             | GIF, animated SVG | Yes (records)      | Rust, npm      | Yes (`.cast`)   | Authentic session recordings       |
| [Rich export](https://rich.readthedocs.io/en/stable/console.html), [`ansitoimg`](https://github.com/FHPythonUtils/AnsiToImg) | SVG, HTML, PNG    | No (converts text) | `uvx` (Python) | Yes (SVG)       | Output you already captured        |
| [ray.so](https://ray.so), [Carbon](https://carbon.now.sh), [chalk.ist](https://chalk.ist)                                    | PNG, SVG          | No (paste)         | Web            | No              | One-off marketing shots            |

A few specifics the table compresses: [`rich-codex`](https://ewels.github.io/rich-codex/) wraps the same Rich export used here, and adds what this command deliberately leaves out, scanning your Markdown for embedded commands and regenerating every image through a companion GitHub Action. [`freeze`](https://github.com/charmbracelet/freeze) is a single Go binary whose `--execute "my-cli --help"` captures real ANSI output with no Python involved. [`vhs`](https://github.com/charmbracelet/vhs) replays a `.tape` script rather than recording you, which makes its animations deterministic and re-runnable in CI. [`asciinema`](https://asciinema.org) records a genuine session into a plain-text `.cast` file that diffs in git, then [`agg`](https://github.com/asciinema/agg) renders it to a GIF or [`svg-term-cli`](https://github.com/marionebl/svg-term-cli) to an animated SVG.

## GitHub integration

Whichever tool you pick, a README can track the reader's theme: capture a dark and a light SVG, then switch between them with a GitHub `<picture>` element keyed on `prefers-color-scheme`.

## `click_extra.screenshot` API

```{eval-rst}
.. automodule:: click_extra.screenshot
   :no-index:
   :members:
   :show-inheritance:
   :undoc-members:
```
