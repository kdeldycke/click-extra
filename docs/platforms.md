# Platform detection

Relationships between groups and platforms:

<!-- platform-sankey-start -->

```mermaid
sankey-beta

all_platforms,aix,1
all_platforms,cygwin,1
all_platforms,freebsd,1
all_platforms,hurd,1
all_platforms,linux,1
all_platforms,macos,1
all_platforms,netbsd,1
all_platforms,openbsd,1
all_platforms,solaris,1
all_platforms,sunos,1
all_platforms,windows,1
all_platforms,wsl1,1
all_platforms,wsl2,1
unix,aix,1
unix,cygwin,1
unix,freebsd,1
unix,hurd,1
unix,linux,1
unix,macos,1
unix,netbsd,1
unix,openbsd,1
unix,solaris,1
unix,sunos,1
unix,wsl1,1
unix,wsl2,1
unix_without_macos,aix,1
unix_without_macos,cygwin,1
unix_without_macos,freebsd,1
unix_without_macos,hurd,1
unix_without_macos,linux,1
unix_without_macos,netbsd,1
unix_without_macos,openbsd,1
unix_without_macos,solaris,1
unix_without_macos,sunos,1
unix_without_macos,wsl1,1
unix_without_macos,wsl2,1
bsd,freebsd,1
bsd,macos,1
bsd,netbsd,1
bsd,openbsd,1
bsd,sunos,1
bsd_without_macos,freebsd,1
bsd_without_macos,netbsd,1
bsd_without_macos,openbsd,1
bsd_without_macos,sunos,1
system_v,aix,1
system_v,solaris,1
linux_layers,wsl1,1
linux_layers,wsl2,1
unix_layers,cygwin,1
other_unix,hurd,1
all_windows,windows,1
all_linux,linux,1
```

<!-- platform-sankey-end -->

## OS families

All platforms are grouped in sets of non-overlpaping families:

<!-- NON_OVERLAPPING_GROUPS-graph-start -->

{caption="`click_extra.platforms.NON_OVERLAPPING_GROUPS` - Non-overlapping groups."}
```mermaid
flowchart
    subgraph "<code>click_extra.platforms.ALL_LINUX</code><br/><em>Any Linux</em>"
        all_linux_linux(<code>linux</code><br/><em>Linux</em>)
    end
    subgraph "<code>click_extra.platforms.ALL_WINDOWS</code><br/><em>Any Windows</em>"
        all_windows_windows(<code>windows</code><br/><em>Windows</em>)
    end
    subgraph "<code>click_extra.platforms.BSD</code><br/><em>Any BSD</em>"
        bsd_freebsd(<code>freebsd</code><br/><em>FreeBSD</em>)
        bsd_macos(<code>macos</code><br/><em>macOS</em>)
        bsd_netbsd(<code>netbsd</code><br/><em>NetBSD</em>)
        bsd_openbsd(<code>openbsd</code><br/><em>OpenBSD</em>)
        bsd_sunos(<code>sunos</code><br/><em>SunOS</em>)
    end
    subgraph "<code>click_extra.platforms.LINUX_LAYERS</code><br/><em>Any Linux compatibility layers</em>"
        linux_layers_wsl1(<code>wsl1</code><br/><em>Windows Subsystem for Linux v1</em>)
        linux_layers_wsl2(<code>wsl2</code><br/><em>Windows Subsystem for Linux v2</em>)
    end
    subgraph "<code>click_extra.platforms.OTHER_UNIX</code><br/><em>Any other Unix</em>"
        other_unix_hurd(<code>hurd</code><br/><em>GNU/Hurd</em>)
    end
    subgraph "<code>click_extra.platforms.SYSTEM_V</code><br/><em>Any Unix derived from AT&T System Five</em>"
        system_v_aix(<code>aix</code><br/><em>AIX</em>)
        system_v_solaris(<code>solaris</code><br/><em>Solaris</em>)
    end
    subgraph "<code>click_extra.platforms.UNIX_LAYERS</code><br/><em>Any Unix compatibility layers</em>"
        unix_layers_cygwin(<code>cygwin</code><br/><em>Cygwin</em>)
    end
```

<!-- NON_OVERLAPPING_GROUPS-graph-end -->

## Other groups

Other groups are available for convenience, but these overlaps:

<!-- EXTRA_GROUPS-graph-start -->

{caption="`click_extra.platforms.EXTRA_GROUPS` - Overlapping groups, defined for convenience."}
```mermaid
flowchart
    subgraph "<code>click_extra.platforms.ALL_PLATFORMS</code><br/><em>Any platforms</em>"
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
    subgraph "<code>click_extra.platforms.BSD_WITHOUT_MACOS</code><br/><em>Any BSD but macOS</em>"
        bsd_without_macos_freebsd(<code>freebsd</code><br/><em>FreeBSD</em>)
        bsd_without_macos_netbsd(<code>netbsd</code><br/><em>NetBSD</em>)
        bsd_without_macos_openbsd(<code>openbsd</code><br/><em>OpenBSD</em>)
        bsd_without_macos_sunos(<code>sunos</code><br/><em>SunOS</em>)
    end
    subgraph "<code>click_extra.platforms.UNIX</code><br/><em>Any Unix</em>"
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
    subgraph "<code>click_extra.platforms.UNIX_WITHOUT_MACOS</code><br/><em>Any Unix but macOS</em>"
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
.. autoclasstree:: click_extra.platforms
   :strict:
```

```{eval-rst}
.. automodule:: click_extra.platforms
   :members:
   :undoc-members:
   :show-inheritance:
```
