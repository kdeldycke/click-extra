# Configuration loader

The configuration loader fetch values according the following precedence:
`CLI parameters > Configuration file > Environment variables > Defaults`.
The parameter will take the first value set in that chain.

The structure of the configuration file is automatically derived from the
parameters of the CLI and their types. There is no need to manually produce a configuration
data structure to mirror the CLI.

The `@config_option()` decorator provided by Click Extra can be used with vanilla Click construction, as demonstrated below.

## Tutorial

Let's start with a vanilla Click CLI with the `@config_option()` decorator from Click Extra:

```{eval-rst}
.. click:example::
    import click

    from click_extra.config import config_option


    @click.group(context_settings={"show_default": True})
    @click.option("--dummy-flag/--no-flag")
    @click.option("--my-list", multiple=True)
    @config_option()
    def my_cli(dummy_flag, my_list):
        click.echo(f"dummy_flag    is {dummy_flag!r}")
        click.echo(f"my_list       is {my_list!r}")

    @my_cli.command()
    @click.option("--int-param", type=int, default=10)
    def subcommand(int_param):
        click.echo(f"int_parameter is {int_param!r}")

We will save it into a file named `my_cli.py`. It produces the following help screen:

.. click:run::
    invoke(my_cli, args=["--help"])

A bare call returns:

.. click:run::
    invoke(my_cli, args=["subcommand"])
```

Now we will change the CLI's default output with a TOML file where the CLI is expecting a configuration.
Here is what `~/Library/Application Support/my-cli/config.toml` contains:

```toml
# My default configuration file.
top_level_param = "is_ignored"

[my-cli]
extra_value = "is ignored too"
dummy_flag = true   # New boolean default.
my_list = ["item 1", "item #2", "Very Last Item!"]

[garbage]
# An empty random section that will be skipped

[my-cli.subcommand]
int_param = 3
random_stuff = "will be ignored"
```

In the file above, pay attention to:

- the default configuration base path (`~/Library/Application Support/`, here for Linux) which is [OS-dependant](https://click.palletsprojects.com/en/8.1.x/api/#click.get_app_dir);
- the app's folder (`~/Library/Application Support/my-cli/`) which correspond to the script's
  name (`my_cli.py`);
- the top-level config section (`[my-cli]`), that is derived from the CLI's
  group ID (`def my_cli()`);
- all the extra comments, sections and values that will be silently ignored.

Now we can verify the configuration file is read automatically and change the defaults:

```shell-session
$ my-cli subcommand
dummy_flag    is True
my_list       is ('item 1', 'item #2', 'Very Last Item!')
int_parameter is 3
```

Still, inline parameters are allowed to override the configuration
defaults:

```shell-session
$ my-cli subcommand --int-param 555
dummy_flag    is True
my_list       is ('item 1', 'item #2', 'Very Last Item!')
int_parameter is 555
```

## YAML configuration

The example above was given for a TOML configuration file, but is working as-is with YAML.

Just replace the TOML file with the following configuration at
`~/Library/Application Support/my-cli/config.yaml`:

```yaml
# My default configuration file.
top_level_param: is_ignored

my-cli:
  extra_value: is ignored too
  dummy_flag: true   # New boolean default.
  my_list:
    - point 1
    - 'point #2'
    - Very Last Point!

  subcommand:
    int_param: 77
    random_stuff: will be ignored

garbage: >
  An empty random section that will be skipped
```

```shell-session
$ my-cli --config "~/Library/Application Support/my-cli/config.yaml" subcommand
dummy_flag    is True
my_list       is ('point 1', 'point #2', 'Very Last Point!')
int_parameter is 77
```

## JSON configuration

Again, same for JSON:

```json
{
  "top_level_param": "is_ignored",
  "garbage": {},
  "my-cli": {
    "dummy_flag": true,
    "extra_value": "is ignored too",
    "my_list": [
      "item 1",
      "item #2",
      "Very Last Item!"
    ],
    "subcommand": {
      "int_param": 65,
      "random_stuff": "will be ignored"
    }
  }
}
```

```shell-session
$ my-cli --config "~/Library/Application Support/my-cli/config.json" subcommand
dummy_flag    is True
my_list       is ('item 1', 'item #2', 'Very Last Item!')
int_parameter is 65
```

## INI configuration

`INI` configuration files are allowed to use [`ExtendedInterpolation`](https://docs.python.org/3/library/configparser.html?highlight=configparser#configparser.ExtendedInterpolation) by default.

```{todo}
Write example.
```

## XML configuration

```{todo}
Write example.
```

## Remote configuration

Remote URL can be passed directly to the `--config` option:

```shell-session
$ my-cli --config https://example.com/dummy/configuration.yaml subcommand
dummy_flag    is True
my_list       is ('point 1', 'point #2', 'Very Last Point!')
int_parameter is 77
```

## `click_extra.config` API

```{eval-rst}
.. automodule:: click_extra.config
   :members:
   :undoc-members:
   :show-inheritance:
```
