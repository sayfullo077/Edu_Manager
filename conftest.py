import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _clear_cache():
    """Rate limit hisoblagichlari va keshlangan sozlamalar testlar orasida o'tib ketmasin."""
    cache.clear()
    yield
    cache.clear()
