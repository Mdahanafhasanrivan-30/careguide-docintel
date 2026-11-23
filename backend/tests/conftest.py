from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / 'fixtures'


@pytest.fixture(scope='session')
def fx():
    def read(name: str) -> bytes:
        path = FIXTURES / name
        if not path.exists():
            pytest.fail(f'Missing fixture {name}. Run: dcrun python -m scripts.make_fixtures')
        return path.read_bytes()
    return read