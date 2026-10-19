"""Base totalmente fictícia e reproduzível da edição pública QualiMatch V2."""

from __future__ import annotations

import json
import random
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

from openpyxl import Workbook
from pypdf import PdfWriter

from .auth import hash_password
from .config import DATA_DIR
from .database import row, transaction


SEED_VERSION = "2.0.0"
RECORDS_PER_AREA = 200
DEMO_EMAIL = "admin@qualimatch.local"
DEMO_PASSWORD = "Demo@2026"


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _create_demo_documents() -> list[Path]:
    folder = DATA_DIR / "demo_documents"
    folder.mkdir(parents=True, exist_ok=True)
    template = folder / "modelo.pdf"
    if not template.exists():
        writer = PdfWriter()
        writer.add_blank_page(width=595, height=842)
        writer.add_metadata({"/Title": "Documento fictício QualiMatch V2", "/Author": "QualiMatch Demo"})
        with template.open("wb") as handle:
            writer.write(handle)
    result = []
    for index in range(1, RECORDS_PER_AREA + 1):
        target = folder / f"documento_demo_{index:03d}.pdf"
        if not target.exists():
            shutil.copy2(template, target)
        result.append(target.resolve())
    return result


def _create_trace_inventory() -> None:
    target = DATA_DIR / "quality_general" / "inventario_tracos.xlsx"
    target.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "CBUQ"
    headers = [
        "CÓD INT LAB CCR", "CÓDIGO EXTERNO - CONTRATADA", "TRAÇO", "TIPO DE TRAÇO",
        "CLASSIFICAÇÃO", "CONSTRUTORA", "Nº CONTRATO", "OBRA", "LOCAL DE APLICAÇÃO",
        "USINA", "TIPO USINA", "ORIGEM DO AGREGADO", "FORNECEDOR LIGANTE", "TIPO LIGANTE",
        "STATUS", "RESPONSÁVEL APROVAÇÃO", "DATA APROVAÇÃO", "DATA VENCIMENTO",
        "SELO DE APROVAÇÃO", "LINK CARTA TRAÇO", "OBSERVAÇÕES",
    ]
    ws.append(headers)
    statuses = ["APROVADO", "APROVADO", "APROVADO", "EM ANÁLISE", "RESTRITO", "REPROVADO"]
    today = date.today()
    for i in range(1, RECORDS_PER_AREA + 1):
        approved = today - timedelta(days=i % 360)
        ws.append([
            f"TR-{i:04d}", f"EXT-{i:04d}", f"FAIXA DEMO {1 + i % 5}", "CBUQ",
            "USO GERAL", "ARENA" if i % 2 else "PAVIDEZ", f"CT-DEMO-{1 + i % 4:02d}",
            f"Obra demonstrativa {1 + i % 8}", f"Trecho fictício {1 + i % 20}",
            f"Usina Demo {1 + i % 4}", "GRAVIMÉTRICA", f"Pedreira Demo {1 + i % 3}",
            f"Fornecedor Demo {1 + i % 3}", ["CAP 30/45", "CAP 50/70", "AMP 60/85"][i % 3],
            statuses[i % len(statuses)], "Equipe de Qualidade", approved.isoformat(),
            (approved + timedelta(days=730)).isoformat(), f"SELO-{i:04d}", "", "Registro exclusivamente fictício.",
        ])
    for column in ws.columns:
        ws.column_dimensions[column[0].column_letter].width = min(34, max(13, max(len(str(c.value or "")) for c in column) + 2))
    wb.save(target)


def _create_nc_inventory() -> None:
    target = DATA_DIR / "quality_general" / "controle_nao_conformidades.xlsx"
    target.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "NC"
    headers = [
        "Tipo (RACP/RNC)", "nº Emissão", "Situação Final (Status)", "Assunto", "Contratada",
        "Descrição Detalhada", "Data de Emissão", "Prazo de Resposta", "Valor para Retenção",
        "Valor Real Retido", "Retido", "Disciplina", "Classificação", "Contrato", "Lote",
        "Trecho", "Disposição Final", "Status Implementação", "Eficácia", "Medição Retida",
        "Solicitante", "Gestor da Obra",
    ]
    ws.append(headers)
    statuses = ["EM ABERTO", "EM TRATAMENTO", "A ENCERRAR", "ENCERRADO", "ENCERRADO"]
    disciplines = ["Pavimentação", "Drenagem", "Sinalização", "Meio Ambiente", "Laboratório"]
    today = date.today()
    for i in range(1, RECORDS_PER_AREA + 1):
        issued = today - timedelta(days=i * 2)
        value = round(1500 + (i * 731.37) % 78000, 2)
        status = statuses[i % len(statuses)]
        ws.append([
            "RNC", f"RNC-DEMO-{i:04d}", status, f"Ocorrência fictícia {1 + i % 12}",
            "ARENA" if i % 2 else "PAVIDEZ", "Descrição criada exclusivamente para demonstração da plataforma.",
            issued.isoformat(), (issued + timedelta(days=10)).isoformat(), value,
            value if status == "ENCERRADO" else 0, "SIM" if i % 3 == 0 else "NÃO",
            disciplines[i % len(disciplines)], ["BAIXA", "MÉDIA", "ALTA"][i % 3],
            f"CT-DEMO-{1 + i % 4:02d}", f"Lote {1 + i % 4}", f"km {100 + i % 80}+000",
            "Correção demonstrativa", "CONCLUÍDA" if status == "ENCERRADO" else "EM ANDAMENTO",
            "EFICAZ" if status == "ENCERRADO" else "PENDENTE", f"M{1 + i % 15}",
            "Fiscal Demo", "Gestor Demo",
        ])
    for column in ws.columns:
        ws.column_dimensions[column[0].column_letter].width = min(38, max(13, max(len(str(c.value or "")) for c in column) + 2))
    wb.save(target)


def ensure_demo_data(force: bool = False) -> dict[str, int | str]:
    """Cria 200 registros por área apenas no banco isolado da V2."""
    saved = row("SELECT value FROM settings WHERE key='demo_seed_version'")
    if saved and saved.get("value") == SEED_VERSION and not force:
        return {"status": "ready", "records_per_area": RECORDS_PER_AREA}

    rng = random.Random(20261019)
    documents = _create_demo_documents()
    _create_trace_inventory()
    _create_nc_inventory()
    now = datetime.now().isoformat(timespec="seconds")
    today = date.today()
    password_hash = hash_password(DEMO_PASSWORD)

    with transaction() as con:
        for table in (
            "email_notification_outbox", "email_notification_preferences", "change_history", "audit_log",
            "password_reset_tokens", "sessions", "pending_justifications", "matches", "certificate_samples",
            "certificate_files", "certificates", "kit_documents", "kit_rows", "bv_documents",
            "quality_snapshots", "quality_rows", "measurements", "auto_import_events", "sync_log", "users",
        ):
            con.execute(f"DELETE FROM {table}")
        con.execute("UPDATE sources SET path='',enabled=0,last_status='DEMO',last_error='',last_sync=?", (now,))

        users = []
        for i in range(1, RECORDS_PER_AREA + 1):
            admin = i == 1
            users.append((
                "Administrador Demo" if admin else f"Usuário Demonstração {i:03d}",
                DEMO_EMAIL if admin else f"usuario{i:03d}@qualimatch.local", password_hash,
                "ADMIN" if admin else "USER", "APPROVED" if i % 8 else "PENDING",
                1, 1, 1, 1, 1, 1, "ADMIN" if admin else ("EDITOR" if i % 3 else "VIEWER"),
                now, now if i % 8 else None, now,
            ))
        con.executemany(
            """INSERT INTO users(name,email,password_hash,role,status,access_bv,access_contractor,
               access_quality_general,access_quality_nc,access_arena,access_pavidez,permission_level,
               created_at,approved_at,password_changed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", users,
        )
        admin_id = int(con.execute("SELECT id FROM users WHERE email=?", (DEMO_EMAIL,)).fetchone()["id"])

        for i in range(1, RECORDS_PER_AREA + 1):
            contractor = "ARENA" if i % 2 else "PAVIDEZ"
            source_row = i
            service_date = today - timedelta(days=(RECORDS_PER_AREA - i) % 180)
            road = ["BR-101", "BR-116", "BR-277", "PR-445"][i % 4]
            kmi = (80 + i % 120) * 1000 + (i * 37) % 1000
            kmf = kmi + 600 + i % 900
            measurement = f"M{1 + (i - 1) % 15}"
            line = f"LIN-DEMO-{i:04d}"
            financial_status = ["APROVADO", "APROVADO", "APROVADO", "PENDENTE", "REPROVADO"][i % 5]
            total_service = round(25000 + (i * 9187.33) % 420000, 2)
            measurement_raw = {"origem": "DEMO", "medicao": measurement, "observacao": "Registro fictício"}
            con.execute(
                """INSERT INTO measurements(contractor,source_row,line_measurement,ref_measurement,team,inspector,date,
                   road,direction,kmi,kmf,lane,extension_m,width_m,thickness_m,scope,mass_type,area_m2,
                   volume_mass_m3,quantity_t,raw_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (contractor, source_row, line, measurement, f"Equipe {1+i%6}", "Fiscal Demo", service_date.isoformat(),
                 road, "NORTE" if i % 2 else "SUL", kmi, kmf, "FAIXA 1", kmf-kmi, 3.6, 0.05,
                 "RESTAURAÇÃO", "CBUQ", round((kmf-kmi)*3.6, 2), round((kmf-kmi)*3.6*0.05, 2),
                 round((kmf-kmi)*3.6*0.05*2.4, 2), _json(measurement_raw)),
            )
            measurement_id = int(con.execute(
                "SELECT id FROM measurements WHERE contractor=? AND source_row=?", (contractor, source_row)
            ).fetchone()["id"])
            quality_raw = {
                "origem": "DEMO", "MEDIÇÃO": measurement, "CERTIFICADO VV": f"{1000+i}",
                "STATUS": financial_status,
            }
            con.execute(
                """INSERT INTO quality_rows(contractor,source_row,visible_excel,line_measurement,ref_measurement,date,
                   road,direction,kmi,kmf,lane,trace_code,status_final,status_summary,extension_m,volume_mass_m3,
                   quantity_t,cap_project_t,total_service,proposed_retention,raw_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (contractor, source_row, 1, line, measurement, service_date.isoformat(), road,
                 "NORTE" if i % 2 else "SUL", kmi, kmf, "FAIXA 1", f"TR-{i:04d}", financial_status,
                 financial_status, kmf-kmi, 120+i, 280+i*1.7, 20+i/10, total_service,
                 round(total_service*0.1, 2) if financial_status == "REPROVADO" else 0, _json(quality_raw)),
            )

            approved = i % 10 < 7
            has_counterproof = i % 10 == 8
            routine_result = "APROVADO" if approved else "REPROVADO"
            counter_result = "REPROVADO" if has_counterproof else ""
            cert_path = str(documents[i-1])
            raw_cert = {
                "origem": "DEMO", "parse_status": "CARREGADO", "service_dates": [service_date.isoformat()],
                "phase_summaries": {}, "observacao": "Certificado inteiramente fictício",
            }
            con.execute(
                """INSERT INTO certificates(identity_key,contractor,number,file_path,file_hash,service_date,
                   extraction_date,road,kmi,kmf,trace_approved,routine_result,counterproof_result,
                   has_counterproof,parsed_at,raw_json,is_active) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                (f"demo-{i:04d}", contractor, str(1000+i), cert_path, f"demo-hash-{i:04d}",
                 service_date.isoformat(), (service_date+timedelta(days=2)).isoformat(), road, kmi, kmf,
                 "SIM", routine_result, counter_result, 1 if has_counterproof else 0, now, _json(raw_cert)),
            )
            cert_id = int(con.execute("SELECT id FROM certificates WHERE identity_key=?", (f"demo-{i:04d}",)).fetchone()["id"])
            con.execute(
                """INSERT INTO certificate_files(contractor,certificate_id,file_path,file_name,mtime_ns,size,
                   file_hash,kind,status,parser_version,error,parsed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (contractor, cert_id, cert_path, f"BI330-DEMO-{1000+i}.pdf", i, documents[i-1].stat().st_size,
                 f"demo-hash-{i:04d}", "ROTINA", "CARREGADO", "demo-v2", "", now),
            )
            sample_vv = 5.0 + rng.uniform(-0.7, 0.7) if approved else 8.3 + rng.uniform(0, 1.2)
            for cp in range(1, 4):
                con.execute(
                    """INSERT INTO certificate_samples(certificate_id,phase,cp_number,application_date,counterproof,
                       direction,lane,station,position,thickness_exec_cm,thickness_project_cm,ratio_ab_pct,
                       rice_gmm,gmb,voids_pct) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (cert_id, "ROTINA", f"CP-{cp}", service_date.isoformat(), 0, "NORTE", "FAIXA 1",
                     kmi + cp*100, "EIXO", 5.0 + rng.uniform(-0.25, .25), 5.0,
                     102 + rng.uniform(-4, 6) if approved else 86 + rng.uniform(-3, 3), 2.45, 2.34,
                     round(sample_vv + rng.uniform(-.2, .2), 2)),
                )
            if has_counterproof:
                con.execute(
                    """INSERT INTO certificate_samples(certificate_id,phase,cp_number,application_date,counterproof,
                       direction,lane,station,position,thickness_exec_cm,thickness_project_cm,ratio_ab_pct,
                       rice_gmm,gmb,voids_pct) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (cert_id, "CONTRA_PROVA", "CP-1", service_date.isoformat(), 1, "NORTE", "FAIXA 1",
                     kmi+150, "EIXO", 4.3, 5.0, 84.0, 2.45, 2.20, 9.2),
                )
            con.execute(
                "INSERT INTO matches(measurement_id,certificate_id,score,reason,matched_at) VALUES(?,?,?,?,?)",
                (measurement_id, cert_id, 95, "Correspondência fictícia por data e rodovia", now),
            )

            delivery = "ENTREGUE" if i % 5 else "PENDENTE"
            kit_raw = {"origem": "DEMO", "ENTREGA": delivery, "medicao": measurement}
            con.execute(
                """INSERT INTO kit_rows(contractor,source_row,seq,service,application_date,mix_project,period,
                   road,kmi,kmf,receipt_date,delivery_status,status,status_1,status_2,status_3,status_4,status_5,
                   status_6,status_7,status_8,sin_retro,raw_json,is_active,manual_override,updated_at,updated_by)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (contractor, source_row, f"KIT-{i:04d}", "CBUQ", service_date.isoformat(), f"TR-{i:04d}",
                 "DIURNO", road, kmi, kmf, (service_date+timedelta(days=1)).isoformat() if delivery == "ENTREGUE" else None,
                 delivery, "OK" if delivery == "ENTREGUE" else "PENDENTE", "OK", "OK", "OK", "OK", "OK",
                 "OK", "OK", "OK", "NÃO", _json(kit_raw), 1, 0, now, admin_id),
            )
            kit_id = int(con.execute(
                "SELECT id FROM kit_rows WHERE contractor=? AND source_row=?", (contractor, source_row)
            ).fetchone()["id"])
            con.execute(
                """INSERT INTO kit_documents(contractor,kit_id,file_path,file_name,relative_path,folder,extension,
                   size,mtime_ns,seq_guess,synced_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (contractor, kit_id, cert_path, f"KIT-DEMO-{i:04d}.pdf", f"M{1+i%15}/KIT-DEMO-{i:04d}.pdf",
                 f"M{1+i%15}", ".pdf", documents[i-1].stat().st_size, i, f"KIT-{i:04d}", now),
            )
            con.execute(
                """INSERT INTO bv_documents(contractor,file_path,file_name,relative_path,folder,top_folder,
                   measurement_label,extension,size,mtime_ns,synced_at,is_active,manual_override)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (contractor, cert_path, f"BV-DEMO-{i:04d}.pdf", f"{measurement}/BV-DEMO-{i:04d}.pdf",
                 measurement, "CERTIFICADOS DEMO", measurement, ".pdf", documents[i-1].stat().st_size, i,
                 now, 1, 0),
            )
            con.execute(
                "INSERT INTO sync_log(contractor,kind,status,message,records,source_path,created_at) VALUES(?,?,?,?,?,?,?)",
                (contractor, "demo", "OK" if i % 9 else "AVISO", f"Evento fictício de sincronização {i}", 1,
                 f"/dados-ficticios/fonte-{i:03d}", now),
            )
            con.execute(
                """INSERT INTO auto_import_events(contractor,portal,kind,file_path,file_name,signature,event_type,
                   status,message,detected_at,processed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (contractor, "BV" if i % 2 else "CONTRACTOR", "certificados", cert_path,
                 f"DOCUMENTO-DEMO-{i:04d}.pdf", f"demo-signature-{i:04d}", "NOVO", "CARREGADO",
                 "Arquivo fictício processado", now, now),
            )
            con.execute(
                """INSERT INTO pending_justifications(pending_key,contractor,reason,item_json,justified_by,
                   justified_at,active) VALUES(?,?,?,?,?,?,?)""",
                (f"demo-pending-{i:04d}", contractor, "Justificativa demonstrativa", _json({"measurement": measurement}),
                 admin_id, now, 1 if i % 4 else 0),
            )
            con.execute(
                "INSERT INTO audit_log(user_id,action,entity_type,entity_id,details_json,ip_address,created_at) VALUES(?,?,?,?,?,?,?)",
                (admin_id, "DEMO_EVENT", "certificate", str(cert_id), _json({"fictitious": True}), "127.0.0.1", now),
            )
            con.execute(
                """INSERT INTO change_history(user_id,action,entity_type,entity_id,before_json,after_json,created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (admin_id, "UPDATE_DEMO", "kit", str(kit_id), "{}", _json({"status": delivery}), now),
            )
            con.execute(
                """INSERT INTO quality_snapshots(contractor,synced_at,source_path,source_mtime,total_service,
                   total_service_visible_sum,total_difference,total_source_cell,extension_m,volume_mass_m3,
                   quantity_t,cap_project_t,proposed_retention,visible_records,total_records,warning,summary_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (contractor, now, f"/dados-ficticios/qualidade-{i:03d}.xlsx", now, total_service,
                 total_service, 0, "DEMO", kmf-kmi, 120+i, 280+i, 20+i/10, 0, 1, 1, "", _json({"demo": True})),
            )

        con.execute(
            "INSERT INTO settings(key,value) VALUES('demo_seed_version',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (SEED_VERSION,),
        )
        con.execute(
            "INSERT INTO settings(key,value) VALUES('auto_monitor_enabled','0') ON CONFLICT(key) DO UPDATE SET value='0'"
        )
    return {"status": "created", "records_per_area": RECORDS_PER_AREA, "admin": DEMO_EMAIL}
