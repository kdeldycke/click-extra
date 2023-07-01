# Version

Click Extra provides its own version option which, compared to [Click's built-in](https://click.palletsprojects.com/en/8.1.x/api/?highlight=version#click.version_option):

- adds colors
- prints complete environment information in JSON

```{eval-rst}
.. click:example::
      import click_extra

      @click_extra.extra_command(params=[
         click_extra.VersionOption(version="0.1")
      ])
      def cli():
         print("It works!")

.. click:run::
   result = invoke(cli, args=["--version"])
   assert result.output == "\x1b[97mcli\x1b[0m, version \x1b[32m0.1\x1b[0m\n"
```

## Environment information

By default, the version option collects and output the environment information. The idea is to collect enough metadata on the system a CLI is run from, to help debugging and reporting of issues from end users.

```{warning}
Environment information collection is temporarily disabled for Python >= 3.10, because we rely on [`boltons.ecoutils`](https://boltons.readthedocs.io/en/latest/ecoutils.html), for which we wait for a new release to have [issue `mahmoud/boltons#294` fixed](https://github.com/mahmoud/boltons/issues/294) upstream.
```

Here is how it looks like:

```ansi-shell-session
$ cli --version
[97mcli[0m, version [32m0.1
[0m[90m{'username': '-', 'guid': 'bd92d7b5d66e95baac0b0fc36a247a5', 'hostname': '-', 'hostfqdn': '-', 'uname': {'system': 'Darwin', 'node': '-', 'release': '21.3.0', 'version': 'Darwin Kernel Version 21.3.0: Wed Jan  5 21:37:58 PST 2022; root:xnu-8019.80.24~20/RELEASE_X86_64', 'machine': 'x86_64', 'processor': 'i386'}, 'linux_dist_name': '', 'linux_dist_version': '', 'cpu_count': 8, 'fs_encoding': 'utf-8', 'ulimit_soft': 256, 'ulimit_hard': 9223372036854775807, 'cwd': '-', 'umask': '0o2', 'python': {'argv': '-', 'bin': '-', 'version': '3.9.12 (main, Mar 26 2022, 15:51:15) [Clang 13.1.6 (clang-1316.0.21.2)]', 'compiler': 'Clang 13.1.6 (clang-1316.0.21.2)', 'build_date': 'Mar 26 2022 15:51:15', 'version_info': [3, 9, 12, 'final', 0], 'features': {'openssl': 'OpenSSL 1.1.1n  15 Mar 2022', 'expat': 'expat_2.4.1', 'sqlite': '3.38.2', 'tkinter': '', 'zlib': '1.2.11', 'unicode_wide': True, 'readline': True, '64bit': True, 'ipv6': True, 'threading': True, 'urandom': True}}, 'time_utc': '2022-04-04 14:09:17.339140', 'time_utc_offset': -6.0, '_eco_version': '1.0.1'}[0m
```

```{note}
The environment JSON output is scrubbed out of identifiable information by default: current working directory, hostname, Python executable path, command-line arguments and username are replaced with `-`.
```

To disable environment metadata reporting, set the `print_env_info` argument:

```{eval-rst}
.. click:example::
      import click_extra

      @click_extra.extra_command(params=[
         click_extra.VersionOption(
            version="0.1",
            print_env_info=False,
         )
      ])
      def cli():
         print("It works!")

.. click:run::
   result = invoke(cli, args=["--version"])
   assert result.output == "\x1b[97mcli\x1b[0m, version \x1b[32m0.1\x1b[0m\n"
```

## `click_extra.version` API

```{eval-rst}
.. autoclasstree:: click_extra.version
   :strict:
```

```{eval-rst}
.. automodule:: click_extra.version
   :members:
   :undoc-members:
   :show-inheritance:
```
