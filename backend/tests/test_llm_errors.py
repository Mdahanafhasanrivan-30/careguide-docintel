"""Which LLM failures are worth a retry later. No network: the SDK client is replaced by a fake."""
from types import SimpleNamespace

import pytest

from app.extraction import llm
from app.extraction.errors import ExtractionError, LLMUnavailable


class FakeAPIError(Exception):
    def __init__(self, code: int):
        super().__init__(code)
        self.code = code
        self.message = f'fake {code}'


class FailingModels:
    def __init__(self, code: int):
        self.code = code
        self.calls = 0

    def generate_content(self, **kwargs):
        self.calls += 1
        raise FakeAPIError(self.code)


def client_that_fails(code: int, monkeypatch) -> llm.GeminiClient:
    monkeypatch.setattr(llm.time, 'sleep', lambda seconds: None)   # do not really wait 15+30+60 s
    c = llm.GeminiClient.__new__(llm.GeminiClient)                  # skip __init__: no SDK, no key
    c._types = SimpleNamespace(GenerateContentConfig=lambda **kw: kw)
    c._api_error = FakeAPIError
    c._client = SimpleNamespace(models=FailingModels(code))
    c._max_retries, c._min_interval, c._last_call, c.model = 3, 0.0, 0.0, 'fake'
    return c


@pytest.mark.parametrize('code', [429, 500, 503])
def test_busy_provider_raises_llm_unavailable_after_all_tries(code, monkeypatch):
    c = client_that_fails(code, monkeypatch)
    with pytest.raises(LLMUnavailable) as err:
        c.extract('system', 'user')
    assert err.value.code == 'llm_unavailable'
    assert c._client.models.calls == 4          # 1 call + 3 retries, the loop is unchanged


@pytest.mark.parametrize('code', [400, 403])
def test_bad_request_is_not_retried(code, monkeypatch):
    c = client_that_fails(code, monkeypatch)
    with pytest.raises(ExtractionError) as err:
        c.extract('system', 'user')
    assert not isinstance(err.value, LLMUnavailable)
    assert c._client.models.calls == 1


def test_llm_unavailable_is_still_an_extraction_error():
    # Old code that catches ExtractionError (scripts, try_extract) keeps working.
    assert issubclass(LLMUnavailable, ExtractionError)