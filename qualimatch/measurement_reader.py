from __future__ import annotations
from dataclasses import dataclass,asdict
from datetime import date
from pathlib import Path
from typing import Any
from zipfile import ZipFile
import xml.etree.ElementTree as ET
from .normalizers import norm_header,norm_road,norm_direction,norm_lane,number,station,text,to_date
from .xlsx_xml import NS_MAIN,cell_value,row_cells,shared_strings,sheet_path

@dataclass(slots=True)
class MeasurementRow:
 source_row:int; line_measurement:str; ref_measurement:str; team:str; inspector:str; date:date|None; road:str; direction:str; kmi:int|None; kmf:int|None; lane:str; extension_m:float|None; width_m:float|None; thickness_m:float|None; scope:str; mass_type:str; area_m2:float|None; paint_m2:float|None; volume_mass_m3:float|None; volume_milled_m3:float|None; quantity_t:float|None; dmt_milled_km:float|None; raw:dict[str,Any]

def read_measurements(path:str|Path,worksheet='RDO_RESTAURA'):
 path=Path(path); out=[]; hmap={}; originals={}; header=None
 with ZipFile(path) as z:
  strings=shared_strings(z); sp=sheet_path(z,worksheet)
  with z.open(sp) as f:
   for ev,row in ET.iterparse(f,events=('end',)):
    if row.tag!=f'{{{NS_MAIN}}}row':continue
    nr=int(row.attrib.get('r','0')); cells=row_cells(row)
    if header is None:
     hm={}; orig={}
     for col,c in cells.items():
      v=cell_value(c,strings)
      if v not in (None,''): hm[norm_header(v)]=col; orig[col]=text(v)
     if nr<=60 and {norm_header('DATA'),norm_header('RODOVIA'),norm_header('KMI'),norm_header('KMF')}.issubset(hm): header=nr;hmap=hm;originals=orig
     row.clear();continue
    def col(*names):
     for n in names:
      c=hmap.get(norm_header(n))
      if c:return c
     return None
    def get(*names):
     c=col(*names);return cell_value(cells.get(c),strings) if c else None
    d=to_date(get('DATA'));road=norm_road(get('RODOVIA'))
    if d and road:
     kmi=station(get('KMI'));kmf=station(get('KMF')); ext=number(get('EXTENSÃO (M)','EXTENSÃO (m)'))
     if ext is None and kmi is not None and kmf is not None:ext=abs(kmf-kmi)
     width=number(get('LARGURA (M)','LARGURA (m)')); thick=number(get('ESPESSURA (M)','ESPESSURA (m)')); area=number(get('AREA (m²)','ÁREA (m²)','AREA (M²)'))
     if area is None and ext is not None and width is not None:area=ext*width
     vol=number(get('VOLUME MASSA (m³)','VOLUME MASSA (M³)'))
     if vol is None and area is not None and thick is not None:vol=area*thick
     raw={}
     for idx,name in originals.items():
      v=cell_value(cells.get(idx),strings)
      if v not in (None,''):raw[name]=v
     out.append(MeasurementRow(nr,text(get('LINHA','LINHA MEDIÇÃO')) or str(nr),text(get('REF MEDIÇÃO')),text(get('EQUIPE')),text(get('FISCAL')),d,road,norm_direction(get('SENTIDO')),kmi,kmf,norm_lane(get('FAIXA')),ext,width,thick,text(get('TIPO','ESCOPO')),text(get('TIPO DE MASSA')),area,number(get('PINTURA DE LIGAÇÃO (m²)','PINTURA DE LIGACAO (m2)')),vol,number(get('VOLUME FRESADO (m³)','VOLUME FRESADO (M³)')),number(get('QUANT (ton)','QUANT PROJETO (ton)','QUANTIDADE (ton)')),number(get('DMT FRESADO (Km)','DMT FRESADO (KM)')),raw))
    row.clear()
 if header is None:raise ValueError('Cabeçalho da medição não localizado.')
 return out

def row_to_dict(r):
 d=asdict(r);d['date']=r.date.isoformat() if r.date else None;return d
