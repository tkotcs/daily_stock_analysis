"""Test-process boundary: free Yahoo GET only, no Python sockets or SMTP."""
import os
import smtplib
import socket
import urllib.request
from urllib.parse import urlsplit


class FreeSafetyStop(BaseException):
    pass


def free_yahoo_get(method, url):
    parts = urlsplit(str(url))
    host = parts.hostname or ''
    return (str(method).upper() == 'GET' and parts.scheme == 'https'
            and (host == 'yahoo.com' or host.endswith('.yahoo.com'))
            and parts.port in (None, 443) and parts.username is None and parts.password is None)


def install():
    for key in list(os.environ):
        if any(s in key for s in ('API_KEY', 'PASSWORD', 'ACCESS_TOKEN', 'WEBHOOK')) or key in ('GH_TOKEN', 'GITHUB_TOKEN'):
            os.environ.pop(key, None)
    import httpx
    import requests
    import curl_cffi.requests as curl
    counters = {'allowed_yahoo_GETs': 0, 'blocked_calls': 0, 'real_model_POSTs': 0, 'mail_sent': 0}

    def deny(*a, **kw):
        counters['blocked_calls'] += 1
        raise FreeSafetyStop('non_free_network_or_SMTP_forbidden')

    async def async_deny(*a, **kw):
        return deny()

    socket.socket.connect = deny
    socket.create_connection = deny
    smtplib.SMTP = deny
    smtplib.SMTP_SSL = deny
    urllib.request.urlopen = deny
    requests.Session.request = deny
    httpx.Client.send = deny
    httpx.AsyncClient.send = async_deny
    original = curl.Session.request

    def request(session, method, url, *a, **kw):
        if not free_yahoo_get(method, url):
            return deny()
        counters['allowed_yahoo_GETs'] += 1
        kw['allow_redirects'] = False
        return original(session, method, url, *a, **kw)

    curl.Session.request = request
    return counters


if __name__ == '__main__':
    import json
    import pathlib
    import sys
    counters = install()
    from phase2i_free_check import main
    # Reuse the reviewed collector; all of its real requests cross the guard above.
    try:
        main()
    finally:
        target = pathlib.Path(sys.argv[sys.argv.index('--out') + 1]).resolve()
        target.mkdir(parents=True, exist_ok=True)
        (target/'FREE_NETWORK_GUARD.json').write_text(json.dumps(counters, indent=2), encoding='utf-8')
