# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
# All Rights Reserved.
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.

import click
from boltons.strutils import strip_ansi
from cloup import Context, group, option, option_group

from .. import __version__
from ..colorize import (
    ExtraCommand,
    ExtraGroup,
    HelpExtraFormatter,
    theme,
    version_option,
)


def test_options_highlight():
    formatter = HelpExtraFormatter()
    formatter.write("applies filtering by --manager and --exclude options")

    formatter.long_options = {"--manager", "--exclude"}

    output = formatter.getvalue()
    assert theme.option("--manager") in output
    assert theme.option("--exclude") in output


def test_choices_highlight():
    formatter = HelpExtraFormatter()
    formatter.write(
        """
        -e, --apt [apm|apt|apt-mint|brew]
                        Exclude a package manager.
                        Repeat to exclude multiple
                        managers.
        """
    )

    formatter.choices = {"apm", "apt", "apt-mint", "brew"}

    output = formatter.getvalue()
    assert theme.choice("apm") in output
    assert theme.choice("apt") in output
    assert theme.choice("apt-mint") in output
    assert theme.choice("brew") in output


def test_metavars_highlight():
    formatter = HelpExtraFormatter()
    formatter.write("-v, --verbosity LEVEL   Either CRITICAL, ERROR or DEBUG.")

    formatter.metavars = {"LEVEL"}

    output = formatter.getvalue()
    assert theme.metavar("LEVEL") in output


def test_only_full_word_highlight():
    formatter = HelpExtraFormatter()
    formatter.write("package snapshot")

    formatter.choices.add("snap")

    output = formatter.getvalue()
    # Make sure no highlighting occured
    assert strip_ansi(output) == output


def test_keyword_collection(invoke):

    # Create a dummy Click CLI.
    Context.formatter_class = HelpExtraFormatter
    CONTEXT_SETTINGS = Context.settings(show_default=True)

    @group(cls=ExtraGroup, context_settings=CONTEXT_SETTINGS)
    @option_group(
        "Group 1",
        option("-a", "--opt1"),
        option("-b", "--opt2"),
    )
    @option_group(
        "Group 2",
        option("--opt3"),
        option("--opt4"),
    )
    @option("--config")
    @version_option()
    @click.help_option("-h", "--help")
    @click.pass_context
    def my_cli(ctx, opt1, opt2, opt3, opt4, config):
        pass

    @click.command(cls=ExtraCommand)
    @click.pass_context
    def command1(ctx):
        pass

    @click.command(cls=ExtraCommand)
    @click.pass_context
    def command2(ctx):
        pass

    @click.command(cls=ExtraCommand)
    @click.pass_context
    def command3(ctx):
        pass

    @click.command(cls=ExtraCommand)
    @click.pass_context
    def command4(ctx):
        pass

    my_cli.section("Subcommand group #1", command1, command2)
    my_cli.section("Extra commands", command3, command4)

    result = invoke(my_cli, "--help")
    result = invoke(my_cli, "-h")
    result = invoke(my_cli, "command4", "--help")
    result = invoke(command4, "--help")


def test_version_option(invoke):

    # Create a dummy Click CLI.
    Context.formatter_class = HelpExtraFormatter
    CONTEXT_SETTINGS = Context.settings(show_default=True)

    @group(cls=ExtraGroup, context_settings=CONTEXT_SETTINGS)
    @version_option()
    def mycli():
        pass

    # Test default colouring.
    result = invoke(mycli, "--version", color=True)
    assert result.exit_code == 0
    assert (
        result.stdout == f"\x1b[97mmycli\x1b[0m, version \x1b[32m{__version__}\x1b[0m\n"
    )
    assert not result.stderr

    # Test command invoker color stripping
    result = invoke(mycli, "--version", color=False)
    assert result.exit_code == 0
    assert result.stdout == f"mycli, version {__version__}\n"
    assert not result.stderr
