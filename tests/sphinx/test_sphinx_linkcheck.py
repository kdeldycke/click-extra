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
"""Tests for the github.com authentication of the `linkcheck` builder."""

from __future__ import annotations

import re
from io import StringIO
from typing import Any

import pytest
from requests import PreparedRequest
from sphinx.application import Sphinx
from sphinx.util.docutils import docutils_namespace

from click_extra.sphinx.linkcheck import (
    GITHUB_TOKEN_ENV,
    GITHUB_URL_PATTERN,
    github_bearer_auth,
)

ORCHARD_AUTH = (r"https://orchard\.example\.com/", ("gardener", "spade"))
"""A `linkcheck_auth` entry a project declares in its own `conf.py`."""


def linkcheck_auth(tmp_path, entries: list[Any]) -> list[Any]:
    """Start a `linkcheck` build of a project declaring `entries`.

    :return: the `linkcheck_auth` the builder reads.
    """
    srcdir = tmp_path / "source"
    srcdir.mkdir()
    (srcdir / "conf.py").write_text(
        f"extensions = ['click_extra.sphinx']\nlinkcheck_auth = {entries!r}\n",
        encoding="UTF-8",
    )
    (srcdir / "index.rst").write_text("Orchard\n=======\n", encoding="UTF-8")
    outdir = tmp_path / "build"
    with docutils_namespace():
        app = Sphinx(
            str(srcdir),
            str(srcdir),
            str(outdir),
            str(outdir / ".doctrees"),
            "linkcheck",
            status=None,
            warning=StringIO(),
        )
    auth: list[Any] = app.config.linkcheck_auth
    return auth


def test_auth_entry_follows_the_project_ones(tmp_path, monkeypatch) -> None:
    """With a token, the github.com entry comes after the entries of `conf.py`.

    Sphinx signs a request with the first entry matching its URL, so a project
    entry keeps precedence.
    """
    monkeypatch.setenv(GITHUB_TOKEN_ENV, "pear-token")
    assert linkcheck_auth(tmp_path, [ORCHARD_AUTH]) == [
        ORCHARD_AUTH,
        (GITHUB_URL_PATTERN, github_bearer_auth),
    ]


@pytest.mark.parametrize("token", [None, ""], ids=["unset", "empty"])
def test_no_auth_entry_without_a_token(tmp_path, monkeypatch, token) -> None:
    """Without a token, `linkcheck_auth` holds the entries of `conf.py` alone."""
    if token is None:
        monkeypatch.delenv(GITHUB_TOKEN_ENV, raising=False)
    else:
        monkeypatch.setenv(GITHUB_TOKEN_ENV, token)
    assert linkcheck_auth(tmp_path, [ORCHARD_AUTH]) == [ORCHARD_AUTH]


def test_bearer_auth_signs_with_the_token(monkeypatch) -> None:
    """The request carries the token the environment holds when it goes out."""
    monkeypatch.setenv(GITHUB_TOKEN_ENV, "plum-token")
    request = PreparedRequest()
    request.prepare(method="GET", url="https://github.com/orchard/plums")
    assert github_bearer_auth(request) is request
    assert request.headers["Authorization"] == "Bearer plum-token"


@pytest.mark.parametrize(
    ("url", "signed"),
    [
        ("https://github.com/orchard/plums", True),
        ("https://github.com/orchard/plums/releases/tag/v1.0.0", True),
        ("https://github.com/orchard/plums/releases/download/v1.0.0/jam.zip", False),
        ("https://github.com/orchard/plums/releases/latest/download/jam.zip", False),
        ("https://github.com.example.com/orchard/plums", False),
        ("https://gist.github.com/orchard", False),
    ],
)
def test_github_url_pattern(url: str, signed: bool) -> None:
    """The token signs every page of github.com but a release download."""
    assert bool(re.match(GITHUB_URL_PATTERN, url)) is signed
