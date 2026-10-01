"""Public synthetic CSV preview/confirmation demonstration; no market input."""
import argparse,csv,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from derivatives_pricing import admission,preflight

def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args(argv)
 if args.output.exists():p.exit(2,'Output already exists\n')
 args.output.mkdir(parents=True)
 raw=args.output/'synthetic_supplier.csv'
 source=ROOT/'examples/admission/synthetic_consistent.csv'
 with source.open(encoding='utf-8-sig',newline='') as f:
  r=csv.DictReader(f);fields=r.fieldnames;rows=list(r)
 aliases={k:preflight.ALIASES[k][0] if preflight.ALIASES[k] else k for k in fields}
 with raw.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=[aliases[k] for k in fields]);w.writeheader();w.writerows({aliases[k]:v for k,v in row.items()} for row in rows)
 before=raw.read_bytes();sha=hashlib.sha256(before).hexdigest()
 mapping=args.output/'confirmed_mapping.json';mapping.write_text(json.dumps(aliases,ensure_ascii=False,indent=2),encoding='utf-8')
 inspect_exit=preflight.main([str(raw),'--output',str(args.output/'preview')])
 convert_exit=preflight.main([str(raw),'--mapping',str(mapping),'--expected-source-sha256',sha,'--policy',str(ROOT/'examples/admission/synthetic_policy.json'),'--output',str(args.output/'converted')])
 report=json.loads((args.output/'converted/preflight.json').read_text())
 assert inspect_exit==0 and convert_exit==0
 assert raw.read_bytes()==before
 assert report['admission']==admission.audit(args.output/'converted/normalized.csv',ROOT/'examples/admission/synthetic_policy.json')
 result={'data_kind':'synthetic','source_unchanged':True,'preview_exit':inspect_exit,'convert_exit':convert_exit,'same_checker_result':True,'source_sha256':sha,'mapping_sha256':report['mapping_sha256'],'evidence_truth_verified':False}
 (args.output/'comparison.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
 print(json.dumps(result));return 0
if __name__=='__main__':raise SystemExit(main())
