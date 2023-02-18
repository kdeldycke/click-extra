# Platform detection

## OS families

All platforms are grouped in sets of non-overlaping families:

<!-- NON_OVERLAPPING_GROUPS-graph-start -->

```{mermaid}
flowchart
    subgraph <code>click_extra.platforms.ALL_LINUX</code><br/><em>All Linux</em>
        all_linux_linux(<code>linux</code><br/><em>Linux</em>)
    end
    subgraph <code>click_extra.platforms.ALL_WINDOWS</code><br/><em>All Windows</em>
        all_windows_windows(<code>windows</code><br/><em>Windows</em>)
    end
    subgraph <code>click_extra.platforms.BSD</code><br/><em>All BSD</em>
        bsd_freebsd(<code>freebsd</code><br/><em>FreeBSD</em>)
        bsd_macos(<code>macos</code><br/><em>macOS</em>)
        bsd_netbsd(<code>netbsd</code><br/><em>NetBSD</em>)
        bsd_openbsd(<code>openbsd</code><br/><em>OpenBSD</em>)
        bsd_sunos(<code>sunos</code><br/><em>SunOS</em>)
    end
    subgraph <code>click_extra.platforms.LINUX_LAYERS</code><br/><em>All Linux compatibility layers</em>
        linux_layers_wsl1(<code>wsl1</code><br/><em>Windows Subsystem for Linux v1</em>)
        linux_layers_wsl2(<code>wsl2</code><br/><em>Windows Subsystem for Linux v2</em>)
    end
    subgraph <code>click_extra.platforms.OTHER_UNIX</code><br/><em>All other Unix</em>
        other_unix_hurd(<code>hurd</code><br/><em>GNU/Hurd</em>)
    end
    subgraph <code>click_extra.platforms.SYSTEM_V</code><br/><em>All Unix derived from AT&T System Five</em>
        system_v_aix(<code>aix</code><br/><em>AIX</em>)
        system_v_solaris(<code>solaris</code><br/><em>Solaris</em>)
    end
    subgraph <code>click_extra.platforms.UNIX_LAYERS</code><br/><em>All Unix compatibility layers</em>
        unix_layers_cygwin(<code>cygwin</code><br/><em>Cygwin</em>)
    end
```

<!-- NON_OVERLAPPING_GROUPS-graph-end -->

## Other groups

Other groups are available for convenience:

<!-- EXTRA_GROUPS-graph-start -->

```{mermaid}
flowchart
    subgraph <code>click_extra.platforms.ALL_PLATFORMS</code><br/><em>All platforms</em>
        all_platforms_aix(<code>aix</code><br/><em>AIX</em>)
        all_platforms_cygwin(<code>cygwin</code><br/><em>Cygwin</em>)
        all_platforms_freebsd(<code>freebsd</code><br/><em>FreeBSD</em>)
        all_platforms_hurd(<code>hurd</code><br/><em>GNU/Hurd</em>)
        all_platforms_linux(<code>linux</code><br/><em>Linux</em>)
        all_platforms_macos(<code>macos</code><br/><em>macOS</em>)
        all_platforms_netbsd(<code>netbsd</code><br/><em>NetBSD</em>)
        all_platforms_openbsd(<code>openbsd</code><br/><em>OpenBSD</em>)
        all_platforms_solaris(<code>solaris</code><br/><em>Solaris</em>)
        all_platforms_sunos(<code>sunos</code><br/><em>SunOS</em>)
        all_platforms_windows(<code>windows</code><br/><em>Windows</em>)
        all_platforms_wsl1(<code>wsl1</code><br/><em>Windows Subsystem for Linux v1</em>)
        all_platforms_wsl2(<code>wsl2</code><br/><em>Windows Subsystem for Linux v2</em>)
    end
    subgraph <code>click_extra.platforms.BSD_WITHOUT_MACOS</code><br/><em>All BSD without macOS</em>
        bsd_without_macos_freebsd(<code>freebsd</code><br/><em>FreeBSD</em>)
        bsd_without_macos_netbsd(<code>netbsd</code><br/><em>NetBSD</em>)
        bsd_without_macos_openbsd(<code>openbsd</code><br/><em>OpenBSD</em>)
        bsd_without_macos_sunos(<code>sunos</code><br/><em>SunOS</em>)
    end
    subgraph <code>click_extra.platforms.UNIX</code><br/><em>All Unix</em>
        unix_aix(<code>aix</code><br/><em>AIX</em>)
        unix_cygwin(<code>cygwin</code><br/><em>Cygwin</em>)
        unix_freebsd(<code>freebsd</code><br/><em>FreeBSD</em>)
        unix_hurd(<code>hurd</code><br/><em>GNU/Hurd</em>)
        unix_linux(<code>linux</code><br/><em>Linux</em>)
        unix_macos(<code>macos</code><br/><em>macOS</em>)
        unix_netbsd(<code>netbsd</code><br/><em>NetBSD</em>)
        unix_openbsd(<code>openbsd</code><br/><em>OpenBSD</em>)
        unix_solaris(<code>solaris</code><br/><em>Solaris</em>)
        unix_sunos(<code>sunos</code><br/><em>SunOS</em>)
        unix_wsl1(<code>wsl1</code><br/><em>Windows Subsystem for Linux v1</em>)
        unix_wsl2(<code>wsl2</code><br/><em>Windows Subsystem for Linux v2</em>)
    end
    subgraph <code>click_extra.platforms.UNIX_WITHOUT_MACOS</code><br/><em>All Unix without macOS</em>
        unix_without_macos_aix(<code>aix</code><br/><em>AIX</em>)
        unix_without_macos_cygwin(<code>cygwin</code><br/><em>Cygwin</em>)
        unix_without_macos_freebsd(<code>freebsd</code><br/><em>FreeBSD</em>)
        unix_without_macos_hurd(<code>hurd</code><br/><em>GNU/Hurd</em>)
        unix_without_macos_linux(<code>linux</code><br/><em>Linux</em>)
        unix_without_macos_netbsd(<code>netbsd</code><br/><em>NetBSD</em>)
        unix_without_macos_openbsd(<code>openbsd</code><br/><em>OpenBSD</em>)
        unix_without_macos_solaris(<code>solaris</code><br/><em>Solaris</em>)
        unix_without_macos_sunos(<code>sunos</code><br/><em>SunOS</em>)
        unix_without_macos_wsl1(<code>wsl1</code><br/><em>Windows Subsystem for Linux v1</em>)
        unix_without_macos_wsl2(<code>wsl2</code><br/><em>Windows Subsystem for Linux v2</em>)
    end
```

<!-- EXTRA_GROUPS-graph-end -->

```{important}
All the graphs above would be better off and user-friendly if merged together. Unfortunately Graphviz is not capable of producing [Euler diagrams](https://xkcd.com/2721/). Only non-overlapping clusters can be rendered.

There's still a chance to [have them supported by Mermaid](https://github.com/mermaid-js/mermaid/issues/2583) so we can switch to that if the feature materialize.
```

## `click_extra.platforms` API

```{eval-rst}
.. automodule:: click_extra.platforms
   :members:
   :undoc-members:
   :show-inheritance:
```

## Deprecated `click_extra.platform` API

```{eval-rst}
.. automodule:: click_extra.platform
   :members:
   :undoc-members:
   :show-inheritance:
```
