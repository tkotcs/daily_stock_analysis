"""Yahoo-only class-share conversion; canonical storage/display code stays dotted."""
from unittest.mock import patch
import pandas as pd
import pytest
from data_provider.yfinance_fetcher import YfinanceFetcher


@pytest.mark.parametrize('code,expected',[
    ('BRK.A','BRK-A'),('BRK.B','BRK-B'),(' brk.b ','BRK-B'),
    ('NVDA','NVDA'),('AAPL','AAPL'),('MSFT','MSFT'),('QQQ','QQQ'),
    ('SPCX','SPCX'),('SKHY','SKHY'),
    ('SPX','^GSPC'),('^GSPC','^GSPC'),('NDX','^NDX'),('DJI','^DJI'),
    ('600519','600519.SS'),('000001','000001.SZ'),('510300','510300.SS'),
    ('hk00700','0700.HK'),('00700','0700.HK'),('9988.HK','9988.HK'),
    ('000660.KS','000660.KS'),('7203.T','7203.T'),
])
def test_yahoo_symbol_conversion(code,expected):
    assert YfinanceFetcher()._convert_stock_code(code)==expected


@pytest.mark.parametrize('code,yahoo',[('BRK.A','BRK-A'),('BRK.B','BRK-B')])
def test_download_uses_alias_but_dataframe_keeps_canonical_code(code,yahoo):
    raw=pd.DataFrame({'Open':[10.0,11.0],'High':[12.0,13.0],'Low':[9.0,10.0],
                      'Close':[11.0,12.0],'Volume':[100,110]},
                     index=pd.date_range('2026-10-12',periods=2,name='Date'))
    with patch('yfinance.download',return_value=raw) as download:
        fetcher=YfinanceFetcher()
        actual=fetcher.get_daily_data(code,start_date='2026-10-12',end_date='2026-10-14')
    assert download.call_args.kwargs['tickers']==yahoo
    assert download.call_args.kwargs['auto_adjust'] is True
    assert actual['code'].tolist()==[code,code]
