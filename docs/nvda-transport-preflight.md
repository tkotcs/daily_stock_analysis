# Free NVDA transport preflight

Manual-only controller branch; a separate checkout pins original business source to 2b896241f69d0177c2b6f298cf69042b8531dd76. No API or mail secrets are injected. The native request uses a placeholder key and is stopped at HTTPX HTTPTransport/AsyncHTTPTransport before any model POST is sent.

The shared gate allows at most one POST attempt to the exact normal DeepSeek endpoint, denies retries at pool level, custom transport bypass and redirects. In free preflight it stops even the first attempt. Native stream and parameter-recovery tests use fake underlying transports; the second POST is denied. This is test instrumentation, not a research framework or monthly budget system.

Original DataFetcherManager days=90 and DatabaseManager save APIs provide fresh NVDA history to the same database used by original process_single_stock. No old evidence fallback is allowed. At least 60 rows and latest completed session are required. Technical MA60 read checks, full native request and raw request hash are recorded. Fundamentals and news are explicitly empty; interface readiness is not report quality validation.

No paid authorization, automatic schedule or email delivery is enabled. A real DEEPSEEK_API_KEY Secret requires separate user confirmation. Disable Actions again after collection. This deployment-specific English note has no existing translated counterpart.
