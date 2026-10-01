"""Local CSV input admission checks; declarations are never external certification."""
from __future__ import annotations
import argparse
import csv
from datetime import date, datetime, timezone, timedelta
import hashlib
import html
import json
import math
from pathlib import Path
import sys
from collections import Counter, defaultdict

AUDIT_VERSION = '0.4.0rc6'
REQUIRED = ('date', 'code', 'underlying', 'cp', 'strike', 'expiry', 'contract_unit', 'adjustment_flag', 'price', 'price_type')
MAX_BYTES = 32 * 1024 * 1024
MAX_ROWS = 100000
MAX_COLUMNS = 128
class InputError(ValueError):
    """Malformed input, distinct from a well-formed file with blocked rows."""

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def timestamp(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return None
    return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None

def business_date(value):
    if value is None:
        return None
    try:
        return value.astimezone(timezone(timedelta(hours=8))).date()
    except (OverflowError, ValueError):
        return None

def finite(value):
    try:
        v = float(value)
        return v if math.isfinite(v) else None
    except (ValueError, TypeError):
        return None

def day(value):
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None

def read_bytes(path, limit=MAX_BYTES):
    try:
        with Path(path).open('rb') as f:
            raw = f.read(limit+1)
    except OSError as exc:
        raise InputError('无法读取输入文件；请检查路径与读取权限') from exc
    if len(raw)>limit:
        raise InputError('文件超出大小上限')
    return raw

def load_csv(path):
    raw = read_bytes(path)
    try:
        import io
        text = raw.decode('utf-8-sig')
        if '\x00' in text:
            raise InputError('CSV含NUL字符')
        reader = csv.DictReader(io.StringIO(text, newline=''), strict=True)
        fields = reader.fieldnames
        if not fields or len(fields)>MAX_COLUMNS or any(not x or x != x.strip() for x in fields) or len(set(fields))!=len(fields):
            raise InputError('CSV至多128列，需要唯一、非空、无首尾空格的列名')
        missing = set(REQUIRED)-set(fields)
        if missing:
            raise InputError('CSV缺必要列：'+', '.join(sorted(missing)))
        rows=[]
        for row in reader:
            if len(rows)>=MAX_ROWS:
                raise InputError('CSV超出100000行上限')
            if None in row or any(v is None for v in row.values()):
                raise InputError('CSV行列数量不匹配，业务记录号：'+str(len(rows)+1))
            if any(len(v)>4096 for v in row.values()):
                raise InputError('CSV单字段超过4096字符')
            rows.append(row)
    except (UnicodeError, csv.Error) as exc:
        raise InputError('输入需要UTF-8 CSV，符合CSV引号与分隔规则') from exc
    if not rows:
        raise InputError('CSV没有数据行')
    return raw,fields,rows

def load_policy(path):
    if path is None:
        return None,None
    raw=read_bytes(path,1024*1024)
    def unique_pairs(pairs):
        out={}
        for k,v in pairs:
            if k in out:
                raise InputError('配置JSON有重复键')
            out[k]=v
        return out
    try:
        p=json.loads(raw.decode('utf-8'),object_pairs_hook=unique_pairs)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise InputError('配置需要有效UTF-8 JSON，无重复键或过深嵌套') from exc
    if not isinstance(p,dict):
        raise InputError('配置须为JSON对象')
    allowed={'schema_version','data_kind','rights_reference','coverage','events','max_pair_lag_seconds'}
    if set(p)-allowed:
        raise InputError('配置含未知键：'+', '.join(sorted(set(p)-allowed)))
    if p.get('schema_version')!=1 or p.get('data_kind') not in ('synthetic','user_market'):
        raise InputError('配置需要schema_version=1，data_kind为synthetic或user_market')
    if not isinstance(p.get('rights_reference'),str) or not p['rights_reference'].strip():
        raise InputError('配置需要rights_reference声明；声明不等于已验证许可')
    c=p.get('coverage')
    if not isinstance(c,dict) or set(c)!={'start','end','complete','evidence_reference'}:
        raise InputError('coverage需要start/end/complete/evidence_reference')
    if not day(c['start']) or not day(c['end']) or day(c['start'])>day(c['end']) or c['complete'] is not True or not isinstance(c['evidence_reference'],str) or not c['evidence_reference'].strip():
        raise InputError('coverage需要有效日期、有序区间、complete=true及非空证据声明')
    events=p.get('events')
    if not isinstance(events,list) or len(events)>1000:
        raise InputError('events须显式提供列表（已声明无事件才可为空）')
    seen=set()
    for e in events:
        if not isinstance(e,dict) or set(e)!={'date','evidence_reference'} or not day(e['date']) or not isinstance(e['evidence_reference'],str) or not e['evidence_reference'].strip():
            raise InputError('每个event需要有效date和非空evidence_reference')
        if e['date'] in seen or not c['start']<=e['date']<=c['end']:
            raise InputError('event重复或超出声明覆盖区间')
        seen.add(e['date'])
    lag=p.get('max_pair_lag_seconds',1)
    if type(lag) not in (int,float) or not 0<=lag<=5 or not math.isfinite(lag):
        raise InputError('max_pair_lag_seconds须为0至5的有限数')
    return p,raw

def audit(path, policy_path=None):
    raw,fields,rows=load_csv(path)
    p,policy_raw=load_policy(policy_path)
    record_reports=[]
    pair_groups=defaultdict(list)
    duplicates=Counter((r['date'],r['code']) for r in rows)
    for index,r in enumerate(rows,1):
        issues=[]
        def issue(code,severity,scope,message,repair):
            issues.append({'code':code,'severity':severity,'scope':scope,'message':message,'repair':repair})
        d,e=day(r['date']),day(r['expiry'])
        k,u,price=finite(r['strike']),finite(r['contract_unit']),finite(r['price'])
        if not d or not e or (d and e and e<=d):
            issue('INVALID_TENOR','error','all','日期无效或到期不晚于观察日','用有效交易日期和官方到期日；到期日样本单独处理')
        if not r['code'].strip() or r['cp'] not in ('C','P') or r['underlying']!='510050':
            issue('INVALID_IDENTITY','error','all','需要非空ID、C/P及underlying=510050','使用合约主表，不从代码尾部推断执行价')
        if k is None or k<=0 or u is None or u<=0 or not u.is_integer():
            issue('INVALID_TERMS','error','all','执行价须正有限数，单位须正整数','以生效时点主表提供真实执行价和单位')
        if r['adjustment_flag']!='M' or u!=10000:
            issue('DYNAMIC_TERMS_UNSUPPORTED','error','all','当前静态模型仅接受M/10000；调整合约未实现动态条款','保留原数据；单列调整合约，不能强改单位为10000')
        if price is None or price<0:
            issue('INVALID_PRICE','error','all','价格须非负有限数','检查缺失、单位和导出格式，禁止用settle补close')
        elif price==0:
            issue('ZERO_PRICE','error','historical_iv','零价格不宜进行常规IV/百分比误差比较','单列零值及舍入/无成交原因，使用绝对误差')
        if duplicates[(r['date'],r['code'])]>1:
            issue('DUPLICATE_RECORD','error','all','日期与合约ID重复','保留版本记录，按已说明规则解决重复；不静默去重')
        if r['price_type'] not in ('close','mid','settle'):
            issue('INVALID_PRICE_TYPE','error','all','price_type仅允许close/mid/settle','明确价格语义')
        elif r['price_type']=='settle':
            issue('SETTLEMENT_NOT_INDEPENDENT','error','historical_iv,pair','结算价可能理论生成，不能作为独立市场验证价格','单列估值制度诊断，提供成交或同步BBO')
        if not p:
            issue('COVERAGE_UNDECLARED','missing_evidence','all','没有有效调整事件覆盖配置','提供覆盖区间、完整性声明及证据；工具不核实声明真假')
        elif d and e:
            c=p['coverage']
            if not c['start']<=d.isoformat()<e.isoformat()<=c['end']:
                issue('OUTSIDE_DECLARED_COVERAGE','error','all','观察日至到期超出声明覆盖','补真实事件清单及独立master；不能仅扩大日期')
            if any(d.isoformat()<x['date']<=e.isoformat() for x in p['events']):
                issue('CROSSES_ADJUSTMENT','error','all','静态条款跨调整事件','本版本不支持动态变换，单独研究或排除并记分母')
            if any(d.isoformat()==x['date'] for x in p['events']):
                issue('EVENT_DAY_UNVERIFIED','error','all','事件生效日需要动态有效条款实现','不能凭M/10000放行事件日')
        if not r.get('terms_reference','').strip():
            issue('MASTER_EVIDENCE_MISSING','missing_evidence','all','缺有效合约主表引用','提供ID条款有效区间和证据；引用不等于外部认证')
        t=timestamp(r.get('price_known_at'))
        if not t or (d and business_date(t)!=d):
            issue('PRICE_TIME_MISSING','missing_evidence','historical_iv,pair','缺带时区且属于观察日的价格业务时间','提供真实业务时戳；日close不能假定同步')
        if not r.get('source_reference','').strip():
            issue('SOURCE_EVIDENCE_MISSING','missing_evidence','all','缺原始数据来源/版本引用','保留原始导出日志、来源版本及许可证明')
        spot=finite(r.get('spot'))
        st=timestamp(r.get('spot_known_at'))
        if spot is None or spot<=0 or not st or not t or st>t or (t-st).total_seconds()>1:
            issue('SPOT_ALIGNMENT_MISSING','missing_evidence','historical_iv','缺正现货及不晚于期权且滞后≤1秒的独立现货时戳','提供独立ETF序列，禁止未来填充；非默认放宽容差')
        for name in ('r','q'):
            value=finite(r.get(name)); known=timestamp(r.get(name+'_known_at'))
            if value is None or not known or not t or known>t or not r.get(name+'_reference','').strip():
                issue(name.upper()+'_INPUT_MISSING','missing_evidence','historical_iv','缺时点已知且有来源的'+name+'输入','提供输入值、已知时间、方法/版本；不默认0')
        bid,ask,bq,aq=[finite(r.get(x)) for x in ('bid','ask','bid_qty','ask_qty')]
        valid_quote_prices = bid is not None and ask is not None and 0 <= bid <= ask
        valid_bbo = (valid_quote_prices and bq is not None and aq is not None
                     and bq > 0 and aq > 0 and bq.is_integer() and aq.is_integer())
        if not valid_bbo:
            issue('BBO_MISSING_OR_INVALID','missing_evidence','pair','缺非交叉双边报价及正数量','提供同步bid/ask和数量，日成交量不能代替深度')
        # Depth eligibility cannot suppress an independently observable price contradiction.
        if r['price_type'] == 'mid':
            if not valid_quote_prices:
                issue('MID_PRICE_UNVERIFIABLE','missing_evidence','historical_iv',
                      '缺有效有序双边价格，不能核验声明mid',
                      '提供该业务时点的有效bid/ask；不要用任意价格重标mid')
            elif price is not None and abs(price - (bid / 2 + ask / 2)) > 1e-9:
                issue('MID_INCONSISTENT','error','all','声明mid与双边均值不一致','核对价格、同一时戳BBO及舍入政策')
        if r['price_type']=='close':
            issue('CLOSE_ASYNCHRONY','warning','pair','最后成交close不证明与另一侧配对同步','使用同步BBO；本版本pair仅接受mid')
        rec={'record':index,'issues':issues}
        record_reports.append(rec)
        if d and e and k is not None and u is not None and r['cp'] in ('C','P'):
            pair_groups[(r['date'],r['expiry'],k,u,r['adjustment_flag'],r['underlying'])].append((index,r,t,valid_bbo))
    paired=[]
    for group in pair_groups.values():
        if len(group)!=2 or {g[1]['cp'] for g in group}!={'C','P'}:
            for index,_,_,_ in group:
                record_reports[index-1]['issues'].append({'code':'PAIR_MISSING_OR_AMBIGUOUS','severity':'error' if len(group)>1 else 'missing_evidence','scope':'pair','message':'配对缺侧或同条款多ID歧义','repair':'按真实条款与交割篮子提供唯一完整C/P整对'})
            continue
        a,b=group
        if not (a[2] and b[2] and abs((a[2]-b[2]).total_seconds()) <= (p.get('max_pair_lag_seconds',1) if p else 1) and a[1]['price_type']==b[1]['price_type']=='mid'):
            for index,_,_,_ in group:
                record_reports[index-1]['issues'].append({'code':'PAIR_NOT_SYNCHRONOUS_MID','severity':'missing_evidence','scope':'pair','message':'整对非带业务时戳的容差内mid','repair':'提供同刻双边报价；拟合好不修复异步close'})
        paired.append((a[0],b[0]))
    def status(rec,scope):
        relevant=[x for x in rec['issues'] if x['scope']=='all' or scope in x['scope'].split(',')]
        if any(x['severity']=='error' for x in relevant): return 'blocked'
        if any(x['severity']=='missing_evidence' for x in relevant): return 'needs_evidence'
        return 'conditional_input_consistent'
    for rec in record_reports:
        rec['historical_iv']=status(rec,'historical_iv')
        rec['pair']=status(rec,'pair')
    # Snapshot each side before propagation; avoid recursive peer diagnostics.
    # Historical-IV qualification remains row-independent.
    own_status = {rec['record']: rec['pair'] for rec in record_reports}
    own_issues = {rec['record']: [x['code'] for x in rec['issues']
                  if x['scope']=='all' or 'pair' in x['scope'].split(',')]
                  for rec in record_reports}
    for left,right in paired:
        for current,peer in ((left,right),(right,left)):
            rec = record_reports[current-1]
            rec['peer_record'] = peer
            peer_status = own_status[peer]
            if peer_status != 'conditional_input_consistent':
                blocked = peer_status == 'blocked'
                rec['issues'].append({
                    'code': 'PAIR_PEER_BLOCKED' if blocked else 'PAIR_PEER_EVIDENCE_MISSING',
                    'severity': 'error' if blocked else 'missing_evidence',
                    'scope': 'pair', 'peer_record': peer,
                    'peer_issue_codes': own_issues[peer],
                    'message': '对侧业务记录 '+str(peer)+' 的自身配对资格为 '+peer_status,
                    'repair': '先修复对侧记录及其配对作用域问题，整对才可条件一致'})
            rec['pair'] = status(rec,'pair')
    counts=Counter(x['code'] for rec in record_reports for x in rec['issues'])
    return {'schema_version':1,'tool_version':AUDIT_VERSION,'checker_sha256':sha(Path(__file__).read_bytes()),'input_sha256':sha(raw),'policy_sha256':sha(policy_raw) if policy_raw else None,'configuration':p,'evidence_level':'synthetic_declared' if p and p['data_kind']=='synthetic' else 'user_declared_unverified','scope':'输入一致性原型；非数据许可认证、完整历史资格认证或投资建议','limits':['不下载/上传数据；不验证引用真实性或许可','不验证独立每日合约母集或日期块样本外研究','不计算IV、carry或价格拟合；不支持动态调整合约','条件一致不等于研究合格；后续需外部证据审阅'], 'summary':{'rows':len(rows),'columns':fields,'historical_iv':dict(Counter(r['historical_iv'] for r in record_reports)),'pair':dict(Counter(r['pair'] for r in record_reports)),'unique_term_pairs':len(paired),'conditional_pairs':sum(all(record_reports[i-1]['pair']=='conditional_input_consistent' for i in pair) for pair in paired),'issue_counts':dict(sorted(counts.items())),'severity_counts':dict(Counter(x['severity'] for rec in record_reports for x in rec['issues']))},'records':record_reports}

def render_html(report):
    esc=lambda v:html.escape(str(v),quote=True)
    rows=[]
    for rec in report['records']:
        issues='<br>'.join(esc(x['severity']+' | '+x['code']+' | '+x['message']+' → '+x['repair']) for x in rec['issues']) or '所实现的检查无问题；仍需外部证据审阅'
        rows.append('<tr><td>'+str(rec['record'])+'</td><td>'+esc(rec.get('peer_record','—'))+'</td><td>'+esc(rec['historical_iv'])+'</td><td>'+esc(rec['pair'])+'</td><td>'+issues+'</td></tr>')
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>50ETF输入审查</title><style>body{font:16px system-ui;max-width:1200px;margin:2em auto;padding:1em}table{border-collapse:collapse;width:100%}td,th{border:1px solid #aaa;padding:.5em;text-align:left;vertical-align:top}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>50ETF输入审查</h1><p>'+esc(report['scope'])+'</p><p>报告不包含原始价格或合约ID，但配置引用也可能含私有内容；分享前人工检查。</p><h2>运行与输入绑定</h2><pre>'+esc(json.dumps({k:report[k] for k in ('tool_version','checker_sha256','input_sha256','policy_sha256','evidence_level')},ensure_ascii=False,indent=2))+'</pre><h2>用户声明配置（未外部核验）</h2><pre>'+esc(json.dumps(report['configuration'],ensure_ascii=False,indent=2))+'</pre><h2>汇总</h2><pre>'+esc(json.dumps(report['summary'],ensure_ascii=False,indent=2))+'</pre><h2>适用限制</h2><ul>'+''.join('<li>'+esc(x)+'</li>' for x in report['limits'])+'</ul><h2>行级检查（业务记录号，从1开始，不是物理文本行号）</h2><table><tr><th>记录</th><th>对侧业务记录</th><th>历史IV输入</th><th>配对输入</th><th>问题与建议</th></tr>'+''.join(rows)+'</table></html>'

def main(argv=None):
    parser=argparse.ArgumentParser(description='本地50ETF CSV研究输入审查原型；不会认证历史数据')
    parser.add_argument('--version', action='version', version='%(prog)s '+AUDIT_VERSION)
    parser.add_argument('csv',type=Path)
    parser.add_argument('--policy',type=Path)
    parser.add_argument('--output',type=Path,required=True,help='新建输出目录；不覆盖已有目录')
    args=parser.parse_args(argv)
    try:
        if args.output.exists(): raise InputError('输出目录已存在；请指定新目录')
        report=audit(args.csv,args.policy)
        args.output.mkdir(parents=True,exist_ok=False)
        (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (args.output/'report.html').write_text(render_html(report),encoding='utf-8')
        print(json.dumps(report['summary'],ensure_ascii=False))
        # 0=implemented checks consistent, 1=reported findings, 2=invalid input/output.
        return 1 if any(r['historical_iv']!='conditional_input_consistent' or r['pair']!='conditional_input_consistent' for r in report['records']) else 0
    except (InputError,OSError) as exc:
        print('INPUT_ERROR: '+str(exc),file=sys.stderr)
        return 2
if __name__=='__main__':
    raise SystemExit(main())
