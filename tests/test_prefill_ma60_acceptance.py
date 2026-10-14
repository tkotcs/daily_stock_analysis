"""Original MA60 boundaries; no network, model, database or alternate formula."""
import math
import pandas as pd
import pytest
from src.stock_analyzer import StockTrendAnalyzer


@pytest.mark.parametrize('length',[60,63,90,124])
def test_original_ma60_has_real_window(length):
    frame=pd.DataFrame({'close':[float(i*i+10) for i in range(length)]})
    actual=StockTrendAnalyzer()._calculate_mas(frame)
    expected=sum(frame['close'].iloc[-60:])/60
    assert actual['MA60'].iloc[:59].isna().all()
    assert actual['MA60'].first_valid_index()==59
    assert math.isclose(actual['MA60'].iloc[-1],expected,rel_tol=1e-12)
    assert actual['MA60'].iloc[-1]!=actual['MA20'].iloc[-1]


def test_insufficient_history_still_falls_back_in_unmodified_upstream():
    # Detect the existing behavior; deployment acceptance must reject this length.
    actual=StockTrendAnalyzer()._calculate_mas(pd.DataFrame({'close':range(41)}))
    assert actual['MA60'].equals(actual['MA20'])
    assert actual['MA60'].first_valid_index()==19
