import time
from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Protocol

from pydantic import ValidationError

from app.extraction.errors import ExtractionError, LLMUnavailable
from app.schemas.invoice import RawExtraction

RETRY_CODES = {429, 500, 502, 503, 504}  # temporary problems worth another try


@dataclass
class LLMResult:
    raw: RawExtraction
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


class LLMClient(Protocol):
    model: str

    def extract(self, system: str, user: str) -> LLMResult: ...


class GeminiClient:
    """The real provider. Only this class knows about the Gemini SDK."""

    def __init__(self, api_key: str, model: str, timeout: float = 60.0,
                 max_retries: int = 3, min_interval: float = 5.0):
        from google import genai  # imported here so tests never need the SDK or a key
        from google.genai import errors, types

        if not api_key:
            raise ExtractionError('GEMINI_API_KEY is not set')
        self._types = types
        self._api_error = errors.APIError
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=int(timeout * 1000)),  # the SDK counts milliseconds
        )
        self._max_retries = max_retries
        self._min_interval = min_interval  # free tier: stay under the requests-per-minute limit
        self._last_call = 0.0
        self.model = model

    def _wait_turn(self) -> None:
        pause = self._min_interval - (time.monotonic() - self._last_call)
        if pause > 0:
            time.sleep(pause)
        self._last_call = time.monotonic()

    def _generate(self, system: str, user: str):
        config = self._types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=8192,
            response_mime_type='application/json',
            response_json_schema=RawExtraction.model_json_schema(),
        )
        for attempt in range(self._max_retries + 1):
            self._wait_turn()
            try:
                return self._client.models.generate_content(model=self.model, contents=user, config=config)
            except self._api_error as exc:
                if exc.code not in RETRY_CODES:
                    raise ExtractionError(f'LLM call failed: {exc.code} {exc.message}') from exc
                if attempt == self._max_retries:
                    raise LLMUnavailable(f'LLM busy after {attempt + 1} tries: {exc.code} {exc.message}') from exc
                time.sleep(15 * 2**attempt)  # 15 s, 30 s, 60 s
    def extract(self, system: str, user: str) -> LLMResult:
        try:
            response = self._generate(system, user)
        except ExtractionError:
            raise
        except Exception as exc:  # timeouts and network errors come from the HTTP layer
            raise LLMUnavailable(f'LLM call failed: {exc}') from exc
        candidate = response.candidates[0] if response.candidates else None
        reason = candidate.finish_reason.name if candidate and candidate.finish_reason else 'NO_ANSWER'
        if reason != 'STOP':
            raise ExtractionError(f'LLM stopped early: {reason}')
        try:
            raw = RawExtraction.model_validate_json(response.text or '')
        except ValidationError as exc:
            raise ExtractionError(f'LLM reply did not match the schema: {exc}') from exc
        usage = response.usage_metadata
        return LLMResult(
            raw=raw,
            model=self.model,
            input_tokens=(usage.prompt_token_count or 0) if usage else 0,
            output_tokens=(usage.candidates_token_count or 0) if usage else 0,
        )


@dataclass
class FakeLLMClient:
    """For tests: returns a fixed answer (or one built from the prompt). No network."""

    response: RawExtraction | Callable[[str], RawExtraction]
    model: str = 'fake'
    calls: list[str] = field(default_factory=list)

    def extract(self, system: str, user: str) -> LLMResult:
        self.calls.append(user)
        raw = self.response(user) if callable(self.response) else self.response
        return LLMResult(raw=raw, model=self.model)


def make_client() -> LLMClient:
    """Build the real client from settings (.env)."""
    from app.core.config import Settings

    settings = Settings()
    return GeminiClient(
        api_key=settings.gemini_api_key,
        model=settings.llm_model,
        min_interval=settings.llm_min_interval,
    )