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

from boltons.strutils import strip_ansi
from cloup import option, option_group

from .. import __version__
from ..colorize import HelpExtraFormatter, theme, version_option
from ..commands import command, group


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
    @group()
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
    def mycli(opt1, opt2, opt3, opt4, config):
        print("It works!")

    @command()
    def command1():
        print("Run command #1...")

    @command()
    def command2():
        print("Run command #2...")

    @command()
    def command3():
        print("Run command #3...")

    @command()
    def command4():
        print("Run command #4...")

    mycli.section("Subcommand group #1", command1, command2)
    mycli.section("Extra commands", command3, command4)

    help_screen = (
        "\x1b[94m\x1b[1m\x1b[94m\x1b[1mUsage\x1b[0m: "
        "\x1b[0m\x1b[97mmycli\x1b[0m [OPTIONS] COMMAND [ARGS]...\n\n"
        "\x1b[94m\x1b[1m\x1b[94m\x1b[1mGroup \x1b[35m1\x1b[0m\x1b[0m:\x1b[0m\n"
        "  \x1b[36m-a, \x1b[36m--opt1\x1b[0m TEXT\x1b[0m\n"
        "  \x1b[36m-b, \x1b[36m--opt2\x1b[0m TEXT\x1b[0m\n\n"
        "\x1b[94m\x1b[1m\x1b[94m\x1b[1mGroup \x1b[35m2\x1b[0m\x1b[0m:\x1b[0m\n"
        "  \x1b[36m--opt3 TEXT\x1b[0m\n"
        "  \x1b[36m--opt4 TEXT\x1b[0m\n\n"
        "\x1b[94m\x1b[1m\x1b[94m\x1b[1mOther options\x1b[0m:\x1b[0m\n"
        "  \x1b[36m--config TEXT\x1b[0m\n\n"
        "\x1b[94m\x1b[1m\x1b[94m\x1b[1mSubcommand group #1\x1b[0m:\x1b[0m\n"
        "  \x1b[36mcommand1\x1b[0m\n"
        "  \x1b[36mcommand2\x1b[0m\n\n"
        "\x1b[94m\x1b[1m\x1b[94m\x1b[1mExtra commands\x1b[0m:\x1b[0m\n"
        "  \x1b[36mcommand3\x1b[0m\n"
        "  \x1b[36mcommand4\x1b[0m\n"
    )

    result = invoke(mycli, "--help", color=True)
    assert result.output == help_screen

    result = invoke(mycli, "-h", color=True)
    assert result.output == help_screen

    # CLI main group is invoked before sub-command.
    result = invoke(mycli, "command4", "--help", color=True)
    assert result.output == (
        "It works!\n"
        "\x1b[94m\x1b[1m\x1b[94m\x1b[1mUsage\x1b[0m: \x1b[0m\x1b[97mmycli command4\x1b[0m [OPTIONS]\n\n"
        "\x1b[94m\x1b[1m\x1b[94m\x1b[1mOptions\x1b[0m:\x1b[0m\n"
        "  \x1b[36m--help\x1b[0m  Show this message and exit.  [default: False]\x1b[0m\n"
    )

    # Check CLI main group is skipped.
    result = invoke(command4, "--help", color=True)
    assert result.output == (
        "\x1b[94m\x1b[1m\x1b[94m\x1b[1mUsage\x1b[0m: \x1b[0m\x1b[97mcommand4\x1b[0m [OPTIONS]\n\n"
        "\x1b[94m\x1b[1m\x1b[94m\x1b[1mOptions\x1b[0m:\x1b[0m\n"
        "  \x1b[36m--help\x1b[0m  Show this message and exit.\x1b[0m\n"
    )


def test_version_option(invoke):

    # Create a dummy Click CLI.
    @group()
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
