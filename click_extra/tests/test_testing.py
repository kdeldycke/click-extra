# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
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
"""Test the testing utilities."""

from __future__ import annotations

from .. import echo, command
from ..testing import ExtraCliRunner


def test_extra_cli_runner():

    @command
    def cli_output():
        echo("1 - stdout")
        echo("2 - stderr", err=True)
        echo("3 - stdout")
        echo("4 - stderr", err=True)

    runner = ExtraCliRunner(mix_stderr=False)
    result = runner.invoke(cli_output)

    assert result.output == "1 - stdout\n3 - stdout\n"
    assert result.stdout == "1 - stdout\n3 - stdout\n"
    assert result.stderr == "2 - stderr\n4 - stderr\n"

    runner_mix = ExtraCliRunner(mix_stderr=True)
    result_mix = runner_mix.invoke(cli_output)

    assert result_mix.output == "1 - stdout\n3 - stdout\n"
    assert result_mix.stdout == "1 - stdout\n3 - stdout\n"

    @command
    def cli_empty_stderr():
        echo("stdout")

    for mix_stderr in (True, False):
        runner = ExtraCliRunner(mix_stderr=mix_stderr)
        result = runner.invoke(cli_empty_stderr)

        assert result.output == "stdout\n"
        assert result.stdout == "stdout\n"
