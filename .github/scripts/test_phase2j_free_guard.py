"""Pure URL-policy tests; no transports or paid requests are used."""
import pytest
from phase2j_free_guard import free_yahoo_get


@pytest.mark.parametrize('url', ['https://query1.finance.yahoo.com/v8/finance/chart/NVDA',
                              'https://query2.finance.yahoo.com/v10/finance/quoteSummary/BRK-B',
                              'https://fc.yahoo.com/'])
def test_public_yahoo_get_allowed(url):
    assert free_yahoo_get('GET', url)


@pytest.mark.parametrize('method,url', [
    ('POST', 'https://api.deepseek.com/chat/completions'),
    ('POST', 'https://query1.finance.yahoo.com/'),
    ('GET', 'https://api.deepseek.com/models'),
    ('GET', 'https://yahoo.com.evil.invalid/'),
    ('GET', 'http://query1.finance.yahoo.com/'),
    ('GET', 'https://secret@query1.finance.yahoo.com/'),
    ('GET', 'https://query1.finance.yahoo.com:444/'),
])
def test_other_endpoints_and_post_forbidden(method, url):
    assert not free_yahoo_get(method, url)
