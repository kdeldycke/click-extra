# {octicon}`repo` Man pages

Every `click-extra` command carries a Unix manual page, rendered from the live command tree while this site builds. A manual therefore always describes the release it ships beside.

The [`click-extra-manpages` directive](man-page.md#click-extra-manpages-directive) renders the index below from the `click_extra_manpages` list in `docs/conf.py`. Each entry points at the HTML rendering that the build produces when `mandoc` or `groff` is on `PATH`.

```{click-extra-manpages}
```

The raw `.1` files sit in the same directory as these renderings: `click-extra.1` for the root command and `click-extra-{subcommand}.1` for the others. [Reading them in a terminal](install.md#man-pages) covers `click-extra --man` and the release tarball.
