"""Small free-input adapter for manual native request preparation; never calls a model."""
import copy,json,re,urllib.request,xml.etree.ElementTree as ET,email.utils
from datetime import datetime,timedelta,timezone
from dataclasses import replace
IR='https://investor.nvidia.com/news/press-release-details/2026/NVIDIA-Announces-Financial-Results-for-Second-Quarter-Fiscal-2027/'
RSS='https://nvidianews.nvidia.com/releases.xml'

class ResearchMaterials:
    def __init__(self,out,asof):
        self.out=out;self.asof=asof;self.news=[];self.official={};self.audit={'asof':asof.isoformat(),'official_source':IR,'provided_fields':[],'selected_news':[],'errors':[]}
        for url,name in [(IR,'OFFICIAL_FINANCIAL_RELEASE.html'),(RSS,'OFFICIAL_NEWS_RSS.xml')]:
            try:
                req=urllib.request.Request(url,headers={'User-Agent':'DSA Personal Research zhuyifeng288@gmail.com'})
                with urllib.request.urlopen(req,timeout=25) as response:
                    raw=response.read(4000000);status=response.status
                (out/name).write_bytes(raw);fetched=datetime.now(timezone.utc).isoformat()
                self.audit[name]={'url':url,'status':status,'fetched_at':fetched}
                if url==RSS:
                    for item in ET.fromstring(raw).findall('.//item'):
                        try:published=email.utils.parsedate_to_datetime(item.findtext('pubDate'))
                        except (TypeError,ValueError):continue
                        if published.tzinfo is None or not asof-timedelta(days=3)<=published<=asof:continue
                        title=item.findtext('title');link=item.findtext('link')
                        if title and link and link.startswith('https://'):
                            self.news.append({'title':title,'url':link,'published_at':published.isoformat(),'fetched_at':fetched,'source':'NVIDIA official newsroom RSS'})
                    self.news=self.news[:3]
                else:
                    from bs4 import BeautifulSoup
                    soup=BeautifulSoup(raw,'html.parser');text=soup.get_text(' ',strip=True)
                    period=re.search(r'quarter ended (July \d{1,2}, 2026)',text,re.I)
                    if not period or 'August 26, 2026' not in text:raise ValueError('official_period_or_publication_date_unverified')
                    self.official={'period_end':datetime.strptime(period.group(1),'%B %d, %Y').date().isoformat(),'published_date':'2026-08-26','publication_time_exact':None,'currency':'USD','values':{}}
                    targets={'Revenue':'revenue','Net income':'net_profit_parent','Net cash provided by operating activities':'operating_cash_flow'}
                    for tr in soup.find_all('tr'):
                        cells=[td.get_text(' ',strip=True) for td in tr.find_all(['td','th'])]
                        if not cells:continue
                        for label,field in targets.items():
                            if cells[0].strip()==label and field not in self.official['values']:
                                nums=re.findall(r'\d[\d,]*', ' '.join(cells[1:]))
                                if nums:self.official['values'][field]=float(nums[0].replace(',',''))*1000000
                    if len(self.official['values'])!=3:raise ValueError('official_table_parse_incomplete')
            except Exception as exc:self.audit['errors'].append({'source':url,'category':type(exc).__name__})
        self.audit['official_verification']=self.official;self.audit['selected_news']=self.news;self.save()

    def save(self):
        (self.out/'RESEARCH_MATERIAL_AUDIT.json').write_text(json.dumps(self.audit,ensure_ascii=False,indent=2),encoding='utf-8')

    def prepare_artifacts(self,artifacts,trend):
        enhanced,news,notes=self.attach(artifacts.enhanced_context,trend)
        prepared=replace(artifacts,enhanced_context=enhanced,fundamental_context=enhanced.get('fundamental_context'),news_context=news,news_result_count=len(self.news))
        self.prepared_context=enhanced;self.prepared_news=news
        return prepared,notes

    def attach(self,enhanced,trend):
        result=copy.deepcopy(enhanced);raw=result.get('fundamental_context') or {}
        (self.out/'ORIGINAL_YAHOO_FUNDAMENTAL_CONTEXT.json').write_text(json.dumps(raw,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
        data=(raw.get('earnings') or {}).get('data') or {};fin=data.get('financial_report') or {}
        fields={k:fin.get(k) for k in ('revenue','net_profit_parent','operating_cash_flow')}
        self.audit['provided_fields']=[k for k,v in fields.items() if v is not None]
        self.audit['yahoo_report_date']=fin.get('report_date');self.audit['yahoo_currency']=fin.get('currency')
        official=self.official;checks={k:(v is not None and v==official.get('values',{}).get(k)) for k,v in fields.items()}
        self.audit['official_value_matches']=checks;notes=['独立免费材料核验说明：']
        if len(self.audit['provided_fields'])==3 and all(checks.values()) and fin.get('currency')=='USD':
            old=fin.get('report_date');fin['report_date']=f"{official['period_end']}（FY2027 Q2；Yahoo原列{old}）"
            result['fundamental_context']['earnings']['data']['financial_report']=fin
            self.audit['period_normalized_to_official']=True
            notes.append(f"财务为截至{official['period_end']}的单季度、USD，三个金额经公司官方财报表核对一致；Yahoo原列日期{old}已保留。官方公告日期{official['published_date']}，精确首次公开时间未证明；当前材料准备不作历史公开时点保证。来源{IR}。不得混用半年现金流或非GAAP净利。")
        else:
            self.audit['period_normalized_to_official']=False
            notes.append(f"财务仍为Yahoo聚合字段（币种{fin.get('currency')}、原列期间{fin.get('report_date')}），未全部通过官方核对，不能统称正式GAAP数据。缺失字段{[k for k,v in fields.items() if v is None]}。")
        if trend:
            t=trend[-1];notes.append(f"原版技术路径用{t['rows']}根真实日线计算；MA60={t['ma60']}，60根复算核验={t['ma60_verified']}；当前收盘={t['close']}，报价USD。均线位置是状态，不自行断言当天发生穿越事件。")
        notes.append('新闻仅由独立准备入口将官方RSS传入news_context；原SearchService仍未配置。不要将财报统计期或采集时间当新闻发布时间。')
        notes.append('ROE、估值、增长率与分红等其余Yahoo字段尚未逐项官方核验，可能为TTM或独立统计口径，不要将三个金额的核对结论扩展到全部指标。')
        news='\n\n'.join(f"来源：{n['source']}\n标题：{n['title']}\n发布时间：{n['published_at']}\n采集时间：{n['fetched_at']}\n原文：{n['url']}\n仅提供标题/发布元数据，未提供全文，不推断未给出的细节。" for n in self.news) or '暂无可验证的截止前官方RSS新闻。'
        self.save();return result,news,'\n'.join(notes)
