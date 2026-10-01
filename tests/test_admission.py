import csv
import json
from pathlib import Path
import pytest
from derivatives_pricing.admission import audit,main,InputError,render_html,REQUIRED

@pytest.fixture
def fixture(tmp_path):
    policy={'schema_version':1,'data_kind':'synthetic','rights_reference':'self generated fixture','coverage':{'start':'2030-01-01','end':'2030-12-31','complete':True,'evidence_reference':'fictional synthetic calendar'},'events':[],'max_pair_lag_seconds':1}
    row=dict(date='2030-01-02',code='demo-C',underlying='510050',cp='C',strike='2.7',expiry='2030-03-01',contract_unit='10000',adjustment_flag='M',price='.1',price_type='mid',bid='.09',ask='.11',bid_qty='1',ask_qty='1',price_known_at='2030-01-02T14:00:00+08:00',spot='2.7',spot_known_at='2030-01-02T14:00:00+08:00',r='.02',q='0',r_known_at='2030-01-02T11:00:00+08:00',q_known_at='2030-01-01T11:00:00+08:00',r_reference='synthetic r',q_reference='synthetic q',terms_reference='synthetic master',source_reference='synthetic generator')
    rows=[row,dict(row,cp='P',code='demo-P')]
    def write(rows=rows,policy=policy):
        f=tmp_path/'input.csv';p=tmp_path/'policy.json'
        with f.open('w',newline='') as stream:
            w=csv.DictWriter(stream,fieldnames=list(row));w.writeheader();w.writerows(rows)
        p.write_text(json.dumps(policy));return f,p
    return write,rows,policy

def codes(report): return {x['code'] for r in report['records'] for x in r['issues']}
def test_synthetic_consistent_is_not_certification(fixture):
    write,_,_=fixture;f,p=write();r=audit(f,p)
    assert r['summary']['conditional_pairs']==1
    assert r['evidence_level']=='synthetic_declared'
    assert r['input_sha256'] and r['policy_sha256'] and r['checker_sha256']
    assert '认证' in r['scope']

def test_no_policy_fails_closed(fixture):
    write,_,_=fixture;f,_=write();r=audit(f)
    assert r['summary']['conditional_pairs']==0
    assert 'COVERAGE_UNDECLARED' in codes(r)

@pytest.mark.parametrize('field,value,expected',[('strike','nan','INVALID_TERMS'),('contract_unit','10205','DYNAMIC_TERMS_UNSUPPORTED'),('adjustment_flag','A','DYNAMIC_TERMS_UNSUPPORTED'),('price','inf','INVALID_PRICE'),('price','-1','INVALID_PRICE'),('price','0','ZERO_PRICE'),('bid_qty','.5','BBO_MISSING_OR_INVALID'),('price_type','settle','SETTLEMENT_NOT_INDEPENDENT'),('price_type','trade','INVALID_PRICE_TYPE'),('expiry','bad','INVALID_TENOR'),('expiry','2030-01-02','INVALID_TENOR'),('underlying','510300','INVALID_IDENTITY'),('cp','call','INVALID_IDENTITY'),('price_known_at','2030-01-02T14:00:00','PRICE_TIME_MISSING'),('spot_known_at','2030-01-02T14:00:01+08:00','SPOT_ALIGNMENT_MISSING'),('r_known_at','2030-01-03T11:00:00+08:00','R_INPUT_MISSING'),('q','','Q_INPUT_MISSING'),('bid','.12','BBO_MISSING_OR_INVALID'),('bid_qty','0','BBO_MISSING_OR_INVALID'),('price','.12','MID_INCONSISTENT'),('terms_reference','','MASTER_EVIDENCE_MISSING'),('source_reference','','SOURCE_EVIDENCE_MISSING')])
def test_row_failures(fixture,field,value,expected):
    write,rows,_=fixture;rows[0][field]=value;f,p=write();assert expected in codes(audit(f,p))

def test_cross_event_and_event_day(fixture):
    write,rows,p=fixture;p['events']=[{'date':'2030-02-01','evidence_reference':'synthetic'}]
    f,c=write();assert 'CROSSES_ADJUSTMENT' in codes(audit(f,c))
    rows[0]['date']='2030-02-01';f,c=write();assert 'EVENT_DAY_UNVERIFIED' in codes(audit(f,c))

def test_outside_coverage(fixture):
    write,rows,_=fixture;rows[0]['expiry']='2031-01-01';f,p=write();assert 'OUTSIDE_DECLARED_COVERAGE' in codes(audit(f,p))

def test_malformed_policy_not_relaxed(fixture):
    write,_,p=fixture;p['coverage']['complete']=False;f,c=write()
    with pytest.raises(InputError):audit(f,c)

def test_empty_inventory_is_only_explicit_declaration(fixture):
    write,_,p=fixture;del p['events'];f,c=write()
    with pytest.raises(InputError):audit(f,c)

def test_duplicate_csv_and_pair_ambiguity(fixture):
    write,rows,_=fixture;rows.append(dict(rows[0]));f,p=write();r=audit(f,p)
    assert {'DUPLICATE_RECORD','PAIR_MISSING_OR_AMBIGUOUS'}<=codes(r)
    assert r['summary']['conditional_pairs']==0

def test_lag_and_close_are_rejected(fixture):
    write,rows,_=fixture;rows[1]['price_known_at']='2030-01-02T14:00:02+08:00';f,p=write()
    assert 'PAIR_NOT_SYNCHRONOUS_MID' in codes(audit(f,p))
    rows[0]['price_type']='close';f,p=write();assert 'CLOSE_ASYNCHRONY' in codes(audit(f,p))

def test_timezones_represent_instants(fixture):
    write,rows,_=fixture;rows[1]['price_known_at']='2030-01-02T06:00:00+00:00';f,p=write()
    assert audit(f,p)['summary']['conditional_pairs']==1

def test_report_html_escapes_config_fields(fixture):
    write,rows,policy=fixture;policy['rights_reference']='<script>alert(1)</script>';f,p=write();report=audit(f,p)
    assert '<script>' not in render_html(report)
    assert '&lt;script&gt;' in render_html(report)

def test_duplicate_headers_and_bad_utf8(tmp_path):
    f=tmp_path/'bad.csv';f.write_text(','.join(REQUIRED+('date',))+'\n')
    with pytest.raises(InputError):audit(f)
    f.write_bytes(b'\xff')
    with pytest.raises(InputError):audit(f)

def test_wrong_shape_and_empty_file(tmp_path):
    f=tmp_path/'bad.csv';f.write_text(','.join(REQUIRED)+'\n1,2\n')
    with pytest.raises(InputError):audit(f)
    f.write_text(','.join(REQUIRED)+'\n')
    with pytest.raises(InputError):audit(f)

def test_duplicate_policy_keys_and_nonfinite_lag(fixture):
    write,_,_=fixture;f,p=write();p.write_text('{"schema_version":1,"schema_version":1}')
    with pytest.raises(InputError):audit(f,p)
    f,p=write();s=json.loads(p.read_text());s['max_pair_lag_seconds']=float('nan');p.write_text(json.dumps(s))
    with pytest.raises(InputError):audit(f,p)

def test_cli_no_overwrite_and_bad_input_does_not_create_output(fixture,tmp_path):
    write,_,_=fixture;f,p=write();out=tmp_path/'output'
    assert main([str(f),'--policy',str(p),'--output',str(out)])==0
    before=(out/'report.json').read_bytes()
    assert main([str(f),'--policy',str(p),'--output',str(out)])==2
    assert (out/'report.json').read_bytes()==before
    assert main([str(tmp_path/'absent'),'--output',str(tmp_path/'new')])==2
    assert not (tmp_path/'new').exists()

def test_cli_findings_exit_one(fixture,tmp_path):
    write,_,_=fixture;f,_=write()
    assert main([str(f),'--output',str(tmp_path/'findings')])==1

def test_hash_changes_with_inputs_and_policy(fixture):
    write,rows,p=fixture;f,c=write();a=audit(f,c)
    rows[0]['code']='other';p['rights_reference']='other declaration';f,c=write();b=audit(f,c)
    assert a['input_sha256']!=b['input_sha256']
    assert a['policy_sha256']!=b['policy_sha256']


def test_extreme_timezone_overflow_is_reported_not_crashed(fixture):
    write,rows,_=fixture;rows[0]['price_known_at']='9999-12-31T23:00:00-12:00';f,p=write()
    assert 'PRICE_TIME_MISSING' in codes(audit(f,p))

def test_oversized_field_and_nul_rejected(fixture):
    write,rows,_=fixture;rows[0]['source_reference']='x'*4097;f,p=write()
    with pytest.raises(InputError):audit(f,p)
    f.write_bytes(b'\x00')
    with pytest.raises(InputError):audit(f,p)

def test_multiline_csv_business_record_number(fixture):
    write,rows,_=fixture;rows[0]['source_reference']='self-generated\nfixture';f,p=write()
    assert [r['record'] for r in audit(f,p)['records']]==[1,2]

def test_row_limit_fails_without_partial_report(fixture,monkeypatch):
    from derivatives_pricing import admission
    write,_,_=fixture;f,p=write();monkeypatch.setattr(admission,'MAX_ROWS',1)
    with pytest.raises(InputError):audit(f,p)


def test_column_and_byte_limits(tmp_path):
    from derivatives_pricing.admission import read_bytes
    f=tmp_path/'wide.csv';f.write_text(','.join(REQUIRED+tuple('extra'+str(i) for i in range(129)))+'\n')
    with pytest.raises(InputError):audit(f)
    with pytest.raises(InputError):read_bytes(f,limit=4)


@pytest.mark.parametrize('bad_index',[0,1])
@pytest.mark.parametrize('field,value,expected',[('price','-1','blocked'),('source_reference','','needs_evidence'),('bid_qty','0','needs_evidence')])
def test_peer_propagation_symmetric(fixture,bad_index,field,value,expected):
    write,rows,_=fixture;rows[bad_index][field]=value;f,p=write();r=audit(f,p)
    assert [x['pair'] for x in r['records']]==[expected]*2
    good=r['records'][1-bad_index]
    assert good['historical_iv']=='conditional_input_consistent'
    assert good['peer_record']==bad_index+1
    peers=[x for x in good['issues'] if x['code'].startswith('PAIR_PEER_')]
    assert len(peers)==1 and peers[0]['peer_record']==bad_index+1
    assert r['summary']['conditional_pairs']==0
    assert '对侧业务记录 '+str(bad_index+1) in render_html(r)
    assert '<tr><td>1</td><td>2</td>' in render_html(r)
    assert '<tr><td>2</td><td>1</td>' in render_html(r)

def test_historical_only_failure_keeps_pair_independent(fixture):
    write,rows,_=fixture;rows[1]['q']='';f,p=write();r=audit(f,p)
    assert r['records'][1]['historical_iv']=='needs_evidence'
    assert r['summary']['conditional_pairs']==1

def test_two_bad_peers_do_not_recursively_propagate(fixture):
    write,rows,_=fixture;rows[0]['price']='-1';rows[1]['source_reference']='';f,p=write();r=audit(f,p)
    assert all(x['pair']=='blocked' for x in r['records'])
    assert r['records'][1]['historical_iv']=='needs_evidence'
    for rec in r['records']:
        peer=[x for x in rec['issues'] if x['code'].startswith('PAIR_PEER_')]
        assert len(peer)==1
        assert not any(x.startswith('PAIR_PEER_') for x in peer[0]['peer_issue_codes'])

def test_ambiguous_group_blocked_singleton_missing(fixture):
    write,rows,_=fixture;rows.append(dict(rows[0]));f,p=write();r=audit(f,p)
    assert all(x['pair']=='blocked' for x in r['records'])
    assert all('peer_record' not in x for x in r['records'])
    rows.pop();rows.pop();f,p=write();r=audit(f,p)
    assert r['records'][0]['pair']=='needs_evidence'
    assert 'peer_record' not in r['records'][0]

@pytest.mark.parametrize('edge',['huge_integer','deep_json'])
def test_extreme_policy_cli_exit_two_no_output(fixture,tmp_path,capsys,edge):
    write,_,policy=fixture;f,p=write()
    if edge=='huge_integer':
        policy['max_pair_lag_seconds']=10**400;p.write_text(json.dumps(policy))
    else:p.write_text('['*1100+'0'+']'*1100)
    output=tmp_path/edge
    assert main([str(f),'--policy',str(p),'--output',str(output)])==2
    assert not output.exists()
    err=capsys.readouterr().err
    assert 'INPUT_ERROR:' in err and 'Traceback' not in err

@pytest.mark.parametrize('bad_index',[0,1])
@pytest.mark.parametrize('quantity',['0','-1','nan','','.5'])
@pytest.mark.parametrize('mid,expected',[('.1','conditional_input_consistent'),('.2','blocked')])
def test_mid_consistency_independent_of_depth(fixture,bad_index,quantity,mid,expected):
    write,rows,_=fixture;rows[bad_index].update(bid_qty=quantity,price=mid);f,p=write();report=audit(f,p)
    assert report['records'][bad_index]['historical_iv']==expected
    assert report['records'][1-bad_index]['historical_iv']=='conditional_input_consistent'
    assert ('MID_INCONSISTENT' in codes(report))==(expected=='blocked')
    expected_pair='blocked' if expected=='blocked' else 'needs_evidence'
    assert all(r['pair']==expected_pair for r in report['records'])

@pytest.mark.parametrize('bid,ask',[('nan','.11'),('.09',''),('.12','.11'),('-.01','.11')])
def test_invalid_quote_prices_cannot_certify_mid_iv(fixture,bid,ask):
    write,rows,_=fixture;rows[1].update(bid=bid,ask=ask,bid_qty='0');f,p=write();report=audit(f,p)
    assert report['records'][1]['historical_iv']=='needs_evidence'
    assert 'MID_PRICE_UNVERIFIABLE' in codes(report)
    assert 'MID_INCONSISTENT' not in codes(report)

def test_mid_average_does_not_overflow_finite_price_inputs(fixture):
    write,rows,_=fixture;rows[1].update(bid='1e308',ask='1e308',price='1e308',bid_qty='0');f,p=write();report=audit(f,p)
    assert 'MID_INCONSISTENT' not in codes(report)
    assert report['records'][1]['historical_iv']=='conditional_input_consistent'

def test_version_self_check_without_input_or_output(capsys):
    from derivatives_pricing.admission import AUDIT_VERSION
    with pytest.raises(SystemExit) as exc:main(['--version'])
    assert exc.value.code==0
    assert AUDIT_VERSION in capsys.readouterr().out
