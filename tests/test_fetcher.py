from __future__ import annotations

import httpx

from engine.crawlers.fetcher import extract_main, fetch_main, fetch_text, strip_html


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


def test_extract_main_drops_nav_keeps_article():
    html = (
        "<html><body><nav>Home Products Support Company Contact</nav>"
        "<article><h1>UC300 Datasheet</h1>"
        + "<p>The UC300 is a 4G LTE controller with 2 relay outputs and MQTT support. </p>" * 6
        + "</article><footer>copyright</footer></body></html>"
    )
    out = extract_main(html)
    assert "UC300" in out and "relay" in out


def test_fetch_main_via_mock_transport():
    def handler(request):
        return httpx.Response(200, text="<p>Milesight UC300</p>")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    # tiny page -> readability falls back to strip_html
    assert fetch_main("https://example.com/uc300", client=client) == "Milesight UC300"
