# {octicon}`bug` Bug reports

A command given a `report_url` ends the run on an error it has no rule for with a bug report. After the traceback of the error comes a block for the user to paste into an issue, and a link to the issue form of the project, with a title filled in:

```{click:source}
from click_extra import command, echo, option

@command(report_url="https://github.com/orchard/harvest/issues/new")
@option("--fruit", help="The fruit to share.")
def harvest(fruit):
    """Share the fruits among the baskets."""
    baskets = []
    echo(f"{fruit}: {10 // len(baskets)} per basket")
```

```{click:run}
import os
import tempfile
from unittest.mock import patch

cache = tempfile.mkdtemp()
with patch.dict(os.environ, {"XDG_CACHE_HOME": cache, "LOCALAPPDATA": cache}):
    result = invoke(harvest, args=["--fruit", "plum"])
assert result.exit_code == 1
assert "harvest stopped on this error, which is a bug." in result.stderr
assert "/issues/new?title=ZeroDivisionError+in+harvest" in result.stderr
assert "Options: --fruit plum" in result.stderr
```

The block gives the version of the CLI, the platform, the options of the run and the traceback of the error. The report is also saved in a file of the cache of the CLI, whose path ends the output: a user who lost the output of the run still finds it there.

The title names the class of the error and the innermost function of the CLI that it went through. Reports of the same bug get the same title, so the issue form of GitHub lists the issue already open for it while the next user types theirs.

## What a report holds

Issues are often public, so a report holds no file path. The traceback shows module names and line numbers, which say as much about the code as file paths, and nothing about where it is installed. The options line masks the values of paths, patterns and positional arguments.

The message of the error shows as the code wrote it, and can quote the data of the user: the report asks them to read it before they paste it.

An AI agent that runs the CLI gets one more line. It tells the agent to show the report to its user, and to ask before it files the issue.

## Which errors get a report

- An exception that Click exits with, like a usage error, an abort, an end of input or a broken pipe, is no bug: Click handles it as before.
- An `OSError`, like a missing permission or a full disk, is for the user to fix: the run ends with a one-line `Error:`.
- Any other error gets a report, and the run exits with code `1`.

Set `report_url` on the root command. On a group, the error of any subcommand then gets one report, which names the subcommand and its options.

## A report that does not stop the run

`log_report()` logs a report of the same shape, for a failure that the CLI survives, like an item it set aside:

```{click:source}
import logging

from click_extra import command, echo, log_report

@command(report_url="https://github.com/orchard/harvest/issues/new")
def sort_fruits():
    """Sort the fruits, and set aside the ones that fail."""
    log_report(
        logging.WARNING,
        "One fruit was set aside after an unexpected error.",
        "Fruit set aside while sorting",
        ("", "Fruits set aside: 1"),
    )
    echo("Sorted the other fruits.")
```

```{click:run}
import os
import tempfile
from unittest.mock import patch

cache = tempfile.mkdtemp()
with patch.dict(os.environ, {"XDG_CACHE_HOME": cache, "LOCALAPPDATA": cache}):
    result = invoke(sort_fruits)
assert result.exit_code == 0
assert "Sorted the other fruits." in result.stdout
assert "Fruits set aside: 1" in result.stderr
```

{func}`~click_extra.bug_report.compact_frames`, {func}`~click_extra.bug_report.culprit_function` and {func}`~click_extra.bug_report.describe_error` reduce an error to the lines and the title of such a report.
