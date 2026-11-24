class ExtractionError(Exception):
    code = 'extraction_failed'

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message