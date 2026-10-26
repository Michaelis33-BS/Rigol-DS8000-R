"""Developer-only SCPI inventory extraction from Rigol's 2020 programming guide.
Regenerate only when a revised instrument manual is supplied.
"""
# Creator: Jeff Michaelis
import argparse
import fitz, re, json, pathlib

parser = argparse.ArgumentParser(description="Refresh the SCPI catalog from a Rigol manual PDF")
parser.add_argument("manual_pdf", help="Path to the Rigol programming guide PDF")
args = parser.parse_args()
pdf=fitz.open(args.manual_pdf)
entries=[]
for idx in range(15,264):
    lines=pdf[idx].get_text(sort=True).splitlines()
    for pos,line in enumerate(lines):
        hit=re.match(r'^\s*Syntax\s+(.+?)\s*$',line)
        if not hit:continue
        syntaxes=[hit.group(1).strip()]
        for s in lines[pos+1:pos+10]:
            s=s.strip()
            if not s:continue
            if re.match(r'^(Description|Parameter|Remarks|Return|Example|Note|Syntax|Command List)',s,re.I):break
            if re.match(r'^(?:\*|:|\[\s*:)[A-Za-z*\[:]',s):syntaxes.append(s)
            elif s.startswith(('*',':','[')) and not s.startswith('/*'):syntaxes.append(s)
            else:break
        # Extract description briefly; take subsequent lines until Parameter etc; no need to trust NLP.
        description=[]
        start=None
        for z in range(pos+1,min(len(lines),pos+25)):
            if re.match(r'^\s*Description(?:\s+|$)',lines[z]):
                start=z;break
        if start is not None:
            first=re.sub(r'^\s*Description\s+', '', lines[start]).strip()
            if first:description.append(first)
            for s in lines[start+1:start+5]:
                s=s.strip()
                if not s or re.match(r'^(Parameter|Remarks|Return|Format|Example|Syntax)',s,re.I):break
                if s.startswith('◆'):break
                description.append(s)
        for syn in syntaxes:
            if not re.match(r'^(?:\*|:|\[\s*:)',syn):continue
            syn=re.split(r'\s*/\*',syn)[0].strip()
            # SCPI can contain optional keywords and placeholders, separate based on first whitespace.
            command=syn.split(' ',1)[0]
            command=command.replace('?', '').strip()
            if not command:continue
            entries.append({'syntax':syn,'name':command,'query':'?' in syn.split(' ',1)[0], 'page':f'2-{idx-13}', 'pdf_page':idx+1,'description':' '.join(description).strip()})
# Keep first for duplicate headers. Preserve full syntax for params and precise query-only.
out=[]; seen=set()
for r in entries:
 key=r['syntax'].lower()
 if key in seen:continue
 seen.add(key);out.append(r)
path=pathlib.Path(__file__).resolve().parents[1] / 'src' / 'rigol_ds8000r' / 'command_catalog.json'
path.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print('Syntax entries',len(entries),'unique',len(out),'set',sum(not x['query'] for x in out),'query',sum(x['query'] for x in out))
print('sample',out[:12]);print('warnings without colon',[(r['syntax'],r['page']) for r in out if len(r['name'])<4][:20]);print('end',out[-4:])
