import copy,pathlib,tempfile,unittest
from nvda_research_materials import ResearchMaterials
class Tests(unittest.TestCase):
    def material(self,out):
        m=object.__new__(ResearchMaterials);m.out=out;m.news=[]
        m.official={'period_end':'2026-07-26','published_date':'2026-08-26','values':{'revenue':10,'net_profit_parent':2,'operating_cash_flow':3}}
        m.audit={};return m
    def context(self):
        return {'fundamental_context':{'earnings':{'data':{'financial_report':{'revenue':10,'net_profit_parent':2,'operating_cash_flow':3,'currency':'USD','report_date':'2026-07-31'}}}}}
    def test_verified_period_annotation_preserves_raw(self):
        with tempfile.TemporaryDirectory() as t:
            m=self.material(pathlib.Path(t));c=self.context();original=copy.deepcopy(c)
            result,news,notes=m.attach(c,[])
            self.assertEqual(c,original);self.assertIn('2026-07-26',result['fundamental_context']['earnings']['data']['financial_report']['report_date'])
            self.assertTrue(m.audit['period_normalized_to_official']);self.assertIn('2026-07-31',notes)
    def test_unmatched_amount_is_not_certified(self):
        with tempfile.TemporaryDirectory() as t:
            m=self.material(pathlib.Path(t));c=self.context();c['fundamental_context']['earnings']['data']['financial_report']['revenue']=11
            r,_,notes=m.attach(c,[]);self.assertFalse(m.audit['period_normalized_to_official']);self.assertIn('不能统称正式GAAP',notes)
    def test_missing_financials_stay_missing(self):
        with tempfile.TemporaryDirectory() as t:
            m=self.material(pathlib.Path(t));r,_,_=m.attach({},[])
            self.assertEqual(m.audit['provided_fields'],[]);self.assertFalse(m.audit['period_normalized_to_official']);self.assertNotIn('fundamental_context',r)
    def test_rss_metadata_only_not_search_claim(self):
        with tempfile.TemporaryDirectory() as t:
            m=self.material(pathlib.Path(t));m.news=[{'source':'official','title':'fixture','published_at':'2026-10-14T10:00:00+00:00','fetched_at':'2026-10-15T00:00:00+00:00','url':'https://nvidianews.nvidia.com/fixture'}]
            _,news,notes=m.attach(self.context(),[]);self.assertIn('未提供全文',news);self.assertIn('未配置',notes)
    def test_native_pack_sees_supplied_news_before_summary(self):
        from src.services.analysis_context_builder import PipelineAnalysisArtifacts,_build_news_block
        with tempfile.TemporaryDirectory() as t:
            m=self.material(pathlib.Path(t));m.news=[{'source':'official','title':'fixture','published_at':'2026-10-14T10:00:00+00:00','fetched_at':'2026-10-15T00:00:00+00:00','url':'https://nvidianews.nvidia.com/fixture'}]
            a=PipelineAnalysisArtifacts(code='NVDA',stock_name='英伟达',market='us',phase=None,base_context={},enhanced_context=self.context(),realtime_quote=None,trend_result=None,chip_data=None,fundamental_context=None,news_context=None,news_result_count=None,metadata={})
            prepared,_=m.prepare_artifacts(a,[])
            self.assertEqual(_build_news_block(prepared).status.value,'available')
            self.assertIsNone(a.news_context)
if __name__=='__main__':unittest.main()
