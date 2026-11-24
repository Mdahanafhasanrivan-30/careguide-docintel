class DocumentError(Exception):
    # Base class for expected, user-facing failures.
    code = 'document_error'

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class UnsupportedFileType(DocumentError):
    code = 'unsupported_file_type'


class CorruptFile(DocumentError):
    code = 'corrupt_file'


class PasswordProtected(DocumentError):
    code = 'password_protected'


class FileTooLarge(DocumentError):
    code = 'file_too_large'


class OcrFailed(DocumentError):
    code = 'ocr_failed'


