#!/usr/bin/env python3
"""Prespecified repeated local efficiency study under the same GBM model."""
import argparse
from dataclasses import asdict
import hashlib
import json
from math import sqrt
from pathlib import Path
import platform
import statistics
from random import Random
import sys
from time import perf_counter
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from derivatives_pricing import BSInputs, price, binomial_price, monte_carlo_price
PROTOCOL={'revision':'v2 adds exploratory seed-resampling uncertainty after review; original v1 kept', 'seed_resampling_draws':2000, 'seed_resampling_seed':20261001, 'scope':'synthetic GBM European options; local hardware only',
 'cases':[dict(S=100,K=100,T=.5,r=.02,q=.01,sigma=.2,option_type='call'),dict(S=100,K=110,T=.5,r=.02,q=.01,sigma=.2,option_type='call'),dict(S=100,K=90,T=1,r=.02,q=.01,sigma=.4,option_type='put')],
 'steps':[100,200,400,800], 'paths':[2000,8000,32000],
 'seeds':[11,29,47,83,101,127,149,173,197,223], 'timing_repeats':5,
 'error_budget_per_underlying_unit':.02,'selection_rule':'minimum median latency among prespecified configurations meeting across-seed RMSE budget; report none if none meets',
 'ordering':'rotate configurations by repetition and reverse every other repetition',
 'uncertainty':'ten seeds are independent sampling repetitions; five repeated timings of each seed are not extra independent prices; observed p95 uses nearest rank',
 'not_claimed':['market accuracy','portable efficiency ranking','monotone single-seed MC error','statistical significance']}
def summarize(xs):
    ordered=sorted(xs)
    return {'median':statistics.median(xs),'p95_nearest_rank':ordered[max(0,(95*len(xs)+99)//100-1)],'min':min(xs),'max':max(xs),'count':len(xs)}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('Choose a fresh output file; old evidence is never replaced')
    protocol_hash=hashlib.sha256(json.dumps(PROTOCOL,sort_keys=True).encode()).hexdigest()
    rows=[]
    for case_index,case in enumerate(PROTOCOL['cases']):
        inputs=BSInputs(**{k:v for k,v in case.items() if k!='option_type'});kind=case['option_type'];truth=price(inputs,kind)
        configs=[('CRR',n) for n in PROTOCOL['steps']]+[('MC',n) for n in PROTOCOL['paths']]
        def evaluate(method,budget,seed):
            if method=='CRR':return binomial_price(inputs,kind,budget),None
            result=monte_carlo_price(inputs,kind,budget,seed);return result.price,result.standard_error
        for m,n in configs:evaluate(m,n,PROTOCOL['seeds'][0])
        for repeat in range(PROTOCOL['timing_repeats']):
            order=configs[repeat%len(configs):]+configs[:repeat%len(configs)]
            if repeat%2:order.reverse()
            for m,n in order:
                for seed in (PROTOCOL['seeds'] if m=='MC' else [None]):
                    start=perf_counter();value,se=evaluate(m,n,seed);seconds=perf_counter()-start
                    rows.append(dict(case=case_index,method=m,budget=n,seed=seed,repeat=repeat,price=value,error=value-truth,standard_error=se,seconds=seconds))
    summaries=[];selected=[]
    for c in range(len(PROTOCOL['cases'])):
        for m,n in [('CRR',n) for n in PROTOCOL['steps']]+[('MC',n) for n in PROTOCOL['paths']]:
            group=[x for x in rows if x['case']==c and x['method']==m and x['budget']==n]
            unique={x['seed']:x for x in group};errors=[x['error'] for x in unique.values()]
            rmse=sqrt(sum(x*x for x in errors)/len(errors))
            interval = None
            if m == 'MC':
                random = Random(PROTOCOL['seed_resampling_seed'] + c*100000+n)
                values = sorted(sqrt(sum(random.choice(errors)**2 for _ in errors)/len(errors)) for _ in range(PROTOCOL['seed_resampling_draws']))
                interval = [values[49], values[1949]]
            summaries.append(dict(seed_resampling_95_percentile_interval=interval, interval_interpretation='descriptive finite-seed sensitivity, not population coverage guarantee or significance test',case=c,method=m,budget=n,rmse=rmse,independent_price_samples=len(unique),timing=summarize([x['seconds'] for x in group]),meets_error_budget=rmse<=PROTOCOL['error_budget_per_underlying_unit']))
        for m in ('CRR','MC'):
            eligible=[x for x in summaries if x['case']==c and x['method']==m and x['meets_error_budget']]
            winner=min(eligible,key=lambda x:x['timing']['median']) if eligible else None
            selected.append(dict(case=c,method=m,selected_budget=winner['budget'] if winner else None,qualified=bool(winner)))
    obj=dict(protocol=PROTOCOL,protocol_sha256=protocol_hash,python=platform.python_version(),platform=platform.platform(),script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),source_sha256={str(x.relative_to(ROOT)):hashlib.sha256(x.read_bytes()).hexdigest() for x in (ROOT/'src/derivatives_pricing').glob('*.py')},rows=rows,summaries=summaries,selection=selected)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'timing_rows':len(rows),'protocol_sha256':protocol_hash,'summaries':summaries,'selection':selected},indent=2))
if __name__=='__main__':main()
