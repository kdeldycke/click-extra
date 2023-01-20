# Platform detection

## OS families

All platforms are grouped in sets of non-overlaping families:

<!-- NON_OVERLAPPING_GROUPS-graph-start -->

```{eval-rst}
.. graphviz::

   // Auto-generated by `click_extra.docs_update` module.
   graph NON_OVERLAPPING_GROUPS {
       graph [fontname="Helvetica,Arial,sans-serif" fontsize=36 label=<<BR/><BR/><FONT FACE="Courier New"><B>click_extra.platforms.NON_OVERLAPPING_GROUPS</B></FONT><BR/><BR/><I>Non-overlapping groups.</I><BR/><BR/><FONT COLOR="gray">Click Extra v3.8.0</FONT><BR/>> layout=osage]
       node [color=lightblue2 fontname="Helvetica,Arial,sans-serif" style=filled]
       edge [dir=none fontname="Helvetica,Arial,sans-serif"]
       subgraph cluster_all_windows {
           cluster=true;
           fontsize=16
           label=<<FONT FACE="Courier New"><B>click_extra.platforms.ALL_WINDOWS</B></FONT><BR/><BR/><I>All Windows.</I><BR/>>
           all_windows_windows [label="windows - Windows"]
       }
       subgraph cluster_bsd {
           cluster=true;
           fontsize=16
           label=<<FONT FACE="Courier New"><B>click_extra.platforms.BSD</B></FONT><BR/><BR/><I>All BSD.</I><BR/>>
           bsd_freebsd [label="freebsd - FreeBSD"]
           bsd_macos [label="macos - macOS"]
           bsd_netbsd [label="netbsd - NetBSD"]
           bsd_openbsd [label="openbsd - OpenBSD"]
           bsd_sunos [label="sunos - SunOS"]
       }
       subgraph cluster_all_linux {
           cluster=true;
           fontsize=16
           label=<<FONT FACE="Courier New"><B>click_extra.platforms.ALL_LINUX</B></FONT><BR/><BR/><I>All Linux.</I><BR/>>
           all_linux_linux [label="linux - Linux"]
       }
       subgraph cluster_linux_layers {
           cluster=true;
           fontsize=16
           label=<<FONT FACE="Courier New"><B>click_extra.platforms.LINUX_LAYERS</B></FONT><BR/><BR/><I>All Linux compatibility layers.</I><BR/>>
           linux_layers_wsl1 [label="wsl1 - Windows Subsystem for Linux v1"]
           linux_layers_wsl2 [label="wsl2 - Windows Subsystem for Linux v2"]
       }
       subgraph cluster_system_v {
           cluster=true;
           fontsize=16
           label=<<FONT FACE="Courier New"><B>click_extra.platforms.SYSTEM_V</B></FONT><BR/><BR/><I>All Unix derived from AT&amp;T System Five.</I><BR/>>
           system_v_aix [label="aix - AIX"]
           system_v_solaris [label="solaris - Solaris"]
       }
       subgraph cluster_unix_layers {
           cluster=true;
           fontsize=16
           label=<<FONT FACE="Courier New"><B>click_extra.platforms.UNIX_LAYERS</B></FONT><BR/><BR/><I>All Unix compatibility layers.</I><BR/>>
           unix_layers_cygwin [label="cygwin - Cygwin"]
       }
       subgraph cluster_other_unix {
           cluster=true;
           fontsize=16
           label=<<FONT FACE="Courier New"><B>click_extra.platforms.OTHER_UNIX</B></FONT><BR/><BR/><I>All other Unix.</I><BR/>>
           other_unix_hurd [label="hurd - GNU/Hurd"]
       }
   }
```

<!-- NON_OVERLAPPING_GROUPS-graph-end -->

## Other groups

Other groups are available for convenience:

<!-- EXTRA_GROUPS-graph-start -->

```{eval-rst}
.. graphviz::

   // Auto-generated by `click_extra.docs_update` module.
   graph EXTRA_GROUPS {
       graph [fontname="Helvetica,Arial,sans-serif" fontsize=36 label=<<BR/><BR/><FONT FACE="Courier New"><B>click_extra.platforms.EXTRA_GROUPS</B></FONT><BR/><BR/><I>Overlapping groups, defined for convenience.</I><BR/><BR/><FONT COLOR="gray">Click Extra v3.8.0</FONT><BR/>> layout=osage]
       node [color=lightblue2 fontname="Helvetica,Arial,sans-serif" style=filled]
       edge [dir=none fontname="Helvetica,Arial,sans-serif"]
       subgraph cluster_unix {
           cluster=true;
           fontsize=16
           label=<<FONT FACE="Courier New"><B>click_extra.platforms.UNIX</B></FONT><BR/><BR/><I>All Unix.</I><BR/>>
           unix_aix [label="aix - AIX"]
           unix_cygwin [label="cygwin - Cygwin"]
           unix_freebsd [label="freebsd - FreeBSD"]
           unix_hurd [label="hurd - GNU/Hurd"]
           unix_linux [label="linux - Linux"]
           unix_macos [label="macos - macOS"]
           unix_netbsd [label="netbsd - NetBSD"]
           unix_openbsd [label="openbsd - OpenBSD"]
           unix_solaris [label="solaris - Solaris"]
           unix_sunos [label="sunos - SunOS"]
           unix_wsl1 [label="wsl1 - Windows Subsystem for Linux v1"]
           unix_wsl2 [label="wsl2 - Windows Subsystem for Linux v2"]
       }
       subgraph cluster_unix_without_macos {
           cluster=true;
           fontsize=16
           label=<<FONT FACE="Courier New"><B>click_extra.platforms.UNIX_WITHOUT_MACOS</B></FONT><BR/><BR/><I>All Unix without macOS.</I><BR/>>
           unix_without_macos_aix [label="aix - AIX"]
           unix_without_macos_cygwin [label="cygwin - Cygwin"]
           unix_without_macos_freebsd [label="freebsd - FreeBSD"]
           unix_without_macos_hurd [label="hurd - GNU/Hurd"]
           unix_without_macos_linux [label="linux - Linux"]
           unix_without_macos_netbsd [label="netbsd - NetBSD"]
           unix_without_macos_openbsd [label="openbsd - OpenBSD"]
           unix_without_macos_solaris [label="solaris - Solaris"]
           unix_without_macos_sunos [label="sunos - SunOS"]
           unix_without_macos_wsl1 [label="wsl1 - Windows Subsystem for Linux v1"]
           unix_without_macos_wsl2 [label="wsl2 - Windows Subsystem for Linux v2"]
       }
   }
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