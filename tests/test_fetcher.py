from __future__ import annotations

import httpx

from engine.crawlers.fetcher import fetch_text, strip_html


def test_strip_html_removes_tags_and_scripts():
    html = (
        "<html><head><style>x{}</style></head><body><h1>Hi</h1>"
        "<script>bad()</script><p>UC300  4G</p></body></html>"
    )
    out = strip_html(html)
    assert "Hi" in out and "UC300 4G" in out
    assert "bad()" not in out and "x{}" not in out
    assert "<" not in out


def test_fetch_text_via_mock_transport():
    def handler(request):
        return httpx.Response(200, text="<p>Milesight UC300</p>")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = fetch_text("https://example.com/uc300", client=client)
    assert out == "Milesight UC300"
