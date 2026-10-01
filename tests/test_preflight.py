import csv,json
import pytest
from derivatives_pricing import admission as a
from derivatives_pricing import preflight as p

def sample(tmp_path,headers=None,values=None,bom=False):
 path=tmp_path/'raw.csv'
 h=headers or list(a.REQUIRED)
 v=values or ['2030-01-02','synthetic','510050','C','2.7','2030-03-01','10000','M','.1','close']
 with path.open('w',encoding='utf-8-sig' if bom else 'utf-8',newline='') as f:
  w=csv.writer(f);w.writerow(h);w.writerow(v)
 return path

def test_chinese_bom_and_unknown(tmp_path):
 headers=['交易日期','合约代码','标的代码','认购认沽','行权价格','到期日','合约单位','调整标记','价格','价格类型','备注']
 path=sample(tmp_path,headers,['2030-01-02','synthetic','510050','认购','2.7','2030-03-01','10000','M','.1','close','unknown'],True)
 r,_=p.inspect(path)
 assert not r['missing_required'] and r['unknown_columns']==['备注']
 assert any(x['field']=='cp' for x in r['warnings'])
 assert not r['confirmed'] and not r['units_verified']

def test_alias_collision(tmp_path):
 path=sample(tmp_path,['date','日期'],['2030-01-02','2030-01-03'])
 r,_=p.inspect(path)
 assert r['ambiguities']['date']==['date','日期'] and 'date' in r['missing_required']

@pytest.mark.parametrize('headers,values',[(['date','date'],['a','b']),(['date'],['a','b']),(['date'],[])])
def test_bad_shape(tmp_path,headers,values):
 with pytest.raises(a.InputError):p.inspect(sample(tmp_path,headers,values))

@pytest.mark.parametrize('field,value,issue',[('date','2030/01/02','needs_ISO_date_explicit_conversion'),('bid_qty','1.5','needs_integer_unit_definition'),('price_known_at','2030-01-02T15:00:00','missing_or_unaware_timestamp'),('price','NaN','nonfinite_or_not_numeric'),('price_type','收盘','unknown_price_semantics')])
def test_semantic_warnings(tmp_path,field,value,issue):
 path=sample(tmp_path,[field],[value]);r,_=p.inspect(path)
 assert r['warnings'][0]['issue']==issue

def test_mixed_offsets_not_guessed(tmp_path):
 path=sample(tmp_path,['price_known_at','spot_known_at'],['2030-01-02T15:00:00+08:00','2030-01-02T07:00:00Z'])
 r,rows=p.inspect(path)
 assert r['timezone_offsets_seconds']==[0,28800]
 assert rows[0]['spot_known_at'].endswith('Z')

def test_confirmed_same_checker_and_repeat_hash(tmp_path):
 source=sample(tmp_path);before=source.read_bytes()
 mapping=tmp_path/'mapping.json';mapping.write_text(json.dumps({k:k for k in a.REQUIRED}))
 for name in ['first','repeat']:
  out=tmp_path/name
  assert p.main([str(source),'--mapping',str(mapping),'--expected-source-sha256',a.sha(before),'--output',str(out)])==1
  r=json.loads((out/'preflight.json').read_text())
  assert r['admission']==a.audit(out/'normalized.csv')
  assert r['mapping_sha256']==a.sha(mapping.read_bytes())
 assert source.read_bytes()==before

def test_confirmation_needs_hash_and_rejects_wrong_hash(tmp_path):
 source=sample(tmp_path);m=tmp_path/'m.json';m.write_text(json.dumps({k:k for k in a.REQUIRED}))
 for extra in [[],['--expected-source-sha256','wrong']]:
  with pytest.raises(SystemExit) as e:p.main([str(source),'--mapping',str(m),'--output',str(tmp_path/'out')]+extra)
  assert e.value.code==2 and not (tmp_path/'out').exists()

def test_missing_header_no_normalized_file(tmp_path):
 source=sample(tmp_path,['日期'],['2030-01-02']);m=tmp_path/'m.json';m.write_text('{"date":"日期"}')
 out=tmp_path/'out'
 assert p.main([str(source),'--mapping',str(m),'--expected-source-sha256',a.sha(source.read_bytes()),'--output',str(out)])==1
 assert not (out/'normalized.csv').exists()

@pytest.mark.parametrize('mapping',[{'price':'收盘价'},{'date':'date','expiry':'date'},{'unrecognized':'date'}])
def test_invalid_mapping(tmp_path,mapping):
 with pytest.raises(a.InputError):p.inspect(sample(tmp_path),mapping)

def test_xlsx_and_invalid_encoding(tmp_path):
 path=tmp_path/'input.xlsx';path.write_bytes(b'PK\xff\x00')
 with pytest.raises(a.InputError):p.inspect(path)


def test_price_semantics_not_inferred(tmp_path):
 path=sample(tmp_path,['收盘价','结算价','买一量（手）'],['.1','.2','2'])
 r,_=p.inspect(path)
 assert 'price' in r['missing_required']
 assert r['warnings'][0]['issue']=='unit_currency_requires_explicit_dictionary_no_scaling'

def test_confirmed_chinese_end_to_end_same_admission(tmp_path):
 headers=['交易日期','合约编码','标的代码','期权类型','执行价','到期日','合约单位','调整标记','价格','价格类型']
 source=sample(tmp_path,headers,bom=True)
 mapping=tmp_path/'m.json';mapping.write_text(json.dumps(dict(zip(a.REQUIRED,headers)),ensure_ascii=False))
 out=tmp_path/'out'
 assert p.main([str(source),'--mapping',str(mapping),'--expected-source-sha256',a.sha(source.read_bytes()),'--output',str(out)])==1
 report=json.loads((out/'preflight.json').read_text())
 assert report['admission']==a.audit(out/'normalized.csv')
 assert (out/'normalized.csv').read_text().splitlines()[1].startswith('2030-01-02,synthetic,510050,C')

def test_no_overwrite(tmp_path):
 source=sample(tmp_path);out=tmp_path/'out';out.mkdir()
 with pytest.raises(SystemExit) as e:p.main([str(source),'--output',str(out)])
 assert e.value.code==2

@pytest.mark.parametrize('content',['null','[]','1','"mapping"','true'])
def test_explicit_nonobject_mapping_rejected_without_output(tmp_path,content):
 source=sample(tmp_path);m=tmp_path/'mapping.json';m.write_text(content)
 out=tmp_path/'out'
 with pytest.raises(SystemExit) as e:p.main([str(source),'--mapping',str(m),'--expected-source-sha256',a.sha(source.read_bytes()),'--output',str(out)])
 assert e.value.code==2 and not out.exists()

def test_policy_failure_leaves_no_partial(tmp_path):
 source=sample(tmp_path);m=tmp_path/'m.json';m.write_text(json.dumps({k:k for k in a.REQUIRED}))
 policy=tmp_path/'policy.json';policy.write_text('{"unknown":1}')
 out=tmp_path/'out'
 with pytest.raises(SystemExit) as e:p.main([str(source),'--mapping',str(m),'--expected-source-sha256',a.sha(source.read_bytes()),'--policy',str(policy),'--output',str(out)])
 assert e.value.code==2 and not out.exists()

def test_mapping_changed_after_read_binds_applied_snapshot(tmp_path,monkeypatch):
 source=sample(tmp_path);m=tmp_path/'m.json';original=json.dumps({k:k for k in a.REQUIRED}).encode();m.write_bytes(original)
 read=a.read_bytes;calls=[]
 def replace_after_read(path,limit=a.MAX_BYTES):
  raw=read(path,limit)
  if Path(path)==m:
   calls.append(path);m.write_text('{"date":"code"}')
  return raw
 from pathlib import Path
 monkeypatch.setattr(a,'read_bytes',replace_after_read)
 out=tmp_path/'out'
 assert p.main([str(source),'--mapping',str(m),'--expected-source-sha256',a.sha(source.read_bytes()),'--output',str(out)])==1
 r=json.loads((out/'preflight.json').read_text())
 assert len(calls)==1 and r['mapping_sha256']==a.sha(original) and r['mapping']['date']=='date'
 assert r['mapping_sha256']!=a.sha(m.read_bytes())

def test_publication_copy_failure_cleans_only_new_output(tmp_path,monkeypatch):
 source=sample(tmp_path);out=tmp_path/'out'
 def fail(*args):raise OSError('simulated disk failure')
 monkeypatch.setattr(p.shutil,'copyfile',fail)
 with pytest.raises(SystemExit) as e:p.main([str(source),'--output',str(out)])
 assert e.value.code==2 and not out.exists()
 sentinel=tmp_path/'existing';sentinel.mkdir();(sentinel/'keep').write_text('keep')
 with pytest.raises(SystemExit):p.main([str(source),'--output',str(sentinel)])
 assert (sentinel/'keep').read_text()=='keep'

def test_actual_cli_null_and_policy_fail_no_output(tmp_path):
 import os,subprocess,sys
 from pathlib import Path
 source=sample(tmp_path);m=tmp_path/'m.json';policy=tmp_path/'policy.json';policy.write_text('{"unknown":1}')
 env=dict(os.environ,PYTHONPATH=str(Path(p.__file__).parents[1]),PYTHONDONTWRITEBYTECODE='1')
 for name,content,extra in [('null','null',[]),('policy',json.dumps({k:k for k in a.REQUIRED}),['--policy',str(policy)])]:
  m.write_text(content);out=tmp_path/name
  run=subprocess.run([sys.executable,'-m','derivatives_pricing.preflight',str(source),'--mapping',str(m),'--expected-source-sha256',a.sha(source.read_bytes()),'--output',str(out)]+extra,env=env,capture_output=True,text=True)
  assert run.returncode==2 and 'INPUT_ERROR' in run.stderr and 'Traceback' not in run.stderr and not out.exists()
