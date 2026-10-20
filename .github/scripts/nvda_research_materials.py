"""Small free-input adapter for manual native request preparation; never calls a model."""
import copy,json,math,re,urllib.request,xml.etree.ElementTree as ET,email.utils
from datetime import date,datetime,timedelta,timezone
from dataclasses import replace
from urllib.parse import urlsplit
IR='https://investor.nvidia.com/news/press-release-details/2026/NVIDIA-Announces-Financial-Results-for-Second-Quarter-Fiscal-2027/'
RSS='https://nvidianews.nvidia.com/releases.xml'


def attach_reviewed_materials(artifacts, packet, asof, out):
    if asof.utcoffset() is None:
        raise ValueError('research_cutoff_timezone_required')
    if not isinstance(packet, dict):
        raise ValueError('research_packet_object_required')
    item = packet.get(artifacts.code, {})
    if not isinstance(item, dict):
        raise ValueError('research_ticker_object_required')
    enhanced, supplied = artifacts.enhanced_context, None
    if 'values' in item:
        release = {key: value for key, value in item.items() if key not in ('dividend_announcements', 'financial_evidence')}
        enhanced, supplied = attach_reviewed_release(enhanced, {artifacts.code: release}, asof, out)
    elif set(item) - {'dividend_announcements', 'financial_evidence'}:
        raise ValueError('research_material_type_unknown')
    enhanced = copy.deepcopy(enhanced)
    if 'financial_evidence' in item:
        if artifacts.enhanced_context.get('is_index_etf'):
            raise ValueError('financial_evidence_not_applicable_ETF')
        evidence = validate_financial_evidence(item['financial_evidence'], asof)
        enhanced['financial_evidence'] = evidence
        (out/'FINANCIAL_EVIDENCE_USED.json').write_text(json.dumps(dict(
            supplied_material_not_automatically_authenticated=True,
            does_not_replace_vendor_financials=True, asof=asof.isoformat(),
            evidence=evidence), ensure_ascii=False, indent=2), encoding='utf-8')
    provided = 'dividend_announcements' in item
    entries = item.get('dividend_announcements', [])
    accepted, rejected = [], []
    if not isinstance(entries, list):
        raise ValueError('dividend_announcements_list_required')
    cutoff_date = asof.astimezone(timezone.utc).date()
    for index, entry in enumerate(entries):
        try:
            if artifacts.enhanced_context.get('is_index_etf'):
                raise ValueError('dividend_enterprise_material_not_applicable_ETF')
            if not isinstance(entry, dict):
                raise ValueError('dividend_announcement_object_required')
            source, source_url = entry.get('source'), entry.get('source_url')
            if not isinstance(source, str) or not source.strip() or not isinstance(source_url, str):
                raise ValueError('dividend_source_required')
            parsed_url = urlsplit(source_url)
            if parsed_url.scheme != 'https' or not parsed_url.hostname or parsed_url.username is not None or parsed_url.password is not None:
                raise ValueError('dividend_https_source_without_credentials_required')
            dates = {}
            for field in ('announcement_date', 'ex_dividend_date', 'record_date', 'payable_date'):
                value = entry.get(field)
                if field in ('record_date', 'payable_date') and value is None:
                    dates[field] = None
                    continue
                if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                    raise ValueError('dividend_date_precision_required')
                dates[field] = date.fromisoformat(value)
            fetched = datetime.fromisoformat(entry['fetched_at'])
            if fetched.utcoffset() is None:
                raise ValueError('dividend_fetched_timezone_required')
            if fetched > asof or dates['announcement_date'] > fetched.astimezone(timezone.utc).date():
                raise ValueError('dividend_announcement_unavailable_at_cutoff')
            if not dates['announcement_date'] <= cutoff_date < dates['ex_dividend_date']:
                raise ValueError('dividend_future_ex_date_required')
            if dates['record_date'] is not None and dates['record_date'] < dates['ex_dividend_date']:
                raise ValueError('dividend_record_date_before_ex_date')
            if dates['payable_date'] is not None and dates['payable_date'] < (dates['record_date'] or dates['ex_dividend_date']):
                raise ValueError('dividend_payable_date_before_record_or_ex_date')
            amount, currency = entry.get('cash_dividend_per_share'), entry.get('currency')
            if type(amount) not in (int, float) or not math.isfinite(amount) or amount <= 0:
                raise ValueError('dividend_positive_finite_amount_required')
            if not isinstance(currency, str) or not re.fullmatch('[A-Z]{3}', currency):
                raise ValueError('dividend_currency_required')
            accepted.append(dict(source=source.strip(), source_url=source_url, fetched_at=entry['fetched_at'],
                                 cash_dividend_per_share=amount, currency=currency,
                                 **{field: value.isoformat() if value is not None else None for field, value in dates.items()}))
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            rejected.append(dict(index=index, reason=str(error)))
    audit = dict(provided=provided, accepted=accepted, rejected=rejected, asof=asof.isoformat(),
                 date_comparison_calendar='UTC', date_precision='date_only_not_first_publication_time',
                 source_verification='supplied_material_not_automatically_authenticated')
    enhanced['dividend_announcement_audit'] = audit
    if accepted:
        fundamental = enhanced.setdefault('fundamental_context', {}) or {}
        enhanced['fundamental_context'] = fundamental
        earnings = fundamental.setdefault('earnings', {})
        data = earnings.setdefault('data', {})
        data.setdefault('dividend', {})['announced_future'] = copy.deepcopy(accepted)
    (out/'DIVIDEND_ANNOUNCEMENT_AUDIT.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    return replace(artifacts, enhanced_context=enhanced, fundamental_context=enhanced.get('fundamental_context'),
                   news_context=supplied or artifacts.news_context)


def validate_financial_evidence(evidence, asof):
    """Check a supplied three-field comparison, without authenticating its sources."""
    if asof.utcoffset() is None or not isinstance(evidence, dict):
        raise ValueError('financial_evidence_object_and_aware_cutoff_required')
    sources = evidence.get('sources')
    fields = evidence.get('fields')
    if not isinstance(sources, dict) or not sources or not isinstance(fields, dict) or not fields:
        raise ValueError('financial_evidence_sources_and_fields_required')
    if set(fields) - {'revenue', 'net_income', 'operating_cash_flow'}:
        raise ValueError('financial_evidence_field_not_supported')
    for source in sources.values():
        parsed = urlsplit(source['url'])
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None or parsed.password is not None:
            raise ValueError('financial_evidence_https_source_required')
        if not re.fullmatch('[0-9a-f]{64}', source['sha256']):
            raise ValueError('financial_evidence_source_hash_required')
        fetched = datetime.fromisoformat(source['fetched_at'])
        if fetched.utcoffset() is None or fetched > asof:
            raise ValueError('financial_evidence_fetched_at_invalid')
        period = date.fromisoformat(source['period_end'])
        published = date.fromisoformat(source['published_date'])
        if not period <= published <= fetched.astimezone(timezone.utc).date():
            raise ValueError('financial_evidence_publication_or_period_invalid')
        if (type(source['page_count']) is not int or source['page_count'] < 1
                or type(source['duration_months']) is not int or source['duration_months'] not in (3, 6, 9, 12)
                or type(source['fiscal_year']) is not int):
            raise ValueError('financial_evidence_source_dimensions_invalid')
        if (not isinstance(source['currency'], str) or not re.fullmatch('[A-Z]{3}', source['currency'])
                or source['unit'] not in ('units', 'thousands', 'millions', 'billions')):
            raise ValueError('financial_evidence_currency_or_unit_invalid')

    def row_source(row):
        source = sources[row['source_id']]
        if (type(row['page']) is not int or not 1 <= row['page'] <= source['page_count']
                or not isinstance(row['statement_label'], str) or not row['statement_label'].strip()):
            raise ValueError('financial_evidence_page_or_statement_label_invalid')
        if type(row['value']) not in (int, float) or not math.isfinite(row['value']):
            raise ValueError('financial_evidence_finite_value_required')
        if row['currency'] != source['currency'] or row['unit'] != source['unit']:
            raise ValueError('financial_evidence_currency_or_unit_mismatch')
        if row['period_end'] != source['period_end']:
            raise ValueError('financial_evidence_period_mismatch')
        return source

    for name, field in fields.items():
        if type(field['value']) not in (int, float) or not math.isfinite(field['value']):
            raise ValueError('financial_evidence_finite_value_required')
        if field['kind'] == 'direct_quarter':
            if row_source(field)['duration_months'] != 3:
                raise ValueError('financial_evidence_direct_quarter_required')
        elif field['kind'] == 'derived_from_ytd_difference':
            if name != 'operating_cash_flow' or len(field['operands']) != 2:
                raise ValueError('financial_evidence_CFO_two_operands_required')
            left, right = field['operands']
            a, b = row_source(left), row_source(right)
            if (a['fiscal_year'] != b['fiscal_year'] or a['duration_months'] - b['duration_months'] != 3
                    or not date.fromisoformat(b['period_end']) < date.fromisoformat(a['period_end'])
                    or field['period_end'] != a['period_end']
                    or left['currency'] != right['currency'] or left['unit'] != right['unit']
                    or field['currency'] != left['currency'] or field['unit'] != left['unit']
                    or left['statement_label'] != right['statement_label']):
                raise ValueError('financial_evidence_CFO_period_or_basis_mismatch')
            if not math.isclose(left['value'] - right['value'], field['value'], rel_tol=1e-12, abs_tol=1e-9):
                raise ValueError('financial_evidence_CFO_difference_mismatch')
        else:
            raise ValueError('financial_evidence_kind_invalid')
    return copy.deepcopy(evidence)


def format_financial_evidence(context, report_language='zh'):
    evidence = context.get('financial_evidence')
    if not evidence:
        return ''
    if report_language == 'en':
        heading = 'Supplied independent financial comparison evidence'
        limit = ('Separate source comparison, not a replacement of vendor fields or financial statuses. '
                 'Net income does not verify parent-attributable income; CFO marked derived_from_ytd_difference '
                 'is calculated from two cumulative periods, not a directly disclosed quarter row. '
                 'Not recent news, a forecast, or a validation of ROE, dividends or valuation. '
                 'Source identity and hashes are supplied, not automatically authenticated.')
    else:
        heading = '随附独立财务比较证据'
        limit = ('独立比较材料，不覆盖供应商原字段、期间键或财务状态。Net income不等于已独立核验归母归属；'
                 '标记derived_from_ytd_difference的CFO为两个累计期间相减，不是直接披露的季度行。'
                 '不是近三日新闻、盈利预测或ROE/分红/估值验证。来源身份及哈希为随附材料，不自动认证。')
    return f'\n### {heading}\n{limit}\n{json.dumps(evidence, ensure_ascii=False, indent=2)}\n'


def format_dividend_announcements(context, report_language='zh'):
    audit = context.get('dividend_announcement_audit')
    if not audit:
        return ''
    english = report_language == 'en'
    heading = 'Supplied announced future dividends' if english else '随附已公告未来分红'
    limit = ('Not historical ex-events, TTM cash, realized yield, actual payment, after-tax income or ADR conversion. '
             'Not recent news or a comprehensive announcement search. Sources are supplied, not automatically authenticated.'
             if english else '独立于历史除息事件及TTM；不是已实现股息率、实际支付、税后到账或ADR换算；'
             '不计入近三日新闻，也不是完整公告检索。来源为随附材料，不自动认证真实性。')
    state = ('materials not supplied' if english else '未提供未来公告材料') if not audit['provided'] else (
        'This input has no displayable records; future announcements remain unknown.' if english else
        '本输入包无可展示记录，不代表不存在未来公告。')
    if audit['accepted']:
        state = 'Display only the validated supplied records.' if english else '仅展示通过结构及截止校验的随附记录。'
    labels = ('Dates use UTC calendar comparisons; announcement dates have day precision only, not first-publication timestamps; payable_date is planned payment.'
              if english else '日期比较采用UTC日历；公告日期仅日精度，不证明首次上线时分；payable_date仅计划支付日。')
    payload = json.dumps(dict(asof=audit['asof'], accepted=audit['accepted'], rejected=audit['rejected']),ensure_ascii=False)
    return f'\n### {heading}\n{state}\n{limit}\n{labels}\n{payload}\n'


def attach_reviewed_release(context, packet, asof, out):
    """Reuse a human-checked public release; retain the original Yahoo block."""
    item = packet.get(context.get('code'))
    if not item or context.get('is_index_etf'):
        return context, None
    if asof.tzinfo is None or datetime.fromisoformat(item['available_after']) > asof or datetime.fromisoformat(item['fetched_at']) > asof:
        raise ValueError('official_release_not_available_at_cutoff')
    if not item['period_end'] <= item['published_date'] <= asof.date().isoformat():
        raise ValueError('official_release_period_or_date_invalid')
    result = copy.deepcopy(context)
    fundamental = result.get('fundamental_context') or {}
    (out/'ORIGINAL_YAHOO_FUNDAMENTAL_CONTEXT.json').write_text(json.dumps(fundamental,ensure_ascii=False,indent=2),encoding='utf-8')
    earnings = fundamental.setdefault('earnings', {})
    data = earnings.setdefault('data', {})
    # Replace the quarter as one block: never mix a new-quarter income with an old CFO.
    data['financial_report'] = dict(item['values'], report_date=item['period_end'], currency=item['currency'], source=item['source_url'])
    earnings['status'] = 'partial'
    earnings.setdefault('source_chain', []).append({'provider':'reviewed_official_release','source':item['source_url'],'period':item['period_end']})
    result['fundamental_context'] = fundamental
    result['official_research'] = item
    result['news_source_note'] = '官方已披露财报资料已提供；未执行综合新闻搜索，近3日新闻覆盖仍不完整，不排除其他事件。'
    (out/'OFFICIAL_RESEARCH_USED.json').write_text(json.dumps(item,ensure_ascii=False,indent=2),encoding='utf-8')
    return result, item['text']

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
        # RSS items are supplied evidence, not SearchService search hits.
        prepared=replace(artifacts,enhanced_context=enhanced,fundamental_context=enhanced.get('fundamental_context'),news_context=news,news_result_count=None)
        self.prepared_context=enhanced;self.prepared_news=news
        return prepared,notes

    def attach(self,enhanced,trend):
        result=copy.deepcopy(enhanced);raw=result.get('fundamental_context') or {}
        result['news_result_count']=None
        result['news_evidence_present']=bool(self.news)
        result['news_source_note']='官方RSS标题及元数据已提供，未提供新闻全文；综合新闻搜索未执行。不能据此排除其他重大利空。' if self.news else '未提供可用官方RSS；综合新闻搜索未执行。'
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
            if t.get('ma60_verified') and t.get('ma60'):
                result['today']=dict(result.get('today') or {})
                result['today']['ma60']=t['ma60']
        notes.append('新闻仅由独立准备入口将官方RSS传入news_context；原SearchService仍未配置。不要将财报统计期或采集时间当新闻发布时间。')
        notes.append('ROE、估值、增长率与分红等其余Yahoo字段尚未逐项官方核验，可能为TTM或独立统计口径，不要将三个金额的核对结论扩展到全部指标。')
        news='\n\n'.join(f"来源：{n['source']}\n标题：{n['title']}\n发布时间：{n['published_at']}\n采集时间：{n['fetched_at']}\n原文：{n['url']}\n仅提供标题/发布元数据，未提供全文，不推断未给出的细节。" for n in self.news) or '暂无可验证的截止前官方RSS新闻。'
        self.save();return result,news,'\n'.join(notes)
