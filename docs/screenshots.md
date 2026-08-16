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
from click_extra.cli import demo
result = invoke(demo, args=["screenshot", "--help"])
assert result.exit_code == 0
assert "--columns" in result.stdout
assert "--merge-stderr" in result.stdout
```

Three things it settles that a general-purpose capture tool leaves to you:

- Colors, which a command strips on its own the moment its output is a pipe rather than a terminal. The capture runs under {func}`click_extra.color.forced_color`, setting the `FORCE_COLOR` lever both Click's and Rich's color systems obey and clearing any `NO_COLOR` the environment carries.
- Width, where `--columns` pins what the command wraps to *and* what the image is drawn at. Let those two disagree and the rendered lines overrun the image.
- `stderr`, which stays out of the capture unless `--merge-stderr` asks for it. That is what keeps a wrapper's build chatter out of the picture with no shell redirection to remember.

Every SVG it writes is also hardened, so it renders correctly outside a web browser, where a file manager, a git client or a thumbnailer would otherwise slide each column out of place. {func}`click_extra.screenshot.harden_svg` documents what that fixes and why the renderer does not do it. The renderer itself sits behind a one-function seam ({func}`click_extra.screenshot._rich_svg`), so Rich can be swapped for another engine without touching the capture or the CLI.

### Capturing a CLI that is not yours

`screenshot` runs whatever the shell runs, Click CLI or not, so `git --help` and `docker ps` capture as readily as your own tool. What it captures is what the command prints: a Click CLI that is not built on Click Extra prints its help uncolored, and that is what lands in the file.

To picture it *with* colors, run it through [`wrap`](wrap.md) first, which patches Click's help rendering without touching the target's code. `--wrap` does that for you:

```shell-session
$ click-extra screenshot --output flask-help.svg --wrap -- flask --help
```

which is the shorthand for composing the two commands by hand:

```shell-session
$ click-extra screenshot --output flask-help.svg --prompt "click-extra wrap -- flask --help" -- click-extra wrap -- flask --help
```

The prompt drawn above the output is the `wrap` invocation, not the bare command, because that is what reproduces the colored screen: running `flask --help` on its own gives back the plain one.

```{note}
The two commands stay separate because they answer different questions. `wrap` decides *how a CLI renders*, and only reaches Click commands it can import: a `module:function`, a project directory, a `.py` file, an entry point. `screenshot` decides *where the output goes*, and reaches anything executable. Composing them covers the overlap; merging them would cost every CLI that `wrap` cannot import, which is most of what a README wants to show.

That separation is also why `--wrap` insists on the installed `click-extra` command rather than falling back to `python -m click_extra`: the two resolve a target differently, so the fallback would quietly capture a different CLI.
```

```{note}
HTML carries two limitations SVG does not. An [OSC 8 hyperlink](https://gist.github.com/egmontkob/eb114294efbcd5adb1944c9f3cb5feda) loses its URL and keeps its visible text, and the eight base ANSI colors render as their CSS names, so the browser's palette decides their exact shade rather than the terminal's. Neither shows up on a help screen, which is why the format is worth having anyway.
```

### Width

`--columns` pins the width twice over: the command wraps its output to it, and the image is laid out at the same one. They have to agree, or the rendered lines overrun the picture.

`--columns auto` pins neither. The command finds its own width (the terminal it runs in, or Click's own 80 through a pipe), and the image is laid out at the longest line that came back:

```shell-session
$ click-extra screenshot --output params.svg --columns auto -- my-cli --params
```

Reach for it when the output holds a line the command does not wrap on its own, which a pinned width folds mid-word: a long invocation drawn as the prompt, a wide table, a machine-readable dump. The trade-off is that the picture stops being a fixed-width terminal, so captures meant to sit side by side at the same width should name that width instead.

### Light and dark chrome

A capture freezes the colors of the run it pictures, so the window it is drawn in has to answer to the theme that run rendered for. `--background light` swaps the dark chrome for white, along with the ANSI palette the capture's own colors resolve against:

```shell-session
$ click-extra screenshot --output light-help.svg --background light -- my-cli --theme light --help
```

Both halves are needed, and they are not the same half: `--theme light` is what the *CLI* renders with, `--background light` is what the *image* is drawn on. Pass one without the other and you get the washed-out screen the [theme gallery](theme.md#built-in-themes) warns about, in one direction or the other.

The prompt line follows the chrome on its own. It is the one line a capture draws itself rather than collects, so on white it would otherwise land in the dark theme's near-white `invoked_command` style and vanish.

So does a CLI that asks. A capture states its chrome to the command the way a terminal would, through the `CLITHEME` and `COLORFGBG` variables [background detection](theme.md#automatic-background-detection) reads, on top of the width it pins and the colors it forces. A CLI passing [`--theme auto`](theme.md#automatic-background-detection) then renders for the window it lands in, and needs telling only once:

```shell-session
$ click-extra screenshot --output light-help.svg --background light -- my-cli --theme auto --help
```

`auto` is not the default, and deliberately: a CLI that never asks for it keeps rendering exactly as it does everywhere else, which is why `--theme dark` and `--theme light` are spelled out below rather than left to detection.

Here is one help screen taken both ways, with the CLI's theme and the image's chrome moving together:

```{click:source}
:hide-source:
import click

from click_extra import Choice, IntRange, argument, option, theme_option
from click_extra.commands import ColorizedCommand

@click.command(cls=ColorizedCommand, name="pantry")
@theme_option
@option("--shelves", type=int, default=3, show_default=True,
        help="Number of shelves to stock.")
@option("--fruit", type=Choice(["apple", "banana", "cherry"]), default="apple",
        show_default=True, show_envvar=True, envvar="PANTRY_FRUIT",
        help="Which fruit to store.")
@option("--crates", type=IntRange(1, 12), default=4, show_default=True,
        help="Crates to stack on each shelf.")
@option("--chill/--no-chill", default=True, help="Refrigerate the aisle afterwards.")
@argument("aisle")
def pantry(**kwargs):
    """Stock a pantry AISLE with fruit."""
```

```{click:run}
:screenshot: chrome-dark-screen
:hide-results:
result = invoke(pantry, args=["--theme", "dark", "--help"])
assert result.exit_code == 0
assert "--crates" in result.stdout
```

![The pantry help screen under the dark theme, drawn on dark chrome](assets/chrome-dark-screen.svg)

```{click:run}
:screenshot: chrome-light-screen
:screenshot-background: light
:hide-results:
result = invoke(pantry, args=["--theme", "light", "--help"])
assert result.exit_code == 0
assert "--crates" in result.stdout
```

![The same screen under the light theme, drawn on light chrome](assets/chrome-light-screen.svg)

Both blocks hide their results, which is the exception to what [`:screenshot:`](sphinx.md#committed-captures) is usually for: a results block on this page is colored by the site's stylesheet and follows the reader's own theme, so the one thing being compared here is the one thing it cannot show.

### The window itself

A capture is drawn as a terminal window: a rounded rectangle in the chrome's background color, framed with a one-pixel border and lifted off the page by a drop shadow. Every part of that is an option:

```shell-session
$ click-extra screenshot --output shot.svg --title "my-cli --help" --backdrop "#1f6feb" --radius 0 --border-width 2 --margin 28 -- my-cli --help
```

| Option           | Takes     | Default      | Draws                                                    |
| :--------------- | :-------- | :----------- | :------------------------------------------------------- |
| `--border`       | CSS color | the chrome's | The frame around the window. `none` leaves it bare.      |
| `--border-width` | pixels    | `1`          | How thick that frame is.                                 |
| `--radius`       | pixels    | `8`          | How round the window's corners are. `0` squares them.    |
| `--shadow`       | CSS color | the chrome's | The drop shadow under the window. `none` leaves it flat. |
| `--backdrop`     | CSS color | none         | A page behind the window, margin included.               |
| `--margin`       | pixels    | `48`         | Transparent space around the window.                     |
| `--padding`      | pixels    | `8`          | Space inside it, on top of the renderer's own.           |
| `--line-numbers` | flag      | off          | A dim gutter numbering the captured lines.               |
| `--title`        | text      | none         | A caption centered in the window's title bar.            |

Two of them carry a default that is not a fixed value but the chrome's own. That is the whole reason they are not constants: a renderer frames its window in a translucent white, and a light capture wearing it is a white window on a white page, its edge left for the reader to infer.

The rest answer to what the capture is *for*. A shadow needs `--margin` to fall into, since a filter paints outside the shape it is applied to and the image's own box cuts whatever lands past it. `--backdrop` fills that same space instead of leaving the page through, which is what turns a capture into a self-contained picture for a slide or a social card. `--radius 0` drops the desktop-window look, for a capture meant to read as a plain block of output.

The frame is rewritten into the rendered source rather than requested up front ({func}`click_extra.screenshot.frame_svg`), which is what lets the same pass serve an HTML capture, where these land on the block's `border`, `border-radius`, `box-shadow`, `margin`, `padding` and the page's `background`.

```{tip}
A shadow is an SVG filter. A renderer that skips filters, and a few outside the browser do, still draws the border, so the window keeps an edge either way.
```

#### Gradients

`--backdrop` also takes a CSS gradient, which is what turns a capture into a picture that carries its own page:

```shell-session
$ click-extra screenshot --output card.svg --backdrop "linear-gradient(135deg, #667eea, #764ba2)" -- my-cli --help
```

An SVG `fill` has no syntax for that, so the CSS is read and re-emitted as the paint server SVG does understand ({func}`click_extra.screenshot.gradient_svg`), placed in user space rather than approximated: the gradient line runs through the image's center at the angle asked for, as long as the image measures along it, and a radial one reaches the farthest corner. Understood are `linear-gradient`, opening with an angle (`135deg`) or a side keyword (`to bottom right`), and `radial-gradient`, both followed by two or more color stops, each pinnable at a percentage (`#667eea 30%`). Anything else is taken for the plain color it presumably is, and HTML captures pass the value through to CSS untouched either way.

#### Line numbers

`--line-numbers` draws each line's number in a dim gutter, the way Pygments does inline. Line 1 is the prompt, the invocation everything under it came from:

```shell-session
$ click-extra screenshot --output numbered.svg --line-numbers -- my-cli --help
```

The numbers land in the terminal text rather than in a column of their own, which is the same trade Pygments makes: every renderer places them for free, and a reader copying an HTML capture copies them too.

It also means the gutter spends columns the command already used: a screen wrapped at 80 comes back a few characters too wide, and folds. Pair the flag with [`--columns auto`](#width), or with a width that leaves room for the gutter, so the image grows instead of the lines breaking.

#### All of it at once

Here is the `pantry` screen again, on a gradient, captioned, numbered, rounded and given room to breathe:

```{click:run}
:screenshot: styled-window-screen
:screenshot-columns: auto
:screenshot-title: pantry --help
:screenshot-backdrop: 'linear-gradient(135deg, #667eea, #764ba2)'
:screenshot-line-numbers:
:screenshot-radius: 12
:screenshot-padding: 24
:hide-results:
result = invoke(pantry, args=["--help"])
assert result.exit_code == 0
assert "--crates" in result.stdout
```

![The pantry help screen, captioned and numbered on a gradient backdrop](assets/styled-window-screen.svg)

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

`themes` renders a sample help screen under each built-in palette, and this capture keeps the first two of them, which is what `--theme` does to a screen:

![The same CLI help screen captured under the dark and dracula themes](assets/theme-gallery-screen.svg)

```shell-session
$ click-extra screenshot --output docs/assets/theme-gallery-screen.svg --head 34 --prompt "click-extra themes" -- uv run --frozen -- click-extra themes
```

`--prompt` is what makes each image show the bare `click-extra …` a reader would type, while `uv run --frozen --` is what actually ran: the plumbing that reaches a checkout's copy of the CLI is not worth picturing. `--head` bounds the two long ones, and the `[...]` marker admits that the rest was cut.

The before/after pair opening the [readme](https://github.com/kdeldycke/click-extra#example) takes the other route. Those two screens already exist as live [`click:run`](sphinx.md#committed-captures) blocks in the [tutorial](tutorial.md), so rather than shoot them again, the blocks maintain them: a `:screenshot:` option writes each image on every documentation build, which is what keeps the readme's front page in step with the code nobody thought to re-check.

Reach for the command when the CLI you want to picture has no live block, and for the directive when it does.

Whichever route, a full click-extra help screen carries `--table-format`, whose choice list is a single 463-character line. Click never wraps an option's own term, so the renderer folds it across six rows, exactly as a terminal would.

### Keeping a capture honest

Once committed, an image goes stale the first time the CLI's help changes, and nothing about it complains. `tests/test_screenshots.py` reads the SVG back, rebuilds the terminal text from the glyph coordinates, and compares it to what the command prints today, failing on the first line that diverged. Re-running the command above is then all it takes to refresh the picture.

## GitHub integration

A README can track the reader's theme. Capture the same screen twice, once per [chrome](#light-and-dark-chrome), with the CLI's own theme moving along:

```shell-session
$ click-extra screenshot --output docs/assets/help-dark.svg -- my-cli --theme dark --help
$ click-extra screenshot --output docs/assets/help-light.svg --background light -- my-cli --theme light --help
```

Then hand both to a `<picture>` element, which GitHub renders in a README and which picks between them on `prefers-color-scheme`:

```html
<picture>
 <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/me/my-cli/main/docs/assets/help-dark.svg"/>
 <img alt="my-cli help screen" src="https://raw.githubusercontent.com/me/my-cli/main/docs/assets/help-light.svg"/>
</picture>
```

The `<img>` is not a spare tyre: it is what every surface without the switch shows, PyPI and most editors' previews included, so it holds the capture that reads on the light background those default to. The `<source>` is the one a reader in dark mode gets instead.

Both URLs are absolute on purpose. A README is read on PyPI and in a hundred forks of the page, none of which resolve a repository-relative path, which is why every capture in [this project's own README](https://github.com/kdeldycke/click-extra#documentation-tooling) is addressed through `raw.githubusercontent.com`. That entry is this exact markup, over the pair of captures [above](#light-and-dark-chrome).

```{note}
The switch keys on the *browser's* color scheme, not on the theme toggle of a documentation site, so it belongs to a README rather than to these pages: Furo's own switch would leave it unmoved.
```

## `click_extra.screenshot` API

```{eval-rst}
.. automodule:: click_extra.screenshot
   :no-index:
   :members:
   :show-inheritance:
   :undoc-members:
```
