# {octicon}`device-camera` CLI screenshots

click-extra produces colored terminal output, and inside this Sphinx documentation the [`click:run`](sphinx.md) directive executes each CLI and renders its real output at build time, so these pages need no screenshots. A README on GitHub or PyPI, a slide, or a social post cannot run code, so those surfaces need a captured image instead. Here is how to produce one from a click-extra CLI.

```{tip}
A tool that captures a command by reading its piped output sees a non-interactive stream, and click-extra strips colors there by default, like any CLI that respects a non-TTY `stdout`. Export `FORCE_COLOR=1` in the capture environment (`FORCE_COLOR=1 my-cli --help`) to keep them. A tool that allocates a real pseudo-terminal (a PTY) receives colors on its own, with no environment variable needed.
```

## Recommended: rich-codex

For a click-extra CLI I recommend [`rich-codex`](https://ewels.github.io/rich-codex/). It lives in the same Python and `uv` toolchain as your project, runs the command, and renders the captured terminal to a vector SVG that diffs cleanly in git. It can also scan your Markdown for embedded commands and regenerate every image when the CLI changes: the docs-as-code idea behind `click:run`, carried to surfaces that cannot run code. A companion GitHub Action commits the refreshed images for you.

Capture one command with `uvx`, with nothing to install:

```shell-session
$ FORCE_COLOR=1 uvx rich-codex --no-search --skip-git-checks --no-confirm --terminal-width 100 --command "my-cli --help" --img-paths cli-help.svg
```

Or wrap it in an alias to shoot any command on demand:

```shell-session
$ alias clishot='FORCE_COLOR=1 uvx rich-codex --no-search --skip-git-checks --no-confirm --img-paths shot.svg --command'
$ clishot "my-cli --help"
```

```{note}
`rich-codex` writes SVG with no extra dependency. PNG and PDF need its `cairo` extra plus the system Cairo library: `uvx --from 'rich-codex[cairo]' rich-codex ...`. To capture colors from programs that ignore `FORCE_COLOR`, add `--use-pty` for a real pseudo-terminal: some locked-down CI sandboxes provide none, where `FORCE_COLOR` stays the portable fallback.
```

## Other tools

The wider landscape splits by need: a regenerable static image, an animated demo, or a quick hand-made shot.

| Tool                                                                                                                         | Output            | Runs your command? | Install        | Diffable source | Best for                           |
| :--------------------------------------------------------------------------------------------------------------------------- | :---------------- | :----------------- | :------------- | :-------------- | :--------------------------------- |
| [`rich-codex`](https://ewels.github.io/rich-codex/)                                                                          | SVG, PNG          | Yes                | `uvx` (Python) | Yes             | Automated, regenerable shots       |
| [`freeze`](https://github.com/charmbracelet/freeze)                                                                          | SVG, PNG, WebP    | Yes (`--execute`)  | Go binary      | Yes             | Static shots without a Python tool |
| [`vhs`](https://github.com/charmbracelet/vhs)                                                                                | GIF, MP4, WebM    | Scripted `.tape`   | Go binary      | No              | Reproducible animated demos        |
| [`asciinema`](https://asciinema.org) + [`agg`](https://github.com/asciinema/agg)                                             | GIF, animated SVG | Yes (records)      | Rust, npm      | Yes (`.cast`)   | Authentic session recordings       |
| [Rich export](https://rich.readthedocs.io/en/stable/console.html), [`ansitoimg`](https://github.com/FHPythonUtils/AnsiToImg) | SVG, HTML, PNG    | No (converts text) | `uvx` (Python) | Yes (SVG)       | Output you already captured        |
| [ray.so](https://ray.so), [Carbon](https://carbon.now.sh), [chalk.ist](https://chalk.ist)                                    | PNG, SVG          | No (paste)         | Web            | No              | One-off marketing shots            |

A few specifics the table compresses: [`freeze`](https://github.com/charmbracelet/freeze) is a single Go binary whose `--execute "my-cli --help"` captures real ANSI output with no Python involved. [`vhs`](https://github.com/charmbracelet/vhs) replays a `.tape` script rather than recording you, which makes its animations deterministic and re-runnable in CI. [`asciinema`](https://asciinema.org) records a genuine session into a plain-text `.cast` file that diffs in git, then [`agg`](https://github.com/asciinema/agg) renders it to a GIF or [`svg-term-cli`](https://github.com/marionebl/svg-term-cli) to an animated SVG. Rich's `Console(record=True).export_svg()` is the zero-dependency engine that both `rich-codex` and `ansitoimg` build on, so reach for it when you already hold the ANSI text and want no capture layer.

## GitHub integration

Whichever tool you pick, a README can track the reader's theme: capture a dark and a light SVG, then switch between them with a GitHub `<picture>` element keyed on `prefers-color-scheme`.
