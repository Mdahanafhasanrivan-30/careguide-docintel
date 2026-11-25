class ExtractionError(Exception):
    code = 'extraction_failed'

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message



class LLMUnavailable(ExtractionError):
    """The provider is busy or unreachable (429, 5xx, timeout). Trying again later may work."""
    code = 'llm_unavailable'