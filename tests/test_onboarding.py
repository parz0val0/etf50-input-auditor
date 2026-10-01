import csv
import json
from pathlib import Path
from html.parser import HTMLParser
import pytest
from scripts import reproduce_onboarding_case as demo
from derivatives_pricing.admission import audit,main,InputError

def test_three_root_causes_and_real_input_edits(tmp_path):
    out=tmp_path/'case';result=demo.replay(out)
    assert result['evidence_truth_verified'] is False
    assert [(r['record'],r['code']) for r in result['root_causes']]==[(2,'SPOT_ALIGNMENT_MISSING'),(3,'Q_INPUT_MISSING'),(6,'SETTLEMENT_NOT_INDEPENDENT')]
    edits={(r['record'],r['field']):(r['before'],r['after']) for r in result['input_changes']}
    assert len(edits)==8
    assert edits[2,'spot']==('2.70','2.69')
    assert edits[3,'q']==('.015','0')
    assert edits[3,'q_reference'][0]!=edits[3,'q_reference'][1]
    evidence=json.loads((demo.ROOT/'examples/onboarding/synthetic_evidence.json').read_text())
    assert edits[6,'price']==(format(evidence['settlement_value']['price'],'.4f'),format(evidence['quote_sequence'][5]['mid'],'.4f'))
    assert edits[6,'price_type']==('settle','mid')
    before=json.loads((out/'before/report.json').read_text());after=json.loads((out/'after/report.json').read_text())
    assert before['summary']['historical_iv']=={'conditional_input_consistent':3,'needs_evidence':2,'blocked':1}
    assert before['summary']['pair']=={'conditional_input_consistent':4,'blocked':2}
    assert after['summary']['conditional_pairs']==3
    assert all(r['historical_iv']=='conditional_input_consistent' and r['pair']=='conditional_input_consistent' for r in after['records'])
    assert all(not r['issues_after'] for r in result['records'])
    class Structure(HTMLParser):
        def __init__(self):super().__init__();self.rows=0;self.headings=0;self.scripts=0
        def handle_starttag(self,tag,attrs):
            if tag=='tr':self.rows+=1
            if tag=='th':self.headings+=1
            if tag=='script':self.scripts+=1
    for name in ('before','after'):
        html=(out/name/'report.html').read_text();parser=Structure();parser.feed(html)
        assert (parser.rows,parser.headings,parser.scripts)==(7,5,0)
        assert '认证' in html
        assert '输入一致性原型' in html


def test_case_replay_is_deterministic_and_does_not_overwrite(tmp_path,capsys):
    a=demo.replay(tmp_path/'a');b=demo.replay(tmp_path/'b');assert a==b
    existing=(tmp_path/'a/comparison.json').read_bytes()
    assert demo.main(['--output',str(tmp_path/'a')])==2
    assert (tmp_path/'a/comparison.json').read_bytes()==existing
    assert 'DEMO_ERROR' in capsys.readouterr().err


def test_minimal_daily_import_keeps_unknown_evidence(tmp_path):
    source=demo.ROOT/'examples/admission/synthetic_minimal_daily.csv'
    assert main([str(source),'--output',str(tmp_path/'minimal')])==1
    r=json.loads((tmp_path/'minimal/report.json').read_text())
    assert r['summary']['rows']==2
    assert r['summary']['historical_iv']=={'needs_evidence':2}
    assert r['summary']['conditional_pairs']==0
    assert {'COVERAGE_UNDECLARED','R_INPUT_MISSING','Q_INPUT_MISSING'}<=set(r['summary']['issue_counts'])


def test_alternate_export_requires_explicit_documented_mapping(tmp_path):
    folder=demo.ROOT/'examples/admission';source=folder/'synthetic_vendor_export.csv'
    with pytest.raises(InputError):audit(source)
    dictionary=json.loads((folder/'synthetic_vendor_dictionary.json').read_text())
    assert dictionary['data_kind']=='synthetic' and dictionary['price_semantics']=='daily_close'
    inverse={v:k for k,v in dictionary['mapping'].items()}
    with source.open() as f:raw=list(csv.DictReader(f))
    mapped=[]
    for row in raw:
        r={inverse[k]:v for k,v in row.items()}
        r['date']=r['date'].replace('/','-');r['expiry']=r['expiry'].replace('/','-')
        r['cp']={'认购':'C','认沽':'P'}[r['cp']]
        r['price_type']='close'  # Supplied fictional dictionary, never an unknown-price default.
        mapped.append(r)
    path=tmp_path/'mapped.csv'
    with path.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(mapped[0]));w.writeheader();w.writerows(mapped)
    r=audit(path)
    assert r['summary']['rows']==2 and r['summary']['historical_iv']=={'needs_evidence':2}
    assert r['summary']['conditional_pairs']==0


def test_saved_comparison_uses_current_checker(tmp_path):
    current=demo.replay(tmp_path/'current')
    saved=json.loads((demo.ROOT/'examples/onboarding/output/comparison.json').read_text())
    assert current==saved
