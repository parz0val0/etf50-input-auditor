#!/usr/bin/env python3
"""Check relative Markdown/HTML file links in a candidate, including notebook prose."""
import argparse,json,re
from pathlib import Path
from urllib.parse import unquote,urlsplit

def missing_links(root):
    findings=[];checked=0
    for file in sorted(root.rglob('*')):
        if not file.is_file() or file.suffix not in ('.md','.html','.ipynb'):continue
        try:text=file.read_text()
        except (UnicodeDecodeError,OSError):continue
        if file.suffix=='.ipynb':
            book=json.loads(text);text='\n'.join(''.join(c.get('source',[])) if isinstance(c.get('source'),list) else c.get('source','') for c in book.get('cells',[]) if c.get('cell_type')=='markdown')
        markdown_text = re.sub(r'<(div|pre|script|style)\b[^>]*>.*?</\1>', '', text, flags=re.S)
        markdown_links = re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', markdown_text) if file.suffix != '.html' else []
        links=markdown_links+re.findall(r'(?:href|src)=["\x27]([^"\x27]+)["\x27]',text)
        for raw in links:
            target=raw.strip()
            if target.startswith('<'):target=target[1:target.index('>')]
            else:target=target.split(' "')[0].split(" '")[0]
            parsed=urlsplit(target)
            if parsed.scheme or target.startswith(('#','/')) or not parsed.path:continue
            checked+=1
            path=(file.parent/unquote(parsed.path)).resolve()
            if not path.exists():findings.append({'file':str(file.relative_to(root)),'target':target})
    return {'checked_relative_links':checked,'missing':findings,'passed':not findings}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);a=p.parse_args();result=missing_links(a.root.resolve());print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
