"""Read-only comparison of a saved BI330 with its current source PDF."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qualimatch.database import rows
from qualimatch.pdf_reader import parse_pdf
from pypdf import PdfReader
import subprocess
import shutil

number = f'BI330-{int(sys.argv[1]):04d}'
for item in rows('SELECT * FROM certificates WHERE number=? AND is_active=1', (number,)):
    fields = ['id','contractor','number','service_date','extraction_date','road','kmi','kmf','trace_approved','routine_result','counterproof_result','has_counterproof','file_path','file_hash','parsed_at']
    print('SAVED', json.dumps({key: item.get(key) for key in fields}, ensure_ascii=False), flush=True)
    raw = json.loads(item['raw_json'] or '{}')
    print('RAW_DATES', json.dumps({k:v for k,v in raw.items() if 'date' in k or 'source_' in k}, ensure_ascii=False), flush=True)
    docs = rows('SELECT * FROM certificate_files WHERE certificate_id=? ORDER BY id', (item['id'],))
    for doc in docs:
        print('DOCUMENT',json.dumps({k:doc.get(k) for k in ('id','kind','status','file_path','file_hash','mtime_ns')}, ensure_ascii=False),flush=True)
        path = Path(doc['file_path'])
        if path.is_file() and doc['status'] not in {'SUBSTITUIDO','EXCLUIDO'}:
            if '--inspect' in sys.argv:
                reader = PdfReader(path)
                print('PAGE_COUNT',len(reader.pages),flush=True)
                for index,page in enumerate(reader.pages):
                    text = page.extract_text() or ''
                    print('PAGE_TEXT',index,len(text),repr(text[:2000]),flush=True)
                renderer = shutil.which('pdftoppm')
                if renderer:
                    output=Path('data/cache/inspect-480'); output.mkdir(parents=True,exist_ok=True)
                    subprocess.run([renderer,'-f','1','-singlefile','-scale-to','1600','-png',str(path),str(output/'page')],check=True)
            cert = parse_pdf(path, item['contractor'])
            print('CURRENT_PDF', json.dumps({key:str(getattr(cert,key,'')) for key in fields if key not in {'id','parsed_at'}}, ensure_ascii=False),flush=True)
            print('CURRENT_DATES',json.dumps({k:v for k,v in cert.raw.items() if 'date' in k},ensure_ascii=False),flush=True)
