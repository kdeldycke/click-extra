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
"""Sign the `linkcheck` requests to github.com with a CI token.

GitHub throttles anonymous requests to about one a minute, which overruns the
link check of a site with many links to github.com. When the environment holds
{data}`GITHUB_TOKEN_ENV`, as a CI workflow sets it on its link-check step, the
requests to github.com carry that token. A local build has no token, so its
requests stay anonymous.

Release downloads stay anonymous: with an `Authorization` header, github.com
redirects them to the legacy `objects.githubusercontent.com` host, whose signed
URL answers 401. A page linking one download per released binary would then
report every one of them as broken. `linkcheck_auth` carries the exception
because its patterns are regular expressions, where `linkcheck_request_headers`
matches whole hosts only.
"""

from __future__ import annotations

import os

TYPE_CHECKING = False
if TYPE_CHECKING:
    from requests import PreparedRequest
    from sphinx.application import Sphinx
    from sphinx.config import Config


GITHUB_TOKEN_ENV = "GITHUB_TOKEN"
"""Environment variable holding the token the requests to github.com carry."""

GITHUB_URL_PATTERN = r"https://github\.com/(?!.*/releases/(?:latest/)?download/)"
"""URLs the token signs: every page of github.com, but a release download."""


def github_bearer_auth(request: PreparedRequest) -> PreparedRequest:
    """Sign `request` with the token {data}`GITHUB_TOKEN_ENV` holds.

    The token is read when the request goes out. A function also stays out of
    the build environment Sphinx pickles, where an object holding the token would
    have written it to disk.

    :return: the request, as `requests` expects from an `auth` callable.
    """
    request.headers["Authorization"] = f"Bearer {os.environ[GITHUB_TOKEN_ENV]}"
    return request


def add_github_auth(app: Sphinx, config: Config) -> None:
    """Append the github.com entry to `linkcheck_auth`, if a token is set.

    The entry goes after the ones `conf.py` declares. Sphinx signs a request with
    the first entry whose pattern matches its URL, so a project entry keeps
    precedence.
    """
    if not os.environ.get(GITHUB_TOKEN_ENV):
        return
    config.linkcheck_auth = [
        *config.linkcheck_auth,
        (GITHUB_URL_PATTERN, github_bearer_auth),
    ]


def setup(app: Sphinx) -> None:
    """Register the github.com authentication on `app`.

    Called from {func}`click_extra.sphinx.setup` so projects only need to list
    `"click_extra.sphinx"` in their `extensions`. `config-inited` fires once
    `conf.py` is read, so its own `linkcheck_auth` entries come first.
    """
    app.connect("config-inited", add_github_auth)
