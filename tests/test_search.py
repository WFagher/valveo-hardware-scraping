from __future__ import annotations

import httpx

from engine.crawlers.search import web_search

_HTML = """
<div class="result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fmilesight.com%2Fuc300">UC300</a>
</div>
<div class="result">
  <a class="result__a" href="https://teracomsystems.com/tcg120">TCG120</a>
</div>
"""


def test_web_search_parses_and_decodes():
    def handler(request):
        return httpx.Response(200, text=_HTML)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    urls = web_search("anything", client=client)
    assert "https://milesight.com/uc300" in urls
    assert "https://teracomsystems.com/tcg120" in urls


def test_web_search_returns_empty_on_error():
    def handler(request):
        return httpx.Response(500, text="boom")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert web_search("anything", client=client) == []
