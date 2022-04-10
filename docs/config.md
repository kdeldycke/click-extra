# Configuration loader usage

The configuration loader source values according the following precedence:
`CLI parameters > Configuration file > Environment variables > Defaults`.

The structure of the configuration file is automaticcaly derived from the
parameters of the CLI. There is no need to manually produce a configuration
data structure to mirror the CLI.

`INI` configuration files are allowed to use [`ExtendedInterpolation`](https://docs.python.org/3/library/configparser.html?highlight=configparser#configparser.ExtendedInterpolation) by default.

## TOML configuration

Given this CLI in a `my_cli.py` file:

```python
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


if __name__ == "__main__":
    my_cli()
```

It produces the following help screens:

```shell-session
$ python ./my_cli.py
Usage: my_cli.py [OPTIONS] COMMAND [ARGS]...

Options:
  --dummy-flag / --no-flag  [default: no-flag]
  --my-list TEXT
  -C, --config CONFIG_PATH  Location of the configuration file. Supports both
                            local path and remote URL.  [default:
                            ~/.my_cli.py/config.{toml,yaml,yml,json,ini,xml}]
  --help                    Show this message and exit.

Commands:
  subcommand
```

A bare call returns:

```shell-session
$ ./my_cli.py subcommand
dummy_flag    is False
my_list       is ()
int_parameter is 10
```

Now we will change the default CLI output by creating a TOML file at
`~/.my_cli.py/config.toml` which contains:

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

- the configuration's folder (`~/.my_cli.py/`) which correspond to the script's
  name (`my_cli.py`);
- the top-level config section (`[my-cli]`), that is derived from the CLI's
  group ID (`def my_cli()`);
- all the extra comments, sections and values that will be silently ignored.

Now we can verify the TOML file is read automatticaly and change the defaults:

```shell-session
$ ./my_cli.py subcommand
dummy_flag    is True
my_list       is ('item 1', 'item #2', 'Very Last Item!')
int_parameter is 3
```

Still, any inline parameter is allowedal to ovverides the configuration
defaults:

```shell-session
$ ./my_cli.py subcommand --int-param 555
dummy_flag    is True
my_list       is ('item 1', 'item #2', 'Very Last Item!')
int_parameter is 555
```

## YAML configuration

Same example as above is working as-is with YAML.

Just replace the TOML file with the following configuration at
`~/.my_cli.py/config.yaml`:

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
$ ./my_cli.py --config ~/.my_cli.py/config.yaml subcommand
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
$ ./my_cli.py --config ~/.my_cli.py/config.json subcommand
dummy_flag    is True
my_list       is ('item 1', 'item #2', 'Very Last Item!')
int_parameter is 65
```

## INI configuration

## XML configuration

## Remote configuration

Remote URL can be passed directly to the `--config` option:

```shell-session
$ ./my_cli.py --config https://example.com/dummy/configuration.yaml subcommand
dummy_flag    is True
my_list       is ('point 1', 'point #2', 'Very Last Point!')
int_parameter is 77
```
