"""Isolated negative checks of the free-only process guard. No real requests."""
import asyncio
import json
import smtplib

import curl_cffi.requests as curl
import httpx
import requests

from phase2j_free_guard import FreeSafetyStop, install

# Windows may use literal loopback internally when creating its event loop.
# Create the loop before locking down sockets; no externally addressed request.
loop = asyncio.new_event_loop()
counters = install()
passed = []


def blocked(name, function):
    try:
        function()
    except FreeSafetyStop:
        passed.append(name)
    else:
        raise AssertionError('guard_did_not_block_' + name)


blocked('SMTP_constructor', lambda: smtplib.SMTP('smtp.gmail.com', 587))
blocked('requests_model_POST', lambda: requests.post('https://api.deepseek.com/chat/completions'))
blocked('curl_model_POST', lambda: curl.Session().post('https://api.deepseek.com/chat/completions'))
with httpx.Client() as client:
    blocked('HTTPX_sync_POST', lambda: client.post('https://api.deepseek.com/chat/completions'))


async def asynchronous():
    async with httpx.AsyncClient() as client:
        try:
            await client.post('https://api.deepseek.com/chat/completions')
        except FreeSafetyStop:
            passed.append('HTTPX_async_POST')
        else:
            raise AssertionError('async_POST_not_blocked')


try:
    loop.run_until_complete(asynchronous())
finally:
    loop.close()
assert len(passed) == counters['blocked_calls'] == 5
assert counters['allowed_yahoo_GETs'] == counters['real_model_POSTs'] == counters['mail_sent'] == 0
print(json.dumps({'passed_checks': passed, 'counters': counters, 'all_injected_attempts_blocked_before_network': True}, indent=2))
