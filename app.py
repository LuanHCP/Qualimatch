from __future__ import annotations
import asyncio, json, os, time, tempfile, re, unicodedata, zipfile, mimetypes, math
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime, date, timedelta
from uuid import uuid4
from collections import Counter, defaultdict

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query, Request, Response, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from openpyxl import load_workbook

from qualimatch.config import FRONTEND_DIR, DATA_DIR, CERT_DIR, BACKUP_DIR, DB_PATH, AUTO_SYNC_SECONDS, DEMO_MODE
from qualimatch.database import init_db, row, rows, transaction, connect, log_sync, automatic_backup, archive_old_sync_logs, backend_name, restore_backup
from qualimatch.local_sync import (
    get_sources, update_source, sync_source, sync_all, auto_sync_loop, auto_monitor_loop, auto_quality_loop,
    monitor_config, update_monitor_config, monitor_events, count_monitor_events, monitor_once,
    auto_fill_quality_for_certificate_paths, auto_fill_quality_for_recent_certificates,
    _upsert_certificate, _record_certificate_file, replace_certificate_record, DuplicateCertificateError,
    deactivate_certificate, discover_kits_source, discover_bv_source, remap_bv_certificate_paths, reprocess_no_result_certificates,
    ZIP_ENTRY_SEP,
)
from qualimatch.pdf_reader import parse_pdf
from qualimatch.normalizers import station as normalize_station, norm_road, to_date
from qualimatch.tools_pdf_quality import analyze_certificates, contractor_hint_from_name
from qualimatch.quality_excel_writer import generate_excel_export, write_excel_to_main_sources
from qualimatch.matching import recalculate_matches
from qualimatch.general_quality import (
    _qg_norm, _qg_path, _qg_set_path, _qg_source_info, _qg_save_upload,
    _qg_load_traces, _qg_trace_filter, _qg_trace_summary, _qg_trace_payload,
    _qg_load_nc, _qg_nc_summary, _qg_nc_payload,
    _QG_TRACE_DEFAULT, _QG_TRACE_SETTING, _QG_NC_DEFAULT, _QG_NC_SETTING,
)
from qualimatch.queries import dashboard, pending_days, pending_measurements, contractor_pending_measurements, list_measurements, count_measurements, list_certificates, certificate_filter_options, certificate_detail, certificate_document, sync_logs, count_sync_logs, diagnostics, list_kits, count_kits, kit_summary, kit_filter_options, kit_detail, list_kit_documents, kit_document, list_bv_documents, count_bv_documents, bv_document, bv_document_groups, bv_general_report, archive_bv_document, archive_duplicate_bv_documents, remove_duplicate_certificate_files, measurement_cycle_bounds, measurement_cycle_options
from qualimatch.auth import (
    admin_exists, create_registration, authenticate, create_session, user_from_session, revoke_session,
    list_users, list_admin_emails, set_user_status, create_password_reset, consume_password_reset,
    audit, list_audit, has_portal_access, set_user_permissions, allowed_contractors, has_contractor_access, can_edit,
)
from qualimatch.emailer import registration_email, user_status_email, password_reset_email, email_configured
from qualimatch.email_notifications import preferences as email_preferences, save_preferences as save_email_preferences, retry_failed as retry_failed_email_notifications, email_notification_loop
from qualimatch.management import review_queue, notification_summary, measurement_cycle_dashboard, global_search, traceability, list_changes, count_changes, undo_change, system_health, record_change, bv_pending_workflow, bv_certificate_pending, bv_kpi_dashboard
from qualimatch.reporting import measurement_cycle_report
from qualimatch.bv_general_report_pdf import build_bv_missing_report_pdf
from qualimatch.uploads import UploadTooLarge, read_upload_limited, save_upload_limited
from qualimatch.version import APP_VERSION
from qualimatch.source_inspector import inspect_workbook
from qualimatch.runtime_control import (
    JobBusyError, JobCancelled, job as runtime_job, snapshot as runtime_snapshot,
    update as runtime_update, check_cancelled, request_cancel, set_paused,
)
from qualimatch.traces_launcher import launch_traces_project, shutdown_traces_project
from qualimatch.nc_launcher import launch_nc_project, shutdown_nc_project
from qualimatch.demo_seed import ensure_demo_data

_tasks=[]


def _local_file_path(value: str) -> Path:
    raw=os.path.abspath(str(value))
    if os.name=='nt' and not raw.startswith('\\\\?\\'):
        raw='\\\\?\\UNC\\'+raw[2:] if raw.startswith('\\\\') else '\\\\?\\'+raw
    return Path(raw)


async def maintenance_loop():
    """Backup diário e compactação dos logs sem pesar durante o uso normal."""
    await asyncio.sleep(20)
    while True:
        try:
            if not runtime_snapshot().get('active'):
                with runtime_job('maintenance','Manutenção diária',2):
                    today=date.today().isoformat()
                    saved=row("SELECT value FROM settings WHERE key='maintenance_last_backup_date'") or {}
                    runtime_update(current='Compactando histórico antigo...')
                    await asyncio.to_thread(archive_old_sync_logs,10000)
                    runtime_update(processed=1,current='Verificando backup diário...')
                    if str(saved.get('value') or '') != today:
                        name=await asyncio.to_thread(automatic_backup,'diario',0)
                        with transaction() as con:
                            con.execute("INSERT INTO settings(key,value) VALUES('maintenance_last_backup_date',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(today,))
                        log_sync(None,'backup_diario','OK',f'Backup diário criado: {name}',1,str(BACKUP_DIR/name))
                    runtime_update(processed=2)
        except JobBusyError:
            pass
        except Exception as exc:
            log_sync(None,'manutencao','ERRO',f'Manutenção automática: {type(exc).__name__}: {exc}',0,'')
        await asyncio.sleep(3600)


def _page_args(page: int, page_size: int) -> tuple[int, int, int]:
    current = max(1, int(page or 1))
    size = int(page_size or 25)
    if size not in {25, 50, 100}:
        size = 25
    return current, size, (current - 1) * size


def _page_response(items, total: int, page: int, page_size: int, **extra):
    pages = max(1, (int(total) + page_size - 1) // page_size)
    current = min(max(1, page), pages)
    return {"items": items, "total": int(total), "page": current, "page_size": page_size, "pages": pages, **extra}


def _page_offset_for_total(page: int, page_size: int, total: int) -> tuple[int, int]:
    pages = max(1, (int(total) + page_size - 1) // page_size)
    current = min(max(1, page), pages)
    return current, (current - 1) * page_size


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _tasks
    init_db()
    if DEMO_MODE:
        await asyncio.to_thread(ensure_demo_data)
        _tasks=[]
    else:
        _tasks=[
            asyncio.create_task(auto_sync_loop(AUTO_SYNC_SECONDS), name='qualimatch-periodic-sync'),
            asyncio.create_task(auto_monitor_loop(15), name='qualimatch-sharepoint-monitor'),
            asyncio.create_task(auto_quality_loop(3), name='qualimatch-bd-quali-worker'),
            asyncio.create_task(email_notification_loop(), name='qualimatch-email-notifications'),
            asyncio.create_task(maintenance_loop(), name='qualimatch-daily-maintenance'),
        ]
    yield
    for task in _tasks:
        task.cancel()
    for task in _tasks:
        try: await task
        except asyncio.CancelledError: pass
    await asyncio.to_thread(shutdown_traces_project)
    await asyncio.to_thread(shutdown_nc_project)

app=FastAPI(title='QualiMatch',version=APP_VERSION,lifespan=lifespan)
app.mount('/static',StaticFiles(directory=str(FRONTEND_DIR/'static')),name='static')

class SourceUpdate(BaseModel):
    path:str
    worksheet:str=''

class AutoMonitorPayload(BaseModel):
    enabled: bool = True
    bv: bool = True
    contractor: bool = True
    auto_quality: bool = True
    seconds: int = 15

class RuntimePausePayload(BaseModel):
    paused: bool

class ShutdownPayload(BaseModel):
    confirmation: str

class LoginPayload(BaseModel):
    email: str
    password: str

class EmailNotificationPayload(BaseModel):
    bv_new_certificates: bool

class RegisterPayload(BaseModel):
    name: str
    email: str
    password: str
    confirm_password: str

class ResetRequestPayload(BaseModel):
    email: str

class ResetConfirmPayload(BaseModel):
    token: str
    password: str
    confirm_password: str

class UserPermissionsPayload(BaseModel):
    bv: bool = False
    quality_general: bool = False
    quality_nc: bool = False
    contractor: bool = False
    arena: bool = False
    pavidez: bool = False
    admin: bool = False
    permission_level: str = 'VIEWER'

class CertificatePhaseEditPayload(BaseModel):
    overall_status: str = ''
    status_vv: str = ''
    status_thickness: str = ''
    k: float | None = None
    vv_mean_pct: float | None = None
    vv_std_pct: float | None = None
    vv_xmin_pct: float | None = None
    vv_xmax_pct: float | None = None
    ratio_mean_pct: float | None = None
    ratio_std_pct: float | None = None
    ratio_xmin_pct: float | None = None
    ratio_xmax_pct: float | None = None

class CertificateSampleEditPayload(BaseModel):
    application_date: str | None = None
    direction: str = ''
    lane: str = ''
    station: int | None = None
    position: str = ''
    thickness_exec_cm: float | None = None
    thickness_project_cm: float | None = None
    ratio_ab_pct: float | None = None
    rice_gmm: float | None = None
    gmb: float | None = None
    voids_pct: float | None = None
    recalculate_summary: bool = True


class RestorePayload(BaseModel):
    confirmation: str = ''

class KitEditPayload(BaseModel):
    seq: str = ''
    service: str = ''
    application_date: str | None = None
    mix_project: str = ''
    period: str = ''
    road: str = ''
    kmi: str | int | float | None = None
    kmf: str | int | float | None = None
    receipt_date: str | None = None
    status: str = ''
    status_1: str = ''
    status_2: str = ''
    status_3: str = ''
    status_4: str = ''
    status_5: str = ''
    status_6: str = ''
    status_7: str = ''
    status_8: str = ''
    sin_retro: str = ''

class PendingJustificationPayload(BaseModel):
    pending_key: str
    contractor: str
    reason: str
    item: dict = {}

class BvReportOverridePayload(BaseModel):
    contractor: str = 'ALL'
    measurement: str
    counts: dict[str, int]
    reason: str = ''

SESSION_COOKIE = "qm_session"
SESSION_MAX_AGE = 12 * 60 * 60
PUBLIC_API = {
    "/api/health", "/api/auth/setup-status", "/api/auth/login", "/api/auth/register",
    "/api/auth/password-reset/request", "/api/auth/password-reset/confirm",
}
_LOGIN_FAILURES: dict[str, list[float]] = {}


def _client_ip(request: Request) -> str:
    trust_proxy = os.getenv("TRUST_PROXY_HEADERS", "").strip().lower() in {"1", "true", "yes", "sim"}
    if trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return request.client.host if request.client else ""


def _request_base_url(request: Request) -> str:
    configured = os.getenv("APP_BASE_URL", "").strip()
    return configured or str(request.base_url).rstrip("/")


def _require_admin(request: Request) -> dict:
    user = getattr(request.state, "user", None)
    if not user or str(user.get("role") or "").upper() != "ADMIN":
        raise HTTPException(403, "Apenas administradores podem realizar esta ação.")
    return user


def _require_editor(request: Request) -> dict:
    user = getattr(request.state, "user", None)
    if not can_edit(user):
        raise HTTPException(403, "Seu perfil é somente leitura. Solicite nível Editor ao administrador.")
    return user


def _public_user(user: dict) -> dict:
    admin = str(user.get("role") or "").upper() == "ADMIN"
    return {
        "id": user.get("id"), "name": user.get("name"), "email": user.get("email"),
        "role": user.get("role"), "status": user.get("status"), "permission_level": "ADMIN" if admin else str(user.get("permission_level") or "VIEWER").upper(),
        "access_bv": True if admin else bool(int(user.get("access_bv") or 0)),
        "access_quality_general": True if admin else bool(int(user.get("access_quality_general") or 0)),
        "access_quality_nc": True if admin else bool(int(user.get("access_quality_nc") or 0)),
        "access_contractor": True if admin else bool(int(user.get("access_contractor") or 0)),
        "access_arena": True if admin else bool(int(user.get("access_arena") or 0)),
        "access_pavidez": True if admin else bool(int(user.get("access_pavidez") or 0)),
        "contractors": ["ARENA", "PAVIDEZ"] if admin else allowed_contractors(user),
        "access_admin": admin,
    }


def _require_portal(request: Request, portal: str) -> dict:
    user = getattr(request.state, "user", None)
    if not has_portal_access(user, portal):
        raise HTTPException(403, f"Seu usuário não possui acesso ao ambiente {portal}.")
    return user


def _contractor_for_user(request: Request, contractor: str) -> str:
    """Resolve ALL para o escopo permitido e bloqueia acesso cruzado Arena/Pavidez."""
    user = _require_portal(request, "CONTRACTOR")
    requested = (contractor or "ALL").upper().strip()
    if requested not in {"ALL", "ARENA", "PAVIDEZ"}:
        raise HTTPException(400, "Contratada inválida")
    allowed = allowed_contractors(user)
    if not allowed:
        raise HTTPException(403, "Nenhuma contratada foi liberada para seu usuário.")
    if requested == "ALL":
        return "ALL" if len(allowed) > 1 else allowed[0]
    if requested not in allowed:
        raise HTTPException(403, f"Seu usuário não possui acesso aos dados da {requested}.")
    return requested


def _login_allowed(ip: str) -> bool:
    now = time.time()
    attempts = [x for x in _LOGIN_FAILURES.get(ip, []) if now - x < 600]
    _LOGIN_FAILURES[ip] = attempts
    return len(attempts) < 5


def _login_failed(ip: str) -> None:
    _LOGIN_FAILURES.setdefault(ip, []).append(time.time())


def _login_success(ip: str) -> None:
    _LOGIN_FAILURES.pop(ip, None)


@app.middleware("http")
async def auth_guard(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and path not in PUBLIC_API:
        user = await asyncio.to_thread(user_from_session, request.cookies.get(SESSION_COOKIE))
        if not user:
            return JSONResponse(status_code=401, content={"detail": "Sessão expirada ou autenticação necessária."})
        request.state.user = user
        # Segurança por ambiente: esconder o card no navegador não é suficiente.
        # Rotas técnicas da BV também exigem a permissão BV no backend.
        bv_prefixes = (
            "/api/dashboard", "/api/pending", "/api/measurements",
            "/api/certificates", "/api/certificate-files",
        )
        if path.startswith(bv_prefixes) and not has_portal_access(user, "BV"):
            return JSONResponse(status_code=403, content={"detail": "Acesso ao ambiente BV não liberado para este usuário."})
        if path.startswith("/api/contractor/") and not has_portal_access(user, "CONTRACTOR"):
            return JSONResponse(status_code=403, content={"detail": "Acesso ao ambiente Contratada não liberado para este usuário."})
        # Checagem grosseira: basta ter Traços OU Não conformidades para passar
        # daqui. A permissão específica de cada rota é conferida por
        # _require_portal dentro do handler (TRACES/QUALITY vs NC).
        if path.startswith("/api/general-quality/") and not (has_portal_access(user, "QUALITY") or has_portal_access(user, "NC")):
            return JSONResponse(status_code=403, content={"detail": "Acesso ao ambiente Qualidade Geral não liberado para este usuário."})
    response = await call_next(request)
    # O QualiMatch costuma ser atualizado mantendo o mesmo endereço (localhost/rede).
    # Evita que o navegador misture HTML novo com CSS/JS de uma versão anterior.
    if path == "/" or path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


def _safe_pdf_name(name: str | None) -> str:
    base = Path(name or 'certificado.pdf').name
    return base if base.lower().endswith('.pdf') else base + '.pdf'


def _automatic_backup(action: str, cert_id: int) -> str:
    return automatic_backup(action, cert_id)


# ---------------------------------------------------------------------------
# Qualidade Geral (Traços + Não Conformidades): a lógica de leitura das
# planilhas e de resumo/filtro mora em qualimatch/general_quality.py — as
# rotas abaixo só validam permissão e delegam, no mesmo padrão do resto
# deste arquivo.
# ---------------------------------------------------------------------------

@app.post("/api/traces-project/launch")
async def traces_project_launch(request: Request):
    user = _require_portal(request, "QUALITY")
    try:
        result = await asyncio.to_thread(
            launch_traces_project, user_email=str(user.get("email") or ""),
            user_name=str(user.get("name") or ""),
            is_admin=str(user.get("role") or "").upper() == "ADMIN",
            permission_level=str(user.get("permission_level") or "VIEWER"),
        )
    except (OSError, RuntimeError) as exc:
        raise HTTPException(503, str(exc)) from exc
    if not result.get("ok"):
        raise HTTPException(504, result.get("message") or "O Controle de Traços não iniciou a tempo.")
    if not result.get("sso"):
        raise HTTPException(503, "Não foi possível validar o acesso automático ao Controle de Traços.")
    return result

@app.post("/api/nc-project/launch")
async def nc_project_launch(request: Request):
    user = _require_portal(request, "NC")
    try:
        result = await asyncio.to_thread(
            launch_nc_project, user_email=str(user.get("email") or ""),
            user_name=str(user.get("name") or ""),
            is_admin=str(user.get("role") or "").upper() == "ADMIN",
            permission_level=str(user.get("permission_level") or "VIEWER"),
        )
        if not result.get("sso"):
            raise HTTPException(503, "Não foi possível validar o acesso automático ao Sistema de NC.")
        return result
    except (OSError, RuntimeError) as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post("/api/embedded-projects/{project}/release")
async def embedded_project_release(project: str, request: Request):
    """Libera memória do módulo externo ao trocar/fechar o ambiente."""
    project = project.strip().lower()
    if project == 'traces':
        _require_portal(request, 'QUALITY')
        await asyncio.to_thread(shutdown_traces_project)
    elif project == 'nc':
        _require_portal(request, 'NC')
        await asyncio.to_thread(shutdown_nc_project)
    else:
        raise HTTPException(404, 'Módulo externo desconhecido.')
    return {'ok': True, 'project': project}

@app.get("/api/general-quality/overview")
def general_quality_overview(request: Request, contractor: str="ALL", trace_type: str="ALL", search: str=""):
    _require_portal(request, "QUALITY")
    return _qg_trace_payload(contractor=contractor, trace_type=trace_type, search=search, limit=1000)


@app.get("/api/general-quality/approved")
def general_quality_approved(request: Request, contractor: str="ALL", trace_type: str="ALL", plant: str="ALL", binder: str="ALL", search: str=""):
    _require_portal(request, "QUALITY")
    data = _qg_trace_payload(contractor=contractor, trace_type=trace_type, plant=plant, binder=binder, search=search, approved_only=True, limit=3000)
    all_approved = _qg_trace_filter(_qg_load_traces(), trace_type=trace_type, plant=plant, binder=binder, search=search, approved_only=True)
    counts = Counter(x.get("contractor") or "Sem contratada" for x in all_approved)
    data["approved_contractors"] = [{"contractor": k, "count": v} for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], _qg_norm(kv[0])))]
    return data


@app.get("/api/general-quality/traces")
def general_quality_traces(request: Request, contractor: str="ALL", trace_type: str="ALL", status: str="ALL", plant: str="ALL", binder: str="ALL", search: str=""):
    _require_portal(request, "QUALITY")
    return _qg_trace_payload(contractor=contractor, trace_type=trace_type, status=status, plant=plant, binder=binder, search=search, limit=5000)


@app.put("/api/general-quality/source")
def general_quality_source(payload: SourceUpdate, request: Request):
    _require_admin(request)
    try:
        _qg_set_path(_QG_TRACE_SETTING, payload.path, _QG_TRACE_DEFAULT)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True, "source": _qg_source_info(_qg_path(_QG_TRACE_SETTING, _QG_TRACE_DEFAULT), _QG_TRACE_DEFAULT)}


@app.post("/api/general-quality/source/upload")
async def general_quality_source_upload(request: Request, file: UploadFile=File(...)):
    _require_admin(request)
    try:
        content = await read_upload_limited(file, 40 * 1024 * 1024)
    except UploadTooLarge as exc:
        raise HTTPException(413, str(exc)) from exc
    _qg_save_upload(content, file.filename or "", _QG_TRACE_DEFAULT, _QG_TRACE_SETTING, 40)
    return {"ok": True, "source": _qg_source_info(_QG_TRACE_DEFAULT, _QG_TRACE_DEFAULT), "summary": _qg_trace_summary(_qg_load_traces(True))}


@app.get("/api/general-quality/nonconformities/overview")
def general_quality_nc_overview(request: Request, contractor: str="ALL", status: str="ALL", discipline: str="ALL", search: str=""):
    _require_portal(request, "NC")
    return _qg_nc_payload(contractor=contractor, status=status, discipline=discipline, search=search, limit=1000)


@app.get("/api/general-quality/nonconformities")
def general_quality_nc_list(request: Request, contractor: str="ALL", status: str="ALL", subject: str="ALL", discipline: str="ALL", classification: str="ALL", retention_status: str="ALL", search: str=""):
    _require_portal(request, "NC")
    return _qg_nc_payload(contractor=contractor, status=status, subject=subject, discipline=discipline, classification=classification, retention_status=retention_status, search=search, limit=5000)


@app.put("/api/general-quality/nonconformities/source")
def general_quality_nc_source(payload: SourceUpdate, request: Request):
    _require_admin(request)
    try:
        _qg_set_path(_QG_NC_SETTING, payload.path, _QG_NC_DEFAULT)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True, "source": _qg_source_info(_qg_path(_QG_NC_SETTING, _QG_NC_DEFAULT), _QG_NC_DEFAULT)}


@app.post("/api/general-quality/nonconformities/source/upload")
async def general_quality_nc_source_upload(request: Request, file: UploadFile=File(...)):
    _require_admin(request)
    try:
        content = await read_upload_limited(file, 60 * 1024 * 1024)
    except UploadTooLarge as exc:
        raise HTTPException(413, str(exc)) from exc
    _qg_save_upload(content, file.filename or "", _QG_NC_DEFAULT, _QG_NC_SETTING, 60)
    return {"ok": True, "source": _qg_source_info(_QG_NC_DEFAULT, _QG_NC_DEFAULT), "summary": _qg_nc_summary(_qg_load_nc(True))}


@app.get('/', response_class=HTMLResponse)
def index():
    html = (FRONTEND_DIR / 'index.html').read_text(encoding='utf-8')
    return HTMLResponse(html.replace('__QUALIMATCH_VERSION__', APP_VERSION))
@app.get('/api/health')
def health(): return {'ok':True,'app':'QualiMatch','version':APP_VERSION,'database':backend_name(),'auth':True,'portals':True,'kits':True,'tools':True,'excel_safe_copy':True,'excel_direct_write':True,'contractor_isolation':True,'management_center':True,'global_search':True,'undo':True,'cycle_dashboard':True,'sharepoint_auto_monitor':True,'auto_bdquali_fill':True}

@app.get('/api/auth/setup-status')
def auth_setup_status():
    return {'admin_configured': admin_exists(), 'email_configured': email_configured(), 'database': backend_name()}

@app.post('/api/auth/register', status_code=202)
def auth_register(payload:RegisterPayload, request:Request, background_tasks:BackgroundTasks):
    if payload.password != payload.confirm_password:
        raise HTTPException(400,'As senhas não conferem.')
    try:
        user=create_registration(payload.name,payload.email,payload.password)
    except RuntimeError as e:
        raise HTTPException(503,str(e))
    except ValueError as e:
        raise HTTPException(400,str(e))
    audit(user['id'],'REGISTER_REQUEST','user',user['id'],{'email':user['email']},_client_ip(request))
    admins=list_admin_emails()
    if admins:
        background_tasks.add_task(registration_email,admins,user,_request_base_url(request))
    return {'ok':True,'status':'PENDING','message':'Solicitação enviada. Aguarde a aprovação do administrador.'}

@app.post('/api/auth/login')
def auth_login(payload:LoginPayload, request:Request, response:Response):
    ip=_client_ip(request)
    if not _login_allowed(ip):
        raise HTTPException(429,'Muitas tentativas de login. Tente novamente em alguns minutos.')
    user,error=authenticate(payload.email,payload.password)
    if not user:
        _login_failed(ip)
        audit(None,'LOGIN_FAILED','user','',{'email':payload.email},ip)
        raise HTTPException(401,error or 'E-mail ou senha inválidos.')
    _login_success(ip)
    token,expires=create_session(user['id'],ip,request.headers.get('user-agent',''))
    response.set_cookie(
        SESSION_COOKIE,token,max_age=SESSION_MAX_AGE,httponly=True,samesite='lax',
        secure=os.getenv('SESSION_COOKIE_SECURE','').strip().lower() in {'1','true','yes','sim'},path='/'
    )
    audit(user['id'],'LOGIN','session','',{},ip)
    return {'ok':True,'user':_public_user(user),'expires_at':expires}

@app.post('/api/auth/logout')
def auth_logout(request:Request,response:Response):
    user=getattr(request.state,'user',{}) or {}
    revoke_session(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE,path='/')
    audit(user.get('id'),'LOGOUT','session','',{},_client_ip(request))
    return {'ok':True}

@app.get('/api/auth/me')
def auth_me(request:Request):
    u=request.state.user
    return _public_user(u)

@app.get('/api/auth/email-notifications')
def get_email_notifications(request: Request):
    return email_preferences(request.state.user)

@app.put('/api/auth/email-notifications')
def update_email_notifications(payload: EmailNotificationPayload, request: Request):
    try:
        result = save_email_preferences(request.state.user, payload.bv_new_certificates)
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    audit(request.state.user['id'], 'EMAIL_NOTIFICATIONS_UPDATE', 'user', request.state.user['id'],
          {'bv_new_certificates': payload.bv_new_certificates}, _client_ip(request))
    return result

@app.post('/api/auth/email-notifications/retry')
def retry_email_notifications(request: Request):
    try:
        result = retry_failed_email_notifications(request.state.user)
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    audit(request.state.user['id'], 'EMAIL_NOTIFICATIONS_RETRY', 'user', request.state.user['id'],
          {'retried': result['retried']}, _client_ip(request))
    return result

@app.post('/api/auth/password-reset/request')
def password_reset_request(payload:ResetRequestPayload, request:Request, background_tasks:BackgroundTasks):
    user,token=create_password_reset(payload.email)
    if user and token:
        background_tasks.add_task(password_reset_email,user,token,_request_base_url(request))
        audit(user['id'],'PASSWORD_RESET_REQUEST','user',user['id'],{},_client_ip(request))
    return {'ok':True,'message':'Se o e-mail estiver cadastrado e ativo, você receberá as instruções para redefinir a senha.'}

@app.post('/api/auth/password-reset/confirm')
def password_reset_confirm(payload:ResetConfirmPayload, request:Request):
    if payload.password != payload.confirm_password:
        raise HTTPException(400,'As senhas não conferem.')
    try:
        user=consume_password_reset(payload.token,payload.password)
    except ValueError as e:
        raise HTTPException(400,str(e))
    audit(user.get('id'),'PASSWORD_RESET_COMPLETE','user',user.get('id',''),{},_client_ip(request))
    return {'ok':True,'message':'Senha redefinida. Você já pode entrar com a nova senha.'}

@app.get('/api/admin/users')
def admin_users(request:Request):
    _require_admin(request)
    return list_users()

@app.post('/api/admin/users/{uid}/{action}')
def admin_user_action(uid:int,action:str,request:Request,background_tasks:BackgroundTasks):
    admin=_require_admin(request)
    action=action.upper()
    if action not in {'APPROVE','REJECT','BLOCK','REACTIVATE'}:
        raise HTTPException(400,'Ação inválida.')
    try:
        user=set_user_status(uid,action,admin['id'])
    except ValueError as e:
        raise HTTPException(400,str(e))
    audit(admin['id'],f'USER_{action}','user',uid,{'email':user.get('email')},_client_ip(request))
    if action in {'APPROVE','REJECT'}:
        background_tasks.add_task(user_status_email,user,action=='APPROVE',_request_base_url(request))
    return {'ok':True,'user':user}

@app.put('/api/admin/users/{uid}/permissions')
def admin_user_permissions(uid:int,payload:UserPermissionsPayload,request:Request):
    admin=_require_admin(request)
    try:
        user=set_user_permissions(uid,payload.bv,payload.contractor,payload.admin,admin['id'],access_arena=payload.arena,access_pavidez=payload.pavidez,access_quality_general=payload.quality_general,access_quality_nc=payload.quality_nc,permission_level=payload.permission_level)
    except ValueError as e:
        raise HTTPException(400,str(e))
    audit(admin['id'],'USER_PERMISSIONS','user',uid,{
        'bv':bool(payload.bv),'quality_general':bool(payload.quality_general),'quality_nc':bool(payload.quality_nc),'contractor':bool(payload.contractor),'arena':bool(payload.arena),'pavidez':bool(payload.pavidez),'admin':bool(payload.admin),'permission_level':payload.permission_level
    },_client_ip(request))
    return {'ok':True,'user':_public_user(user)}


@app.post('/api/admin/tools/pdf-quality/analyze')
async def admin_tool_pdf_quality_analyze(request:Request, files:list[UploadFile]=File(...), overrides_json:str=Form('')):
    user=_require_admin(request)
    if not files:
        raise HTTPException(400,'Selecione pelo menos um PDF.')
    if len(files)>30:
        raise HTTPException(400,'Envie no máximo 30 PDFs por análise.')
    parsed=[]; errors=[]
    with tempfile.TemporaryDirectory(prefix='qualimatch_tool_') as tmpdir:
        tmp=Path(tmpdir)
        for upload in files:
            name=_safe_pdf_name(upload.filename)
            if not name.lower().endswith('.pdf'):
                errors.append({'file_name':upload.filename or '', 'error':'Apenas PDF é aceito.'})
                continue
            target=tmp/f"{uuid4().hex}_{name}"
            try:
                await save_upload_limited(upload,target,30*1024*1024)
            except UploadTooLarge:
                errors.append({'file_name':name,'error':'PDF acima de 30 MB.'})
                continue
            try:
                cert=parse_pdf(target,contractor_hint_from_name(name))
                parsed.append((name,cert))
            except Exception as e:
                errors.append({'file_name':name,'error':str(e)})
    if not parsed:
        raise HTTPException(422,{'message':'Nenhum PDF pôde ser analisado.','errors':errors})
    try:
        raw_overrides=json.loads(overrides_json or '{}')
        overrides={str(k):int(v) for k,v in (raw_overrides or {}).items()}
    except Exception:
        raise HTTPException(400,'Revisões manuais inválidas.')
    result=analyze_certificates(parsed,overrides)
    result['errors']=errors
    audit(user.get('id'),'TOOL_PDF_BDQUALI_PREVIEW','tool','pdf-quality',{'pdfs':len(files),'parsed':len(parsed),'errors':len(errors)},_client_ip(request))
    return result


@app.post('/api/admin/tools/source-inspector')
async def admin_tool_source_inspector(request:Request, file:UploadFile=File(...)):
    user=_require_admin(request)
    name=Path(file.filename or 'planilha.xlsx').name
    if Path(name).suffix.lower() not in {'.xlsx','.xlsm'}:
        raise HTTPException(400,'Envie uma planilha .xlsx ou .xlsm.')
    with tempfile.TemporaryDirectory(prefix='qualimatch_inspector_') as tmpdir:
        target=Path(tmpdir)/name
        try:
            await save_upload_limited(file,target,60*1024*1024)
        except UploadTooLarge as exc:
            raise HTTPException(413,str(exc)) from exc
        try:
            result=await asyncio.to_thread(inspect_workbook,target)
        except Exception as exc:
            raise HTTPException(422,f'Não foi possível inspecionar a planilha: {exc}') from exc
    audit(user.get('id'),'TOOL_SOURCE_INSPECT','tool','source-inspector',{
        'file':name,'sheets':result['summary']['sheets'],'issues':result['summary']['issues']
    },_client_ip(request))
    return result


@app.post('/api/admin/tools/pdf-quality/generate-excel')
async def admin_tool_pdf_quality_generate_excel(request:Request, files:list[UploadFile]=File(...), overrides_json:str=Form('')):
    user=_require_admin(request)
    if not files:
        raise HTTPException(400,'Selecione pelo menos um PDF.')
    if len(files)>30:
        raise HTTPException(400,'Envie no máximo 30 PDFs por geração.')
    parsed=[]; errors=[]
    with tempfile.TemporaryDirectory(prefix='qualimatch_excel_') as tmpdir:
        tmp=Path(tmpdir)
        for upload in files:
            name=_safe_pdf_name(upload.filename)
            if not name.lower().endswith('.pdf'):
                errors.append({'file_name':upload.filename or '', 'error':'Apenas PDF é aceito.'})
                continue
            target=tmp/f"{uuid4().hex}_{name}"
            try:
                await save_upload_limited(upload,target,30*1024*1024)
            except UploadTooLarge:
                errors.append({'file_name':name,'error':'PDF acima de 30 MB.'})
                continue
            try:
                cert=parse_pdf(target,contractor_hint_from_name(name))
                parsed.append((name,cert))
            except Exception as e:
                errors.append({'file_name':name,'error':str(e)})
    if not parsed:
        raise HTTPException(422,{'message':'Nenhum PDF pôde ser analisado.','errors':errors})
    try:
        raw_overrides=json.loads(overrides_json or '{}')
        overrides={str(k):int(v) for k,v in (raw_overrides or {}).items()}
    except Exception:
        raise HTTPException(400,'Revisões manuais inválidas.')
    result=analyze_certificates(parsed,overrides)
    result['errors']=errors
    try:
        file_name,media_type,content,report=generate_excel_export(result)
    except ValueError as e:
        raise HTTPException(409,str(e))
    audit(user.get('id'),'TOOL_PDF_BDQUALI_EXCEL_COPY','tool','pdf-quality',{
        'pdfs':len(files),'parsed':len(parsed),'errors':len(errors),
        'files':len(report.get('files') or []),
        'rows':sum(int(x.get('rows_written') or 0) for x in report.get('files') or []),
        'blocked':len(report.get('blocked') or []),
    },_client_ip(request))
    files_report=report.get('files') or []
    target_rows=[]
    for item in files_report:
        target_rows.extend(int(x) for x in (item.get('target_rows') or []))
    rows_label=''
    if target_rows:
        ordered=sorted(set(target_rows))
        rows_label=(f'{ordered[0]}-{ordered[-1]}' if len(ordered)>1 else str(ordered[0]))
    headers={
        'Content-Disposition':f'attachment; filename="{file_name}"',
        'X-QualiMatch-Mode':'SAFE_COPY_ONLY',
        'X-QualiMatch-Blocked':str(len(report.get('blocked') or [])),
        'X-QualiMatch-Appended':str(sum(int(x.get('appended_rows') or 0) for x in files_report)),
        'X-QualiMatch-Updated':str(sum(int(x.get('updated_rows') or 0) for x in files_report)),
        'X-QualiMatch-Target-Rows':rows_label,
        'X-QualiMatch-Validated':'true',
        'X-QualiMatch-Filters-Cleared':str(any(bool(x.get('filters_cleared')) for x in files_report)).lower(),
    }
    return Response(content=content,media_type=media_type,headers=headers)

@app.get('/api/admin/audit')
def admin_audit(request:Request,limit:int=100):
    _require_admin(request)
    return list_audit(limit)
@app.get('/api/sources')
def sources(request:Request): _require_admin(request); return get_sources()
@app.post('/api/admin/tools/pdf-quality/write-main')
async def admin_tool_pdf_quality_write_main(request:Request, files:list[UploadFile]=File(...), overrides_json:str=Form('')):
    user=_require_admin(request)
    if not files:
        raise HTTPException(400,'Selecione pelo menos um PDF.')
    if len(files)>30:
        raise HTTPException(400,'Envie no máximo 30 PDFs por gravação.')
    parsed=[]; errors=[]
    with tempfile.TemporaryDirectory(prefix='qualimatch_main_') as tmpdir:
        tmp=Path(tmpdir)
        for upload in files:
            name=_safe_pdf_name(upload.filename)
            if not name.lower().endswith('.pdf'):
                errors.append({'file_name':upload.filename or '', 'error':'Apenas PDF é aceito.'}); continue
            target=tmp/f"{uuid4().hex}_{name}"
            try:
                await save_upload_limited(upload,target,30*1024*1024)
            except UploadTooLarge:
                errors.append({'file_name':name,'error':'PDF acima de 30 MB.'}); continue
            try:
                cert=parse_pdf(target,contractor_hint_from_name(name)); parsed.append((name,cert))
            except Exception as e:
                errors.append({'file_name':name,'error':str(e)})
    if not parsed:
        raise HTTPException(422,{'message':'Nenhum PDF pôde ser analisado.','errors':errors})
    try:
        raw_overrides=json.loads(overrides_json or '{}')
        overrides={str(k):int(v) for k,v in (raw_overrides or {}).items()}
    except Exception:
        raise HTTPException(400,'Revisões manuais inválidas.')
    # Antes de casar os certificados com a BD_QUALI e gravar, força um reprocesso
    # completo da fonte Qualidade (e Medição) de cada contratada envolvida. Isso
    # evita depender do usuário ter clicado em "Sincronizar"/"Reprocessar" antes:
    # a gravação sempre compara contra o estado mais atual possível do arquivo
    # local, reduzindo a janela para o erro "BD_QUALI foi alterada depois da
    # última sincronização" aparecer por causa de uma sincronização que não
    # rodou de verdade.
    presync_contractors={str(c.contractor or '').upper() for _,c in parsed if getattr(c,'contractor',None)}
    presync_errors=[]
    for c in presync_contractors:
        for kind in ('qualidade','medicao'):
            try:
                r=await asyncio.to_thread(sync_source,c,kind,True)
                if not r.get('ok',True):
                    presync_errors.append(f"{c}/{kind}: {r.get('message') or 'falha'}")
            except Exception as e:
                presync_errors.append(f"{c}/{kind}: {e}")
    result=analyze_certificates(parsed,overrides)
    result['errors']=errors
    result['presync_errors']=presync_errors
    try:
        report=await asyncio.to_thread(write_excel_to_main_sources,result)
    except ValueError as e:
        raise HTTPException(409,str(e))
    except Exception as e:
        raise HTTPException(500,f'Falha ao atualizar a BD_QUALI principal: {e}')
    sync_results=[]
    for f in report.get('files') or []:
        contractor=str(f.get('contractor') or '').upper()
        try:
            sync_results.append(await asyncio.to_thread(sync_source,contractor,'qualidade',True))
        except Exception as e:
            sync_results.append({'ok':False,'contractor':contractor,'kind':'qualidade','error':str(e)})
    report['sync_results']=sync_results
    audit(user.get('id'),'TOOL_PDF_BDQUALI_WRITE_MAIN','tool','pdf-quality',{
        'files':len(report.get('files') or []),'blocked':len(report.get('blocked') or []),
        'rows_written':sum(int(x.get('rows_written') or 0) for x in report.get('files') or [])
    },_client_ip(request))
    return {'ok':True,'report':report}


@app.put('/api/sources/{contractor}/{kind}')
def source_update(contractor:str,kind:str,payload:SourceUpdate,request:Request):
    admin=_require_admin(request)
    contractor=contractor.upper();
    if contractor not in {'ARENA','PAVIDEZ'} or kind not in {'medicao','qualidade','kits','kit_documentos','certificados','bv_documentos'}: raise HTTPException(400,'Fonte inválida')
    update_source(contractor,kind,payload.path,payload.worksheet); audit(admin['id'],'SOURCE_UPDATE','source',f'{contractor}:{kind}',{'path':payload.path},_client_ip(request)); return {'ok':True}
@app.post('/api/sources/{contractor}/kits/discover')
async def source_discover_kits(contractor:str,request:Request):
    admin=_require_admin(request)
    contractor=contractor.upper()
    if contractor not in {'ARENA','PAVIDEZ'}:
        raise HTTPException(400,'Contratada inválida')
    found=await asyncio.to_thread(discover_kits_source,contractor)
    if not found:
        raise HTTPException(404,'Não encontrei automaticamente uma planilha de kits na pasta local da contratada. Cole o caminho do arquivo manualmente.')
    update_source(contractor,'kits',found,'d.KIT')
    audit(admin['id'],'SOURCE_DISCOVER','source',f'{contractor}:kits',{'path':found},_client_ip(request))
    return {'ok':True,'path':found,'worksheet':'d.KIT'}

@app.post('/api/sources/{contractor}/bv-documentos/discover')
async def source_discover_bv(contractor:str,request:Request):
    admin=_require_admin(request)
    contractor=contractor.upper()
    if contractor not in {'ARENA','PAVIDEZ'}:
        raise HTTPException(400,'Contratada inválida')
    found=await asyncio.to_thread(discover_bv_source,contractor)
    if not found:
        raise HTTPException(404,'Não encontrei automaticamente a pasta 04.0 VV - CERTIFICADOS desta contratada.')
    await asyncio.to_thread(remap_bv_certificate_paths,contractor,Path(found))
    update_source(contractor,'bv_documentos',found,'')
    audit(admin['id'],'SOURCE_DISCOVER','source',f'{contractor}:bv_documentos',{'path':found},_client_ip(request))
    return {'ok':True,'path':found}

@app.get('/api/bv-documents/groups')
def bv_document_groups_api(request:Request,contractor:str='ALL',search:str='',extension:str=''):
    _require_portal(request,'BV')
    contractor=contractor.upper()
    if contractor not in {'ALL','ARENA','PAVIDEZ'}: raise HTTPException(400,'Contratada inválida')
    return bv_document_groups(contractor,search,extension)

def _bv_general_report_payload(contractor:str) -> dict:
    report=bv_general_report(contractor)
    cycles=measurement_cycle_dashboard(contractor,100).get('cycles') or []
    by_measurement={str(x.get('measurement')):x for x in report.get('measurements') or []}
    categories=report.get('categories') or []
    setting=row("SELECT value FROM settings WHERE key='bv_general_report_overrides'") or {}
    try: overrides=json.loads(setting.get('value') or '{}')
    except Exception: overrides={}
    for cycle in cycles:
        label=str(cycle.get('measurement') or '')
        item=by_measurement.get(label)
        if item is None:
            item={'measurement':label,'total':0,'counts':{name:0 for name in categories},'files':{name:[] for name in categories}}
            report['measurements'].append(item); by_measurement[label]=item
        execution_days=int(cycle.get('execution_days') or 0)
        # A amostragem de 20% sempre arredonda para baixo.
        sample_target=math.floor(execution_days*.20) if execution_days else 0
        item['execution_days']=execution_days
        item['expected']={'VV/ESP':execution_days,'CA':sample_target,'LIGANTE':sample_target,'DUI':1,'AGREGADOS':sample_target,'OUTROS':0}
        item['counts']['VV/ESP']=min(execution_days,int(cycle.get('certificate_days') or 0))
    for item in report.get('measurements') or []:
        item.setdefault('execution_days',0)
        item.setdefault('expected',{'VV/ESP':0,'CA':0,'LIGANTE':0,'DUI':1,'AGREGADOS':0,'OUTROS':0})
        saved=overrides.get(f"{contractor}:{item.get('measurement')}") or {}
        for name,value in (saved.get('counts') or {}).items():
            if name in item['counts']: item['counts'][name]=max(0,int(value))
        item['manual_override']=bool(saved); item['override_reason']=saved.get('reason','')
        item['total']=sum(int(item['counts'].get(name) or 0) for name in categories)
    report['totals']={name:sum(int(item['counts'].get(name) or 0) for item in report.get('measurements') or []) for name in categories}
    report['total']=sum(int(item.get('total') or 0) for item in report.get('measurements') or [])
    report['measurements'].sort(key=lambda x:int(re.sub(r'\D','',str(x.get('measurement') or '')) or -1),reverse=True)
    return report

@app.get('/api/bv-general-report')
def bv_general_report_api(request:Request,contractor:str='ALL'):
    _require_portal(request,'BV')
    contractor=contractor.upper()
    if contractor not in {'ALL','ARENA','PAVIDEZ'}: raise HTTPException(400,'Contratada inválida')
    report=_bv_general_report_payload(contractor)
    if contractor=='ALL':
        report['contractor_sections']=[
            {'contractor':name,'measurements':_bv_general_report_payload(name).get('measurements') or []}
            for name in ('ARENA','PAVIDEZ')
        ]
    return report

@app.get('/api/bv-general-report/missing.pdf')
def bv_general_report_missing_pdf(request:Request,contractor:str='ALL'):
    _require_portal(request,'BV')
    contractor=contractor.upper()
    if contractor not in {'ALL','ARENA','PAVIDEZ'}: raise HTTPException(400,'Contratada inválida')
    pdf=build_bv_missing_report_pdf(bv_general_report_api(request,contractor),contractor)
    suffix='arena-pavidez' if contractor=='ALL' else contractor.lower()
    return Response(content=pdf,media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="pendencias-bv-{suffix}.pdf"'})

@app.put('/api/bv-general-report/override')
def bv_general_report_override_api(payload:BvReportOverridePayload,request:Request):
    user=_require_portal(request,'BV')
    if not can_edit(user): raise HTTPException(403,'Seu perfil é somente leitura.')
    contractor=payload.contractor.upper(); measurement=payload.measurement.upper().strip()
    if contractor not in {'ALL','ARENA','PAVIDEZ'}: raise HTTPException(400,'Contratada inválida')
    allowed={'VV/ESP','CA','LIGANTE','DUI','AGREGADOS','OUTROS'}
    counts={k:max(0,int(v)) for k,v in payload.counts.items() if k in allowed}
    setting=row("SELECT value FROM settings WHERE key='bv_general_report_overrides'") or {}
    try: data=json.loads(setting.get('value') or '{}')
    except Exception: data={}
    data[f'{contractor}:{measurement}']={'counts':counts,'reason':payload.reason.strip(),'updated_at':datetime.now().isoformat(timespec='seconds'),'updated_by':user.get('id')}
    with transaction() as con:
        con.execute("INSERT INTO settings(key,value) VALUES('bv_general_report_overrides',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(data,ensure_ascii=False),))
    audit(user.get('id'),'BV_REPORT_OVERRIDE','measurement',f'{contractor}:{measurement}',{'counts':counts,'reason':payload.reason},_client_ip(request))
    return {'ok':True,'message':'Quantidades atualizadas.'}

@app.get('/api/bv-documents')
def bv_documents_api(request:Request,contractor:str='ALL',search:str='',measurement:str='',extension:str='',limit:int=200,page:int|None=None,page_size:int=25):
    _require_portal(request,'BV')
    contractor=contractor.upper()
    if contractor not in {'ALL','ARENA','PAVIDEZ'}: raise HTTPException(400,'Contratada inválida')
    if page is None:
        return list_bv_documents(contractor,search,measurement,extension,min(limit,1000))
    current,size,offset=_page_args(page,page_size)
    total=count_bv_documents(contractor,search,measurement,extension)
    current,offset=_page_offset_for_total(current,size,total)
    return _page_response(list_bv_documents(contractor,search,measurement,extension,size,offset),total,current,size)

@app.delete('/api/bv-documents/{doc_id}')
def bv_document_archive_api(doc_id:int,request:Request):
    user=_require_portal(request,'BV')
    if not can_edit(user): raise HTTPException(403,'Seu perfil é somente leitura.')
    d=archive_bv_document(doc_id,int(user['id']))
    if not d: raise HTTPException(404,'Arquivo não encontrado')
    audit(user['id'],'BV_DOCUMENT_ARCHIVE','bv_document',str(doc_id),{'file_name':d.get('file_name'),'relative_path':d.get('relative_path')},_client_ip(request))
    return {'ok':True,'message':'Arquivo removido da visualização do QualiMatch. O arquivo original do SharePoint não foi apagado.'}

@app.post('/api/bv-documents/remove-duplicates')
def bv_document_remove_duplicates_api(request:Request,contractor:str='ALL'):
    user=_require_portal(request,'BV')
    if not can_edit(user): raise HTTPException(403,'Seu perfil é somente leitura.')
    contractor=contractor.upper()
    if contractor not in {'ALL','ARENA','PAVIDEZ'}: raise HTTPException(400,'Contratada inválida')
    result=archive_duplicate_bv_documents(contractor,int(user['id']))
    audit(user['id'],'BV_DUPLICATES_BULK_ARCHIVE','bv_document',contractor,{
        'removed':result.get('removed',0),'by_contractor':result.get('by_contractor',{})
    },_client_ip(request))
    removed=int(result.get('removed') or 0)
    return {
        'ok':True,
        **result,
        'message': (f'{removed} arquivo(s) duplicado(s) removido(s) da visualização. A ocorrência original foi preservada.'
                    if removed else 'Nenhum arquivo marcado como duplicado foi encontrado neste filtro.')
    }

@app.get('/api/bv-documents/{doc_id}/file')
def bv_document_file(doc_id:int,request:Request):
    _require_portal(request,'BV'); d=bv_document(doc_id,include_archived=True)
    if not d: raise HTTPException(404,'Arquivo não encontrado')
    p=_local_file_path(d['file_path'])
    if not p.exists(): raise HTTPException(404,'Arquivo ainda não está disponível localmente')
    return FileResponse(str(p),filename=d.get('file_name') or p.name)

@app.get('/api/contractor/kits')
def contractor_kits(request:Request,contractor:str='ALL',search:str='',limit:int=1000,sort:str='newest',status:str='ALL',road:str='',period:str='',service:str='',start:str|None=None,end:str|None=None,page:int|None=None,page_size:int=25):
    contractor=_contractor_for_user(request,contractor)
    if page is None:
        return list_kits(contractor,search,min(limit,3000),sort,status,road,period,service,start,end)
    current,size,offset=_page_args(page,page_size)
    total=count_kits(contractor,search,status,road,period,service,start,end)
    current,offset=_page_offset_for_total(current,size,total)
    items=list_kits(contractor,search,size,sort,status,road,period,service,start,end,offset)
    return _page_response(items,total,current,size)

@app.get('/api/contractor/kits/filter-options')
def contractor_kits_filter_options(request:Request,contractor:str='ALL'):
    contractor=_contractor_for_user(request,contractor)
    return kit_filter_options(contractor)

@app.get('/api/contractor/kits/summary')
def contractor_kits_summary(request:Request,contractor:str='ALL'):
    contractor=_contractor_for_user(request,contractor)
    return kit_summary(contractor)


@app.get('/api/contractor/kits/{kit_id}')
def contractor_kit_detail(kit_id:int,request:Request):
    user=_require_portal(request,'CONTRACTOR')
    item=kit_detail(kit_id)
    if not item or not int(item.get('is_active') or 0):
        raise HTTPException(404,'Kit não encontrado')
    if not has_contractor_access(user,str(item.get('contractor') or '')):
        raise HTTPException(403,'Seu usuário não possui acesso a este kit.')
    return item

@app.put('/api/contractor/kits/{kit_id}')
def contractor_kit_edit(kit_id:int,payload:KitEditPayload,request:Request):
    editor=_require_editor(request)
    current=kit_detail(kit_id)
    if not current or not int(current.get('is_active') or 0):
        raise HTTPException(404,'Kit não encontrado')
    contractor=str(current.get('contractor') or '').upper()
    if str(editor.get('role') or '').upper()!='ADMIN' and not has_contractor_access(editor,contractor):
        raise HTTPException(403,'Seu usuário não possui acesso a esta contratada.')
    before=dict(current)
    app_date=to_date(payload.application_date) if payload.application_date else None
    receipt=to_date(payload.receipt_date) if payload.receipt_date else None
    status=str(payload.status or '').strip().upper()
    if status and status not in {'OK','INCOMPLETO','PENDENTE'}:
        raise HTTPException(400,'Situação deve ser OK, INCOMPLETO ou PENDENTE.')
    period=str(payload.period or '').strip().upper()
    if period and period not in {'DIURNO','NOTURNO'}:
        raise HTTPException(400,'Período deve ser DIURNO ou NOTURNO.')
    values=(str(payload.seq or '').strip(),str(payload.service or '').strip(),
        app_date.isoformat() if app_date else None,str(payload.mix_project or '').strip(),period,
        norm_road(payload.road),normalize_station(payload.kmi),normalize_station(payload.kmf),
        receipt.isoformat() if receipt else None,status,
        str(payload.status_1 or '').strip().upper(),str(payload.status_2 or '').strip().upper(),
        str(payload.status_3 or '').strip().upper(),str(payload.status_4 or '').strip().upper(),
        str(payload.status_5 or '').strip().upper(),str(payload.status_6 or '').strip().upper(),
        str(payload.status_7 or '').strip().upper(),str(payload.status_8 or '').strip().upper(),
        str(payload.sin_retro or '').strip().upper(),datetime.now().isoformat(timespec='seconds'),editor['id'],kit_id)
    sql='UPDATE kit_rows SET seq=?,service=?,application_date=?,mix_project=?,period=?,road=?,kmi=?,kmf=?,receipt_date=?,status=?,status_1=?,status_2=?,status_3=?,status_4=?,status_5=?,status_6=?,status_7=?,status_8=?,sin_retro=?,manual_override=1,updated_at=?,updated_by=? WHERE id=?'
    with transaction() as con:
        con.execute(sql,values)
    after=kit_detail(kit_id) or {}
    record_change(editor.get('id'),'KIT_EDIT','kit',kit_id,before,after)
    audit(editor['id'],'KIT_EDIT','kit',kit_id,{'contractor':contractor,'source_row':current.get('source_row')},_client_ip(request))
    log_sync(contractor,'kits_edicao','OK',f'Kit #{current.get("seq") or current.get("source_row")} editado manualmente no site.',1,'')
    return {'ok':True,'kit':kit_detail(kit_id),'message':'Kit atualizado. A sincronização não sobrescreverá esta edição manual.'}

@app.delete('/api/contractor/kits/{kit_id}')
def contractor_kit_delete(kit_id:int,request:Request):
    editor=_require_editor(request)
    current=kit_detail(kit_id)
    if not current or not int(current.get('is_active') or 0):
        raise HTTPException(404,'Kit não encontrado')
    contractor=str(current.get('contractor') or '').upper()
    if str(editor.get('role') or '').upper()!='ADMIN' and not has_contractor_access(editor,contractor):
        raise HTTPException(403,'Seu usuário não possui acesso a esta contratada.')
    before=dict(current)
    with transaction() as con:
        con.execute('UPDATE kit_rows SET is_active=0,manual_override=1,updated_at=?,updated_by=? WHERE id=?',(datetime.now().isoformat(timespec='seconds'),editor['id'],kit_id))
    after=kit_detail(kit_id) or {**before,'is_active':0}
    record_change(editor.get('id'),'KIT_ARCHIVE','kit',kit_id,before,after)
    audit(editor['id'],'KIT_ARCHIVE','kit',kit_id,{'contractor':contractor,'seq':current.get('seq'),'source_row':current.get('source_row')},_client_ip(request))
    log_sync(contractor,'kits_edicao','OK',f'Kit #{current.get("seq") or current.get("source_row")} arquivado no QualiMatch. A linha original da d.KIT não foi apagada.',1,'')
    return {'ok':True,'message':'Kit removido das telas e estatísticas. A planilha original não foi apagada.'}

@app.get('/api/contractor/pending')
def contractor_pending(request:Request,contractor:str='ALL',start:str|None=None,end:str|None=None):
    """Pendências da Contratada: certificados BV + Data aplicação dos kits."""
    contractor=_contractor_for_user(request,contractor)
    return contractor_pending_measurements(contractor,start,end)

def _pending_key(item:dict) -> str:
    sequences=','.join(sorted(str(x) for x in (item.get('kit_sequences') or []) if x))
    return '|'.join(str(x or '').strip().upper() for x in (
        item.get('contractor'),item.get('pending_reason'),item.get('date'),sequences,item.get('road')
    ))

@app.get('/api/contractor/pending-view')
def contractor_pending_view(request:Request,contractor:str='ALL',start:str|None=None,end:str|None=None):
    contractor=_contractor_for_user(request,contractor)
    current=contractor_pending_measurements(contractor,start,end)
    saved=rows("SELECT pending_key,contractor,reason,item_json,justified_at FROM pending_justifications WHERE active=1" + (" AND contractor=?" if contractor!='ALL' else "") + " ORDER BY justified_at DESC",(contractor,) if contractor!='ALL' else ())
    saved_by_key={str(x['pending_key']):x for x in saved}
    active=[]
    for item in current:
        item={**item,'pending_key':_pending_key(item)}
        if item['pending_key'] not in saved_by_key:
            active.append(item)
    justified=[]
    for record in saved:
        try: item=json.loads(record.get('item_json') or '{}')
        except Exception: item={}
        justified.append({**item,'pending_key':record['pending_key'],'contractor':record['contractor'],'justification':record['reason'],'justified_at':record['justified_at']})
    return {'items':active,'justified':justified}

@app.post('/api/contractor/pending/justify')
def contractor_pending_justify(payload:PendingJustificationPayload,request:Request):
    editor=_require_editor(request); contractor=str(payload.contractor or '').upper()
    if contractor not in {'ARENA','PAVIDEZ'} or (str(editor.get('role') or '').upper()!='ADMIN' and not has_contractor_access(editor,contractor)):
        raise HTTPException(403,'Seu usuário não possui acesso a esta contratada.')
    reason=str(payload.reason or '').strip()
    if len(reason)<3: raise HTTPException(400,'Informe uma justificativa com pelo menos 3 caracteres.')
    now=datetime.now().isoformat(timespec='seconds')
    with transaction() as con:
        con.execute("INSERT INTO pending_justifications(pending_key,contractor,reason,item_json,justified_by,justified_at,active) VALUES(?,?,?,?,?,?,1) ON CONFLICT(pending_key) DO UPDATE SET reason=excluded.reason,item_json=excluded.item_json,justified_by=excluded.justified_by,justified_at=excluded.justified_at,active=1",(payload.pending_key,contractor,reason,json.dumps(payload.item,ensure_ascii=False,default=str),editor['id'],now))
    audit(editor['id'],'PENDING_JUSTIFY','pending',payload.pending_key,{'contractor':contractor,'reason':reason},_client_ip(request))
    return {'ok':True}

@app.delete('/api/contractor/pending/justify/{pending_key:path}')
def contractor_pending_restore(pending_key:str,request:Request):
    editor=_require_editor(request)
    saved=row("SELECT contractor FROM pending_justifications WHERE pending_key=?",(pending_key,))
    if not saved: raise HTTPException(404,'Justificativa não encontrada.')
    contractor=str(saved['contractor']).upper()
    if str(editor.get('role') or '').upper()!='ADMIN' and not has_contractor_access(editor,contractor): raise HTTPException(403,'Sem acesso.')
    with transaction() as con: con.execute("UPDATE pending_justifications SET active=0 WHERE pending_key=?",(pending_key,))
    audit(editor['id'],'PENDING_RESTORE','pending',pending_key,{'contractor':contractor},_client_ip(request))
    return {'ok':True}


@app.get('/api/contractor/kit-documents')
def contractor_kit_documents(request:Request,contractor:str='ALL',kit_id:int|None=None,search:str='',limit:int=2000,extension:str='',top_folder:str=''):
    contractor=_contractor_for_user(request,contractor)
    return list_kit_documents(contractor,kit_id,search,min(limit,5000),extension,top_folder)

@app.get('/api/contractor/kit-document-folders')
def contractor_kit_document_folders(request:Request,contractor:str='ALL',extension:str=''):
    contractor=_contractor_for_user(request,contractor)
    where=[]; params=[]
    if contractor!='ALL': where.append('contractor=?'); params.append(contractor)
    if extension:
        ext=extension.lower(); ext=ext if ext.startswith('.') else '.'+ext
        where.append('LOWER(extension)=?'); params.append(ext)
    data=rows('SELECT relative_path FROM kit_documents'+((' WHERE '+' AND '.join(where)) if where else ''),tuple(params))
    counts={}
    for item in data:
        path=str(item.get('relative_path') or '').replace('\\','/').strip('/')
        folder=path.split('/',1)[0] if '/' in path else '(raiz)'
        counts[folder]=counts.get(folder,0)+1
    def folder_order(value:str):
        match=re.fullmatch(r'M\s*0*(\d+)',value.strip(),re.I)
        return (0,int(match.group(1))) if match else (1,value.upper())
    return [{'folder':key,'count':counts[key]} for key in sorted(counts,key=folder_order)]

@app.get('/api/contractor/kit-documents/{doc_id}/file')
def contractor_kit_document_file(doc_id:int,request:Request,preview:bool=False):
    user=_require_portal(request,'CONTRACTOR')
    d=kit_document(doc_id)
    if not d: raise HTTPException(404,'Documento do kit não encontrado')
    if not has_contractor_access(user,str(d.get('contractor') or '')):
        raise HTTPException(403,'Seu usuário não possui acesso a este documento.')
    file_path=str(d['file_path'])
    file_name=d.get('file_name') or Path(file_path).name
    disposition='inline' if preview else 'attachment'
    if ZIP_ENTRY_SEP in file_path:
        # Documento indexado de dentro de um .zip de entrega: não existe como
        # arquivo solto no disco, então extrai o conteúdo em memória a partir
        # do .zip (sem descompactar nada permanentemente).
        zip_path,inner_name=file_path.split(ZIP_ENTRY_SEP,1)
        zp=Path(zip_path)
        if not zp.exists(): raise HTTPException(404,'O .zip de origem não está disponível no servidor local. Aguarde o SharePoint/OneDrive sincronizar.')
        try:
            with zipfile.ZipFile(zp) as zf:
                data=zf.read(inner_name)
        except KeyError:
            raise HTTPException(404,'Arquivo não encontrado dentro do .zip (pode ter sido renomeado/removido na origem).')
        except zipfile.BadZipFile:
            raise HTTPException(404,'O .zip de origem está corrompido ou ainda sincronizando pelo OneDrive.')
        media_type=mimetypes.guess_type(file_name)[0] or 'application/octet-stream'
        return Response(
            content=data,media_type=media_type,
            headers={'Content-Disposition': f'{disposition}; filename="{file_name}"'},
        )
    p=Path(file_path)
    if not p.exists(): raise HTTPException(404,'Arquivo não está disponível no servidor local. Aguarde o SharePoint/OneDrive sincronizar.')
    return FileResponse(
        str(p),
        filename=file_name,
        content_disposition_type=disposition,
    )

@app.get('/api/admin/auto-monitor')
def auto_monitor_status_api(request:Request,limit:int=80,page:int|None=None,page_size:int=25):
    _require_admin(request)
    if page is None:
        return {'config':monitor_config(),'events':monitor_events(min(limit,300))}
    current,size,offset=_page_args(page,page_size)
    total=count_monitor_events()
    current,offset=_page_offset_for_total(current,size,total)
    return {'config':monitor_config(),**_page_response(monitor_events(size,offset),total,current,size)}

@app.put('/api/admin/auto-monitor')
def auto_monitor_update_api(payload:AutoMonitorPayload,request:Request):
    admin=_require_admin(request)
    cfg=update_monitor_config(payload.enabled,payload.bv,payload.contractor,payload.seconds,payload.auto_quality)
    audit(admin['id'],'AUTO_MONITOR_CONFIG','sync','auto-monitor',cfg,_client_ip(request))
    return {'ok':True,'config':cfg}

@app.post('/api/admin/auto-monitor/run')
async def auto_monitor_run_api(request:Request):
    admin=_require_admin(request)
    try:
        with runtime_job('monitor','Verificação das pastas locais',1):
            runtime_update(current='Procurando arquivos novos...')
            result=await asyncio.to_thread(monitor_once)
            runtime_update(processed=1)
    except JobBusyError as exc:
        raise HTTPException(409,str(exc))
    audit(admin['id'],'AUTO_MONITOR_RUN','sync','auto-monitor',{'detected':result.get('detected',0),'processed':result.get('processed',0),'errors':result.get('errors',0)},_client_ip(request))
    return result

@app.post('/api/sync/all')
async def sync_all_api(request:Request,force:bool=False):
    admin=_require_admin(request)
    try:
        with runtime_job('sync_all','Sincronização de todas as fontes'):
            result=await asyncio.to_thread(sync_all,force,runtime_update,check_cancelled)
    except JobBusyError as exc:
        raise HTTPException(409,str(exc))
    except JobCancelled as exc:
        raise HTTPException(409,str(exc))
    audit(admin['id'],'SYNC_ALL','sync','',{'force':force},_client_ip(request)); return result
@app.post('/api/sync/{contractor}/{kind}')
async def sync_one(contractor:str,kind:str,request:Request,force:bool=False):
    admin=_require_admin(request); c=contractor.upper()
    try:
        with runtime_job('sync_source',f'Sincronização {c} / {kind}',1):
            runtime_update(current=f'{c} / {kind}')
            result=await asyncio.to_thread(sync_source,c,kind,force)
            runtime_update(processed=1)
    except JobBusyError as exc:
        raise HTTPException(409,str(exc))
    if kind in {'certificados','bv_documentos'} and result.get('ok'):
        try:
            result['auto_quality']=await asyncio.to_thread(auto_fill_quality_for_recent_certificates,c,300)
        except Exception as exc:
            result['auto_quality']={'ok':False,'errors':1,'message':str(exc)}
    audit(admin['id'],'SYNC_SOURCE','sync',f'{c}:{kind}',{'force':force},_client_ip(request)); return result
@app.get('/api/dashboard')
def dash(contractor:str='ALL',start:str|None=None,end:str|None=None,status:str='ALL',measurement:str='',certificates:str=''):
    status=status.upper()
    contractor=contractor.upper()
    selected_certificates=[x.strip() for x in str(certificates or '').split(',') if x.strip()]
    if status not in {'ALL','APROVADO','REPROVADO'}: raise HTTPException(400,'Status inválido')
    if contractor not in {'ALL','ARENA','PAVIDEZ'}: raise HTTPException(400,'Contratada inválida')
    if measurement and not measurement_cycle_bounds(measurement): raise HTTPException(400,'Medição inválida')
    if len(selected_certificates)>250: raise HTTPException(400,'Selecione no máximo 250 certificados por vez')
    return dashboard(contractor,start,end,status,measurement,selected_certificates)

@app.get('/api/measurement-cycles/options')
def measurement_options(contractor:str='ALL'):
    contractor=contractor.upper()
    if contractor not in {'ALL','ARENA','PAVIDEZ'}: raise HTTPException(400,'Contratada inválida')
    return measurement_cycle_options(contractor)
@app.get('/api/pending')
def pending(contractor:str='ALL',start:str|None=None,end:str|None=None): return bv_certificate_pending(contractor.upper(),start,end)

def _bv_pending_key(item:dict) -> str:
    return 'BV|' + '|'.join(str(x or '').strip().upper() for x in (
        item.get('contractor'),item.get('date'),item.get('road'),item.get('measurement')
    ))

@app.get('/api/pending-view')
def pending_view(request:Request,contractor:str='ALL',start:str|None=None,end:str|None=None):
    _require_portal(request,'BV')
    contractor=contractor.upper()
    if contractor not in {'ALL','ARENA','PAVIDEZ'}: raise HTTPException(400,'Contratada inválida')
    current=bv_certificate_pending(contractor,start,end)
    sql="SELECT pending_key,contractor,reason,item_json,justified_at FROM pending_justifications WHERE active=1 AND pending_key LIKE ?"
    params=('BV|%',)
    if contractor!='ALL':
        sql+=' AND contractor=?'
        params=('BV|%',contractor)
    sql+=' ORDER BY justified_at DESC'
    saved=rows(sql,params); saved_by_key={str(x['pending_key']):x for x in saved}
    active=[]
    for item in current:
        item={**item,'pending_key':_bv_pending_key(item)}
        if item['pending_key'] not in saved_by_key: active.append(item)
    justified=[]
    for record in saved:
        try: item=json.loads(record.get('item_json') or '{}')
        except Exception: item={}
        justified.append({**item,'pending_key':record['pending_key'],'contractor':record['contractor'],'justification':record['reason'],'justified_at':record['justified_at']})
    return {'items':active,'justified':justified}

@app.post('/api/pending/justify')
def pending_justify(payload:PendingJustificationPayload,request:Request):
    editor=_require_editor(request); _require_portal(request,'BV')
    contractor=str(payload.contractor or '').upper(); reason=str(payload.reason or '').strip()
    if contractor not in {'ARENA','PAVIDEZ'}: raise HTTPException(400,'Contratada inválida')
    if not str(payload.pending_key).startswith('BV|'): raise HTTPException(400,'Pendência BV inválida.')
    if len(reason)<3: raise HTTPException(400,'Informe uma justificativa com pelo menos 3 caracteres.')
    now=datetime.now().isoformat(timespec='seconds')
    with transaction() as con:
        con.execute("INSERT INTO pending_justifications(pending_key,contractor,reason,item_json,justified_by,justified_at,active) VALUES(?,?,?,?,?,?,1) ON CONFLICT(pending_key) DO UPDATE SET reason=excluded.reason,item_json=excluded.item_json,justified_by=excluded.justified_by,justified_at=excluded.justified_at,active=1",(payload.pending_key,contractor,reason,json.dumps(payload.item,ensure_ascii=False,default=str),editor['id'],now))
    audit(editor['id'],'BV_PENDING_JUSTIFY','pending',payload.pending_key,{'contractor':contractor,'reason':reason},_client_ip(request))
    return {'ok':True}

@app.delete('/api/pending/justify/{pending_key:path}')
def pending_restore(pending_key:str,request:Request):
    editor=_require_editor(request); _require_portal(request,'BV')
    if not pending_key.startswith('BV|'): raise HTTPException(400,'Pendência BV inválida.')
    saved=row("SELECT contractor FROM pending_justifications WHERE pending_key=?",(pending_key,))
    if not saved: raise HTTPException(404,'Justificativa não encontrada.')
    with transaction() as con: con.execute("UPDATE pending_justifications SET active=0 WHERE pending_key=?",(pending_key,))
    audit(editor['id'],'BV_PENDING_RESTORE','pending',pending_key,{'contractor':saved['contractor']},_client_ip(request))
    return {'ok':True}
@app.get('/api/measurements')
def measurements(contractor:str='ALL',search:str='',limit:int=500,page:int|None=None,page_size:int=25):
    contractor=contractor.upper()
    if page is None: return list_measurements(contractor,search,min(limit,2000))
    current,size,offset=_page_args(page,page_size)
    total=count_measurements(contractor,search)
    current,offset=_page_offset_for_total(current,size,total)
    return _page_response(list_measurements(contractor,search,size,offset),total,current,size)
@app.get('/api/certificates')
def certificates(
    contractor:str='ALL',search:str='',limit:int=300,sort:str='newest',
    cp_min:int|None=Query(None,ge=0),cp_max:int|None=Query(None,ge=0),
    status:str='ALL',road:str='',segment:str='',number:str='',
    vv_status:str='ALL',thickness_status:str='ALL',measurement:str='',
    counterproof:str='ALL',date_issue:str='ALL',page:int|None=None,page_size:int=25,
):
    if cp_min is not None and cp_max is not None and cp_min>cp_max:
        raise HTTPException(400,'CP mínimo não pode ser maior que CP máximo')
    if sort.lower() not in {'newest','oldest','desc','asc','recente','antigo'}:
        raise HTTPException(400,'Ordenação inválida')
    if status.upper() not in {'ALL','APROVADO','REPROVADO','SEM_RESULTADO','SEM RESULTADO'}:
        raise HTTPException(400,'Situação inválida')
    valid_technical={'ALL','APROVADO','REPROVADO','SEM_RESULTADO','SEM RESULTADO'}
    if vv_status.upper() not in valid_technical:
        raise HTTPException(400,'Situação de Vv inválida')
    if thickness_status.upper() not in valid_technical:
        raise HTTPException(400,'Situação de espessura inválida')
    if counterproof.upper() not in {'ALL','ENTREGUE','PENDENTE','NAO','NÃO'}:
        raise HTTPException(400,'Filtro de contra-prova inválido')
    if date_issue.upper() not in {'ALL','INCONSISTENTE','SIM'}:
        raise HTTPException(400,'Filtro de consistência de datas inválido')
    if measurement and not measurement_cycle_bounds(measurement):
        raise HTTPException(400,'Medição inválida')
    args=(contractor.upper(),search,min(limit,1000),sort,cp_min,cp_max,status.upper(),road,segment,number,
          vv_status.upper(),thickness_status.upper(),measurement,counterproof.upper(),date_issue.upper())
    if page is None:
        return list_certificates(*args)
    current,size,offset=_page_args(page,page_size)
    result=list_certificates(*args[:2],size,*args[3:],offset=offset,with_total=True)
    current,corrected_offset=_page_offset_for_total(current,size,result['total'])
    if corrected_offset != offset:
        result=list_certificates(*args[:2],size,*args[3:],offset=corrected_offset,with_total=True)
    return _page_response(result['items'],result['total'],current,size,summary=result['summary'])

@app.post('/api/certificates/remove-duplicates')
def certificate_remove_duplicates_api(request:Request,contractor:str='ALL'):
    user=_require_portal(request,'BV')
    if not can_edit(user): raise HTTPException(403,'Seu perfil é somente leitura.')
    contractor=contractor.upper().strip()
    if contractor not in {'ALL','ARENA','PAVIDEZ'}: raise HTTPException(400,'Contratada inválida')
    result=remove_duplicate_certificate_files(contractor,int(user['id']))
    audit(user['id'],'CERTIFICATE_DUPLICATES_BULK_REMOVE','certificates',contractor,{
        'removed':result.get('removed',0),'by_contractor':result.get('by_contractor',{}),
        'canonical_certificates':result.get('canonical_certificates',0),
    },_client_ip(request))
    removed=int(result.get('removed') or 0)
    return {
        'ok':True, **result,
        'message': (f'{removed} cópia(s) duplicada(s) removida(s) da aba Certificados. Uma ocorrência canônica de cada conteúdo foi preservada.'
                    if removed else 'Nenhuma cópia marcada tecnicamente como DUPLICADO foi encontrada neste filtro.')
    }


@app.post('/api/certificates/reprocess-no-result')
async def reprocess_no_result(request:Request,contractor:str='ALL'):
    admin=_require_admin(request)
    contractor=contractor.upper().strip()
    if contractor not in {'ALL','ARENA','PAVIDEZ'}:
        raise HTTPException(400,'Contratada inválida')
    try:
        result=await asyncio.to_thread(reprocess_no_result_certificates,contractor)
    except Exception as exc:
        raise HTTPException(500,f'Falha ao validar certificados sem resultado: {exc}') from exc
    audit(admin['id'],'REPROCESS_NO_RESULT','certificates',contractor,{
        'total_before':result.get('total_before',0),'fixed':result.get('fixed',0),
        'remaining':result.get('remaining',0),'errors':result.get('errors',0),
        'missing_files':result.get('missing_files',0),'unsupported_files':result.get('unsupported_files',0),'parser_version':result.get('parser_version',''),
    },_client_ip(request))
    return result


@app.get('/api/certificates-filter-options')
def certificate_filters(contractor:str='ALL'):
    return certificate_filter_options(contractor.upper())
@app.get('/api/certificates/{cid}')
def certificate_info(cid:int):
    c=certificate_detail(cid)
    if not c: raise HTTPException(404,'Certificado não encontrado')
    return c
@app.get('/api/certificate-files/{fid}/file')
def certificate_document_file(fid:int):
    d=certificate_document(fid)
    if not d: raise HTTPException(404,'Documento não encontrado')
    p=Path(d['file_path'])
    if not p.exists(): raise HTTPException(404,'PDF não existe mais no caminho sincronizado')
    return FileResponse(p,media_type='application/pdf',filename=d['file_name'] or p.name)
@app.get('/api/certificates/{cid}/file')
def certificate_file(cid:int):
    c=row('SELECT * FROM certificates WHERE id=? AND is_active=1',(cid,))
    if not c: raise HTTPException(404,'Certificado não encontrado')
    p=Path(c['file_path'])
    if not p.exists(): raise HTTPException(404,'PDF não existe mais no caminho salvo')
    return FileResponse(p,media_type='application/pdf',filename=p.name)
def _import_uploaded_certificate(dest: Path, contractor: str):
    cert = parse_pdf(dest, contractor)
    cid = _upsert_certificate(cert, reactivate=True)
    _record_certificate_file(contractor, dest, cid, cert)
    recalculate_matches(contractor)
    return cert, cid


def _replace_uploaded_certificate(cid: int, dest: Path, contractor: str, current: dict):
    # Run parsing, backup and database writes in a worker, keeping HTTP responsive.
    changed = False
    try:
        cert = parse_pdf(dest, contractor)
        backup = _automatic_backup('substituir', cid)
        replace_certificate_record(cid, cert)
        changed = True
        try:
            _record_certificate_file(contractor, dest, cid, cert)
        except Exception as doc_error:
            log_sync(contractor, 'certificado_edicao', 'AVISO', f'Substituição do certificado {cid} concluída, mas falhou o registro documental: {doc_error}', 1, str(dest))
        recalculate_matches(contractor)
        log_sync(contractor, 'certificado_edicao', 'OK', f'Certificado {current["number"]} substituído por {cert.number}. Backup: {backup}', 1, str(dest))
        return cert, backup
    except Exception:
        if not changed:
            dest.unlink(missing_ok=True)
        raise


@app.post('/api/certificates/upload')
async def upload_certificate(request:Request,contractor:str=Form(...),file:UploadFile=File(...)):
    user=_require_editor(request)
    _require_portal(request,'BV')
    contractor=contractor.upper();
    if contractor not in {'ARENA','PAVIDEZ'}: raise HTTPException(400,'Contratada inválida')
    if not (file.filename or '').lower().endswith('.pdf'): raise HTTPException(400,'Envie um PDF')
    name=_safe_pdf_name(file.filename or f'cert_{datetime.now().timestamp()}.pdf')
    dest=CERT_DIR/contractor/name
    if dest.exists():
        dest=CERT_DIR/contractor/f'{dest.stem}_{uuid4().hex[:8]}{dest.suffix}'
    try:
        await save_upload_limited(file,dest,30*1024*1024)
    except UploadTooLarge as exc:
        raise HTTPException(413,str(exc)) from exc
    try:
        cert,cid=await asyncio.to_thread(_import_uploaded_certificate,dest,contractor)
    except DuplicateCertificateError as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(409, str(e))
    except Exception as e:
        dest.unlink(missing_ok=True); raise HTTPException(400,f'Falha ao extrair BI330: {e}')
    audit(user['id'],'CERTIFICATE_UPLOAD','certificate',cid,{'number':cert.number,'contractor':contractor},_client_ip(request))
    try:
        auto_quality=await asyncio.to_thread(auto_fill_quality_for_certificate_paths,contractor,[dest],'BV')
    except Exception as auto_exc:
        auto_quality={'ok':False,'errors':1,'message':str(auto_exc)}
    return {'ok':True,'id':cid,'number':cert.number,'extraction_date':cert.extraction_date.isoformat() if cert.extraction_date else None,'samples':len(cert.samples),'counterproof':cert.has_counterproof,'parse_status':cert.raw.get('parse_status','CARREGADO'),'warnings':cert.raw.get('parse_warnings',[]),'auto_quality':auto_quality}

@app.post('/api/certificates/{cid}/replace')
async def replace_certificate(cid:int,request:Request,file:UploadFile=File(...)):
    admin=_require_admin(request)
    current=await asyncio.to_thread(row,'SELECT * FROM certificates WHERE id=? AND is_active=1',(cid,))
    if not current: raise HTTPException(404,'Certificado não encontrado')
    if not (file.filename or '').lower().endswith('.pdf'): raise HTTPException(400,'Envie um PDF')
    contractor=current['contractor']
    folder=CERT_DIR/contractor/'substituicoes'; folder.mkdir(parents=True,exist_ok=True)
    clean=_safe_pdf_name(file.filename)
    dest=folder/f'cert_{cid}_{datetime.now().strftime("%Y%m%d_%H%M%S")}_{uuid4().hex[:6]}_{clean}'
    try:
        await save_upload_limited(file,dest,30*1024*1024)
    except UploadTooLarge as exc:
        raise HTTPException(413,str(exc)) from exc
    try:
        cert,backup=await asyncio.to_thread(_replace_uploaded_certificate,cid,dest,contractor,current)
    except DuplicateCertificateError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        raise HTTPException(400,f'Falha ao substituir certificado: {e}')
    audit(admin['id'],'CERTIFICATE_REPLACE','certificate',cid,{'old_number':current['number'],'new_number':cert.number,'backup':backup},_client_ip(request))
    return {
        'ok':True,'id':cid,'number':cert.number,'backup':backup,
        'parse_status':cert.raw.get('parse_status','CARREGADO'),'warnings':cert.raw.get('parse_warnings',[]),
        'message':'Certificado substituído. O PDF anterior foi preservado no histórico.'
    }

@app.put('/api/certificates/{cid}/phase/{phase}')
def edit_certificate_phase(cid:int,phase:str,payload:CertificatePhaseEditPayload,request:Request):
    admin=_require_admin(request)
    phase=phase.upper().strip()
    if phase not in {'ROTINA','CONTRA_PROVA'}:
        raise HTTPException(400,'Fase inválida.')
    current=row('SELECT * FROM certificates WHERE id=? AND is_active=1',(cid,))
    if not current: raise HTTPException(404,'Certificado não encontrado')
    status=(payload.overall_status or '').upper().strip()
    if status not in {'','APROVADO','REPROVADO'}:
        raise HTTPException(400,'Status deve ser APROVADO ou REPROVADO.')
    backup=_automatic_backup('editar_resumo',cid)
    try:
        raw=json.loads(current.get('raw_json') or '{}')
    except Exception:
        raw={}
    summaries=dict(raw.get('phase_summaries') or {})
    summary=dict(summaries.get(phase) or {})
    for status_key in ('status_vv','status_thickness'):
        status_value=str(getattr(payload,status_key) or '').upper().strip()
        if status_value not in {'','APROVADO','REPROVADO'}:
            raise HTTPException(400,f'{status_key}: status inválido.')
        if status_value:
            summary[status_key]=status_value
    for key in ('k','vv_mean_pct','vv_std_pct','vv_xmin_pct','vv_xmax_pct','ratio_mean_pct','ratio_std_pct','ratio_xmin_pct','ratio_xmax_pct'):
        value=getattr(payload,key)
        if value is not None:
            summary[key]=value
    summaries[phase]=summary
    raw['phase_summaries']=summaries
    result_col='counterproof_result' if phase=='CONTRA_PROVA' else 'routine_result'
    before=dict(current)
    with transaction() as con:
        con.execute(f"UPDATE certificates SET {result_col}=?,raw_json=?,manual_override=1 WHERE id=?",(status,json.dumps(raw,ensure_ascii=False),cid))
    after=row('SELECT * FROM certificates WHERE id=?',(cid,)) or {}
    record_change(admin.get('id'),'CERTIFICATE_PHASE_EDIT','certificate',cid,before,after)
    audit(admin['id'],'CERTIFICATE_PHASE_EDIT','certificate',cid,{'phase':phase,'status':status,'backup':backup},_client_ip(request))
    log_sync(current['contractor'],'certificado_edicao','OK',f'Resumo/status de {current["number"]} ({phase}) editado manualmente. Backup: {backup}',1,current.get('file_path') or '')
    return {'ok':True,'backup':backup,'certificate':certificate_detail(cid)}

@app.put('/api/certificate-samples/{sid}')
def edit_certificate_sample(sid:int,payload:CertificateSampleEditPayload,request:Request):
    admin=_require_admin(request)
    sample=row('SELECT s.*,c.contractor,c.number,c.raw_json,c.file_path FROM certificate_samples s JOIN certificates c ON c.id=s.certificate_id WHERE s.id=? AND c.is_active=1',(sid,))
    if not sample: raise HTTPException(404,'CP não encontrado')
    cid=int(sample['certificate_id']); phase=str(sample.get('phase') or 'ROTINA').upper()
    backup=_automatic_backup('editar_cp',cid)
    values=(payload.application_date,payload.direction.strip(),payload.lane.strip(),payload.station,payload.position.strip(),payload.thickness_exec_cm,payload.thickness_project_cm,payload.ratio_ab_pct,payload.rice_gmm,payload.gmb,payload.voids_pct,sid)
    with transaction() as con:
        con.execute('UPDATE certificate_samples SET application_date=?,direction=?,lane=?,station=?,position=?,thickness_exec_cm=?,thickness_project_cm=?,ratio_ab_pct=?,rice_gmm=?,gmb=?,voids_pct=? WHERE id=?',values)
        if payload.recalculate_summary:
            try: raw=json.loads(sample.get('raw_json') or '{}')
            except Exception: raw={}
            summaries=dict(raw.get('phase_summaries') or {})
            ps=dict(summaries.get(phase) or {})
            for key in ('vv_mean_pct','vv_std_pct','vv_xmin_pct','vv_xmax_pct','ratio_mean_pct','ratio_std_pct','ratio_xmin_pct','ratio_xmax_pct'):
                ps.pop(key,None)
            summaries[phase]=ps; raw['phase_summaries']=summaries
            con.execute('UPDATE certificates SET raw_json=?,manual_override=1 WHERE id=?',(json.dumps(raw,ensure_ascii=False),cid))
        else:
            con.execute('UPDATE certificates SET manual_override=1 WHERE id=?',(cid,))
    after_sample=row('SELECT * FROM certificate_samples WHERE id=?',(sid,)) or {}
    record_change(admin.get('id'),'CERTIFICATE_SAMPLE_EDIT','certificate_sample',sid,dict(sample),after_sample)
    recalculate_matches(sample['contractor'])
    audit(admin['id'],'CERTIFICATE_SAMPLE_EDIT','certificate',cid,{'sample_id':sid,'phase':phase,'backup':backup},_client_ip(request))
    log_sync(sample['contractor'],'certificado_edicao','OK',f'CP {sample.get("cp_number") or sid} de {sample["number"]} editado manualmente. Backup: {backup}',1,sample.get('file_path') or '')
    return {'ok':True,'backup':backup,'certificate':certificate_detail(cid)}

@app.delete('/api/certificates/{cid}')
def delete_certificate(cid:int,request:Request):
    admin=_require_admin(request)
    current=row('SELECT * FROM certificates WHERE id=? AND is_active=1',(cid,))
    if not current: raise HTTPException(404,'Certificado não encontrado')
    backup=_automatic_backup('excluir',cid)
    try:
        before=dict(current)
        contractor=deactivate_certificate(cid)
        after=row('SELECT * FROM certificates WHERE id=?',(cid,)) or {}
        record_change(admin.get('id'),'CERTIFICATE_DELETE','certificate',cid,before,after)
        recalculate_matches(contractor)
        log_sync(contractor,'certificado_edicao','OK',f'Certificado {current["number"]} excluído logicamente. Backup: {backup}',1,'')
    except Exception as e:
        raise HTTPException(400,f'Falha ao excluir certificado: {e}')
    audit(admin['id'],'CERTIFICATE_DELETE','certificate',cid,{'number':current['number'],'backup':backup},_client_ip(request))
    return {
        'ok':True,'id':cid,'number':current['number'],'backup':backup,
        'message':'Certificado excluído da operação e das estatísticas. O histórico e os PDFs foram preservados.'
    }

@app.get('/api/notifications')
def notifications(request:Request):
    return notification_summary(request.state.user)


@app.get('/api/desktop-notifications/certificates')
def desktop_certificate_notifications(request:Request,after_id:int=Query(0,ge=0)):
    """Small authenticated feed used by browser/Windows desktop notifications."""
    _require_portal(request,'BV')
    latest=row('SELECT COALESCE(MAX(id),0) latest_id FROM certificates WHERE is_active=1') or {}
    total=row('SELECT COUNT(*) total FROM certificates WHERE is_active=1 AND id>?',(after_id,)) or {}
    items=rows('''SELECT id,number,contractor,road,parsed_at FROM certificates
        WHERE is_active=1 AND id>? ORDER BY id DESC LIMIT 5''',(after_id,))
    return {'latest_id':int(latest.get('latest_id') or 0),'new_count':int(total.get('total') or 0),'items':items}

@app.get('/api/search')
def search_api(request:Request,q:str='',limit:int=30):
    return global_search(q,request.state.user,min(limit,50))

@app.get('/api/management/review')
def management_review(request:Request,contractor:str='ALL',limit:int=500,severity:str='ALL',item_type:str='ALL',search:str='',page:int|None=None,page_size:int=25):
    _require_admin(request)
    contractor=contractor.upper()
    if contractor not in {'ALL','ARENA','PAVIDEZ'}: raise HTTPException(400,'Contratada inválida')
    if page is None:
        return review_queue(contractor,min(limit,1000),severity,item_type,search)
    current,size,offset=_page_args(page,page_size)
    result=review_queue(contractor,size,severity,item_type,search,offset)
    current,corrected_offset=_page_offset_for_total(current,size,result['total'])
    if corrected_offset != offset:
        result=review_queue(contractor,size,severity,item_type,search,corrected_offset)
    return {**result,'page':current,'page_size':size,'pages':max(1,(int(result['total'])+size-1)//size)}

@app.get('/api/management/measurement-cycles')
def management_cycles(request:Request,contractor:str='ALL',limit:int=14):
    user=_require_portal(request,'BV')
    contractor=contractor.upper()
    if contractor not in {'ALL','ARENA','PAVIDEZ'}: raise HTTPException(400,'Contratada inválida')
    return measurement_cycle_dashboard(contractor,min(limit,36))

@app.get('/api/management/bv-kpi')
def management_bv_kpi(request:Request,contractor:str='ALL',measurement:str='ALL'):
    _require_portal(request,'BV')
    contractor=contractor.upper(); measurement=measurement.upper().strip() or 'ALL'
    if contractor not in {'ALL','ARENA','PAVIDEZ'}: raise HTTPException(400,'Contratada inválida')
    if measurement!='ALL' and not measurement_cycle_bounds(measurement): raise HTTPException(400,'Medição inválida')
    return bv_kpi_dashboard(contractor,measurement)

@app.get('/api/measurements/{measurement_id}/traceability')
def measurement_traceability(measurement_id:int,request:Request):
    _require_portal(request,'BV')
    data=traceability(measurement_id)
    if not data: raise HTTPException(404,'Medição não encontrada')
    return data

@app.get('/api/reports/measurement/{measurement}')
def measurement_report(measurement:str,request:Request,contractor:str='ALL'):
    _require_portal(request,'BV')
    contractor=contractor.upper()
    if contractor not in {'ALL','ARENA','PAVIDEZ'}: raise HTTPException(400,'Contratada inválida')
    try: name,content=measurement_cycle_report(measurement,contractor)
    except ValueError as e: raise HTTPException(404,str(e))
    return Response(content=content,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':f'attachment; filename="{name}"'})

@app.get('/api/admin/changes')
def admin_changes(request:Request,limit:int=100,date:str|None=None,page:int|None=None,page_size:int=25):
    _require_admin(request)
    if page is None:
        return list_changes(min(limit,500),date_filter=date)
    current,size,offset=_page_args(page,page_size)
    total=count_changes(date_filter=date)
    current,offset=_page_offset_for_total(current,size,total)
    return _page_response(list_changes(size,date_filter=date,offset=offset),total,current,size)

@app.post('/api/admin/changes/{change_id}/undo')
def admin_undo(change_id:int,request:Request):
    admin=_require_admin(request)
    try: result=undo_change(change_id,admin['id'])
    except ValueError as e: raise HTTPException(409,str(e))
    try:
        recalculate_matches('ARENA'); recalculate_matches('PAVIDEZ')
    except Exception: pass
    audit(admin['id'],'UNDO_CHANGE','change',change_id,result,_client_ip(request))
    return result

@app.get('/api/admin/health')
def admin_health(request:Request):
    _require_admin(request)
    health=system_health()
    health['operation']=runtime_snapshot()
    health['counts']['sync_logs']=int((row('SELECT COUNT(*) n FROM sync_log') or {}).get('n') or 0)
    health['maintenance']={
        'last_daily_backup':str((row("SELECT value FROM settings WHERE key='maintenance_last_backup_date'") or {}).get('value') or ''),
        'log_retention':10000,
    }
    return health

@app.get('/api/admin/runtime')
def admin_runtime(request:Request):
    _require_admin(request)
    return runtime_snapshot()

@app.put('/api/admin/runtime/pause')
def admin_runtime_pause(payload:RuntimePausePayload,request:Request):
    admin=_require_admin(request)
    state=set_paused(payload.paused)
    audit(admin['id'],'RUNTIME_PAUSE' if payload.paused else 'RUNTIME_RESUME','system','runtime',{},_client_ip(request))
    return state

@app.post('/api/admin/runtime/cancel')
def admin_runtime_cancel(request:Request):
    admin=_require_admin(request)
    state=request_cancel()
    audit(admin['id'],'RUNTIME_CANCEL','system','runtime',{},_client_ip(request))
    return state

@app.post('/api/admin/logs/archive')
async def admin_archive_logs(request:Request):
    admin=_require_admin(request)
    try:
        with runtime_job('maintenance','Compactação dos registros antigos',1):
            runtime_update(current='Criando arquivo compactado...')
            result=await asyncio.to_thread(archive_old_sync_logs,10000)
            runtime_update(processed=1)
    except JobBusyError as exc:
        raise HTTPException(409,str(exc))
    audit(admin['id'],'SYNC_LOG_ARCHIVE','system','sync_log',result,_client_ip(request))
    return result

@app.post('/api/admin/shutdown')
async def admin_shutdown(payload:ShutdownPayload,request:Request):
    admin=_require_admin(request)
    if str(payload.confirmation or '').strip().upper()!='ENCERRAR':
        raise HTTPException(400,'Digite ENCERRAR para confirmar.')
    callback=getattr(app.state,'request_shutdown',None)
    if not callable(callback):
        raise HTTPException(409,'Encerramento pelo painel indisponível nesta execução.')
    audit(admin['id'],'SAFE_SHUTDOWN','system','server',{},_client_ip(request))
    async def delayed_shutdown():
        await asyncio.sleep(.7)
        callback()
    asyncio.create_task(delayed_shutdown())
    return {'ok':True,'message':'QualiMatch será encerrado com segurança.'}

@app.post('/api/backups/{name}/restore')
def backup_restore(name:str,payload:RestorePayload,request:Request):
    admin=_require_admin(request)
    if str(payload.confirmation or '').strip().upper()!='RESTAURAR':
        raise HTTPException(400,'Digite RESTAURAR para confirmar a restauração.')
    try: result=restore_backup(name)
    except (ValueError,FileNotFoundError) as e: raise HTTPException(409,str(e))
    audit(admin['id'],'BACKUP_RESTORE','backup',name,{'safety_backup':result.get('safety_backup')},_client_ip(request))
    return result

@app.get('/api/logs')
def logs(request:Request,limit:int=200,date:str|None=None,page:int|None=None,page_size:int=25):
    _require_admin(request)
    if page is None: return sync_logs(min(limit,1000),date)
    current,size,offset=_page_args(page,page_size)
    total=count_sync_logs(date)
    current,offset=_page_offset_for_total(current,size,total)
    return _page_response(sync_logs(size,date,offset),total,current,size)
@app.get('/api/diagnostics')
def diagnostic(request:Request): _require_admin(request); return diagnostics()

@app.post('/api/backups')
def create_backup(request:Request):
    admin=_require_admin(request)
    name=automatic_backup('manual',0)
    audit(admin['id'],'BACKUP_CREATE','backup',name,{},_client_ip(request))
    return {'ok':True,'name':name,'database':backend_name()}
@app.get('/api/backups')
def backups(request:Request):
    _require_admin(request)
    files=list(BACKUP_DIR.glob('*.db'))+[p for p in BACKUP_DIR.glob('*.json.gz') if not p.name.startswith('logs_arquivados_')]
    return [{'name':p.name,'size':p.stat().st_size,'modified':datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec='seconds')} for p in sorted(files,key=lambda x:x.stat().st_mtime,reverse=True)]
@app.get('/api/backups/{name}')
def backup_file(name:str,request:Request):
    _require_admin(request)
    p=BACKUP_DIR/Path(name).name
    if not p.exists(): raise HTTPException(404,'Backup não encontrado')
    return FileResponse(p,filename=p.name)
