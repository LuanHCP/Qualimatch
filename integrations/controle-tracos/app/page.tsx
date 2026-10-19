'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Image from 'next/image';
import {
  BarChart3,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ClipboardList,
  Database,
  Download,
  Eye,
  EyeOff,
  ExternalLink,
  FolderOpen,
  FilePenLine,
  FileSpreadsheet,
  FileText,
  LayoutDashboard,
  LogOut,
  Plus,
  Paperclip,
  Search,
  Settings,
  ShieldCheck,
  RefreshCw,
  Trash2,
  UserPlus,
  Wrench,
  Users,
  Upload,
  X,
} from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  AppUser,
  buildTraceCode,
  capDistributors,
  categories,
  Category,
  cementSuppliers,
  initialTraces,
  initialUsers,
  materials,
  statuses,
  Status,
  statusMeta,
  statusSeals,
  Trace,
  units,
  usinaTypes,
} from '@/lib/trace-data';

type View =
  | 'dashboard'
  | 'traces'
  | 'inventory'
  | 'reports'
  | 'people'
  | 'admin';
type DataMode = 'checking' | 'local' | 'database';
type StampStatus = 'Aprovado' | 'Restrito' | 'Não conforme';
type SubmitLike = { preventDefault(): void };
const API = 'http://127.0.0.1:3001';
const stampStatuses: StampStatus[] = ['Aprovado', 'Restrito', 'Não conforme'];

// Lê o corpo de erro que o servidor devolve (ex.: {"error":"..."}) para
// mostrar o motivo real da falha em vez de uma mensagem genérica — isso é
// o que permite diagnosticar um "não foi possível anexar" de verdade.
async function describeApiError(
  response: Response,
  fallback = 'Não foi possível concluir a operação.',
): Promise<string> {
  if (response.status === 401)
    return 'Sua sessão expirou. Saia e entre novamente para continuar.';
  try {
    const body = (await response.json()) as { error?: string };
    if (body?.error) return body.error;
  } catch {}
  return `${fallback} (erro ${response.status}).`;
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = typeof reader.result === 'string' ? reader.result : '';
      const comma = result.indexOf(',');
      resolve(comma >= 0 ? result.slice(comma + 1) : result);
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

async function uploadFiles(
  traceId: string,
  kind: 'trace' | 'checklist',
  files: File[],
  token: string,
) {
  if (!files.length) return;
  const encoded = await Promise.all(
    files.map(async (file) => ({
      name: file.name,
      dataBase64: await fileToBase64(file),
    })),
  );
  const response = await fetch(`${API}/api/traces/${traceId}/files`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ kind, files: encoded }),
  });
  if (!response.ok)
    throw new Error(
      await describeApiError(response, 'Não foi possível salvar o anexo'),
    );
}

// Converte um Uint8Array (ex.: o PDF já carimbado, gerado pelo pdf-lib) para
// base64 em pedaços, evitando estourar a pilha de chamadas do
// String.fromCharCode em arquivos grandes.
function uint8ToBase64(bytes: Uint8Array): string {
  let binary = '';
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
  }
  return btoa(binary);
}

async function fetchTraceFileBytes(
  traceId: string,
  fileName: string,
  token: string,
): Promise<Uint8Array> {
  const response = await fetch(
    `${API}/api/traces/${traceId}/files/${encodeURIComponent(fileName)}`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  if (!response.ok)
    throw new Error(
      await describeApiError(response, 'Não foi possível baixar o arquivo'),
    );
  const buffer = await response.arrayBuffer();
  return new Uint8Array(buffer);
}

async function deleteTraceFile(
  traceId: string,
  fileName: string,
  token: string,
) {
  const response = await fetch(
    `${API}/api/traces/${traceId}/files/${encodeURIComponent(fileName)}`,
    { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } },
  );
  if (!response.ok)
    throw new Error(
      await describeApiError(response, 'Não foi possível remover o arquivo'),
    );
}

type TraceFileEntry = {
  name: string;
  kind: 'trace' | 'checklist';
  size?: number;
  updatedAt?: string;
};

async function fetchTraceFiles(
  traceId: string,
  token: string,
): Promise<TraceFileEntry[]> {
  const response = await fetch(`${API}/api/traces/${traceId}/files`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok)
    throw new Error(
      await describeApiError(response, 'Não foi possível listar os anexos'),
    );
  return response.json();
}

type TraceLocalMatch = { documentId: string; fileName: string };

// Procura, na mesma pasta local já configurada em "Documentos sincronizados",
// um PDF cujo código bate com o do traço — reaproveita a mesma varredura
// usada no acervo, então se o traço já "acha" o arquivo lá, aqui a gente só
// pergunta se pode puxar ele como anexo, sem precisar escolher o arquivo à
// mão de novo.
async function fetchTraceLocalMatch(
  traceId: string,
  token: string,
): Promise<TraceLocalMatch | null> {
  const response = await fetch(`${API}/api/traces/${traceId}/local-match`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) return null;
  const body = (await response.json()) as { match: TraceLocalMatch | null };
  return body.match || null;
}

async function attachTraceLocalMatch(
  traceId: string,
  documentId: string,
  token: string,
): Promise<string> {
  const response = await fetch(
    `${API}/api/traces/${traceId}/local-match/attach`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ documentId }),
    },
  );
  if (!response.ok)
    throw new Error(
      await describeApiError(response, 'Não foi possível anexar o arquivo local'),
    );
  const body = (await response.json()) as { attached: string };
  return body.attached;
}

// Carrega pdfjs-dist e pdf-lib como dependências normais do projeto (via
// import() dinâmico), em vez de injetar <script> de CDN como na primeira
// tentativa — isso evita qualquer risco de o carregamento das libs mexer no
// DOM durante o carregamento inicial da página. O worker do pdf.js é servido
// como arquivo estático próprio (public/pdf.worker.min.mjs), então não
// depende de nenhuma configuração especial do empacotador.
let pdfLibsPromise: Promise<{
  pdfjsLib: typeof import('pdfjs-dist');
  pdfLib: typeof import('pdf-lib');
}> | null = null;

function loadPdfLibs() {
  if (!pdfLibsPromise) {
    pdfLibsPromise = Promise.all([import('pdfjs-dist'), import('pdf-lib')])
      .then(([pdfjsLib, pdfLib]) => {
        pdfjsLib.GlobalWorkerOptions.workerSrc = '/pdf.worker.min.mjs';
        return { pdfjsLib, pdfLib };
      })
      .catch((error) => {
        pdfLibsPromise = null;
        throw error;
      });
  }
  return pdfLibsPromise;
}

// Carrega só o pdf-lib (sem pdfjs-dist) para gerar o PDF do relatório —
// mais leve que loadPdfLibs(), que também baixa o pdfjs-dist usado só na
// ferramenta de posicionar o selo.
let pdfLibOnlyPromise: Promise<typeof import('pdf-lib')> | null = null;
function loadPdfLibOnly() {
  if (!pdfLibOnlyPromise) {
    pdfLibOnlyPromise = import('pdf-lib').catch((error) => {
      pdfLibOnlyPromise = null;
      throw error;
    });
  }
  return pdfLibOnlyPromise;
}

function Combo({
  label,
  value,
  options,
  onChange,
  placeholder = 'Selecione...',
}: {
  label?: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node))
        setOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);
  const filtered = options.filter((item) =>
    item.toLocaleLowerCase('pt-BR').includes(query.toLocaleLowerCase('pt-BR')),
  );
  return (
    <div className="field" ref={ref}>
      {label && (
        <label>
          {label} <span>*</span>
        </label>
      )}
      <button
        type="button"
        className="select-trigger"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <span className={value ? '' : 'placeholder'}>
          {value || placeholder}
        </span>
        <ChevronDown size={15} />
      </button>
      {open && (
        <div className="select-menu">
          <div className="select-search">
            <Search size={14} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Pesquisar opção..."
            />
          </div>
          <div className="options">
            {filtered.length ? (
              filtered.map((item) => (
                <button
                  type="button"
                  key={item}
                  onClick={() => {
                    onChange(item);
                    setOpen(false);
                    setQuery('');
                  }}
                >
                  {item}
                  {item === value && <b>✓</b>}
                </button>
              ))
            ) : (
              <p>Nenhuma opção encontrada</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Pill({ status }: { status: Status }) {
  return (
    <span className={`pill ${statusMeta[status].className}`}>
      <i />
      {status}
    </span>
  );
}

function SyncFolderSettings({ flash }: { flash: (message: string) => void }) {
  const [inventoryPath, setInventoryPath] = useState('');
  const [traceLibraryPath, setTraceLibraryPath] = useState('');
  const [sitePaths, setSitePaths] = useState<Record<string, string>>({});
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetch(`${API}/api/config`)
      .then(
        (response) =>
          response.json() as Promise<{
            sharePointPath?: string;
            inventoryPath?: string;
            traceLibraryPath?: string;
            sitePaths?: Record<string, string>;
          }>,
      )
      .then((config) => {
        setInventoryPath(config.inventoryPath || '');
        setTraceLibraryPath(
          config.traceLibraryPath || config.sharePointPath || '',
        );
        setSitePaths(config.sitePaths || {});
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
  }, []);

  const save = async (showConfirmation = true) => {
    setSaving(true);
    try {
      const response = await fetch(`${API}/api/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sharePointPath: traceLibraryPath,
          certificatesPath: traceLibraryPath,
          inventoryPath,
          traceLibraryPath,
          sitePaths,
        }),
      });
      if (!response.ok)
        throw new Error(await describeApiError(response, 'Falha ao salvar.'));
      if (showConfirmation) flash('Configurações salvas.');
      return true;
    } catch {
      flash('Não foi possível salvar o caminho agora.');
      return false;
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="sync-settings">
      <strong>Acervo de cartas-traço</strong>
      <small>
        Caminho oficial que contém as pastas 03, 04 e 05. Novos traços e
        mudanças de status são organizados automaticamente por situação e
        tipo de material.
      </small>
      <div className="sync-settings-field">
        <input
          value={traceLibraryPath}
          onChange={(event) => setTraceLibraryPath(event.target.value)}
          placeholder={'Ex.: C:\\Motiva\\...\\02. CARTAS TRAÇOS'}
          disabled={!loaded || saving}
        />
        <button
          type="button"
          onClick={() => void save()}
          disabled={saving || !traceLibraryPath.trim()}
        >
          {saving ? 'Salvando...' : 'Salvar acervo'}
        </button>
      </div>
      <details className="sync-sites">
        <summary>Caminhos por sede</summary>
        <small>
          Preencha somente as sedes que usam um acervo diferente do caminho
          oficial acima.
        </small>
        <div className="sync-sites-grid">
          {units.map((unit) => (
            <label className="sync-site-field" key={unit}>
              <span>{unit}</span>
              <input
                value={sitePaths[unit] || ''}
                onChange={(event) =>
                  setSitePaths((current) => ({
                    ...current,
                    [unit]: event.target.value,
                  }))
                }
                placeholder="Usar acervo oficial"
                disabled={!loaded || saving}
              />
            </label>
          ))}
        </div>
      </details>
      <strong>Planilha do inventário</strong>
      <small>
        Arquivo Excel usado na tela Inventário. São lidas apenas as abas
        CONCRETO, BGS, BGTC, CBUQ, MRAF, TSD, PMF e MACADAME.
      </small>
      <div className="sync-settings-field">
        <input
          value={inventoryPath}
          onChange={(event) => setInventoryPath(event.target.value)}
          placeholder="Ex.: C:\Motiva\...\INVENTARIO TRAÇOS.xlsx"
          disabled={!loaded || saving}
        />
        <button
          type="button"
          onClick={() => void save()}
          disabled={saving || !inventoryPath.trim()}
        >
          {saving ? 'Salvando...' : 'Salvar planilha'}
        </button>
      </div>
    </div>
  );
}

type InventoryRecord = {
  id: string;
  sheet: string;
  code: string;
  trace: string;
  type: string;
  contract: string;
  company: string;
  plant: string;
  status: string;
  approvalDate: string;
  validityDate: string;
  fileName: string;
  link: string;
  documentId?: string;
  documentCount?: number;
  folderId?: string;
  fileCount?: number;
};

function inventoryStatusClass(status: string) {
  const key = status
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^A-Za-z]/g, '')
    .toUpperCase();
  if (key.includes('APROVADO')) return 'approved';
  if (key.includes('RESTRITO')) return 'restricted';
  if (key.includes('REPROVADO') || key.includes('NAOCONFORME'))
    return 'nonconforming';
  if (key.includes('SOLICITADO')) return 'requested';
  return 'analysis';
}

function InventoryScreen({
  token,
  flash,
}: {
  token: string;
  flash: (message: string) => void;
}) {
  const [records, setRecords] = useState<InventoryRecord[]>([]);
  const [query, setQuery] = useState('');
  const [sheet, setSheet] = useState('Todas');
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    fetch(`${API}/api/inventory`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (response) => {
        if (!response.ok)
          throw new Error(
            await describeApiError(response, 'Falha ao ler o inventário'),
          );
        return response.json() as Promise<{ records: InventoryRecord[] }>;
      })
      .then((result) => setRecords(result.records || []))
      .catch((error) =>
        flash(
          error instanceof Error
            ? error.message
            : 'Não foi possível carregar o inventário.',
        ),
      )
      .finally(() => setLoading(false));
  }, [token, flash]);

  const openFolder = async (item: InventoryRecord) => {
    if (!item.folderId) return;
    setDownloading(item.id);
    try {
      const response = await fetch(
        `${API}/api/inventory/folders/${item.folderId}/open`,
        {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
        },
      );
      if (!response.ok)
        throw new Error(
          await describeApiError(response, 'Falha ao abrir a pasta'),
        );
    } catch (error) {
      flash(
        error instanceof Error ? error.message : 'Não foi possível abrir a pasta.',
      );
    } finally {
      setDownloading('');
    }
  };

  const downloadDocument = async (item: InventoryRecord) => {
    if (!item.documentId) return;
    setDownloading(item.id);
    try {
      const response = await fetch(
        `${API}/api/inventory/files/${item.documentId}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (!response.ok)
        throw new Error(
          await describeApiError(response, 'Falha ao baixar o PDF'),
        );
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = item.fileName || `${item.code || 'carta-traco'}.pdf`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1500);
    } catch (error) {
      flash(
        error instanceof Error ? error.message : 'Não foi possível baixar o PDF.',
      );
    } finally {
      setDownloading('');
    }
  };

  useEffect(() => {
    const timer = window.setTimeout(load, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const sheetOptions = useMemo(
    () => ['Todas', ...Array.from(new Set(records.map((item) => item.sheet)))],
    [records],
  );
  const visible = useMemo(() => {
    const search = query.trim().toLocaleLowerCase('pt-BR');
    return records.filter(
      (item) =>
        (sheet === 'Todas' || item.sheet === sheet) &&
        (!search ||
          `${item.code} ${item.trace} ${item.type} ${item.contract} ${item.company} ${item.plant} ${item.status}`
            .toLocaleLowerCase('pt-BR')
            .includes(search)),
    );
  }, [records, query, sheet]);
  const withLinks = records.filter((item) => item.folderId).length;
  const approved = records.filter(
    (item) => inventoryStatusClass(item.status) === 'approved',
  ).length;

  return (
    <>
      <div className="page-heading inventory-heading">
        <div>
          <p className="eyebrow">ACERVO TÉCNICO</p>
          <h2>Inventário de traços</h2>
          <p>Consulta direta às pastas oficiais, com dados complementares da planilha.</p>
        </div>
        <button className="secondary icon-command" onClick={load}>
          <RefreshCw size={15} /> Atualizar
        </button>
      </div>
      <div className="inventory-summary">
        <div>
          <span>Total catalogado</span>
          <strong>{records.length}</strong>
        </div>
        <div>
          <span>Pastas localizadas</span>
          <strong>{withLinks}</strong>
        </div>
        <div>
          <span>Aprovados</span>
          <strong>{approved}</strong>
        </div>
        <div>
          <span>Tipos consultados</span>
          <strong>{Math.max(0, sheetOptions.length - 1)}</strong>
        </div>
      </div>
      <div className="inventory-toolbar">
        <label className="searchbox">
          <Search size={15} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Buscar código, traço, empresa, contrato ou usina"
          />
        </label>
        <Combo
          value={sheet}
          options={sheetOptions}
          onChange={setSheet}
          placeholder="Todos os tipos"
        />
      </div>
      <div className="inventory-table-wrap">
        <table className="inventory-table">
          <thead>
            <tr>
              <th>Código</th>
              <th>Traço</th>
              <th>Tipo</th>
              <th>Empresa / contrato</th>
              <th>Usina / origem</th>
              <th>Status</th>
              <th>Validade</th>
              <th aria-label="Pasta do traço" />
            </tr>
          </thead>
          <tbody>
            {visible.map((item) => (
              <tr key={item.id}>
                <td>
                  <strong>{item.code || '—'}</strong>
                </td>
                <td title={item.trace}>{item.trace || '—'}</td>
                <td>{item.sheet}</td>
                <td>
                  {item.company || '—'}
                  {item.contract && <small>{item.contract}</small>}
                </td>
                <td>{item.plant || '—'}</td>
                <td>
                  <span
                    className={`inventory-status ${inventoryStatusClass(item.status)}`}
                  >
                    {item.status || 'Sem status'}
                  </span>
                </td>
                <td>{item.validityDate || item.approvalDate || '—'}</td>
                <td>
                  <div className="inventory-actions">
                  {item.documentId && (
                    <button
                      type="button"
                      className="inventory-download"
                      onClick={() => void downloadDocument(item)}
                      disabled={downloading === item.id}
                      title={`Baixar ${item.fileName || 'PDF da carta-traço'}`}
                      aria-label={`Baixar PDF de ${item.code || item.trace}`}
                    >
                      <Download size={15} />
                    </button>
                  )}
                  {item.folderId ? (
                    <button
                      type="button"
                      className="inventory-download"
                      onClick={() => void openFolder(item)}
                      disabled={downloading === item.id}
                      title={`Abrir pasta: ${item.fileCount || 0} arquivo(s), ${
                        item.documentCount || 0
                      } PDF(s)`}
                      aria-label={`Abrir pasta de ${item.code || item.trace}`}
                    >
                      <FolderOpen size={15} />
                    </button>
                  ) : item.link ? (
                    <a
                      className="inventory-download"
                      href={item.link}
                      target="_blank"
                      rel="noreferrer"
                      title={item.fileName || 'Abrir documento'}
                      aria-label={`Abrir documento de ${item.code || item.trace}`}
                    >
                      <ExternalLink size={15} />
                    </a>
                  ) : !item.documentId ? (
                    <span className="inventory-no-file">—</span>
                  ) : null}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && !visible.length && (
          <div className="inventory-empty">
            <FileSpreadsheet size={24} />
            <p>Nenhum traço encontrado com esses filtros.</p>
          </div>
        )}
        {loading && <div className="inventory-empty">Lendo acervo...</div>}
      </div>
    </>
  );
}

type StampBox = { xPct: number; yPct: number; widthPct: number };

function clampNum(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function StampPositioner({
  traceId,
  token,
  initialStatus,
  initialConcessionaria,
  onApplied,
}: {
  traceId: string;
  token: string;
  initialStatus?: StampStatus | null;
  initialConcessionaria?: string;
  onApplied: (
    status: StampStatus,
    fileName: string,
    dateLabel: string,
  ) => void;
}) {
  const [status, setStatus] = useState<StampStatus | null>(
    initialStatus || null,
  );
  const [concessionaria, setConcessionaria] = useState(
    initialConcessionaria || '',
  );
  const [pageTarget, setPageTarget] = useState<'one' | 'all'>('one');
  const sealSrc = status ? (statusSeals[status] as string) : null;
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const canvasWrapRef = useRef<HTMLDivElement>(null);
  const originalBytesRef = useRef<Uint8Array | null>(null);
  const pdfFileNameRef = useRef('');
  const dragRef = useRef<{
    mode: 'move' | 'resize';
    clientX: number;
    clientY: number;
    box: StampBox;
  } | null>(null);
  const [canvasSize, setCanvasSize] = useState({ width: 0, height: 0 });
  const [phase, setPhase] = useState<
    'loading' | 'ready' | 'saving' | 'error' | 'no-pdf' | 'uploading'
  >('loading');
  const [error, setError] = useState('');
  const [box, setBox] = useState<StampBox>({
    xPct: 60,
    yPct: 66,
    widthPct: 28,
  });
  const [aspect, setAspect] = useState(1);
  const [pageNumber, setPageNumber] = useState(1);
  const [pageCount, setPageCount] = useState(1);
  const [isRendering, setIsRendering] = useState(false);
  const [reloadTick, setReloadTick] = useState(0);
  const [stampDate, setStampDate] = useState(() => {
    const now = new Date();
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  });
  const stampDateLabel = useMemo(() => {
    const [y, m, d] = stampDate.split('-').map(Number);
    if (!y || !m || !d) return '';
    return new Intl.DateTimeFormat('pt-BR', { dateStyle: 'long' }).format(
      new Date(y, m - 1, d),
    );
  }, [stampDate]);

  const renderFromBytes = useCallback(
    async (bytes: Uint8Array, fileName: string, requestedPage = 1) => {
      originalBytesRef.current = bytes;
      pdfFileNameRef.current = fileName;
      setIsRendering(true);
      const { pdfjsLib } = await loadPdfLibs();
      const doc = await pdfjsLib.getDocument({ data: bytes.slice() }).promise;
      const nextPage = clampNum(requestedPage, 1, doc.numPages);
      const page = await doc.getPage(nextPage);
      // Escala maior que antes: agora que o editor ocupa a tela em vez de um
      // modal pequeno, dá pra mostrar a página maior e mais nítida.
      const viewport = page.getViewport({ scale: 1.7 });
      setPageCount(doc.numPages);
      setPageNumber(nextPage);
      setPhase('ready');
      await new Promise<void>((resolve) =>
        window.requestAnimationFrame(() => resolve()),
      );
      const canvas = canvasRef.current;
      if (!canvas)
        throw new Error('Não foi possível preparar o editor do PDF.');
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      const ctx = canvas.getContext('2d');
      if (!ctx) throw new Error('Não foi possível preparar o desenho do PDF.');
      await page.render({ canvas, canvasContext: ctx, viewport }).promise;
      setCanvasSize({ width: viewport.width, height: viewport.height });
      setIsRendering(false);
    },
    [],
  );

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        setPhase('loading');
        const files = await fetchTraceFiles(traceId, token);
        const pdfFile = files.find(
          (item) =>
            item.kind === 'trace' && item.name.toLowerCase().endsWith('.pdf'),
        );
        if (!pdfFile) {
          if (cancelled) return;
          setPhase('no-pdf');
          return;
        }
        const bytes = await fetchTraceFileBytes(traceId, pdfFile.name, token);
        if (cancelled) return;
        await renderFromBytes(bytes, pdfFile.name);
      } catch (err) {
        if (cancelled) return;
        setIsRendering(false);
        setError(
          err instanceof Error
            ? err.message
            : 'Não foi possível abrir o PDF para posicionar o selo.',
        );
        setPhase('error');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [traceId, token, reloadTick, renderFromBytes]);

  const attachPdf = async (file: File) => {
    setPhase('uploading');
    try {
      const dataBase64 = await fileToBase64(file);
      const response = await fetch(`${API}/api/traces/${traceId}/files`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          kind: 'trace',
          files: [{ name: file.name, dataBase64 }],
        }),
      });
      if (!response.ok)
        throw new Error(
          await describeApiError(response, 'Não foi possível anexar o PDF'),
        );
      const bytes = new Uint8Array(await file.arrayBuffer());
      await renderFromBytes(bytes, file.name);
    } catch (err) {
      setIsRendering(false);
      setError(
        err instanceof Error ? err.message : 'Não foi possível anexar o PDF.',
      );
      setPhase('error');
    }
  };

  const heightPct =
    canvasSize.width && canvasSize.height
      ? (((box.widthPct / 100) * canvasSize.width * aspect) /
          canvasSize.height) *
        100
      : box.widthPct;

  const openPage = async (nextPage: number) => {
    if (!originalBytesRef.current || isRendering) return;
    try {
      await renderFromBytes(
        originalBytesRef.current,
        pdfFileNameRef.current,
        nextPage,
      );
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Não foi possível abrir esta página.',
      );
      setIsRendering(false);
      setPhase('error');
    }
  };

  const startDrag = (
    mode: 'move' | 'resize',
    event: React.PointerEvent<HTMLElement>,
  ) => {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = {
      mode,
      clientX: event.clientX,
      clientY: event.clientY,
      box,
    };
  };

  const moveDrag = (event: React.PointerEvent<HTMLElement>) => {
    const drag = dragRef.current;
    const bounds = canvasWrapRef.current?.getBoundingClientRect();
    if (!drag || !bounds?.width || !bounds.height) return;
    const dxPct = ((event.clientX - drag.clientX) / bounds.width) * 100;
    const dyPct = ((event.clientY - drag.clientY) / bounds.height) * 100;
    if (drag.mode === 'move') {
      const dragHeightPct =
        (((drag.box.widthPct / 100) * bounds.width * aspect) / bounds.height) *
        100;
      setBox({
        ...drag.box,
        xPct: clampNum(drag.box.xPct + dxPct, 0, 100 - drag.box.widthPct),
        yPct: clampNum(
          drag.box.yPct + dyPct,
          0,
          Math.max(0, 100 - dragHeightPct),
        ),
      });
      return;
    }
    const maxWidthByHeight =
      ((((100 - drag.box.yPct) / 100) * bounds.height) /
        bounds.width /
        aspect) *
      100;
    setBox({
      ...drag.box,
      widthPct: clampNum(
        drag.box.widthPct + dxPct,
        6,
        Math.max(6, Math.min(100 - drag.box.xPct, maxWidthByHeight)),
      ),
    });
  };

  const stopDrag = (event: React.PointerEvent<HTMLElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId))
      event.currentTarget.releasePointerCapture(event.pointerId);
    dragRef.current = null;
  };

  const confirm = async () => {
    if (!originalBytesRef.current || !status || !sealSrc) return;
    setPhase('saving');
    try {
      const { pdfLib } = await loadPdfLibs();
      const pdfDoc = await pdfLib.PDFDocument.load(
        originalBytesRef.current.slice(),
      );
      const sealResponse = await fetch(sealSrc);
      const sealBytes = new Uint8Array(await sealResponse.arrayBuffer());
      const embeddedSeal = await pdfDoc.embedPng(sealBytes);
      const allPages = pdfDoc.getPages();
      // Passo 4: o selo pode ir só na página que está sendo visualizada ou em
      // todas as páginas do documento — mesma proporção/posição em cada uma.
      const targetPages =
        pageTarget === 'all'
          ? allPages
          : [allPages[clampNum(pageNumber - 1, 0, allPages.length - 1)]];
      const trimmedConcessionaria = concessionaria.trim();
      const textFont =
        trimmedConcessionaria || stampDateLabel
          ? await pdfDoc.embedFont(pdfLib.StandardFonts.HelveticaBold)
          : null;
      for (const page of targetPages) {
        const { width: pageWidthPt, height: pageHeightPt } = page.getSize();
        const widthPt = (box.widthPct / 100) * pageWidthPt;
        const stampHeightPt = widthPt * aspect;
        const xPt = (box.xPct / 100) * pageWidthPt;
        const yPt =
          pageHeightPt - (box.yPct / 100) * pageHeightPt - stampHeightPt;
        page.drawImage(embeddedSeal, {
          x: xPt,
          y: yPt,
          width: widthPt,
          height: stampHeightPt,
        });
        // Escreve a concessionária e a data centralizadas logo abaixo do
        // selo — mesma ideia usada quando o carimbo é aplicado manualmente.
        let cursorY = yPt;
        if (trimmedConcessionaria && textFont) {
          const concSize = Math.max(7, Math.min(11, widthPt * 0.09));
          const concWidth = textFont.widthOfTextAtSize(
            trimmedConcessionaria,
            concSize,
          );
          cursorY = Math.max(4, cursorY - concSize - 4);
          page.drawText(trimmedConcessionaria, {
            x: xPt + widthPt / 2 - concWidth / 2,
            y: cursorY,
            size: concSize,
            font: textFont,
            color: pdfLib.rgb(0.15, 0.15, 0.15),
          });
        }
        if (stampDateLabel && textFont) {
          const dateSize = Math.max(7, Math.min(11, widthPt * 0.1));
          const dateWidth = textFont.widthOfTextAtSize(
            stampDateLabel,
            dateSize,
          );
          cursorY = Math.max(4, cursorY - dateSize - 4);
          page.drawText(stampDateLabel, {
            x: xPt + widthPt / 2 - dateWidth / 2,
            y: cursorY,
            size: dateSize,
            font: textFont,
            color: pdfLib.rgb(0.15, 0.15, 0.15),
          });
        }
      }
      const savedBytes = await pdfDoc.save();
      const sourceName = pdfFileNameRef.current
        .replace(/^trace-/, '')
        .replace(/^(carimbado-)+/, '');
      const stampedName = `carimbado-${sourceName}`;
      const response = await fetch(`${API}/api/traces/${traceId}/files`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          kind: 'trace',
          files: [{ name: stampedName, dataBase64: uint8ToBase64(savedBytes) }],
        }),
      });
      if (!response.ok)
        throw new Error(
          await describeApiError(
            response,
            'Não foi possível salvar o PDF carimbado',
          ),
        );
      const downloadBytes = savedBytes.buffer.slice(
        savedBytes.byteOffset,
        savedBytes.byteOffset + savedBytes.byteLength,
      ) as ArrayBuffer;
      const url = URL.createObjectURL(
        new Blob([downloadBytes], { type: 'application/pdf' }),
      );
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = stampedName;
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      onApplied(status, stampedName, stampDateLabel);
      setPhase('ready');
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Não foi possível gerar o PDF carimbado.',
      );
      setPhase('error');
    }
  };

  if (phase === 'loading' || phase === 'uploading') {
    return (
      <div className="card-section">
        <div className="stamp-positioner-error">
          <p>
            {phase === 'uploading'
              ? 'Enviando o PDF...'
              : 'Carregando o PDF da carta traço...'}
          </p>
        </div>
      </div>
    );
  }

  if (phase === 'no-pdf') {
    return (
      <div className="card-section">
        <div className="stamp-positioner-dropzone">
          <FileText size={30} />
          <strong>Nenhum PDF anexado ainda</strong>
          <p>
            Anexe a carta traço em PDF para visualizar o documento em tela
            cheia e posicionar o selo.
          </p>
          <label className="secondary" style={{ cursor: 'pointer' }}>
            <Upload size={14} /> Anexar PDF...
            <input
              type="file"
              accept="application/pdf"
              style={{ display: 'none' }}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void attachPdf(file);
              }}
            />
          </label>
        </div>
      </div>
    );
  }

  if (phase === 'error') {
    return (
      <div className="card-section">
        <div className="stamp-positioner-dropzone error">
          <p>{error}</p>
          <button
            type="button"
            className="secondary"
            onClick={() => setReloadTick((tick) => tick + 1)}
          >
            Tentar de novo
          </button>
        </div>
      </div>
    );
  }

  // Fluxo em 4 passos numerados, inspirado na referência que o usuário
  // mandou: 1) documento (aqui é o traço, escolhido antes pelo ToolsScreen),
  // 2) selo, 3) concessionária + data e 4) posição/tamanho/páginas — mantendo
  // o documento grande e navegável em tela cheia dentro do próprio passo 4.
  return (
    <>
      <section className="card-section">
        <h3 className="section-title">
          <span className="step-num">2</span>Selo
        </h3>
        <div className="stamp-choice-grid">
          {stampStatuses.map((option) => (
            <button
              type="button"
              key={option}
              className={`stamp-choice ${statusMeta[option].className} ${status === option ? 'selected' : ''}`}
              onClick={() => setStatus(option)}
            >
              <Image
                src={statusSeals[option] as string}
                alt={`Selo ${option}`}
                width={64}
                height={64}
                unoptimized
              />
              <span>{option}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="card-section">
        <h3 className="section-title">
          <span className="step-num">3</span>Concessionária e data
        </h3>
        <div className="field-grid">
          <div className="field">
            <label htmlFor="stamp-conc-input">Concessionária</label>
            <input
              id="stamp-conc-input"
              type="text"
              value={concessionaria}
              maxLength={60}
              placeholder="Nome da concessionária"
              onChange={(event) => setConcessionaria(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="stamp-date-input">Data do carimbo</label>
            <input
              id="stamp-date-input"
              type="date"
              value={stampDate}
              onChange={(event) => setStampDate(event.target.value)}
            />
          </div>
        </div>
      </section>

      <section className="card-section">
        <h3 className="section-title">
          <span className="step-num">4</span>Posição, tamanho e páginas
        </h3>
        <div className="position-layout">
          <div className="stamp-positioner-canvas-wrap" ref={canvasWrapRef}>
            <canvas ref={canvasRef} />
            {isRendering && (
              <div className="stamp-positioner-loading">Abrindo página...</div>
            )}
            {status && sealSrc && (
              <>
                <Image
                  src={sealSrc}
                  alt="Selo selecionado"
                  width={240}
                  height={240}
                  unoptimized
                  className="stamp-positioner-seal"
                  draggable={false}
                  style={{
                    left: `${box.xPct}%`,
                    top: `${box.yPct}%`,
                    width: `${box.widthPct}%`,
                  }}
                  onLoad={(event) => {
                    const img = event.currentTarget;
                    if (img.naturalWidth > 0)
                      setAspect(img.naturalHeight / img.naturalWidth);
                  }}
                  onPointerDown={(event) => startDrag('move', event)}
                  onPointerMove={moveDrag}
                  onPointerUp={stopDrag}
                  onPointerCancel={stopDrag}
                />
                <button
                  type="button"
                  className="stamp-positioner-resize-handle"
                  style={{
                    left: `calc(${box.xPct}% + ${box.widthPct}% - 10px)`,
                    top: `calc(${box.yPct}% + ${heightPct}% - 10px)`,
                  }}
                  aria-label="Redimensionar selo"
                  onPointerDown={(event) => startDrag('resize', event)}
                  onPointerMove={moveDrag}
                  onPointerUp={stopDrag}
                  onPointerCancel={stopDrag}
                />
              </>
            )}
            <div className="page-controls" aria-label="Navegação do PDF">
              <button
                type="button"
                onClick={() => void openPage(pageNumber - 1)}
                disabled={pageNumber === 1 || isRendering}
                aria-label="Página anterior"
                title="Página anterior"
              >
                <ChevronLeft size={16} />
              </button>
              <span>
                Página <strong>{pageNumber}</strong> de {pageCount}
              </span>
              <button
                type="button"
                onClick={() => void openPage(pageNumber + 1)}
                disabled={pageNumber === pageCount || isRendering}
                aria-label="Próxima página"
                title="Próxima página"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
          <div className="position-controls">
            <div className="field">
              <label>Tamanho do selo</label>
              <div className="size-row">
                <input
                  type="range"
                  min={10}
                  max={60}
                  value={box.widthPct}
                  disabled={!status}
                  onChange={(event) =>
                    setBox((current) => ({
                      ...current,
                      widthPct: Number(event.target.value),
                    }))
                  }
                />
                <span>{Math.round(box.widthPct)}%</span>
              </div>
              <p className="hint">
                {status
                  ? 'Arraste o selo no documento e ajuste pelo canto ou pelo controle acima.'
                  : 'Escolha um selo para poder posicioná-lo no documento.'}
              </p>
            </div>
            <div className="field">
              <label>Aplicar em</label>
              <div className="target-choice">
                <label>
                  <input
                    type="radio"
                    name="stamp-page-target"
                    checked={pageTarget === 'one'}
                    onChange={() => setPageTarget('one')}
                  />
                  Página
                  <input
                    type="number"
                    className="page-num-input"
                    min={1}
                    max={pageCount}
                    value={pageNumber}
                    disabled={pageTarget !== 'one' || isRendering}
                    onChange={(event) =>
                      void openPage(Number(event.target.value) || 1)
                    }
                  />
                </label>
                <label>
                  <input
                    type="radio"
                    name="stamp-page-target"
                    checked={pageTarget === 'all'}
                    onChange={() => setPageTarget('all')}
                  />
                  Todas as páginas ({pageCount})
                </label>
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className="apply-bar">
        <div className="summary">
          {status ? (
            <>
              Selo <strong>{status}</strong>
              {concessionaria.trim() ? ` · ${concessionaria.trim()}` : ''}
              {stampDateLabel ? ` · ${stampDateLabel}` : ''}
              {pageTarget === 'all' ? ' · todas as páginas' : ''}
            </>
          ) : (
            'Escolha um selo para continuar.'
          )}
        </div>
        <button
          type="button"
          className="primary"
          onClick={confirm}
          disabled={!status || phase === 'saving' || isRendering}
        >
          <Download size={16} />
          {phase === 'saving' ? 'Gerando PDF...' : 'Aplicar selo e baixar PDF'}
        </button>
      </div>
    </>
  );
}

function formatFileSize(size?: number) {
  if (size === undefined) return '';
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.ceil(size / 1024)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function TraceFilesPanel({
  traceId,
  token,
  flash,
  onOpenEditor,
}: {
  traceId: string;
  token: string;
  flash: (message: string) => void;
  onOpenEditor: () => void;
}) {
  const [files, setFiles] = useState<TraceFileEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState<'trace' | 'checklist' | null>(
    null,
  );
  const [error, setError] = useState('');
  const [localMatch, setLocalMatch] = useState<TraceLocalMatch | null>(null);
  const [attachingMatch, setAttachingMatch] = useState(false);

  // Ao abrir um traço, traz automaticamente a carta já existente no acervo
  // sincronizado. Se a cópia local falhar, preserva a sugestão na tela para
  // que o usuário ainda possa tentar novamente pelo botão.
  const checkLocalMatch = useCallback(async () => {
    let match: TraceLocalMatch | null = null;
    try {
      match = await fetchTraceLocalMatch(traceId, token);
      if (!match) {
        setLocalMatch(null);
        return;
      }
      setAttachingMatch(true);
      await attachTraceLocalMatch(traceId, match.documentId, token);
      setLocalMatch(null);
      setFiles(await fetchTraceFiles(traceId, token));
      flash(`${match.fileName} carregado da pasta sincronizada.`);
    } catch (err) {
      setLocalMatch(match);
      setError(
        err instanceof Error
          ? err.message
          : 'Não foi possível carregar o arquivo da pasta sincronizada.',
      );
    } finally {
      setAttachingMatch(false);
    }
  }, [traceId, token, flash]);

  useEffect(() => {
    checkLocalMatch();
  }, [checkLocalMatch]);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setFiles(await fetchTraceFiles(traceId, token));
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Não foi possível listar os anexos.',
      );
    } finally {
      setLoading(false);
    }
  }, [traceId, token]);

  const attachLocalMatch = async () => {
    if (!localMatch) return;
    setAttachingMatch(true);
    setError('');
    try {
      await attachTraceLocalMatch(traceId, localMatch.documentId, token);
      const attachedName = localMatch.fileName;
      setLocalMatch(null);
      await load();
      flash(`${attachedName} anexado a partir da pasta local.`);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Não foi possível anexar o arquivo local.',
      );
    } finally {
      setAttachingMatch(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    fetchTraceFiles(traceId, token)
      .then((next) => {
        if (!cancelled) setFiles(next);
      })
      .catch((err: unknown) => {
        if (!cancelled)
          setError(
            err instanceof Error
              ? err.message
              : 'Não foi possível listar os anexos.',
          );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [traceId, token]);

  const attach = async (kind: 'trace' | 'checklist', file?: File) => {
    if (!file) return;
    setUploading(kind);
    setError('');
    try {
      await uploadFiles(traceId, kind, [file], token);
      await load();
      flash(
        `${kind === 'trace' ? 'Carta traço' : 'Checklist'} anexado com sucesso.`,
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Não foi possível salvar o anexo.',
      );
    } finally {
      setUploading(null);
    }
  };

  const download = async (file: TraceFileEntry) => {
    setError('');
    try {
      const bytes = await fetchTraceFileBytes(traceId, file.name, token);
      const blobBytes = bytes.buffer.slice(
        bytes.byteOffset,
        bytes.byteOffset + bytes.byteLength,
      ) as ArrayBuffer;
      const url = URL.createObjectURL(new Blob([blobBytes]));
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = file.name.replace(/^(trace|checklist)-/, '');
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Não foi possível baixar o arquivo.',
      );
    }
  };

  const [removing, setRemoving] = useState<string | null>(null);
  const remove = async (file: TraceFileEntry) => {
    const isStamped = file.name.startsWith('carimbado-');
    const displayName = file.name.replace(/^(trace|checklist)-/, '');
    const confirmed = window.confirm(
      isStamped
        ? `Remover o selo aplicado (${displayName})? A carta traço original continua disponível.`
        : `Remover ${displayName}? Essa ação não pode ser desfeita.`,
    );
    if (!confirmed) return;
    setRemoving(file.name);
    setError('');
    try {
      await deleteTraceFile(traceId, file.name, token);
      await load();
      flash(isStamped ? 'Selo removido.' : `${displayName} removido.`);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Não foi possível remover o arquivo.',
      );
    } finally {
      setRemoving(null);
    }
  };

  const hasPdf = files.some(
    (file) => file.kind === 'trace' && file.name.toLowerCase().endsWith('.pdf'),
  );

  return (
    <section className="trace-files-panel">
      <div className="trace-files-heading">
        <div>
          <span>
            <Paperclip size={14} /> Documentos da análise
          </span>
          <small>Carta traço, checklist e versões carimbadas</small>
        </div>
        <button
          type="button"
          className="secondary compact"
          onClick={onOpenEditor}
          disabled={!hasPdf}
          title={
            hasPdf
              ? 'Abrir editor de PDF'
              : 'Anexe uma carta traço em PDF primeiro'
          }
        >
          <FilePenLine size={15} /> Editar PDF
        </button>
      </div>
      {localMatch && (
        <div className="trace-local-match">
          <FolderOpen size={15} />
          <div>
            <strong>Encontramos este arquivo na pasta local</strong>
            <span>{localMatch.fileName}</span>
          </div>
          <button
            type="button"
            className="primary compact"
            onClick={() => void attachLocalMatch()}
            disabled={attachingMatch}
          >
            {attachingMatch ? 'Anexando...' : 'Anexar'}
          </button>
        </div>
      )}
      {loading ? (
        <p className="trace-files-state">Carregando documentos...</p>
      ) : files.length ? (
        <div className="trace-file-list">
          {files.map((file) => {
            const isStamped = file.name.startsWith('carimbado-');
            return (
              <div
                className={`trace-file-row ${isStamped ? 'stamped' : ''}`}
                key={file.name}
              >
                <FileText size={16} />
                <div>
                  <strong>
                    {file.name.replace(/^(trace|checklist)-/, '')}
                  </strong>
                  <span>
                    {isStamped
                      ? 'Versão carimbada'
                      : file.kind === 'trace'
                        ? 'Carta traço'
                        : 'Checklist'}
                    {file.size !== undefined
                      ? ` · ${formatFileSize(file.size)}`
                      : ''}
                    {file.updatedAt
                      ? ` · ${new Date(file.updatedAt).toLocaleString('pt-BR')}`
                      : ''}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => void download(file)}
                  aria-label={`Baixar ${file.name}`}
                  title="Baixar arquivo"
                >
                  <Download size={15} />
                </button>
                <button
                  type="button"
                  className="trace-file-remove"
                  onClick={() => void remove(file)}
                  disabled={removing === file.name}
                  aria-label={
                    isStamped
                      ? `Remover selo de ${file.name}`
                      : `Remover ${file.name}`
                  }
                  title={isStamped ? 'Remover selo aplicado' : 'Remover arquivo'}
                >
                  <Trash2 size={15} />
                </button>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="trace-files-state">
          Nenhum documento anexado a este traço.
        </p>
      )}
      <div className="trace-files-actions">
        <label className="secondary compact">
          <Upload size={15} />
          {uploading === 'trace' ? 'Enviando...' : 'Anexar carta traço'}
          <input
            type="file"
            accept="application/pdf,.pdf"
            disabled={Boolean(uploading)}
            onChange={(event) => {
              void attach('trace', event.target.files?.[0]);
              event.currentTarget.value = '';
            }}
          />
        </label>
        <label className="secondary compact">
          <Upload size={15} />
          {uploading === 'checklist' ? 'Enviando...' : 'Anexar checklist'}
          <input
            type="file"
            accept="application/pdf,image/*,.doc,.docx,.xls,.xlsx"
            disabled={Boolean(uploading)}
            onChange={(event) => {
              void attach('checklist', event.target.files?.[0]);
              event.currentTarget.value = '';
            }}
          />
        </label>
      </div>
      {error && <div className="trace-files-error">{error}</div>}
    </section>
  );
}

function ToolsScreen({
  traces,
  changeStatus,
  flash,
  token,
  initialTraceId,
}: {
  traces: Trace[];
  changeStatus: (id: string, status: Status) => void | Promise<void>;
  flash: (message: string) => void;
  token: string;
  initialTraceId?: string;
}) {
  const [selectedId, setSelectedId] = useState(
    initialTraceId || traces[0]?.id || '',
  );
  const [showHistory, setShowHistory] = useState(false);
  const selected = traces.find((trace) => trace.id === selectedId) || null;
  const traceLabel = (trace: Trace) =>
    `${trace.code} · ${trace.contract} · ${trace.company}`;
  const traceOptions = useMemo(() => traces.map(traceLabel), [traces]);
  const labelToId = useMemo(
    () => new Map(traces.map((trace) => [traceLabel(trace), trace.id])),
    [traces],
  );
  const selectTrace = (id: string) => {
    setSelectedId(id);
    setShowHistory(false);
  };
  return (
    <div className="tools-page">
      <div className="tools-wizard">
        <div className="page-heading">
          <div>
            <p className="eyebrow">FERRAMENTAS</p>
            <h2>Carimbar documento</h2>
            <p>
              Escolha o traço, o selo e a posição para gerar o PDF carimbado.
            </p>
          </div>
        </div>
        <section className="card-section">
          <h3 className="section-title">
            <span className="step-num">1</span>Traço
          </h3>
          <Combo
            value={selected ? traceLabel(selected) : ''}
            options={traceOptions}
            onChange={(next) => {
              const id = labelToId.get(next);
              if (id) selectTrace(id);
            }}
            placeholder="Buscar traço por código, contrato ou construtora..."
          />
          {selected && (
            <div className="tools-selected-summary">
              <div>
                <strong>{selected.code}</strong>
                <span>
                  {selected.contract} · {selected.company} · Responsável:{' '}
                  {selected.owner && selected.owner !== '—'
                    ? selected.owner
                    : 'Não atribuído'}
                </span>
              </div>
              <div className="tools-selected-actions">
                <Pill status={selected.status} />
                <button
                  type="button"
                  className="secondary compact"
                  onClick={() => setShowHistory((v) => !v)}
                >
                  <ClipboardList size={14} />
                  {showHistory ? 'Ver documento' : 'Ver histórico'}
                </button>
              </div>
            </div>
          )}
        </section>

        {!selected ? (
          <div className="empty">
            <ShieldCheck size={28} />
            <h4>Selecione um traço</h4>
            <p>
              Use a busca acima para encontrar o traço e abrir o documento.
            </p>
          </div>
        ) : showHistory ? (
          <section className="card-section">
            <div className="timeline">
              {[...selected.history].reverse().map((entry, index) => (
                <div key={`${entry.date}-${index}`}>
                  <i className={statusMeta[entry.status].className} />
                  <span>
                    <b>{entry.status}</b>
                    <small>
                      {entry.date}
                      <br />
                      {entry.owner}
                    </small>
                  </span>
                </div>
              ))}
            </div>
          </section>
        ) : (
          <StampPositioner
            key={selected.id}
            traceId={selected.id}
            token={token}
            initialConcessionaria={selected.unit}
            onApplied={(status, fileName, dateLabel) => {
              void changeStatus(selected.id, status);
              flash(
                `${fileName} foi salvo com carimbo de ${dateLabel} e baixado para o computador.`,
              );
            }}
          />
        )}
      </div>
    </div>
  );
}

type AuthMode = 'login' | 'forgot' | 'register';

function LoginScreen({
  onLogin,
  dataMode,
  sessionNotice = '',
}: {
  onLogin: (
    email: string,
    password: string,
    remember: boolean,
  ) => Promise<string | null>;
  dataMode: DataMode;
  sessionNotice?: string;
}) {
  const [mode, setMode] = useState<AuthMode>('login');
  const [email, setEmail] = useState('admin@qualimatch.local');
  const [password, setPassword] = useState('Demo@2026');
  const [remember, setRemember] = useState(true);
  const [show, setShow] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [recoveryEmail, setRecoveryEmail] = useState('');
  const [registerName, setRegisterName] = useState('');
  const [registerEmail, setRegisterEmail] = useState('');
  const [notice, setNotice] = useState('');
  const submit = async (event: SubmitLike) => {
    event.preventDefault();
    setLoading(true);
    setError('');
    const result = await onLogin(email, password, remember);
    if (result) setError(result);
    setLoading(false);
  };
  const switchMode = (next: AuthMode) => {
    setMode(next);
    setError('');
    setNotice('');
  };
  const submitForgot = (event: SubmitLike) => {
    event.preventDefault();
    setNotice(
      `Se ${recoveryEmail || 'o e-mail informado'} estiver cadastrado, enviaremos um link de redefinição (simulado neste protótipo).`,
    );
  };
  const submitRegister = (event: SubmitLike) => {
    event.preventDefault();
    setNotice(
      `Solicitação de acesso registrada para ${registerName || 'o nome informado'}. Um administrador precisa aprovar (simulado neste protótipo).`,
    );
  };
  return (
    <div className="login-page">
      <section className="login-brand">
        <div className="login-logo">
          <span>CT</span>
          <strong>Controle de Traço</strong>
        </div>
        <div className="login-copy">
          <span className="overline">ENGENHARIA & QUALIDADE</span>
          <h1>Do recebimento à aprovação, tudo no mesmo fluxo.</h1>
          <p>
            Organize cartas traço, acompanhe análises e mantenha o histórico
            técnico acessível para toda a equipe.
          </p>
          <div className="login-features">
            <span>
              <CheckCircle2 size={17} /> Status e responsáveis em tempo real
            </span>
            <span>
              <CheckCircle2 size={17} /> Histórico de alterações rastreável
            </span>
            <span>
              <CheckCircle2 size={17} /> Indicadores para decisões rápidas
            </span>
          </div>
        </div>
        <small>Protótipo local · Nenhum dado é publicado</small>
      </section>
      <section className="login-panel">
        {mode === 'login' && (
          <form onSubmit={submit}>
            <div className="mobile-logo">
              <span>CT</span>
              <strong>Controle de Traço</strong>
            </div>
            <span className="overline purple">BEM-VINDO</span>
            <h2>Acesse sua conta</h2>
            <p>Use suas credenciais para entrar no ambiente de controle.</p>
            <label>
              E-mail corporativo
              <input
                type="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="nome@empresa.com.br"
              />
            </label>
            <label>
              Senha
              <div className="password-field">
                <input
                  type={show ? 'text' : 'password'}
                  required
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
                <button
                  type="button"
                  onClick={() => setShow(!show)}
                  aria-label="Mostrar senha"
                >
                  {show ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </div>
            </label>
            <div className="login-options">
              <label>
                <input
                  type="checkbox"
                  checked={remember}
                  onChange={(event) => setRemember(event.target.checked)}
                />{' '}
                Manter conectado
              </label>
              <button type="button" onClick={() => switchMode('forgot')}>
                Esqueci minha senha
              </button>
            </div>
            {sessionNotice && !error && (
              <div className="login-notice">{sessionNotice}</div>
            )}
            {error && <div className="login-error">{error}</div>}
            <button className="login-submit" disabled={loading}>
              {loading ? 'Entrando...' : 'Entrar no sistema'}
            </button>
            <div className="auth-links">
              <span>Não tem acesso?</span>
              <button type="button" onClick={() => switchMode('register')}>
                Solicitar cadastro
              </button>
            </div>
            <div className="demo-access">
              <ShieldCheck size={18} />
              <div>
                <strong>Acesso de demonstração</strong>
                <span>admin@qualimatch.local · senha Demo@2026</span>
              </div>
            </div>
            <div className={`connection-state ${dataMode}`}>
              <Database size={14} />
              {dataMode === 'database'
                ? 'PostgreSQL conectado'
                : dataMode === 'checking'
                  ? 'Verificando banco de dados...'
                  : 'Modo local de demonstração'}
            </div>
          </form>
        )}
        {mode === 'forgot' && (
          <form onSubmit={submitForgot}>
            <div className="mobile-logo">
              <span>CT</span>
              <strong>Controle de Traço</strong>
            </div>
            <span className="overline purple">RECUPERAÇÃO</span>
            <h2>Redefinir senha</h2>
            <p>
              Informe seu e-mail corporativo. Se a conta estiver ativa,
              enviaremos um link temporário.
            </p>
            <label>
              E-mail corporativo
              <input
                type="email"
                required
                value={recoveryEmail}
                onChange={(event) => setRecoveryEmail(event.target.value)}
                placeholder="nome@empresa.com.br"
              />
            </label>
            {notice && <div className="login-notice">{notice}</div>}
            <button className="login-submit" type="submit">
              Enviar instruções
            </button>
            <div className="auth-links">
              <button type="button" onClick={() => switchMode('login')}>
                Voltar para entrar
              </button>
            </div>
          </form>
        )}
        {mode === 'register' && (
          <form onSubmit={submitRegister}>
            <div className="mobile-logo">
              <span>CT</span>
              <strong>Controle de Traço</strong>
            </div>
            <span className="overline purple">NOVO ACESSO</span>
            <h2>Solicitar cadastro</h2>
            <p>O acesso só é liberado após aprovação do administrador.</p>
            <label>
              Nome completo
              <input
                required
                value={registerName}
                onChange={(event) => setRegisterName(event.target.value)}
                placeholder="Seu nome completo"
              />
            </label>
            <label>
              E-mail corporativo
              <input
                type="email"
                required
                value={registerEmail}
                onChange={(event) => setRegisterEmail(event.target.value)}
                placeholder="nome@empresa.com.br"
              />
            </label>
            {notice && <div className="login-notice">{notice}</div>}
            <button className="login-submit" type="submit">
              Solicitar acesso
            </button>
            <div className="auth-links">
              <button type="button" onClick={() => switchMode('login')}>
                Voltar para entrar
              </button>
            </div>
          </form>
        )}
      </section>
    </div>
  );
}

// Tela "Administração" (só para is Admin): lista os usuários cadastrados
// no banco e permite criar/editar, definindo papel, Sedes e se é
// administrador. Só faz sentido com o PostgreSQL conectado — sem banco não
// há onde persistir os usuários.
function AdminUsersScreen({
  token,
  flash,
}: {
  token: string;
  flash: (message: string) => void;
}) {
  const [users, setUsers] = useState<AppUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalUser, setModalUser] = useState<AppUser | 'new' | null>(null);
  const [siteFilter, setSiteFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState<
    'all' | 'active' | 'inactive'
  >('all');

  const load = useCallback(() => {
    setLoading(true);
    fetch(`${API}/api/admin/users`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((data: AppUser[]) => setUsers(data))
      .catch(() => flash('Não foi possível carregar os usuários.'))
      .finally(() => setLoading(false));
  }, [token, flash]);

  useEffect(() => {
    load();
  }, [load]);

  const siteOptions = useMemo(() => ['Todas as Sedes', ...units], []);
  const filteredUsers = users.filter((person) => {
    const matchesSite =
      !siteFilter || person.isAdmin || (person.sites || []).includes(siteFilter);
    const isActive = person.active !== false;
    const matchesStatus =
      statusFilter === 'all' ||
      (statusFilter === 'active' ? isActive : !isActive);
    return matchesSite && matchesStatus;
  });

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">ADMINISTRAÇÃO</p>
          <h2>Usuários e Sedes</h2>
          <p>
            Controle quem acessa o sistema e a quais Sedes cada pessoa tem
            permissão.
          </p>
        </div>
        <button className="primary" onClick={() => setModalUser('new')}>
          <UserPlus size={16} /> Novo usuário
        </button>
      </div>
      <div className="admin-filters">
        <Combo
          value={siteFilter || 'Todas as Sedes'}
          options={siteOptions}
          onChange={(next) =>
            setSiteFilter(next === 'Todas as Sedes' ? '' : next)
          }
          placeholder="Todas as Sedes"
        />
        <div className="status-chip-row inline">
          <button
            type="button"
            className={`status-chip all ${statusFilter === 'all' ? 'active' : ''}`}
            onClick={() => setStatusFilter('all')}
          >
            Todos
          </button>
          <button
            type="button"
            className={`status-chip ${statusFilter === 'active' ? 'active' : ''}`}
            onClick={() => setStatusFilter('active')}
          >
            Ativos
          </button>
          <button
            type="button"
            className={`status-chip ${statusFilter === 'inactive' ? 'active' : ''}`}
            onClick={() => setStatusFilter('inactive')}
          >
            Inativos
          </button>
        </div>
      </div>
      <div className="people-grid">
        {filteredUsers.map((person) => (
          <article className="person-card admin-user-card" key={person.id}>
            <div className="person-head">
              <b>{person.initials}</b>
              <span
                className={`user-status-dot ${person.active === false ? 'inactive' : ''}`}
                title={person.active === false ? 'Inativo' : 'Ativo'}
              />
            </div>
            <h3>{person.name}</h3>
            <p>{person.role}</p>
            <small>{person.email}</small>
            <div className="admin-user-tags">
              {person.isAdmin && (
                <span className="tag admin">
                  <ShieldCheck size={11} /> Administrador
                </span>
              )}
              {!person.isAdmin && (person.sites?.length ?? 0) > 0 &&
                person.sites!.map((site) => (
                  <span className="tag" key={site}>
                    {site}
                  </span>
                ))}
              {!person.isAdmin && !(person.sites?.length ?? 0) && (
                <span className="tag muted">Sem Sede atribuída</span>
              )}
              {person.active === false && (
                <span className="tag muted">Inativo</span>
              )}
            </div>
            <button type="button" onClick={() => setModalUser(person)}>
              Editar
            </button>
          </article>
        ))}
        {!loading && !filteredUsers.length && (
          <div className="empty">
            <Users size={26} />
            <p>
              {users.length
                ? 'Nenhum usuário encontrado com esses filtros.'
                : 'Nenhum usuário cadastrado ainda.'}
            </p>
          </div>
        )}
      </div>
      {modalUser && (
        <AdminUserModal
          user={modalUser === 'new' ? null : modalUser}
          token={token}
          flash={flash}
          onClose={() => setModalUser(null)}
          onSaved={() => {
            setModalUser(null);
            load();
          }}
        />
      )}
      <div className="card-section admin-sync-section">
        <h3 className="section-title">Pastas do sistema</h3>
        <p className="admin-sync-hint">
          Configuração central dos documentos sincronizados e da planilha de
          inventário. Somente administradores enxergam esta seção.
        </p>
        <SyncFolderSettings flash={flash} />
      </div>
    </>
  );
}

function AdminUserModal({
  user,
  token,
  flash,
  onClose,
  onSaved,
}: {
  user: AppUser | null;
  token: string;
  flash: (message: string) => void;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(user?.name || '');
  const [email, setEmail] = useState(user?.email || '');
  const [role, setRole] = useState(user?.role || 'Analista');
  const [isAdmin, setIsAdmin] = useState(user?.isAdmin || false);
  const [active, setActive] = useState(user?.active !== false);
  const [sites, setSites] = useState<string[]>(user?.sites || []);
  const [password, setPassword] = useState('');
  const [saving, setSaving] = useState(false);

  const toggleSite = (site: string) => {
    setSites((current) =>
      current.includes(site)
        ? current.filter((item) => item !== site)
        : [...current, site],
    );
  };

  const submit = async (event: SubmitLike) => {
    event.preventDefault();
    if (!name.trim() || !email.trim()) {
      flash('Preencha nome e e-mail.');
      return;
    }
    if (!user && !password) {
      flash('Defina uma senha para o novo usuário.');
      return;
    }
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {
        name: name.trim(),
        email: email.trim(),
        role: role.trim() || 'Analista',
        isAdmin,
        active,
        sites,
      };
      if (password) payload.password = password;
      const response = await fetch(
        user ? `${API}/api/admin/users/${user.id}` : `${API}/api/admin/users`,
        {
          method: user ? 'PATCH' : 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify(payload),
        },
      );
      const result = await response.json().catch(() => ({}));
      if (!response.ok)
        throw new Error(
          result.error || 'Não foi possível salvar o usuário.',
        );
      flash(user ? 'Usuário atualizado.' : 'Usuário criado com sucesso.');
      onSaved();
    } catch (error) {
      flash(
        error instanceof Error ? error.message : 'Erro ao salvar usuário.',
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <form className="modal" onSubmit={submit}>
        <header>
          <div>
            <small>{user ? 'EDITAR USUÁRIO' : 'NOVO USUÁRIO'}</small>
            <h2>{user ? user.name : 'Cadastrar usuário'}</h2>
            <p>Defina o papel, as Sedes e o acesso administrativo.</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Fechar">
            <X size={17} />
          </button>
        </header>
        <div className="form-body">
          <div className="form-grid">
            <label className="field">
              <span>Nome *</span>
              <input
                required
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </label>
            <label className="field">
              <span>E-mail *</span>
              <input
                required
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </label>
            <label className="field">
              <span>Papel / cargo</span>
              <input
                value={role}
                onChange={(event) => setRole(event.target.value)}
                placeholder="Ex.: Analista de Qualidade"
              />
            </label>
            <label className="field">
              <span>{user ? 'Nova senha (opcional)' : 'Senha *'}</span>
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder={user ? 'Deixe em branco para manter' : ''}
              />
            </label>
          </div>
          <div className="admin-toggle-row">
            <label className="switch-field">
              <input
                type="checkbox"
                checked={isAdmin}
                onChange={(event) => setIsAdmin(event.target.checked)}
              />
              <span>
                É administrador (acesso e gestão de todas as Sedes)
              </span>
            </label>
            <label className="switch-field">
              <input
                type="checkbox"
                checked={active}
                onChange={(event) => setActive(event.target.checked)}
              />
              <span>Usuário ativo (consegue entrar no sistema)</span>
            </label>
          </div>
          <div className="section-title">
            <b>2</b>
            <div>
              <h3>Sedes</h3>
              <p>
                {isAdmin
                  ? 'Administradores enxergam todas as Sedes automaticamente.'
                  : 'Selecione as Sedes que esse usuário poderá acessar.'}
              </p>
            </div>
          </div>
          <div className="site-chip-row">
            {units.map((site) => (
              <button
                type="button"
                key={site}
                className={`site-chip ${sites.includes(site) ? 'active' : ''}`}
                onClick={() => toggleSite(site)}
                disabled={isAdmin}
              >
                {site}
              </button>
            ))}
          </div>
        </div>
        <footer>
          <button type="button" className="secondary" onClick={onClose}>
            Cancelar
          </button>
          <button className="primary" disabled={saving}>
            {saving ? 'Salvando...' : 'Salvar'}
          </button>
        </footer>
      </form>
    </div>
  );
}

function DataTable({
  traces,
  onStatus,
  onSelect,
}: {
  traces: Trace[];
  onStatus: (id: string, status: Status) => void;
  onSelect: (trace: Trace) => void;
}) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Traço / contrato</th>
            <th>Unidade</th>
            <th>Material</th>
            <th>Status</th>
            <th>Responsável</th>
            <th>Última atualização</th>
            <th aria-label="Ações" />
          </tr>
        </thead>
        <tbody>
          {traces.map((trace) => (
            <tr
              key={trace.id}
              className={`row-${statusMeta[trace.status].className}`}
            >
              <td>
                <button className="record-link" onClick={() => onSelect(trace)}>
                  {trace.code}
                </button>
                <span>
                  {trace.contract} · {trace.company}
                </span>
              </td>
              <td>
                <b className="unit-code">
                  {trace.unit.slice(0, 2).toUpperCase()}
                </b>
                <span>{trace.unit}</span>
              </td>
              <td>
                <strong>{trace.material}</strong>
                <span>{trace.category}</span>
              </td>
              <td>
                <div className="status-control">
                  <Pill status={trace.status} />
                  <select
                    value={trace.status}
                    onChange={(event) =>
                      onStatus(trace.id, event.target.value as Status)
                    }
                    aria-label={`Alterar status de ${trace.code}`}
                  >
                    {statuses.map((status) => (
                      <option key={status}>{status}</option>
                    ))}
                  </select>
                </div>
              </td>
              <td>
                <strong>
                  {trace.owner && trace.owner !== '—'
                    ? trace.owner
                    : 'Não atribuído'}
                </strong>
              </td>
              <td>
                <strong>{trace.updated}</strong>
              </td>
              <td>
                <button
                  className="more"
                  onClick={() => onSelect(trace)}
                  aria-label={`Ver ${trace.code}`}
                >
                  •••
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!traces.length && (
        <div className="empty">
          <Search size={28} />
          <h4>Nenhum traço encontrado</h4>
          <p>Tente remover alguns filtros ou buscar por outro termo.</p>
        </div>
      )}
    </div>
  );
}

export default function Home() {
  const [user, setUser] = useState<AppUser | null>(null);
  const [token, setToken] = useState('');
  const [sessionNotice, setSessionNotice] = useState('');
  const [dataMode, setDataMode] = useState<DataMode>('checking');
  const [mode, setMode] = useState<'analise' | 'ferramentas'>('analise');
  const [view, setView] = useState<View>('dashboard');
  const [statusNavOpen, setStatusNavOpen] = useState(false);
  const [traces, setTraces] = useState<Trace[]>(initialTraces);
  const [people, setPeople] = useState<AppUser[]>(initialUsers);
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<Status | 'Todos'>('Todos');
  const [unitFilter, setUnitFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [page, setPage] = useState(1);
  const pageSize = 10;
  const [showForm, setShowForm] = useState(false);
  const [selected, setSelected] = useState<Trace | null>(null);
  const [toast, setToast] = useState('');
  const [exportingPdf, setExportingPdf] = useState(false);
  const blank = {
    unit: '',
    company: '',
    contract: '',
    category: '' as Category | '',
    material: '',
    plant: '',
    usinaType: '',
    capType: '',
    capPercent: '',
    capSupplier: '',
    additive: '',
    range: '',
    rapPercent: '',
    cementContent: '',
    cementSupplier: '',
    abrasion: '',
    place: '',
    technical: '',
    owner: '',
    workType: '',
  };
  const [form, setForm] = useState(blank);
  const [traceFiles, setTraceFiles] = useState<File[]>([]);
  const [checklistFiles, setChecklistFiles] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [toolTraceId, setToolTraceId] = useState('');
  const nextSequential = traces.length + 1;
  const generatedCode = useMemo(
    () =>
      buildTraceCode({
        category: form.category,
        sequential: nextSequential,
        unit: form.unit,
        company: form.company,
        plant: form.plant,
        capType: form.capType,
        capPercent: form.capPercent,
        capSupplier: form.capSupplier,
        range: form.range,
        rapPercent: form.rapPercent,
        cementContent: form.cementContent,
      }),
    [form, nextSequential],
  );

  useEffect(() => {
    const embedded = window.self !== window.top;
    document.documentElement.classList.toggle('qualimatch-embedded', embedded);
    return () => document.documentElement.classList.remove('qualimatch-embedded');
  }, []);

  useEffect(() => {
    const handleQualimatchNavigation = (event: MessageEvent) => {
      const data = event.data as
        | { source?: string; type?: string; target?: string }
        | null;
      if (
        !data ||
        data.source !== 'qualimatch' ||
        data.type !== 'traces-navigate'
      )
        return;
      if (data.target === 'tools') {
        setMode('ferramentas');
        return;
      }
      const allowedViews: View[] = [
        'dashboard',
        'traces',
        'inventory',
        'reports',
        'people',
        'admin',
      ];
      if (!allowedViews.includes(data.target as View)) return;
      setMode('analise');
      setView(data.target as View);
      setPage(1);
      if (data.target === 'traces') setStatusFilter('Todos');
    };
    window.addEventListener('message', handleQualimatchNavigation);
    return () =>
      window.removeEventListener('message', handleQualimatchNavigation);
  }, []);

  useEffect(() => {
    if (window.self === window.top) return;
    window.parent.postMessage(
      {
        source: 'traces-app',
        type: 'traces-route',
        target: mode === 'ferramentas' ? 'tools' : view,
      },
      '*',
    );
  }, [mode, view]);

  useEffect(() => {
    // Login automático quando aberto de dentro do QualiMatch (iframe): a
    // pessoa já se autenticou lá, então o pai manda o login pronto por
    // postMessage em vez de mostrar a tela de login de novo aqui. Só aceita
    // a mensagem específica que o QualiMatch envia — qualquer outra coisa
    // (extensão do navegador, outra aba) é ignorada.
    const handleSsoMessage = (event: MessageEvent) => {
      const data = event.data as
        | { source?: string; type?: string; token?: string; user?: AppUser }
        | null;
      if (
        !data ||
        data.source !== 'qualimatch' ||
        data.type !== 'sso-login' ||
        !data.token ||
        !data.user
      )
        return;
      setSessionNotice('');
      setUser(data.user);
      setToken(data.token);
      localStorage.setItem('tracos-user', JSON.stringify(data.user));
      localStorage.setItem('tracos-token', data.token);
    };
    window.addEventListener('message', handleSsoMessage);
    const savedUser = localStorage.getItem('tracos-user');
    const savedToken =
      sessionStorage.getItem('tracos-token') ||
      localStorage.getItem('tracos-token') ||
      '';
    const savedTraces = localStorage.getItem('tracos-prototipo');
    queueMicrotask(() => {
      if (savedUser && savedToken)
        try {
          setUser(JSON.parse(savedUser) as AppUser);
          setToken(savedToken);
        } catch {}
      else if (savedUser) localStorage.removeItem('tracos-user');
      if (savedTraces)
        try {
          setTraces(JSON.parse(savedTraces) as Trace[]);
        } catch {}
    });
    fetch(`${API}/health`)
      .then((r) => r.json())
      .then((health: unknown) =>
        setDataMode(
          (health as { database?: boolean }).database ? 'database' : 'local',
        ),
      )
      .catch(() => setDataMode('local'));
    return () => window.removeEventListener('message', handleSsoMessage);
  }, []);

  useEffect(() => {
    if (dataMode !== 'database' || !token) return;
    Promise.all([
      fetch(`${API}/api/traces`, {
        headers: { Authorization: `Bearer ${token}` },
      }),
      fetch(`${API}/api/users`, {
        headers: { Authorization: `Bearer ${token}` },
      }),
    ])
      .then(async ([traceResponse, userResponse]) => {
        // Token velho (servidor reiniciado, sessão removida): em vez de
        // seguir mostrando dados antigos e só quebrar lá na frente, volta
        // para o login já avisando o motivo.
        if (traceResponse.status === 401 || userResponse.status === 401) {
          setUser(null);
          setToken('');
          localStorage.removeItem('tracos-user');
          localStorage.removeItem('tracos-token');
          sessionStorage.removeItem('tracos-token');
          setSessionNotice(
            'Sua sessão expirou. Entre novamente para continuar.',
          );
          return;
        }
        if (traceResponse.ok) setTraces(await traceResponse.json());
        if (userResponse.ok) setPeople(await userResponse.json());
      })
      .catch(() => setDataMode('local'));
  }, [dataMode, token]);

  const flash = useCallback((message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(''), 2600);
  }, []);
  const saveLocal = useCallback((next: Trace[]) => {
    setTraces(next);
    localStorage.setItem('tracos-prototipo', JSON.stringify(next));
  }, []);
  const login = async (email: string, password: string, remember: boolean) => {
    if (dataMode === 'database') {
      try {
        const response = await fetch(`${API}/api/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
        });
        const result = (await response.json()) as {
          error?: string;
          token: string;
          user: AppUser;
        };
        if (!response.ok) return result.error || 'Não foi possível entrar';
        setSessionNotice('');
        setUser(result.user);
        setToken(result.token);
        localStorage.setItem('tracos-user', JSON.stringify(result.user));
        (remember ? localStorage : sessionStorage).setItem(
          'tracos-token',
          result.token,
        );
        return null;
      } catch {
        setDataMode('local');
      }
    }
    if (email.toLowerCase() !== 'admin@qualimatch.local' || password !== 'Demo@2026')
      return 'E-mail ou senha inválidos para o ambiente de teste.';
    const demo: AppUser = {
      id: 'demo',
      name: 'Administrador Teste',
      email,
      role: 'Administrador',
      initials: 'AT',
      isAdmin: true,
      sites: [],
      active: true,
    };
    setSessionNotice('');
    setUser(demo);
    setToken('local-demo');
    localStorage.setItem('tracos-user', JSON.stringify(demo));
    (remember ? localStorage : sessionStorage).setItem(
      'tracos-token',
      'local-demo',
    );
    return null;
  };
  const logout = () => {
    setSessionNotice('');
    setUser(null);
    setToken('');
    localStorage.removeItem('tracos-user');
    localStorage.removeItem('tracos-token');
    sessionStorage.removeItem('tracos-token');
  };
  // Escopo por Sede: administrador enxerga tudo; os demais usuários só
  // veem os traços das Sedes atribuídas a eles (já vem filtrado do backend
  // quando há PostgreSQL — isso aqui garante o mesmo comportamento no modo
  // local de demonstração, sem banco).
  const visibleTraces = useMemo(() => {
    const administrator = user?.role
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLocaleLowerCase('pt-BR')
      .includes('administrador');
    if (!user || user.isAdmin || administrator) return traces;
    const sites = user.sites || [];
    return traces.filter((trace) => sites.includes(trace.unit));
  }, [traces, user]);
  const shown = useMemo(
    () =>
      visibleTraces.filter(
        (trace) =>
          `${trace.code} ${trace.company} ${trace.contract} ${trace.unit} ${trace.material} ${trace.owner}`
            .toLocaleLowerCase('pt-BR')
            .includes(query.toLocaleLowerCase('pt-BR')) &&
          (statusFilter === 'Todos' || trace.status === statusFilter) &&
          (!unitFilter || trace.unit === unitFilter) &&
          (!categoryFilter || trace.category === categoryFilter),
      ),
    [visibleTraces, query, statusFilter, unitFilter, categoryFilter],
  );
  useEffect(() => {
    setPage(1);
  }, [query, statusFilter, unitFilter, categoryFilter]);
  const totalPages = Math.max(1, Math.ceil(shown.length / pageSize));
  const pagedShown = useMemo(
    () => shown.slice((page - 1) * pageSize, page * pageSize),
    [shown, page],
  );
  const changeStatus = useCallback(
    async (id: string, status: Status) => {
      const date = new Intl.DateTimeFormat('pt-BR', {
        dateStyle: 'short',
        timeStyle: 'short',
      }).format(new Date());
      const next = traces.map((trace) =>
        trace.id === id
          ? {
              ...trace,
              status,
              updated: 'Agora',
              history: [
                ...trace.history,
                { status, date, owner: user?.name || 'Você' },
              ],
            }
          : trace,
      );
      saveLocal(next);
      if (selected?.id === id)
        setSelected(next.find((trace) => trace.id === id) || null);
      if (dataMode === 'database' && token !== 'local-demo') {
        try {
          const response = await fetch(`${API}/api/traces/${id}/status`, {
            method: 'PATCH',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({ status }),
          });
          if (!response.ok)
            throw new Error(
              await describeApiError(
                response,
                'Não foi possível mover o arquivo entre as pastas',
              ),
            );
        } catch (error) {
          saveLocal(traces);
          if (selected?.id === id)
            setSelected(traces.find((trace) => trace.id === id) || null);
          flash(
            error instanceof Error
              ? error.message
              : 'Não foi possível mover o arquivo entre as pastas.',
          );
          return;
        }
      }
      flash(`Traço organizado em “${status}”.`);
    },
    [traces, user, selected, dataMode, token, saveLocal, flash],
  );
  const changeOwner = useCallback(
    async (id: string, owner: string) => {
      const next = traces.map((trace) =>
        trace.id === id ? { ...trace, owner } : trace,
      );
      saveLocal(next);
      if (selected?.id === id)
        setSelected(next.find((trace) => trace.id === id) || null);
      if (dataMode === 'database' && token !== 'local-demo')
        fetch(`${API}/api/traces/${id}/owner`, {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ owner }),
        }).catch(() =>
          flash('Alteração salva localmente; banco indisponível.'),
        );
      flash(`Responsável atualizado para ${owner}.`);
    },
    [traces, selected, dataMode, token, saveLocal, flash],
  );
  useEffect(() => {
    const context = (
      document as Document & {
        modelContext?: {
          registerTool: (
            tool: unknown,
            options?: { signal?: AbortSignal },
          ) => void | Promise<void>;
        };
      }
    ).modelContext;
    if (!context?.registerTool || !user) return;
    const lifecycle = new AbortController();
    void Promise.resolve(
      context.registerTool(
        {
          name: 'update_trace_status',
          title: 'Atualizar status de traço',
          description:
            'Atualiza o status de uma carta-traço existente e registra a alteração no histórico visível.',
          inputSchema: {
            type: 'object',
            properties: {
              id: { type: 'string' },
              status: { type: 'string', enum: statuses },
            },
            required: ['id', 'status'],
            additionalProperties: false,
          },
          annotations: { readOnlyHint: false, untrustedContentHint: false },
          async execute(input: unknown) {
            const value = input as { id?: string; status?: Status };
            if (!value.id || !value.status || !statuses.includes(value.status))
              throw new Error('Informe um id e um status válidos.');
            const trace = traces.find((item) => item.id === value.id);
            if (!trace) throw new Error('Traço não encontrado.');
            await changeStatus(trace.id, value.status);
            return { id: trace.id, code: trace.code, status: value.status };
          },
        },
        { signal: lifecycle.signal },
      ),
    ).catch(() => undefined);
    return () => lifecycle.abort();
  }, [traces, user, changeStatus]);
  const submit = async (event: SubmitLike) => {
    event.preventDefault();
    if (submitting) return;
    if (!traceFiles.length || !checklistFiles.length) {
      flash(
        'Anexe a carta traço e o checklist de análise antes de enviar (itens 30 e 31 do formulário oficial).',
      );
      return;
    }
    const now = new Intl.DateTimeFormat('pt-BR').format(new Date());
    const trace: Trace = {
      id: crypto.randomUUID(),
      code: generatedCode,
      unit: form.unit,
      company: form.company,
      contract: form.contract,
      category: form.category as Category,
      material: form.material,
      place: form.place || 'Local não informado',
      status: 'Solicitado',
      updated: 'Agora',
      owner: form.owner || user?.name || '—',
      note: form.technical,
      history: [
        {
          status: 'Solicitado',
          date: `${now} · agora`,
          owner: user?.name || 'Solicitante',
        },
      ],
    };
    setSubmitting(true);
    try {
      await Promise.all([
        uploadFiles(trace.id, 'trace', traceFiles, token),
        uploadFiles(trace.id, 'checklist', checklistFiles, token),
      ]);
      let saved = trace;
      if (dataMode === 'database' && token !== 'local-demo') {
        const response = await fetch(`${API}/api/traces`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify(trace),
        });
        if (!response.ok)
          throw new Error(
            await describeApiError(
              response,
              'Não foi possível criar a solicitação',
            ),
          );
        saved = (await response.json()) as Trace;
      }
      saveLocal([saved, ...traces]);
      setShowForm(false);
      setForm(blank);
      setTraceFiles([]);
      setChecklistFiles([]);
      flash('Solicitação criada com os dois documentos em “Solicitado”.');
    } catch (err) {
      flash(
        err instanceof Error
          ? err.message
          : 'Não foi possível criar a solicitação. Tente novamente.',
      );
    } finally {
      setSubmitting(false);
    }
  };
  const selectView = (next: View) => {
    setView(next);
    if (next !== 'traces') setStatusFilter('Todos');
  };
  const exportCsv = () => {
    const rows = [
      [
        'Código',
        'Contrato',
        'Unidade',
        'Construtora',
        'Categoria',
        'Material',
        'Status',
        'Responsável',
      ],
      ...visibleTraces.map((trace) => [
        trace.code,
        trace.contract,
        trace.unit,
        trace.company,
        trace.category,
        trace.material,
        trace.status,
        trace.owner,
      ]),
    ];
    const csv = rows
      .map((row) =>
        row.map((cell) => `"${cell.replaceAll('"', '""')}"`).join(';'),
      )
      .join('\n');
    const url = URL.createObjectURL(
      new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' }),
    );
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'relatorio-tracos.csv';
    anchor.click();
    URL.revokeObjectURL(url);
  };
  const exportPdf = async () => {
    if (exportingPdf) return;
    setExportingPdf(true);
    try {
      const { PDFDocument, StandardFonts, rgb } = await loadPdfLibOnly();
      const pageWidth = 841.89;
      const pageHeight = 595.28;
      const margin = 36;
      const pdfDoc = await PDFDocument.create();
      const font = await pdfDoc.embedFont(StandardFonts.Helvetica);
      const fontBold = await pdfDoc.embedFont(StandardFonts.HelveticaBold);
      const generatedAt = new Intl.DateTimeFormat('pt-BR', {
        dateStyle: 'short',
        timeStyle: 'short',
      }).format(new Date());
      const approvalRate = visibleTraces.length
        ? Math.round(
            (visibleTraces.filter((t) => t.status === 'Aprovado').length /
              visibleTraces.length) *
              100,
          )
        : 0;
      const kpis = [
        { label: 'Total de traços', value: String(visibleTraces.length) },
        { label: 'Taxa de aprovação', value: `${approvalRate}%` },
        {
          label: 'Em andamento',
          value: String(
            visibleTraces.filter(
              (t) => t.status === 'Em análise' || t.status === 'Solicitado',
            ).length,
          ),
        },
        {
          label: 'Pontos de atenção',
          value: String(
            visibleTraces.filter(
              (t) => t.status === 'Não conforme' || t.status === 'Restrito',
            ).length,
          ),
        },
      ];
      const statusCounts = statuses.map((status) => ({
        status,
        count: visibleTraces.filter((t) => t.status === status).length,
      }));
      const columns: { key: keyof Trace; label: string; width: number }[] = [
        { key: 'code', label: 'Código', width: 70 },
        { key: 'contract', label: 'Contrato', width: 62 },
        { key: 'unit', label: 'Unidade', width: 52 },
        { key: 'company', label: 'Construtora', width: 128 },
        { key: 'category', label: 'Categoria', width: 100 },
        { key: 'material', label: 'Material', width: 128 },
        { key: 'status', label: 'Status', width: 72 },
        { key: 'owner', label: 'Responsável', width: 108 },
      ];
      const tableWidth = columns.reduce((sum, c) => sum + c.width, 0);
      const rowHeight = 16;
      let page = pdfDoc.addPage([pageWidth, pageHeight]);
      let y = pageHeight;
      const drawBrandHeader = () => {
        page.drawRectangle({
          x: 0,
          y: pageHeight - 64,
          width: pageWidth,
          height: 64,
          color: rgb(0.055, 0.051, 0.078),
        });
        page.drawRectangle({
          x: margin,
          y: pageHeight - 48,
          width: 32,
          height: 32,
          color: rgb(0.659, 0.478, 1),
        });
        page.drawText('CT', {
          x: margin + 8,
          y: pageHeight - 38,
          size: 12,
          font: fontBold,
          color: rgb(1, 1, 1),
        });
        page.drawText('Controle de Traço', {
          x: margin + 44,
          y: pageHeight - 29,
          size: 13,
          font: fontBold,
          color: rgb(1, 1, 1),
        });
        page.drawText('Motiva - Engenharia & Qualidade', {
          x: margin + 44,
          y: pageHeight - 43,
          size: 8,
          font,
          color: rgb(0.72, 0.7, 0.8),
        });
        const label = `Gerado em ${generatedAt}`;
        const labelWidth = font.widthOfTextAtSize(label, 8);
        page.drawText(label, {
          x: pageWidth - margin - labelWidth,
          y: pageHeight - 29,
          size: 8,
          font,
          color: rgb(0.72, 0.7, 0.8),
        });
        y = pageHeight - 64 - 22;
      };
      const drawTableHeader = () => {
        page.drawRectangle({
          x: margin,
          y: y - rowHeight,
          width: tableWidth,
          height: rowHeight,
          color: rgb(0.9, 0.89, 0.94),
        });
        let x = margin;
        columns.forEach((col) => {
          page.drawText(col.label, {
            x: x + 4,
            y: y - rowHeight + 5,
            size: 7,
            font: fontBold,
            color: rgb(0.2, 0.19, 0.28),
          });
          x += col.width;
        });
        y -= rowHeight;
      };
      const truncate = (text: string, width: number) => {
        if (font.widthOfTextAtSize(text, 7) <= width - 8) return text;
        let result = text;
        while (
          result.length > 1 &&
          font.widthOfTextAtSize(`${result}…`, 7) > width - 8
        ) {
          result = result.slice(0, -1);
        }
        return `${result}…`;
      };
      drawBrandHeader();
      page.drawText('Relatório de desempenho', {
        x: margin,
        y,
        size: 16,
        font: fontBold,
        color: rgb(0.08, 0.08, 0.1),
      });
      y -= 20;
      page.drawText(
        'Resumo executivo - leitura rápida da carteira atual de cartas traço.',
        { x: margin, y, size: 9, font, color: rgb(0.35, 0.33, 0.42) },
      );
      y -= 22;
      const kpiWidth = tableWidth / kpis.length;
      kpis.forEach((kpi, index) => {
        const x = margin + index * kpiWidth;
        page.drawText(kpi.value, {
          x,
          y,
          size: 18,
          font: fontBold,
          color: rgb(0.42, 0.28, 0.75),
        });
        page.drawText(kpi.label, {
          x,
          y: y - 13,
          size: 8,
          font,
          color: rgb(0.4, 0.4, 0.45),
        });
      });
      y -= 38;
      page.drawText('Status da carteira', {
        x: margin,
        y,
        size: 10,
        font: fontBold,
        color: rgb(0.3, 0.28, 0.4),
      });
      y -= 16;
      const statusColWidth = tableWidth / statusCounts.length;
      statusCounts.forEach((item, index) => {
        const x = margin + index * statusColWidth;
        page.drawText(String(item.count), {
          x,
          y,
          size: 13,
          font: fontBold,
          color: rgb(0.1, 0.1, 0.12),
        });
        page.drawText(item.status, {
          x,
          y: y - 12,
          size: 7,
          font,
          color: rgb(0.4, 0.4, 0.45),
        });
      });
      y -= 32;
      page.drawText('Detalhamento dos traços', {
        x: margin,
        y,
        size: 10,
        font: fontBold,
        color: rgb(0.3, 0.28, 0.4),
      });
      y -= 16;
      drawTableHeader();
      visibleTraces.forEach((trace, index) => {
        if (y - rowHeight < margin) {
          page = pdfDoc.addPage([pageWidth, pageHeight]);
          drawBrandHeader();
          drawTableHeader();
        }
        if (index % 2 === 1) {
          page.drawRectangle({
            x: margin,
            y: y - rowHeight,
            width: tableWidth,
            height: rowHeight,
            color: rgb(0.965, 0.96, 0.98),
          });
        }
        let x = margin;
        columns.forEach((col) => {
          const raw = String(trace[col.key] ?? '');
          page.drawText(truncate(raw, col.width), {
            x: x + 4,
            y: y - rowHeight + 5,
            size: 7,
            font,
            color: rgb(0.15, 0.14, 0.2),
          });
          x += col.width;
        });
        y -= rowHeight;
      });
      const bytes = await pdfDoc.save();
      const blob = new Blob([new Uint8Array(bytes)], {
        type: 'application/pdf',
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = 'relatorio-tracos.pdf';
      anchor.click();
      URL.revokeObjectURL(url);
      flash('Relatório em PDF gerado com sucesso.');
    } catch (err) {
      flash(
        err instanceof Error
          ? err.message
          : 'Não foi possível gerar o PDF. Tente novamente.',
      );
    } finally {
      setExportingPdf(false);
    }
  };

  if (!user)
    return (
      <LoginScreen
        onLogin={login}
        dataMode={dataMode}
        sessionNotice={sessionNotice}
      />
    );
  const title =
    view === 'dashboard'
      ? 'Visão geral'
      : view === 'traces'
        ? 'Todos os traços'
        : view === 'inventory'
          ? 'Inventário'
          : view === 'reports'
            ? 'Relatórios'
            : view === 'admin'
              ? 'Administração'
              : 'Responsáveis';
  return (
    <div className="shell-root">
      <div className="mode-tabs">
        <div className="module-brand" aria-label="Controle de Traços">
          <span>CT</span>
          <strong>Controle de Traços</strong>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger className="module-switcher">
            <span className="module-switcher-icon">
              {mode === 'analise' ? (
                <ClipboardList size={17} />
              ) : (
                <Wrench size={17} />
              )}
            </span>
            <span className="module-switcher-copy">
              <small>MÓDULO</small>
              <strong>
                {mode === 'analise' ? 'Análise de Traços' : 'Ferramentas'}
              </strong>
            </span>
            <ChevronDown size={15} />
          </DropdownMenuTrigger>
          <DropdownMenuContent
            className="module-menu"
            align="start"
            sideOffset={8}
          >
            <DropdownMenuGroup>
              <DropdownMenuLabel>Alternar módulo</DropdownMenuLabel>
              <DropdownMenuItem
                className={
                  mode === 'analise'
                    ? 'module-menu-item active'
                    : 'module-menu-item'
                }
                onClick={() => setMode('analise')}
              >
                <ClipboardList size={17} />
                <span>
                  <strong>Análise de Traços</strong>
                  <small>Receber, analisar e acompanhar</small>
                </span>
                {mode === 'analise' && <CheckCircle2 size={16} />}
              </DropdownMenuItem>
              <DropdownMenuItem
                className={
                  mode === 'ferramentas'
                    ? 'module-menu-item active'
                    : 'module-menu-item'
                }
                onClick={() => setMode('ferramentas')}
              >
                <Wrench size={17} />
                <span>
                  <strong>Ferramentas</strong>
                  <small>Editar e carimbar documentos</small>
                </span>
                {mode === 'ferramentas' && <CheckCircle2 size={16} />}
              </DropdownMenuItem>
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>
        <div className="mode-user">
          <span>{user.initials}</span>
          <div>
            <strong>{user.name}</strong>
            <small>{user.role}</small>
          </div>
        </div>
      </div>
      {mode === 'ferramentas' ? (
        <ToolsScreen
          traces={visibleTraces}
          changeStatus={changeStatus}
          flash={flash}
          token={token}
          initialTraceId={toolTraceId}
        />
      ) : (
        <div className="app-shell">
          <aside className="sidebar">
            <div className="brand">
              <div className="brand-mark">CT</div>
              <div>
                <strong>Controle de Traço</strong>
                <span>Engenharia & Qualidade</span>
              </div>
            </div>
            <nav>
              <button
                className={`nav ${view === 'dashboard' ? 'active' : ''}`}
                onClick={() => selectView('dashboard')}
              >
                <LayoutDashboard size={17} />
                <span>Visão geral</span>
              </button>
              <button
                className={`nav ${view === 'traces' && statusFilter === 'Todos' ? 'active' : ''}`}
                onClick={() => {
                  selectView('traces');
                  setStatusFilter('Todos');
                }}
              >
                <ClipboardList size={17} />
                <span>Todos os traços</span>
                <em>{visibleTraces.length}</em>
              </button>
              <button
                className={`nav ${view === 'inventory' ? 'active' : ''}`}
                onClick={() => selectView('inventory')}
              >
                <FileSpreadsheet size={17} />
                <span>Inventário</span>
              </button>
              <button
                type="button"
                className={`nav-section-toggle ${statusNavOpen ? '' : 'collapsed'}`}
                onClick={() => setStatusNavOpen((open) => !open)}
                aria-expanded={statusNavOpen}
              >
                STATUS
                <ChevronDown size={12} />
              </button>
              {statusNavOpen &&
                statuses.map((status) => (
                  <button
                    className={`nav ${view === 'traces' && statusFilter === status ? 'active' : ''}`}
                    key={status}
                    onClick={() => {
                      setView('traces');
                      setStatusFilter(status);
                    }}
                  >
                    <i className={statusMeta[status].className} />
                    <span>{status}</span>
                    <em>
                      {visibleTraces.filter((trace) => trace.status === status).length}
                    </em>
                  </button>
                ))}
              <p>GESTÃO</p>
              <button
                className={`nav ${view === 'reports' ? 'active' : ''}`}
                onClick={() => selectView('reports')}
              >
                <BarChart3 size={17} />
                <span>Relatórios</span>
              </button>
              <button
                className={`nav ${view === 'people' ? 'active' : ''}`}
                onClick={() => selectView('people')}
              >
                <Users size={17} />
                <span>Responsáveis</span>
              </button>
              {user.isAdmin && (
                <button
                  className={`nav ${view === 'admin' ? 'active' : ''}`}
                  onClick={() => selectView('admin')}
                >
                  <Settings size={17} />
                  <span>Administração</span>
                </button>
              )}
            </nav>
            <p className="data-mode-hint" title="Origem dos dados">
              <Database size={10} />
              {dataMode === 'database' ? 'PostgreSQL' : 'Dados locais'}
            </p>
            <div className="profile">
              <b>{user.initials}</b>
              <div>
                <strong>{user.name}</strong>
                <span>
                  {user.role}
                  {user.isAdmin ? (
                    <em className="scope-tag admin">Todas as Sedes</em>
                  ) : (user.sites?.length ?? 0) > 0 ? (
                    <em className="scope-tag">{user.sites!.join(', ')}</em>
                  ) : null}
                </span>
              </div>
              <button onClick={logout} title="Sair" aria-label="Sair">
                <LogOut size={16} />
              </button>
            </div>
          </aside>
          <main>
            <header className="topbar">
              <div>
                <h1>{title}</h1>
                <p>Recebimento, análise e organização técnica</p>
              </div>
              <div className="topbar-actions">
                {(view === 'dashboard' || view === 'traces') && (
                  <button className="primary" onClick={() => setShowForm(true)}>
                    <Plus size={16} /> Nova solicitação
                  </button>
                )}
              </div>
            </header>
            <section className="content">
              {view === 'dashboard' && (
                <>
                  <div className="welcome">
                    <div>
                      <p className="eyebrow">VISÃO GERAL</p>
                      <h2>Bom dia, {user.name.split(' ')[0]}</h2>
                      <p>
                        Acompanhe o fluxo de aprovação e mantenha cada traço no
                        lugar certo.
                      </p>
                    </div>
                    <small>● Atualizado agora</small>
                  </div>
                  <div className="stats">
                    {statuses.map((status) => (
                      <button
                        key={status}
                        onClick={() => {
                          setView('traces');
                          setStatusFilter(status);
                        }}
                      >
                        <i className={statusMeta[status].className}>
                          {statusMeta[status].short}
                        </i>
                        <span>
                          {status}
                          <strong>
                            {visibleTraces
                              .filter((trace) => trace.status === status)
                              .length.toString()
                              .padStart(2, '0')}
                          </strong>
                        </span>
                        <b>›</b>
                      </button>
                    ))}
                  </div>
                  <section className="records">
                    <div className="records-head">
                      <div>
                        <h3>Solicitações recentes</h3>
                        <p>Últimos registros atualizados</p>
                      </div>
                      <button onClick={() => selectView('traces')}>
                        Ver todos
                      </button>
                    </div>
                    <DataTable
                      traces={visibleTraces.slice(0, 5)}
                      onStatus={changeStatus}
                      onSelect={setSelected}
                    />
                    <footer>
                      Mostrando os 5 registros mais recentes{' '}
                      <button onClick={() => selectView('traces')}>
                        Abrir lista completa
                      </button>
                    </footer>
                  </section>
                </>
              )}
              {view === 'traces' && (
                <>
                  <div className="page-heading">
                    <div>
                      <p className="eyebrow">GESTÃO DE REGISTROS</p>
                      <h2>
                        {statusFilter === 'Todos'
                          ? 'Todos os traços'
                          : statusFilter}
                      </h2>
                      <p>
                        Pesquise, filtre e atualize o fluxo de cada carta traço.
                      </p>
                    </div>
                    <div className="result-count">
                      <strong>{shown.length}</strong>
                      <span>registros</span>
                    </div>
                  </div>
                  <section className="records">
                    <div className="status-chip-row">
                      <button
                        type="button"
                        className={`status-chip all ${statusFilter === 'Todos' ? 'active' : ''}`}
                        onClick={() => setStatusFilter('Todos')}
                      >
                        <i>Tod</i>
                        <span>Todos</span>
                        <b>{visibleTraces.length}</b>
                      </button>
                      {statuses.map((status) => (
                        <button
                          type="button"
                          key={status}
                          className={`status-chip ${statusFilter === status ? 'active' : ''}`}
                          onClick={() => setStatusFilter(status)}
                        >
                          <i className={statusMeta[status].className}>
                            {statusMeta[status].short}
                          </i>
                          <span>{status}</span>
                          <b>
                            {
                              visibleTraces.filter((trace) => trace.status === status)
                                .length
                            }
                          </b>
                        </button>
                      ))}
                    </div>
                    <div className="toolbar">
                      <div className="search">
                        <Search size={15} />
                        <input
                          value={query}
                          onChange={(event) => setQuery(event.target.value)}
                          placeholder="Buscar por código, contrato, construtora, responsável..."
                        />
                      </div>
                      <Combo
                        value={unitFilter}
                        options={units}
                        onChange={setUnitFilter}
                        placeholder="Todas as unidades"
                      />
                      <Combo
                        value={categoryFilter}
                        options={categories}
                        onChange={setCategoryFilter}
                        placeholder="Todas as categorias"
                      />
                    </div>
                    {(query ||
                      statusFilter !== 'Todos' ||
                      unitFilter ||
                      categoryFilter) && (
                      <div className="filter-summary">
                        <span>Filtros aplicados</span>
                        <button
                          onClick={() => {
                            setQuery('');
                            setStatusFilter('Todos');
                            setUnitFilter('');
                            setCategoryFilter('');
                          }}
                        >
                          <X size={13} /> Limpar tudo
                        </button>
                      </div>
                    )}
                    <DataTable
                      traces={pagedShown}
                      onStatus={changeStatus}
                      onSelect={setSelected}
                    />
                    <footer>
                      <span>
                        Mostrando{' '}
                        {pagedShown.length
                          ? (page - 1) * pageSize + 1
                          : 0}
                        –{(page - 1) * pageSize + pagedShown.length} de{' '}
                        {shown.length} traços
                      </span>
                      <div className="pagination">
                        <button
                          type="button"
                          onClick={() => setPage((p) => Math.max(1, p - 1))}
                          disabled={page <= 1}
                          aria-label="Página anterior"
                        >
                          <ChevronLeft size={14} />
                        </button>
                        <span>
                          Página <b>{page}</b> de {totalPages}
                        </span>
                        <button
                          type="button"
                          onClick={() =>
                            setPage((p) => Math.min(totalPages, p + 1))
                          }
                          disabled={page >= totalPages}
                          aria-label="Próxima página"
                        >
                          <ChevronRight size={14} />
                        </button>
                      </div>
                    </footer>
                  </section>
                </>
              )}
              {view === 'inventory' && (
                <InventoryScreen token={token} flash={flash} />
              )}
              {view === 'reports' && (
                <>
                  <div className="page-heading">
                    <div>
                      <p className="eyebrow">INDICADORES</p>
                      <h2>Relatório de desempenho</h2>
                      <p>
                        Uma leitura rápida da carteira atual de cartas traço.
                      </p>
                    </div>
                    <div className="report-actions">
                      <button
                        className="primary"
                        onClick={exportPdf}
                        disabled={exportingPdf}
                      >
                        <FileText size={16} />
                        {exportingPdf ? 'Gerando PDF...' : 'Exportar PDF'}
                      </button>
                      <button className="secondary" onClick={exportCsv}>
                        <Download size={16} /> Exportar Excel (CSV)
                      </button>
                    </div>
                  </div>
                  <div className="report-kpis">
                    <article>
                      <span>Total de traços</span>
                      <strong>{visibleTraces.length}</strong>
                      <small>Base atual</small>
                    </article>
                    <article>
                      <span>Taxa de aprovação</span>
                      <strong>
                        {visibleTraces.length
                          ? Math.round(
                              (visibleTraces.filter((t) => t.status === 'Aprovado')
                                .length /
                                visibleTraces.length) *
                                100,
                            )
                          : 0}
                        %
                      </strong>
                      <small className="positive">Aprovados na carteira</small>
                    </article>
                    <article>
                      <span>Em andamento</span>
                      <strong>
                        {
                          visibleTraces.filter(
                            (t) =>
                              t.status === 'Em análise' ||
                              t.status === 'Solicitado',
                          ).length
                        }
                      </strong>
                      <small>Aguardando conclusão</small>
                    </article>
                    <article>
                      <span>Pontos de atenção</span>
                      <strong>
                        {
                          visibleTraces.filter(
                            (t) =>
                              t.status === 'Não conforme' ||
                              t.status === 'Restrito',
                          ).length
                        }
                      </strong>
                      <small className="warning">
                        Não conformes ou restritos
                      </small>
                    </article>
                  </div>
                  <div className="report-grid">
                    <section className="report-card wide">
                      <div className="card-title">
                        <div>
                          <h3>Distribuição por categoria</h3>
                          <p>Quantidade de traços por família de material</p>
                        </div>
                        <BarChart3 size={20} />
                      </div>
                      <div className="bar-chart">
                        {categories.map((category) => {
                          const count = visibleTraces.filter(
                            (t) => t.category === category,
                          ).length;
                          const width = visibleTraces.length
                            ? Math.max(8, (count / visibleTraces.length) * 100)
                            : 0;
                          return (
                            <div key={category}>
                              <span>
                                {category}
                                <b>{count}</b>
                              </span>
                              <div>
                                <i style={{ width: `${width}%` }} />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </section>
                    <section className="report-card">
                      <div className="card-title">
                        <div>
                          <h3>Status da carteira</h3>
                          <p>Visão consolidada</p>
                        </div>
                      </div>
                      <div className="status-report">
                        {statuses.map((status) => {
                          const count = visibleTraces.filter(
                            (t) => t.status === status,
                          ).length;
                          return (
                            <div key={status}>
                              <Pill status={status} />
                              <b>{count}</b>
                            </div>
                          );
                        })}
                      </div>
                    </section>
                    <section className="report-card">
                      <div className="card-title">
                        <div>
                          <h3>Responsáveis</h3>
                          <p>Carga em aberto</p>
                        </div>
                      </div>
                      <div className="ranking">
                        {people.slice(0, 4).map((person, index) => (
                          <div key={person.id}>
                            <span>{index + 1}</span>
                            <b>{person.name}</b>
                            <em>
                              {
                                visibleTraces.filter(
                                  (t) =>
                                    t.owner === person.name &&
                                    !['Aprovado', 'Cancelado'].includes(
                                      t.status,
                                    ),
                                ).length
                              }{' '}
                              ativos
                            </em>
                          </div>
                        ))}
                      </div>
                    </section>
                  </div>
                </>
              )}
              {view === 'people' && (
                <>
                  <div className="page-heading">
                    <div>
                      <p className="eyebrow">EQUIPE</p>
                      <h2>Responsáveis</h2>
                      <p>
                        Distribuição de análises e acompanhamento da equipe
                        técnica.
                      </p>
                    </div>
                    <div className="result-count">
                      <strong>{people.length}</strong>
                      <span>pessoas</span>
                    </div>
                  </div>
                  <div className="people-grid">
                    {people.map((person) => {
                      const assigned = visibleTraces.filter(
                        (t) => t.owner === person.name,
                      );
                      const pending = assigned.filter(
                        (t) =>
                          t.status === 'Em análise' ||
                          t.status === 'Solicitado',
                      ).length;
                      return (
                        <article className="person-card" key={person.id}>
                          <div className="person-head">
                            <b>{person.initials}</b>
                            <span className="online-dot" />
                          </div>
                          <h3>{person.name}</h3>
                          <p>{person.role}</p>
                          <small>{person.email}</small>
                          {(person.isAdmin || person.sites?.length) && (
                            <div className="admin-user-tags">
                              {person.isAdmin ? (
                                <span className="tag admin">
                                  <ShieldCheck size={11} /> Administrador
                                </span>
                              ) : (
                                person.sites!.map((site) => (
                                  <span className="tag" key={site}>
                                    {site}
                                  </span>
                                ))
                              )}
                            </div>
                          )}
                          <div className="person-metrics">
                            <div>
                              <strong>{assigned.length}</strong>
                              <span>Total</span>
                            </div>
                            <div>
                              <strong>{pending}</strong>
                              <span>Pendentes</span>
                            </div>
                            <div>
                              <strong>
                                {
                                  assigned.filter(
                                    (t) => t.status === 'Aprovado',
                                  ).length
                                }
                              </strong>
                              <span>Aprovados</span>
                            </div>
                          </div>
                          <button
                            onClick={() => {
                              setView('traces');
                              setQuery(person.name);
                            }}
                          >
                            Ver traços atribuídos
                          </button>
                        </article>
                      );
                    })}
                  </div>
                </>
              )}
              {view === 'admin' && user.isAdmin && (
                dataMode === 'database' ? (
                  <AdminUsersScreen token={token} flash={flash} />
                ) : (
                  <div className="empty">
                    <ShieldCheck size={26} />
                    <p>
                      A administração de usuários precisa do PostgreSQL
                      conectado — no modo local de demonstração não há onde
                      salvar os usuários.
                    </p>
                  </div>
                )
              )}
            </section>
          </main>
          {showForm && (
            <div
              className="backdrop"
              role="presentation"
              onMouseDown={(event) => {
                if (event.target === event.currentTarget) setShowForm(false);
              }}
            >
              <form className="modal" onSubmit={submit}>
                <header>
                  <div>
                    <small>NOVA SOLICITAÇÃO</small>
                    <h2>Registrar carta traço</h2>
                    <p>
                      Os campos técnicos se adaptam à categoria selecionada.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setShowForm(false)}
                    aria-label="Fechar"
                  >
                    <X size={17} />
                  </button>
                </header>
                <div className="form-body">
                  <div className="section-title">
                    <b>1</b>
                    <div>
                      <h3>Dados gerais</h3>
                      <p>Identificação da solicitação e do contrato</p>
                    </div>
                  </div>
                  <div className="form-grid">
                    <Combo
                      label="Unidade"
                      value={form.unit}
                      options={
                        user.isAdmin || !user.sites?.length
                          ? units
                          : user.sites
                      }
                      onChange={(value) => setForm({ ...form, unit: value })}
                    />
                    <Combo
                      label="Tipo de obra"
                      value={form.workType}
                      options={['Pavimentos', 'Implantação']}
                      onChange={(value) =>
                        setForm({ ...form, workType: value })
                      }
                    />
                    <label className="field">
                      <span>Construtora *</span>
                      <input
                        required
                        value={form.company}
                        onChange={(event) =>
                          setForm({ ...form, company: event.target.value })
                        }
                        placeholder="Nome da construtora"
                      />
                    </label>
                    <label className="field">
                      <span>Contrato *</span>
                      <input
                        required
                        value={form.contract}
                        onChange={(event) =>
                          setForm({ ...form, contract: event.target.value })
                        }
                        placeholder="Ex.: CT-184/26"
                      />
                    </label>
                    <div className="full">
                      <Combo
                        label="Categoria da carta traço"
                        value={form.category}
                        options={categories}
                        onChange={(value) =>
                          setForm({
                            ...form,
                            category: value as Category,
                            material: '',
                          })
                        }
                      />
                    </div>
                  </div>
                  {form.category && (
                    <>
                      <div className="section-title">
                        <b>2</b>
                        <div>
                          <h3>Dados técnicos</h3>
                          <p>
                            Campos exigidos pela codificação do
                            PE.COR.GLO.QUA.003 para{' '}
                            {form.category.toLowerCase()}
                          </p>
                        </div>
                      </div>
                      <div className="form-grid">
                        <Combo
                          label={
                            form.category === 'Misturas asfálticas'
                              ? 'Tipo de revestimento'
                              : 'Tipo de material'
                          }
                          value={form.material}
                          options={materials[form.category]}
                          onChange={(value) =>
                            setForm({ ...form, material: value })
                          }
                        />
                        <label className="field">
                          <span>
                            Usina {form.category !== 'Agregados' && '*'}
                          </span>
                          <input
                            required={form.category !== 'Agregados'}
                            value={form.plant}
                            onChange={(event) =>
                              setForm({ ...form, plant: event.target.value })
                            }
                            placeholder="Ex.: Polimix, PSI, dosado em obra..."
                          />
                        </label>
                        {form.category === 'Misturas asfálticas' && (
                          <>
                            <Combo
                              label="Tipo de Usina"
                              value={form.usinaType}
                              options={usinaTypes}
                              onChange={(value) =>
                                setForm({ ...form, usinaType: value })
                              }
                            />
                            <label className="field">
                              <span>Tipo de CAP *</span>
                              <input
                                required
                                value={form.capType}
                                onChange={(event) =>
                                  setForm({
                                    ...form,
                                    capType: event.target.value,
                                  })
                                }
                                placeholder="Ex.: CAP 60/85"
                              />
                            </label>
                            <label className="field">
                              <span>% de CAP *</span>
                              <input
                                required
                                value={form.capPercent}
                                onChange={(event) =>
                                  setForm({
                                    ...form,
                                    capPercent: event.target.value,
                                  })
                                }
                                placeholder="Ex.: 4,5%"
                              />
                            </label>
                            <Combo
                              label="Distribuidora (fornecedor do CAP)"
                              value={form.capSupplier}
                              options={capDistributors}
                              onChange={(value) =>
                                setForm({ ...form, capSupplier: value })
                              }
                            />
                            <Combo
                              label="Aditivo"
                              value={form.additive}
                              options={['Sim', 'Não']}
                              onChange={(value) =>
                                setForm({ ...form, additive: value })
                              }
                            />
                            <label className="field">
                              <span>Faixa *</span>
                              <input
                                required
                                value={form.range}
                                onChange={(event) =>
                                  setForm({
                                    ...form,
                                    range: event.target.value,
                                  })
                                }
                                placeholder="Ex.: EGL1619"
                              />
                            </label>
                            <label className="field">
                              <span>% de RAP</span>
                              <input
                                value={form.rapPercent}
                                onChange={(event) =>
                                  setForm({
                                    ...form,
                                    rapPercent: event.target.value,
                                  })
                                }
                                placeholder="Ex.: 20%RAP (deixe em branco se 0%)"
                              />
                            </label>
                          </>
                        )}
                        {form.category === 'Camadas cimentícias' && (
                          <>
                            <label className="field">
                              <span>Teor de cimento *</span>
                              <input
                                required
                                value={form.cementContent}
                                onChange={(event) =>
                                  setForm({
                                    ...form,
                                    cementContent: event.target.value,
                                  })
                                }
                                placeholder="Ex.: 4%"
                              />
                            </label>
                            <label className="field">
                              <span>Faixa *</span>
                              <input
                                required
                                value={form.range}
                                onChange={(event) =>
                                  setForm({
                                    ...form,
                                    range: event.target.value,
                                  })
                                }
                                placeholder="Ex.: Faixa 1"
                              />
                            </label>
                            <Combo
                              label="Tipo de Cimento e Fornecedor"
                              value={form.cementSupplier}
                              options={cementSuppliers}
                              onChange={(value) =>
                                setForm({ ...form, cementSupplier: value })
                              }
                            />
                          </>
                        )}
                        {form.category === 'Agregados' && (
                          <label className="field">
                            <span>Abrasão *</span>
                            <input
                              required
                              value={form.abrasion}
                              onChange={(event) =>
                                setForm({
                                  ...form,
                                  abrasion: event.target.value,
                                })
                              }
                              placeholder="Ex.: 28%"
                            />
                          </label>
                        )}
                        <label className="field">
                          <span>Pedreira / fornecedor *</span>
                          <input
                            required
                            value={form.place}
                            onChange={(event) =>
                              setForm({ ...form, place: event.target.value })
                            }
                            placeholder="Informe o local"
                          />
                        </label>
                        <label className="field">
                          <span>Informação técnica</span>
                          <input
                            value={form.technical}
                            onChange={(event) =>
                              setForm({
                                ...form,
                                technical: event.target.value,
                              })
                            }
                            placeholder="Observações complementares"
                          />
                        </label>
                        <Combo
                          label="Responsável"
                          value={form.owner}
                          options={people.map((person) => person.name)}
                          onChange={(value) =>
                            setForm({ ...form, owner: value })
                          }
                          placeholder="Selecione o responsável..."
                        />
                      </div>
                      <div className="code-preview">
                        <span>
                          Código gerado · PE.COR.GLO.QUA.003, item 7
                          {form.category === 'Agregados' &&
                            ' (categoria sem codificação prevista na norma — código interno)'}
                        </span>
                        <code>{generatedCode}</code>
                      </div>
                    </>
                  )}
                  <div className="upload">
                    <div>
                      <FileText size={22} />
                      <span>
                        <strong>Anexar carta traço para aprovação *</strong>
                        <small>
                          PDF, Word, Excel, PPT, imagem, vídeo ou áudio · até 3
                          arquivos
                        </small>
                        {traceFiles.length > 0 && (
                          <small>
                            Selecionados:{' '}
                            {traceFiles.map((file) => file.name).join(', ')}
                          </small>
                        )}
                      </span>
                    </div>
                    <label className="upload-btn">
                      Selecionar arquivos
                      <input
                        type="file"
                        multiple
                        hidden
                        onChange={(event) =>
                          setTraceFiles(Array.from(event.target.files || []))
                        }
                      />
                    </label>
                  </div>
                  <div className="upload">
                    <div>
                      <FileText size={22} />
                      <span>
                        <strong>Anexar checklist de análise do traço *</strong>
                        <small>
                          PDF, Word, Excel, PPT, imagem, vídeo ou áudio · até 2
                          arquivos
                        </small>
                        {form.category && (
                          <small>
                            Check List aplicável (item 13):{' '}
                            {form.category === 'Misturas asfálticas'
                              ? 'FO.COR.GLO.QUA.010 (CBUQ) ou FO.COR.GLO.QUA.011 (micro revestimento), conforme o material'
                              : form.category === 'Camadas cimentícias'
                                ? 'FO.COR.GLO.QUA.012 (BGMC/BGTC)'
                                : 'FO.COR.GLO.QUA.013 (BGS), FO.CR.GLO.QUA.019 (Macadame Seco) ou FO.CR.GLO.QUA.020 (Solo Cimento)'}
                          </small>
                        )}
                        {checklistFiles.length > 0 && (
                          <small>
                            Selecionados:{' '}
                            {checklistFiles.map((file) => file.name).join(', ')}
                          </small>
                        )}
                      </span>
                    </div>
                    <label className="upload-btn">
                      Selecionar arquivos
                      <input
                        type="file"
                        multiple
                        hidden
                        onChange={(event) =>
                          setChecklistFiles(
                            Array.from(event.target.files || []),
                          )
                        }
                      />
                    </label>
                  </div>
                </div>
                <footer>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => setShowForm(false)}
                  >
                    Cancelar
                  </button>
                  <button className="primary" disabled={submitting}>
                    {submitting
                      ? 'Salvando documentos...'
                      : 'Criar solicitação'}
                  </button>
                </footer>
              </form>
            </div>
          )}
          {selected && (
            <div
              className="drawer-backdrop"
              role="presentation"
              onMouseDown={(event) => {
                if (event.target === event.currentTarget) setSelected(null);
              }}
            >
              <aside className="drawer">
                <header>
                  <div>
                    <small>DETALHES DO TRAÇO</small>
                    <h2>{selected.code}</h2>
                  </div>
                  <button onClick={() => setSelected(null)} aria-label="Fechar">
                    <X size={17} />
                  </button>
                </header>
                <div className="drawer-body">
                  <div className="detail-status">
                    <div>
                      <small>Status atual</small>
                      <Pill status={selected.status} />
                    </div>
                    <label>
                      Atualizar status
                      <select
                        value={selected.status}
                        onChange={(event) =>
                          changeStatus(
                            selected.id,
                            event.target.value as Status,
                          )
                        }
                      >
                        {statuses.map((status) => (
                          <option key={status}>{status}</option>
                        ))}
                      </select>
                    </label>
                    <div className="detail-owner">
                      <small>Responsável</small>
                      <Combo
                        value={selected.owner}
                        options={people.map((person) => person.name)}
                        onChange={(value) => changeOwner(selected.id, value)}
                        placeholder="Selecionar responsável..."
                      />
                    </div>
                  </div>
                  <dl>
                    <div>
                      <dt>Unidade</dt>
                      <dd>{selected.unit}</dd>
                    </div>
                    <div>
                      <dt>Contrato</dt>
                      <dd>{selected.contract}</dd>
                    </div>
                    <div>
                      <dt>Construtora</dt>
                      <dd>{selected.company}</dd>
                    </div>
                    <div>
                      <dt>Categoria</dt>
                      <dd>{selected.category}</dd>
                    </div>
                    <div>
                      <dt>Material</dt>
                      <dd>{selected.material}</dd>
                    </div>
                    <div>
                      <dt>Aplicação</dt>
                      <dd>{selected.place}</dd>
                    </div>
                  </dl>
                  {selected.note && (
                    <div className="note">
                      <b>Observação técnica</b>
                      <p>{selected.note}</p>
                    </div>
                  )}
                  <TraceFilesPanel
                    key={selected.id}
                    traceId={selected.id}
                    token={token}
                    flash={flash}
                    onOpenEditor={() => {
                      setToolTraceId(selected.id);
                      setSelected(null);
                      setMode('ferramentas');
                    }}
                  />
                  <div className="norm-note">
                    <b>PE.COR.GLO.QUA.003</b>
                    <p>
                      Item 9: validade máxima de 12 meses a partir da data de
                      conferência no carimbo de aprovação. Item 6: a Motiva tem
                      até 5 dias úteis para retornar o parecer após a submissão
                      completa (mínimo de 15 dias de antecedência da aplicação).
                    </p>
                  </div>
                  <h3>Histórico</h3>
                  <div className="timeline">
                    {[...selected.history].reverse().map((entry, index) => (
                      <div key={`${entry.date}-${index}`}>
                        <i className={statusMeta[entry.status].className} />
                        <span>
                          <b>{entry.status}</b>
                          <small>
                            {entry.date}
                            <br />
                            {entry.owner}
                          </small>
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </aside>
            </div>
          )}
        </div>
      )}
      {toast && (
        <div className="toast">
          <CheckCircle2 size={17} />
          {toast}
        </div>
      )}
    </div>
  );
}
