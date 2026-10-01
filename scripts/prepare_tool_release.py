"""Build a synthetic-only local tool candidate; no publishing or license selection."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
ROOT=Path(__file__).resolve().parents[1]
FILES=('.gitignore','README.md','README.zh-CN.md','docs/GETTING_STARTED.md','docs/GETTING_STARTED.zh-CN.md','docs/REPORT_WALKTHROUGH.md','docs/REPORT_WALKTHROUGH.zh-CN.md','docs/assets/workflow.en.svg','docs/assets/workflow.zh.svg','LICENSE','docs/SUPPLIER_REQUIREMENTS.md','docs/PREFLIGHT_VALIDATION.md','pyproject.toml','docs/ADMISSION_SCHEMA.md','docs/TOOL_BOUNDARIES.md','docs/RELATED_WORK.md','docs/RELEASE_CHECKLIST.md','docs/ONBOARDING_CASE.md','docs/IMPORT_GUIDE.md','docs/INSTALLATION.md','docs/SIMULATED_USER_EVALUATION.md','docs/NUMERICAL_AUXILIARY.md','scripts/reproduce_onboarding_case.py','scripts/reproduce_preflight_case.py','scripts/numerical_budget_study.py','scripts/check_relative_links.py','scripts/prepare_tool_release.py')
TESTS=('test_preflight.py','test_admission.py','test_black_scholes.py','test_numerical.py','test_implied_volatility.py','test_heston.py','test_experiments.py','test_research.py','test_tool_release.py','test_onboarding.py')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def audit_tree(root):
 findings=[]
 pattern=re.compile('/'+'Users/'+r'[^\s/"\x27<>]+/')
 for p in root.rglob('*'):
  if p.is_symlink():findings.append({'path':str(p.relative_to(root)),'reason':'symlink'})
  if not p.is_file():continue
  if p.suffix not in ('.py','.md','.toml','.json','.csv','.html','.svg') and p.name!='.gitignore':continue
  text=p.read_text(encoding='utf-8')
  if pattern.search(text):findings.append({'path':str(p.relative_to(root)),'reason':'personal_absolute_path'})
  if re.search(r'AKIA[0-9A-Z]{16}',text):findings.append({'path':str(p.relative_to(root)),'reason':'possible_access_key'})
 return findings

def verify_manifest(root):
 m=json.loads((root/'PUBLIC_CANDIDATE_MANIFEST.json').read_text())
 expected={f['path'] for f in m['files']}
 actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}-{'PUBLIC_CANDIDATE_MANIFEST.json'}
 if expected!=actual:return False
 return all((root/f['path']).stat().st_size==f['bytes'] and digest(root/f['path'])==f['sha256'] for f in m['files'])

def build(out):
 out=out.resolve()
 if out.exists():raise ValueError('choose a fresh candidate directory')
 if out==ROOT or ROOT in out.parents:raise ValueError('candidate must be outside source project')
 selected=[ROOT/f for f in FILES]
 selected+=sorted((ROOT/'src/derivatives_pricing').glob('*.py'))
 selected+=[ROOT/'tests'/name for name in TESTS]
 selected+=[ROOT/'examples/admission'/name for name in ('synthetic_consistent.csv','synthetic_failures.csv','synthetic_policy.json','synthetic_failure_policy.json','synthetic_minimal_daily.csv','synthetic_vendor_export.csv','synthetic_vendor_dictionary.json')]
 selected+=[ROOT/'examples/output'/name for name in ('README.md','consistent/report.json','consistent/report.html','failures/report.json','failures/report.html')]
 selected+=[ROOT/'examples/onboarding'/name for name in ('before.csv','after.csv','synthetic_policy.json','synthetic_evidence.json','output/before/report.json','output/before/report.html','output/after/report.json','output/after/report.html','output/comparison.json','output/comparison.md')]
 if any(not p.is_file() or p.is_symlink() for p in selected):raise ValueError('required file missing or symlink')
 out.mkdir(parents=True)
 for p in selected:
  target=out/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
 # Report fixtures are published only when explicitly synthetic.
 for p in (out/'examples/output').rglob('report.json'):
  if json.loads(p.read_text()).get('evidence_level')!='synthetic_declared':raise ValueError('non-synthetic report in examples')
 for p in (out/'examples/onboarding/output').rglob('report.json'):
  if json.loads(p.read_text()).get('evidence_level')!='synthetic_declared':raise ValueError('non-synthetic onboarding output')
 for p in (out/'examples/admission').glob('*.json'):
  if json.loads(p.read_text()).get('data_kind')!='synthetic':raise ValueError('non-synthetic example configuration')
 from importlib.util import spec_from_file_location,module_from_spec
 spec=spec_from_file_location('relative_links',out/'scripts/check_relative_links.py');module=module_from_spec(spec);spec.loader.exec_module(module)
 links=module.missing_links(out);privacy=audit_tree(out)
 if not links['passed'] or privacy:raise ValueError('public-content checks failed: '+json.dumps({'links':links,'privacy':privacy}))
 evidence={'candidate_version':'0.4.0rc6','content_scope':'own code and synthetic examples; no historical market outputs','not_published':False,'code_release_published':True,'code_release_commit':'5074c46cddd8605ffad5bfddbc56b1e0c0ac2a92','documentation_update_status':'pre_push_review_snapshot_not_live_status','remote_ci':'not_configured','license':'MIT; Copyright (c) 2026 JasonChen','relative_links':links,'privacy_static_findings':privacy,'verification':'build checks only; execution evidence maintained separately until final manifest'}
 (out/'RELEASE_EVIDENCE.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
 write_manifest(out)
 return out

def write_manifest(out):
 files=[{'path':str(p.relative_to(out)),'bytes':p.stat().st_size,'sha256':digest(p)} for p in sorted(out.rglob('*')) if p.is_file() and p.name!='PUBLIC_CANDIDATE_MANIFEST.json']
 (out/'PUBLIC_CANDIDATE_MANIFEST.json').write_text(json.dumps({'scope':'all candidate files excluding self','candidate_version':'0.4.0rc6','files':files},ensure_ascii=False,indent=2)+'\n')
 assert verify_manifest(out)

def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv)
 try:
  result=build(a.output);print(json.dumps({'candidate':result.name,'manifest_sha256':digest(result/'PUBLIC_CANDIDATE_MANIFEST.json'),'verified':verify_manifest(result)}));return 0
 except (OSError,ValueError) as exc:
  print('BUILD_ERROR: '+str(exc),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
