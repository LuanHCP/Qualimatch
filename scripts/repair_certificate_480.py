"""One-off, hash-bound repair from visual verification. Dry-run unless --apply."""
import json
import shutil
import sys
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qualimatch import database, local_sync
from qualimatch.config import DATA_DIR
from qualimatch.pdf_reader import Certificate, Sample, file_hash, PARSER_VERSION
from qualimatch.queries import certificate_detail

CID = 836
HASH = 'ea9ce9759ceced344138ecbdce3048ea2df7b5af4bcb62f04f0ce1fa22e9f036'


def verified_certificate(pdf):
    samples = [
        Sample('ROTINA', '4370', date(2026,8,21), False, 'SUL', 'FAIXA 2', 81580,
               'BD', 4.68, 2.0, 234.0, 2.447, 11.4, 2.678),
        Sample('ROTINA', '4371', date(2026,8,21), False, 'SUL', 'FAIXA 2', 81580,
               'EX', 3.98, 4.0, 99.5, 2.470, 10.3, 2.678),
    ]
    raw = {
        'parser_version': PARSER_VERSION, 'pages': 1, 'source_kind': 'bv_documentos', 'source_priority': 100,
        'service_dates': ['2026-08-21'], 'extraction_dates': ['2026-08-28'],
        'receipt_dates': ['2026-08-31'], 'assay_dates': ['2026-09-01'],
        'segment_source': 'CONFERENCIA_VISUAL_PDF', 'manual_visual_hash': HASH,
        'parse_status': 'PARCIAL',
        'parse_warnings': [
            'PDF em imagem: dados transcritos por conferência visual, sem alterar o PDF original.',
            'O PDF original apresenta #N/D no resultado final e nos limites estatísticos; solicitar parecer corrigido à BV.',
            'O resumo impresso de VV (8,2%) usa os valores com filme (8,6% e 7,8%); a coluna principal dos CPs informa 11,4% e 10,3%.',
        ],
        'phase_summaries': {'ROTINA': {
            'result_unavailable': True, 'vv_mean_pct': 8.2, 'vv_std_pct': 0.6,
            'ratio_mean_pct': 166.8, 'ratio_std_pct': 95.0,
        }},
        'film_voids_pct': {'4370': 8.6, '4371': 7.8},
    }
    return Certificate('PAVIDEZ', 'BI330-0480', str(pdf.resolve()), HASH,
        date(2026,8,21), date(2026,8,28), 'PR-445', 81080, 81580,
        'BI330_035_1435_TAPALAM_TAPALAM_FX-C_50-70_GRECA_T-4,6%',
        '', '', False, samples, raw)


def main():
    saved = database.row('SELECT * FROM certificates WHERE id=?', (CID,))
    assert saved and saved['number']=='BI330-0480' and saved['contractor']=='PAVIDEZ' and saved['is_active']
    assert saved['file_hash']==HASH, 'O conteúdo do 480 mudou; interrompido para nova conferência.'
    docs = database.rows('SELECT * FROM certificate_files WHERE certificate_id=? ORDER BY id DESC', (CID,))
    pdf = Path(saved['file_path'])
    assert pdf.is_file() and file_hash(pdf)==HASH, 'O PDF atual não coincide com o documento conferido.'
    cert = verified_certificate(pdf)
    print(json.dumps({'target': CID, 'number':cert.number, 'documents_before':len(docs),
                      'dates':cert.raw['service_dates'], 'samples':[s.cp_number for s in cert.samples]}, ensure_ascii=False), flush=True)
    if '--apply' not in sys.argv:
        return
    backup = DATA_DIR/'backups'/('repair_480_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    backup.mkdir(parents=True, exist_ok=False)
    before = {'certificate': saved, 'documents':docs,
              'samples':database.rows('SELECT * FROM certificate_samples WHERE certificate_id=?', (CID,)),
              'matches':database.rows('SELECT * FROM matches WHERE certificate_id=?', (CID,))}
    with (backup/'before.json').open('x',encoding='utf-8') as stream:
        json.dump(before,stream,ensure_ascii=False,indent=2,default=str)
    copied = {}
    for doc in docs:
        source = Path(doc['file_path'])
        try:
            if source.is_file():
                digest = file_hash(source)
                if digest not in copied:
                    target = backup/(digest+'.pdf')
                    shutil.copy2(source,target)
                    assert file_hash(target)==digest
                    copied[digest] = str(target)
        except OSError:
            continue  # Already absent SharePoint files remain described in before.json.
    assert HASH in copied, 'Não foi possível preservar o PDF atual; nenhuma alteração aplicada.'
    with database.transaction() as con:
        current = con.execute('SELECT * FROM certificates WHERE id=?', (CID,)).fetchone()
        assert dict(current)==saved, 'Registro alterado durante a conferência; correção cancelada.'
        now = datetime.now().isoformat(timespec='seconds')
        raw = dict(cert.raw, management_action='CONFERENCIA_VISUAL_480', management_updated_at=now,
                   recovery_backup=str(backup))
        con.execute('''UPDATE certificates SET identity_key=?,service_date=?,extraction_date=?,road=?,kmi=?,kmf=?,
            trace_approved=?,routine_result='',counterproof_result='',has_counterproof=0,
            parsed_at=?,raw_json=?,manual_override=1 WHERE id=?''',
            (local_sync._cert_identity(cert),'2026-08-21','2026-08-28',cert.road,cert.kmi,cert.kmf,cert.trace_approved,now,database.json_dumps(raw),CID))
        con.execute('DELETE FROM certificate_samples WHERE certificate_id=?', (CID,))
        con.executemany('''INSERT INTO certificate_samples(certificate_id,phase,cp_number,application_date,
            counterproof,direction,lane,station,position,thickness_exec_cm,thickness_project_cm,ratio_ab_pct,gmb,voids_pct,rice_gmm)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            [(CID,s.phase,s.cp_number,s.application_date.isoformat(),int(s.counterproof),s.direction,s.lane,
              s.station,s.position,s.thickness_exec_cm,s.thickness_project_cm,s.ratio_ab_pct,s.gmb,s.voids_pct,s.rice_gmm) for s in cert.samples])
        active = next(d for d in docs if d['file_path']==str(pdf.resolve()))
        # Retain tracking rows to avoid re-importing removed copies; hide from this card.
        con.execute("UPDATE certificate_files SET certificate_id=NULL,status='DUPLICADO_REMOVIDO',error='Consolidado no 480; cópia de recuperação: ' || ? WHERE certificate_id=?", (str(backup),CID))
        con.execute("UPDATE certificate_files SET certificate_id=?,status='PARCIAL',kind='ROTINA',error='',file_name=? WHERE id=?",
                    (CID,'BI330-0480-PAVIDEZ_TAPALAM_PR445_TR1435-21.08.26.pdf',active['id']))
        # One downloadable previous version per genuinely different, available content.
        seen = {HASH}
        for doc in docs:
            digest = doc.get('file_hash')
            if digest in copied and digest not in seen:
                source = Path(doc['file_path'])
                if source.is_file() and file_hash(source)==digest:
                    con.execute("UPDATE certificate_files SET certificate_id=?,status='SUBSTITUIDO',error='' WHERE id=?", (CID,doc['id']))
                    seen.add(digest)
        con.execute('''INSERT INTO audit_log(user_id,action,entity_type,entity_id,details_json,created_at)
            VALUES(NULL,'CORRECAO_VISUAL_480','certificate',?,?,?)''',
            (str(CID),database.json_dumps({'backup':str(backup),'current_pdf':str(pdf),'raw':raw}),now))
    print('BACKUP',backup,flush=True)
    detail = certificate_detail(CID)
    print('VERIFIED',json.dumps({k:detail.get(k) for k in ('number','service_date','extraction_date','kmi','kmf','sample_count','mean_vv','overall_status','parse_warnings')},ensure_ascii=False),flush=True)
    print('DOCUMENTS',[(d['id'],d['status']) for d in detail['documents']],flush=True)


if __name__=='__main__':
    main()
