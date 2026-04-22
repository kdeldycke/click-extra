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
"""Allow the module to be run as a CLI. I.e.:

.. code-block:: shell-session

    $ python -m click_extra
"""

from __future__ import annotations

from click_extra.cli import demo


def main():
    """Indirection required to reconcile all invocation methods:

    - ``python -m click_extra``
    - entry point script: ``click-extra``
    - Nuitka: ``python -m nuitka (...) click_extra/__main__.py``

    See `poetry#5981 <https://github.com/python-poetry/poetry/issues/5981>`_.
    """
    demo()


if __name__ == "__main__":
    main()
