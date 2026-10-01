"""Conservative CSV mapping preview. No evidence or units inferred."""
import argparse
import csv
import io
import json
import tempfile
import shutil
from pathlib import Path
from . import admission as a

ALIASES = {
 'date':['交易日期','日期'], 'code':['合约编码','合约代码'],
 'underlying':['标的代码'], 'cp':['认购认沽','期权类型'],
 'strike':['行权价格','执行价'], 'expiry':['到期日'],
 'contract_unit':['合约单位'], 'adjustment_flag':['调整标记'],
 'price':['价格'], 'price_type':['价格类型'],
 'spot':['标的价格'], 'bid':['买一价'], 'ask':['卖一价'],
 'bid_qty':['买一量'], 'ask_qty':['卖一量'],
 'price_known_at':['价格业务时间'], 'spot_known_at':['标的业务时间'],
 'r':['连续利率'], 'q':['连续收益率'],
 'r_known_at':['利率已知时间'], 'q_known_at':['收益率已知时间'],
 'r_reference':['利率依据'], 'q_reference':['收益率依据'],
 'terms_reference':['条款依据'], 'source_reference':['来源依据'],
}
PURPOSE = {
 'historical_iv':['spot','spot_known_at','r','q','r_known_at','q_known_at','r_reference','q_reference','price_known_at','terms_reference','source_reference'],
 'call_put_pair':['bid','ask','bid_qty','ask_qty','price_known_at','terms_reference','source_reference'],
}

def inspect(path, mapping=None):
 raw=a.read_bytes(path)
 try:
  text=raw.decode('utf-8-sig')
  if '\x00' in text: raise a.InputError('CSV含NUL')
  reader=csv.DictReader(io.StringIO(text,newline=''),strict=True)
  fields=reader.fieldnames
  if not fields or len(fields)>a.MAX_COLUMNS or len(set(fields))!=len(fields) or any(not f or f!=f.strip() for f in fields): raise a.InputError('列名重复、为空或含首尾空白')
  rows=[]
  for row in reader:
   if len(rows)>=a.MAX_ROWS or None in row or any(v is None or len(v)>4096 for v in row.values()): raise a.InputError('CSV形状或规模无效')
   rows.append(row)
  if not rows: raise a.InputError('CSV无业务行')
 except (UnicodeError,csv.Error) as e: raise a.InputError('需要UTF-8 CSV；Excel请先导出') from e
 suggestions={k:[f for f in fields if f in [k]+aliases] for k,aliases in ALIASES.items()}
 chosen={k:v[0] for k,v in suggestions.items() if len(v)==1}
 confirmed=mapping is not None
 if confirmed:
  if not isinstance(mapping,dict) or set(mapping)-set(ALIASES) or any(not isinstance(v,str) or v not in fields for v in mapping.values()) or len(set(mapping.values()))!=len(mapping): raise a.InputError('映射必须是一对一的已知目标列→原列')
  chosen=mapping
 normalized=[{k:r[v] for k,v in chosen.items()} for r in rows]
 warnings=[]
 for i,r in enumerate(normalized,1):
  for k in ('date','expiry'):
   if k in r and a.day(r[k]) is None: warnings.append({'row':i,'field':k,'issue':'needs_ISO_date_explicit_conversion'})
  for k in ('price_known_at','spot_known_at','r_known_at','q_known_at'):
   if k in r and a.timestamp(r[k]) is None: warnings.append({'row':i,'field':k,'issue':'missing_or_unaware_timestamp'})
  for k in ('strike','price','spot','r','q','bid','ask'):
   if k in r and a.finite(r[k]) is None: warnings.append({'row':i,'field':k,'issue':'nonfinite_or_not_numeric'})
  for k in ('contract_unit','bid_qty','ask_qty'):
   if k in r and (a.finite(r[k]) is None or not a.finite(r[k]).is_integer()): warnings.append({'row':i,'field':k,'issue':'needs_integer_unit_definition'})
  if 'cp' in r and r['cp'] not in ('C','P'): warnings.append({'row':i,'field':'cp','issue':'needs_explicit_C_P_conversion'})
  if 'price_type' in r and r['price_type'] not in ('mid','close','settle'): warnings.append({'row':i,'field':'price_type','issue':'unknown_price_semantics'})
 header_unit_hints=[f for f in fields if any(t in f for t in ('万元','千元','百分比','%','(手)','（手）','(股)','（股）','USD','美元'))]
 for f in header_unit_hints: warnings.append({'field':f,'issue':'unit_currency_requires_explicit_dictionary_no_scaling'})
 offsets=sorted({a.timestamp(r[k]).utcoffset().total_seconds() for r in normalized for k in ('price_known_at','spot_known_at') if k in r and a.timestamp(r[k]) is not None})
 return {'source_sha256':a.sha(raw),'row_count':len(rows),'suggestions':suggestions,'ambiguities':{k:v for k,v in suggestions.items() if len(v)>1},'confirmed':confirmed,'mapping':chosen,'missing_required':sorted(set(a.REQUIRED)-set(chosen)),'missing_by_purpose':{k:sorted(set(v)-set(chosen)) for k,v in PURPOSE.items()},'unknown_columns':[f for f in fields if f not in chosen.values()],'warnings':warnings,'timezone_offsets_seconds':offsets,'mixed_timezone_offsets':len(offsets)>1,'semantic_review_required':['price meaning/currency/per-share units','quantities in contracts; contract unit in ETF shares','business timestamp versus receipt time','source and terms references; declared coverage completeness'],'evidence_truth_verified':False,'units_verified':False,'preview':normalized[:5]},normalized

def main(argv=None):
 p=argparse.ArgumentParser(description='CSV预检；不推断单位、价格语义或真实时点')
 p.add_argument('--policy',help='原准入配置；预检不认证声明');p.add_argument('csv');p.add_argument('--mapping',help='显式确认的JSON映射；仅列重命名，不改变值');p.add_argument('--expected-source-sha256');p.add_argument('--output',required=True)
 args=p.parse_args(argv)
 try:
  mapping=None
  mapping_raw=None
  if args.mapping:
   def unique(pairs):
    d={}
    for k,v in pairs:
     if k in d: raise a.InputError('JSON重复映射键')
     d[k]=v
    return d
   mapping_raw=a.read_bytes(args.mapping,1024*1024)
   mapping=json.loads(mapping_raw.decode('utf-8'),object_pairs_hook=unique)
   if not isinstance(mapping,dict): raise a.InputError('显式映射必须是JSON对象')
  result,rows=inspect(args.csv,mapping)
  result['mapping_sha256']=a.sha(mapping_raw) if mapping_raw is not None else None
  result['contains_private_preview']=True
  if mapping is not None and not args.expected_source_sha256: raise a.InputError('确认转换必须提供预检源SHA-256；复用映射也须确认当前源')
  if args.expected_source_sha256 and args.expected_source_sha256!=result['source_sha256']: raise a.InputError('源哈希不匹配')
  out=Path(args.output)
  if out.exists(): raise a.InputError('输出目录已存在；不覆盖')
  # Stage everything privately. Deterministic input failures never expose final files.
  # Policy is already single-read in admission.load_policy: parse and SHA share raw.
  with tempfile.TemporaryDirectory(prefix='etf50-preflight-') as temporary:
   stage=Path(temporary)
   if mapping is not None and not result['missing_required']:
    target=stage/'normalized.csv'
    with target.open('w',encoding='utf-8',newline='') as f:
     w=csv.DictWriter(f,fieldnames=list(mapping));w.writeheader();w.writerows(rows)
    result['normalized_sha256']=a.sha(target.read_bytes())
    result['admission']=a.audit(target,args.policy)
   elif args.policy:
    # Explicit policy must be valid even for preview/missing-column paths.
    policy,policy_raw=a.load_policy(args.policy)
    result['policy_sha256']=a.sha(policy_raw)
   (stage/'preflight.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
   out.parent.mkdir(parents=True,exist_ok=True)
   # Reserve destination exclusively; clean only this invocation's new directory.
   out.mkdir(exist_ok=False)
   try:
    for file in stage.iterdir(): shutil.copyfile(file,out/file.name)
   except BaseException:
    shutil.rmtree(out)
    raise
  return 1 if result['missing_required'] or result['ambiguities'] or result['warnings'] or (result.get('admission') and any(r['historical_iv']!='conditional_input_consistent' or r['pair']!='conditional_input_consistent' for r in result['admission']['records'])) else 0
 except (a.InputError,ValueError,OSError,RecursionError) as e:
  p.exit(2,'INPUT_ERROR: '+str(e)+'\n')

if __name__=='__main__': raise SystemExit(main())
