# -*- coding: utf-8 -*-
"""Replay the fixed fictional onboarding case; expected findings are demo success."""
import argparse
import contextlib
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from derivatives_pricing.admission import main as audit_main

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def replay(output):
    if output.exists():raise ValueError('输出目录已存在，请使用新目录')
    fixture=ROOT/'examples/onboarding'
    before=fixture/'before.csv';after=fixture/'after.csv';policy=fixture/'synthetic_policy.json'
    # Validate fixture availability before creating any output.
    for p in (before,after,policy,fixture/'synthetic_evidence.json'):
        if not p.is_file():raise ValueError('缺合成案例文件：'+p.name)
    output.mkdir(parents=True,exist_ok=False)
    for name,source,expected in (('before',before,1),('after',after,0)):
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream):
            code=audit_main([str(source),
        '--policy',str(policy),
        '--output',str(output/name)])
        if code!=expected:raise ValueError(name+'退出码不符合冻结案例预期：'+str(code))
    reports={name:json.loads((output/name/'report.json').read_text()) for name in ('before',
        'after')}
    assert reports['before']['summary']['conditional_pairs']==2
    assert reports['after']['summary']['conditional_pairs']==3
    assert reports['after']['summary']['issue_counts']=={}
    changes=[]
    for a,b in zip(reports['before']['records'],reports['after']['records']):
        changes.append({'record':a['record'],
        'historical_iv_before':a['historical_iv'],
        'historical_iv_after':b['historical_iv'],
        'pair_before':a['pair'],
        'pair_after':b['pair'],
        'issues_before':[x['code'] for x in a['issues']],
        'issues_after':[x['code'] for x in b['issues']]})
    with before.open(newline='') as f:before_rows=list(csv.DictReader(f))
    with after.open(newline='') as f:after_rows=list(csv.DictReader(f))
    input_changes=[{'record':i,
        'field':k,
        'before':a[k],
        'after':b[k]} for i,(a,b) in enumerate(zip(before_rows,after_rows),1) for k in a if a[k]!=b[k]]
    result={
        'scope':'固定、完全合成案例；不是市场实证或资格认证',
        'evidence_truth_verified':False,
        'data_kind':'synthetic',
        'checker_version':reports['after']['tool_version'],
        'checker_sha256':reports['after']['checker_sha256'],
        'fixture_sha256':{p.name:digest(p) for p in (before,after,policy,fixture/'synthetic_evidence.json')},
        'expected_exit_codes':{'before':1,
        'after':0},
        'root_causes':[{'record':2,
        'code':'SPOT_ALIGNMENT_MISSING',
        'repair':'用独立较早合成ETF观测替代未来观测，不给未来价格回填时间'},
        {'record':3,
        'code':'Q_INPUT_MISSING',
        'repair':'改用事前合成估计及其真实场景已知时间，不把后来信息伪装已知'},
        {'record':6,
        'code':'SETTLEMENT_NOT_INDEPENDENT',
        'repair':'按独立合成BBO重新计算mid和价格来源，不仅改price_type'}],
        'input_changes':input_changes,
        'records':changes,
        'limits':['合成证据文件由本项目构造；其引用真实性不由审查器自动验证',
        '条件输入一致不是数据许可、母集、市场定价或样本外有效性认证',
        '状态前后对比不评价模型、预测能力或工具使用者成功率']}
    (output/'comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    lines=['# 三个问题的合成前后对比',
        '',
        '全部数据和证据是人为构造。修正后仅条件相容，实际证据真实性仍未由工具验证。',
        '',
        '| 业务记录 | 历史IV前→后 | 配对前→后 | 原问题代码 |',
        '| --- | --- | --- | --- |']
    for r in changes:lines.append('| '+str(r['record'])+' | '+r['historical_iv_before']+' → '+r['historical_iv_after']+' | '+r['pair_before']+' → '+r['pair_after']+' | '+', '.join(r['issues_before'])+' |')
    lines+=['',
        '三个根因在记录2、3、6；其余配对提示是根因造成的派生问题，不是额外三份独立证据。',
        '', '[修正前HTML](before/report.html) · [修正后HTML](after/report.html) · [字段修改与哈希](comparison.json)',
        '', '每次输出目录须新建。不能把本案例的补证值或虚构覆盖配置用于行情。']
    (output/'comparison.md').write_text('\n'.join(lines)+'\n')
    return result

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv)
    try:
        result=replay(a.output)
        print(json.dumps({'case':'synthetic_three_research_problems',
        'expected_before_exit':1,
        'expected_after_exit':0,
        'changed_fields':len(result['input_changes']),
        'comparison':str(a.output/'comparison.md'),
        'evidence_truth_verified':False},ensure_ascii=False))
        return 0
    except (OSError,ValueError,AssertionError) as exc:
        print('DEMO_ERROR: '+str(exc),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
