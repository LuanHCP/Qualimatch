from __future__ import annotations

from zipfile import ZipFile
import xml.etree.ElementTree as ET
import re
from typing import Any

NS_MAIN='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
NS_REL='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
NS_PKG='http://schemas.openxmlformats.org/package/2006/relationships'


def col_to_num(col:str)->int:
    n=0
    for ch in col.upper():
        if 'A'<=ch<='Z': n=n*26+ord(ch)-64
    return n


def split_ref(ref:str)->tuple[str,int]:
    m=re.fullmatch(r'([A-Za-z]+)(\d+)',ref)
    if not m: raise ValueError(ref)
    return m.group(1),int(m.group(2))


def sheet_path(z:ZipFile,sheet_name:str)->str:
    wb=ET.fromstring(z.read('xl/workbook.xml'))
    rels=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
    relmap={r.attrib['Id']:r.attrib['Target'] for r in rels.findall(f'{{{NS_PKG}}}Relationship')}
    sheets=wb.find(f'{{{NS_MAIN}}}sheets')
    for s in sheets:
        if s.attrib.get('name')==sheet_name:
            rid=s.attrib[f'{{{NS_REL}}}id']; target=relmap[rid]
            if target.startswith('/'): return target.lstrip('/')
            if target.startswith('xl/'): return target
            return 'xl/'+target
    raise KeyError(f'Aba {sheet_name!r} não encontrada')


def shared_strings(z:ZipFile)->list[str]:
    if 'xl/sharedStrings.xml' not in z.namelist(): return []
    root=ET.fromstring(z.read('xl/sharedStrings.xml'))
    out=[]
    for si in root.findall(f'{{{NS_MAIN}}}si'):
        out.append(''.join(t.text or '' for t in si.iter(f'{{{NS_MAIN}}}t')))
    return out


def cell_value(cell:ET.Element|None,strings:list[str])->Any:
    if cell is None: return None
    t=cell.attrib.get('t','')
    if t=='inlineStr':
        return ''.join(x.text or '' for x in cell.iter(f'{{{NS_MAIN}}}t'))
    v=cell.find(f'{{{NS_MAIN}}}v')
    if v is None or v.text is None: return None
    raw=v.text
    if t=='s':
        try: return strings[int(raw)]
        except Exception: return raw
    if t=='b': return raw=='1'
    if t in {'str','d'}: return raw
    try:
        n=float(raw)
        return int(n) if n.is_integer() else n
    except ValueError:
        return raw


def row_cells(row:ET.Element)->dict[int,ET.Element]:
    out={}
    for c in row.findall(f'{{{NS_MAIN}}}c'):
        ref=c.attrib.get('r','')
        try: col,_=split_ref(ref); out[col_to_num(col)]=c
        except Exception: pass
    return out
