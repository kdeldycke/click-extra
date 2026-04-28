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
"""Fixtures and helpers for MkDocs tests.

Separated from the root ``tests/conftest.py`` so that the MkDocs dependency
(and ``mkdocs-click``, ``pymdown-extensions``) is only imported when running
the tests in this subdirectory.  Downstream packagers can skip these tests
with ``--ignore=tests/mkdocs`` without affecting the rest of the test suite.
"""

from __future__ import annotations
