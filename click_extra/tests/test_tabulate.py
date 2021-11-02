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

from ..tabulate import table_format_option


def test_unrecognized_format(invoke):
    @click.command()
    @table_format_option()
    def dummy_cli():
        click.echo("It works!")

    result = invoke(dummy_cli, "--table-format", "random")
    assert result.exit_code == 2
    assert not result.output
    assert result.stderr == (
        "Usage: dummy-cli [OPTIONS]\n"
        "Try 'dummy-cli --help' for help.\n\n"
        "Error: Invalid value for '-t' / '--table-format': "
        "'random' is not one of 'ascii', 'csv', 'csv-tab', 'double', 'double_grid', "
        "'double_outline', 'fancy_grid', 'github', 'grid', 'html', 'jira', 'latex', "
        "'latex_booktabs', 'mediawiki', 'minimal', 'moinmoin', 'orgtbl', 'outline', "
        "'pipe', 'plain', 'psql', 'psql_unicode', 'rounded_grid', 'rounded_outline', "
        "'rst', 'simple', 'simple_grid', 'simple_outline', 'textile', 'tsv', "
        "'vertical'.\n"
    )


def test_standalone_verbosity_option(invoke):
    @click.command()
    @table_format_option()
    @click.pass_context
    def dummy_cli(ctx):
        click.echo(
            f"ctx.table_formatter.format_name = {ctx.table_formatter.format_name}"
        )
        data = ((1, 87), (2, 80), (3, 79))
        headers = ("day", "temperature")
        ctx.print_table(data, headers)

    result = invoke(dummy_cli, "--table-format", "fancy_grid")

    assert result.exit_code == 0
    assert result.output == (
        "ctx.table_formatter.format_name = fancy_grid\n"
        "╒═════╤═════════════╕\n"
        "│ day │ temperature │\n"
        "╞═════╪═════════════╡\n"
        "│   1 │          87 │\n"
        "├─────┼─────────────┤\n"
        "│   2 │          80 │\n"
        "├─────┼─────────────┤\n"
        "│   3 │          79 │\n"
        "╘═════╧═════════════╛\n"
    )
