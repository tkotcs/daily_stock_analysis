"""Offline regression for quote/statement currency separation and native rendering."""
import json,os,pathlib,socket,sys,unittest
os.environ['LITELLM_LOCAL_MODEL_COST_MAP']='True'
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]))
from src.formatters import resolve_quote_currency
from src.analyzer import GeminiAnalyzer,AnalysisResult
from src.notification import NotificationService

class CurrencyTests(unittest.TestCase):
    def setUp(self):
        self.a=object.__new__(GeminiAnalyzer)
        self.a._skill_instructions_override=''
        self.a._default_skill_policy_override=''
        self.a._use_legacy_default_prompt_override=True

    def context(self,code):
        return {'code':code,'stock_name':code,'date':'2026-10-14','today':{'close':221.3,'open':225.53,'high':226,'low':219.64,'amount':25947204057.8,'ma5':227.18,'ma10':231.63,'ma20':228.69,'volume':117249000},'yesterday':{'close':228.52}}

    def test_us_stock_etf_adr_and_class_shares(self):
        for code in ['NVDA','QQQ','SOXX','SKHY','TSM','BRK.A','BRK.B','SPCX']:
            with self.subTest(code=code):self.assertEqual(resolve_quote_currency({'code':code}),'USD')

    def test_cn_hk_markets(self):
        for code,currency in [('600519','CNY'),('510300','CNY'),('hk00700','HKD'),('00700','HKD')]:
            with self.subTest(code=code):self.assertEqual(resolve_quote_currency({'code':code}),currency)

    def test_unknown_currency_explicitly_marked(self):
        c=self.context('UNKNOWN-SYMBOL')
        self.assertIsNone(resolve_quote_currency(c))
        self.assertIn('币种未核实',self.a._format_prompt(c,'unknown'))

    def test_quote_metadata_beats_market_without_using_financial_currency(self):
        c=self.context('TSM');c['fundamental_context']={'earnings':{'data':{'financial_report':{'currency':'TWD'}}}}
        self.assertEqual(resolve_quote_currency(c),'USD')
        c['quote_currency']='HKD'
        self.assertEqual(resolve_quote_currency(c),'HKD')

    def test_invalid_explicit_metadata_does_not_guess(self):
        self.assertIsNone(resolve_quote_currency({'code':'NVDA','quote_currency':'UNKNOWN'}))

    def test_us_prompt_prices_amount_and_instruction(self):
        p=self.a._format_prompt(self.context('NVDA'),'英伟达')
        self.assertIn('221.3 美元',p);self.assertIn('259.47 亿美元',p)
        self.assertIn('报价币种：USD',p);self.assertNotIn('221.3 元',p)

    def test_cn_and_hk_prompts_keep_currency(self):
        self.assertIn('221.3 元',self.a._format_prompt(self.context('600519'),'茅台'))
        self.assertIn('221.3 港元',self.a._format_prompt(self.context('hk00700'),'腾讯'))

    def test_realtime_and_chip_use_quote_currency(self):
        c=self.context('NVDA');c['realtime']={'price':222,'total_mv':100000000};c['chip']={'avg_cost':220}
        p=self.a._format_prompt(c,'英伟达')
        self.assertIn('222 美元',p);self.assertIn('220 美元',p);self.assertIn('1.00 亿美元',p)

    def test_snapshot_and_native_table(self):
        snap=self.a._build_market_snapshot(self.context('NVDA'))
        r=AnalysisResult(code='NVDA',name='英伟达',sentiment_score=45,trend_prediction='震荡',operation_advice='观望',market_snapshot=snap)
        lines=[];NotificationService()._append_market_snapshot(lines,r)
        report='\n'.join(lines)
        self.assertIn('报价币种：USD',report);self.assertIn('259.47 亿美元',report)

    def test_financial_formatter_keeps_separate_currency(self):
        self.assertIn('新台币',NotificationService._format_amount_cn(100000000,'TWD'))
        self.assertIn('美元',NotificationService._format_amount_cn(100000000,'USD'))

if __name__=='__main__':unittest.main()
