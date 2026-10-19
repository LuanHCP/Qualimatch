import { createServer } from 'node:http';
import { createHash, createHmac, randomUUID } from 'node:crypto';
import { spawn } from 'node:child_process';
import {
  copyFileSync,
  cpSync,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
  unlinkSync,
  writeFileSync,
} from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import ExcelJS from 'exceljs';
import pg from 'pg';

const projectRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const { Pool } = pg;
const port = Number(process.env.API_PORT || 3001);
const origin = process.env.APP_ORIGIN || 'http://localhost:3000';
// Chave compartilhada só com o QualiMatch (qualimatch/traces_launcher.py),
// usada para assinar o login automático quando o Controle de Traços é aberto
// a partir de lá — sem isso, quem já logou no QualiMatch teria que logar de
// novo aqui dentro, o que não faz sentido. Gerada uma única vez e gravada em
// disco (nunca no código-fonte/git) num arquivo que o QualiMatch lê
// diretamente do mesmo jeito que já lê sessions.json/sync-config.json.
const ssoSecretPath = path.join(projectRoot, 'server', 'qualimatch-sso.key');
function loadOrCreateSsoSecret() {
  try {
    const existing = readFileSync(ssoSecretPath, 'utf8').trim();
    if (existing) return existing;
  } catch {}
  const secret = randomUUID().replace(/-/g, '') + randomUUID().replace(/-/g, '');
  try {
    mkdirSync(path.dirname(ssoSecretPath), { recursive: true });
    writeFileSync(ssoSecretPath, secret, 'utf8');
  } catch (error) {
    console.error('Não foi possível gravar a chave de SSO:', error.message);
  }
  return secret;
}
const QUALIMATCH_SSO_SECRET = loadOrCreateSsoSecret();
const pool = process.env.DATABASE_URL
  ? new Pool({ connectionString: process.env.DATABASE_URL })
  : null;

async function repairStatusConstraint() {
  if (!pool) return;
  const client = await pool.connect();
  try {
    await client.query('begin');
    await client.query(
      'alter table traces drop constraint if exists traces_status_check',
    );
    await client.query(
      "update traces set status='Não conforme' where status in ('NÃ£o conforme','NÃƒÂ£o conforme')",
    );
    await client.query(
      "update traces set status='Em análise' where status in ('Em anÃ¡lise','Em anÃƒÂ¡lise')",
    );
    await client.query(
      "update trace_history set status='Não conforme' where status in ('NÃ£o conforme','NÃƒÂ£o conforme')",
    );
    await client.query(
      "update trace_history set status='Em análise' where status in ('Em anÃ¡lise','Em anÃƒÂ¡lise')",
    );
    await client.query(
      "alter table traces add constraint traces_status_check check (status in ('Aprovado','Não conforme','Restrito','Cancelado','Em análise','Solicitado'))",
    );
    await client.query('commit');
  } catch (error) {
    await client.query('rollback');
    throw error;
  } finally {
    client.release();
  }
}

try {
  await repairStatusConstraint();
} catch (error) {
  console.error('Não foi possível corrigir os status do banco:', error.message);
}
// Armazenamento local dos anexos e configuração da pasta sincronizada
// (OneDrive/SharePoint) — mesmo padrão usado no QualiMatch: nada de API do
// SharePoint, só um caminho local que o usuário aponta manualmente.
const uploadsRoot = path.join(projectRoot, 'uploads');
const configPath = path.join(projectRoot, 'server', 'sync-config.json');
const sessionsPath = path.join(projectRoot, 'server', 'sessions.json');
const inventorySheets = new Set([
  'CONCRETO',
  'BGS',
  'BGTC',
  'CBUQ',
  'MRAF',
  'TSD',
  'PMF',
  'MACADAME',
]);
let inventoryCache = { filePath: '', mtimeMs: 0, records: [] };
let inventoryDocuments = new Map();
let inventoryFolders = new Map();
let localPdfIndex = [];
let spreadsheetPdfByCode = new Map();
const inventoryStatusFolders = [
  ['03. Aprovados', 'Aprovado'],
  ['04. Em análise', 'Em análise'],
  ['04. Restritos', 'Restrito'],
  ['05. Não conforme', 'Não conforme'],
  ['05. Reprovados', 'Reprovado'],
];

// As sessões ficam gravadas em disco: antes elas viviam só na memória, então
// toda vez que o servidor reiniciava (fechar/abrir o iniciar.bat) o navegador
// continuava com o token antigo e tudo respondia "Sessão inválida".
const sessions = new Map();
function loadSessions() {
  try {
    const saved = JSON.parse(readFileSync(sessionsPath, 'utf8'));
    for (const [token, user] of Object.entries(saved))
      sessions.set(token, user);
  } catch {}
}
function persistSessions() {
  try {
    mkdirSync(path.dirname(sessionsPath), { recursive: true });
    writeFileSync(
      sessionsPath,
      JSON.stringify(Object.fromEntries(sessions), null, 2),
      'utf8',
    );
  } catch (error) {
    console.error('Não foi possível gravar as sessões:', error.message);
  }
}
loadSessions();

function safeName(name) {
  const cleaned = String(name)
    .split('')
    .map((character) => (character.charCodeAt(0) < 32 ? '_' : character))
    .join('')
    .replace(/[<>:"/\\|?*]/g, '_')
    .replace(/\.\.+/g, '.')
    .trim()
    .replace(/[. ]+$/g, '');
  // Evita estourar o limite de caminho do Windows (MAX_PATH ~260 chars),
  // já que os nomes de traço aqui são bem descritivos e o projeto já mora
  // num caminho fundo (OneDrive/Documents/...). Mantém a extensão.
  const MAX_LEN = 120;
  if (cleaned.length <= MAX_LEN) return cleaned;
  const dot = cleaned.lastIndexOf('.');
  const ext = dot > 0 ? cleaned.slice(dot) : '';
  const base = dot > 0 ? cleaned.slice(0, dot) : cleaned;
  return base.slice(0, Math.max(1, MAX_LEN - ext.length)) + ext;
}
function safeTraceId(traceId) {
  const value = String(traceId || '').trim();
  return /^[a-zA-Z0-9_-]{1,100}$/.test(value) ? value : '';
}
function readSyncConfig() {
  try {
    const config = JSON.parse(readFileSync(configPath, 'utf8'));
    return {
      sharePointPath: String(config.sharePointPath || ''),
      certificatesPath: String(config.certificatesPath || ''),
      inventoryPath: String(config.inventoryPath || ''),
      traceLibraryPath: String(config.traceLibraryPath || ''),
      sitePaths:
        config.sitePaths && typeof config.sitePaths === 'object'
          ? config.sitePaths
          : {},
    };
  } catch {
    return {
      sharePointPath: '',
      certificatesPath: '',
      inventoryPath: '',
      traceLibraryPath: '',
      sitePaths: {},
    };
  }
}
function writeSyncConfig(config) {
  mkdirSync(path.dirname(configPath), { recursive: true });
  writeFileSync(configPath, JSON.stringify(config, null, 2), 'utf8');
}
function libraryStatusFolder(status) {
  return (
    {
      Aprovado: '03. Aprovados',
      Solicitado: '04. Em análise',
      'Em análise': '04. Em análise',
      Restrito: '04. Restritos',
      'Não conforme': '05. Não conforme',
      Cancelado: '05. Reprovados',
    }[status] || '04. Em análise'
  );
}

function libraryCategoryFolder(trace = {}) {
  const key = inventoryHeaderKey(`${trace.category || ''} ${trace.material || ''}`);
  if (/CONCRETO|ARGAMASSA|CALDA/.test(key)) return '01. Concreto';
  if (/BGTC|TRATADA COM CIMENTO|MELHORADA COM CIMENTO|CIMENTICIA/.test(key))
    return '05. BGTC';
  if (/MACADAME/.test(key)) return '06. Macadame';
  if (/RACHAO/.test(key)) return '04. Rachão';
  if (/BGS|BRITA GRADUADA SIMPLES|PEDRA BRITADA|AGREGADO/.test(key))
    return '03. BGS';
  return '02. CBUQ';
}

function mirrorToSharePoint(traceId, status, trace = {}) {
  const config = readSyncConfig();
  const libraryRoot =
    String(config.sitePaths?.[trace.unit] || '').trim() ||
    config.traceLibraryPath;
  if (!libraryRoot || !existsSync(libraryRoot)) return;
  const traceDir = path.join(uploadsRoot, traceId);
  const files = existsSync(traceDir)
    ? readdirSync(traceDir, { withFileTypes: true })
        .filter((entry) => entry.isFile())
        .map((entry) => entry.name)
    : [];
  const traceFolder = safeName(trace.code || traceId);
  if (!traceFolder) return;
  const statusFolder = libraryStatusFolder(status);
  const categoryFolder = libraryCategoryFolder(trace);
  const newDir = path.join(libraryRoot, statusFolder, categoryFolder, traceFolder);
  const publicNames = files.map((file) =>
    file.replace(/^(trace|checklist)-/, ''),
  );

  mkdirSync(newDir, { recursive: true });
  for (const [officialFolder] of inventoryStatusFolders) {
    const officialPath = path.join(libraryRoot, officialFolder);
    if (!existsSync(officialPath)) continue;
    for (const category of readdirSync(officialPath, { withFileTypes: true })) {
      if (!category.isDirectory()) continue;
      const oldDir = path.join(officialPath, category.name, traceFolder);
      if (!existsSync(oldDir) || path.resolve(oldDir) === path.resolve(newDir))
        continue;
      try {
        cpSync(oldDir, newDir, { recursive: true, force: true });
        rmSync(oldDir, { recursive: true, force: true });
      } catch (error) {
        console.error(`Não foi possível mover ${oldDir}:`, error.message);
      }
    }
  }

  files.forEach((file, index) => {
    try {
      copyFileSync(
        path.join(traceDir, file),
        path.join(newDir, publicNames[index]),
      );
    } catch (error) {
      console.error(`Não foi possível copiar ${file}:`, error.message);
    }
  });
}

function listCertificatePdfs(statusDir) {
  const pdfs = [];
  for (const entry of readdirSync(statusDir, { withFileTypes: true })) {
    if (entry.isFile() && entry.name.toLowerCase().endsWith('.pdf')) {
      pdfs.push({
        code: path.basename(entry.name, path.extname(entry.name)),
        fileName: entry.name,
        filePath: path.join(statusDir, entry.name),
      });
      continue;
    }
    if (!entry.isDirectory()) continue;
    const traceDir = path.join(statusDir, entry.name);
    for (const file of readdirSync(traceDir, { withFileTypes: true })) {
      if (file.isFile() && file.name.toLowerCase().endsWith('.pdf'))
        pdfs.push({
          code: entry.name,
          fileName: file.name,
          filePath: path.join(traceDir, file.name),
        });
    }
  }
  return pdfs;
}

function inventoryValueText(value) {
  if (value === null || value === undefined) return '';
  if (value instanceof Date) {
    if (Number.isNaN(value.getTime()) || value.getUTCFullYear() < 2000) return '';
    return value.toLocaleDateString('pt-BR', { timeZone: 'UTC' });
  }
  if (typeof value === 'object') {
    if ('text' in value) return String(value.text || '').trim();
    if ('result' in value) return inventoryValueText(value.result);
    if (Array.isArray(value.richText))
      return value.richText.map((part) => part.text || '').join('').trim();
  }
  return String(value).trim();
}

function inventoryCellText(cell) {
  return inventoryValueText(cell?.value);
}

function normalizeInventoryLink(link) {
  const value = String(link || '').replace(/\\/g, '/').trim();
  if (!value) return '';
  if (/^https?:\/\//i.test(value)) return value;
  const sharePointPath = value.match(/(:[a-z]:\/r\/sites\/.*)$/i)?.[1];
  return sharePointPath
    ? `https://grupoccr.sharepoint.com/${sharePointPath}`
    : '';
}

function inventoryLinkRelativeToGeneral(link) {
  let value = String(link || '').replace(/\\/g, '/').trim();
  if (!value) return '';
  const idParameter = value.match(/[?&]id=([^&]+)/i)?.[1];
  if (idParameter) value = idParameter;
  else value = value.split('?')[0];
  try {
    value = decodeURIComponent(value);
  } catch {}
  value = value.replace(/\\/g, '/');
  const marker = '/Documentos Compartilhados/General/';
  const markerIndex = value.toLocaleLowerCase('pt-BR').indexOf(
    marker.toLocaleLowerCase('pt-BR'),
  );
  if (markerIndex >= 0) return value.slice(markerIndex + marker.length);
  const generalIndex = value.toLocaleLowerCase('pt-BR').indexOf('/general/');
  return generalIndex >= 0 ? value.slice(generalIndex + '/general/'.length) : '';
}

function localFileFromInventoryLink(link, libraryPath) {
  const relative = inventoryLinkRelativeToGeneral(link);
  if (!relative || !libraryPath) return '';
  const generalMarker = `${path.sep}General${path.sep}`;
  const markerIndex = libraryPath.toLocaleLowerCase('pt-BR').indexOf(
    generalMarker.toLocaleLowerCase('pt-BR'),
  );
  const generalRoot =
    markerIndex >= 0
      ? libraryPath.slice(0, markerIndex + generalMarker.length - 1)
      : path.dirname(libraryPath);
  const direct = path.join(generalRoot, ...relative.split('/').filter(Boolean));

  // Links antigos usam "02. CTR" ou "02. Carta Traço". No computador a
  // pasta atual se chama "02. CARTAS TRAÇOS"; conserva o restante do caminho.
  const parts = relative.split('/').filter(Boolean);
  const oldLibraryIndex = parts.findIndex((part) =>
    /^(?:02\.\s*)?(?:CTR|CARTA(?:S)?\s*TRA)/i.test(part),
  );
  if (oldLibraryIndex >= 0) {
    return path.join(libraryPath, ...parts.slice(oldLibraryIndex + 1));
  }
  // Não chama existsSync aqui: há centenas de links e o Windows/OneDrive pode
  // tentar hidratar cada caminho remoto, bloqueando todo o servidor. A
  // existência é conferida somente quando aquele traço é aberto.
  return direct;
}

function inventoryHeaderKey(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toUpperCase()
    .replace(/\s+/g, ' ')
    .trim();
}

function findInventoryColumn(headers, predicate) {
  return headers.find((header) => predicate(header.key))?.column || 0;
}

async function readSpreadsheetInventory() {
  const { inventoryPath, traceLibraryPath } = readSyncConfig();
  if (!inventoryPath || !existsSync(inventoryPath))
    throw new Error('Configure uma planilha de inventário válida.');
  const info = statSync(inventoryPath);
  if (
    inventoryCache.filePath === inventoryPath &&
    inventoryCache.mtimeMs === info.mtimeMs
  )
    return inventoryCache.records;

  const workbook = new ExcelJS.Workbook();
  await workbook.xlsx.readFile(inventoryPath, {
    ignoreNodes: [
      'dataValidations',
      'sheetPr',
      'sheetViews',
      'sheetFormatPr',
      'cols',
      'mergeCells',
      'conditionalFormatting',
      'pageMargins',
      'pageSetup',
      'headerFooter',
      'printOptions',
      'picture',
      'drawing',
      'sheetProtection',
      'tableParts',
      'extLst',
    ],
  });
  const records = [];
  workbook.eachSheet((worksheet) => {
    if (!inventorySheets.has(worksheet.name.trim())) return;
    let headerRow = 0;
    let headers = [];
    for (
      let rowNumber = 1;
      rowNumber <= Math.min(5, worksheet.rowCount);
      rowNumber += 1
    ) {
      const candidates = [];
      worksheet
        .getRow(rowNumber)
        .eachCell({ includeEmpty: false }, (cell, column) => {
          candidates.push({
            column,
            key: inventoryHeaderKey(inventoryCellText(cell)),
          });
        });
      if (candidates.some((header) => header.key.startsWith('LINK'))) {
        headerRow = rowNumber;
        headers = candidates;
        break;
      }
    }
    if (!headerRow) return;

    const column = {
      code: findInventoryColumn(headers, (key) =>
        key.includes('DIGO INTERNO'),
      ),
      trace: findInventoryColumn(
        headers,
        (key) => key.startsWith('TRA') && key.length <= 16,
      ),
      type: findInventoryColumn(headers, (key) =>
        key.includes('TIPO DE TRA'),
      ),
      contract: findInventoryColumn(headers, (key) =>
        key.includes('CONTRATO'),
      ),
      company: findInventoryColumn(
        headers,
        (key) => key === 'EMPRESA' || key === 'CONSTRUTORA',
      ),
      plant: findInventoryColumn(headers, (key) => key === 'USINA'),
      source: findInventoryColumn(
        headers,
        (key) => key.includes('ORIGEM DO AGREGADO') || key === 'PEDREIRA',
      ),
      status: findInventoryColumn(headers, (key) => key === 'STATUS'),
      approvalDate: findInventoryColumn(
        headers,
        (key) => key.includes('DATA') && key.includes('APROVA'),
      ),
      validityDate: findInventoryColumn(
        headers,
        (key) =>
          key.includes('DATA') &&
          (key.includes('VALIDADE') || key.includes('VENCIMENTO')),
      ),
      link: findInventoryColumn(
        headers,
        (key) => key.startsWith('LINK') && !key.includes('E-MAIL'),
      ),
    };

    for (
      let rowNumber = headerRow + 1;
      rowNumber <= worksheet.rowCount;
      rowNumber += 1
    ) {
      const row = worksheet.getRow(rowNumber);
      const code = inventoryCellText(row.getCell(column.code || 2));
      const trace = inventoryCellText(row.getCell(column.trace || 4));
      const status = inventoryCellText(row.getCell(column.status));
      const linkCell = row.getCell(column.link);
      const linkValue =
        linkCell.hyperlink ||
        (typeof linkCell.value === 'object' && linkCell.value
          ? linkCell.value.hyperlink
          : '');
      const link = normalizeInventoryLink(linkValue);
      const localFilePath = localFileFromInventoryLink(
        linkValue || link,
        traceLibraryPath || path.dirname(inventoryPath),
      );
      if ((!code && !trace) || (!status && !link)) continue;
      records.push({
        id: `${worksheet.name}-${rowNumber}`,
        sheet: worksheet.name.trim(),
        code,
        trace,
        type: inventoryCellText(row.getCell(column.type)) || worksheet.name,
        contract: inventoryCellText(row.getCell(column.contract)),
        company: inventoryCellText(row.getCell(column.company)),
        plant:
          inventoryCellText(row.getCell(column.plant)) ||
          inventoryCellText(row.getCell(column.source)),
        status,
        approvalDate: inventoryCellText(row.getCell(column.approvalDate)),
        validityDate: inventoryCellText(row.getCell(column.validityDate)),
        fileName: localFilePath
          ? path.basename(localFilePath)
          : inventoryCellText(linkCell),
        link,
        localFilePath,
      });
    }
  });
  inventoryCache = { filePath: inventoryPath, mtimeMs: info.mtimeMs, records };
  return records;
}

function inventoryComparable(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, '');
}

function inventoryCategory(folderName) {
  const key = inventoryComparable(folderName).replace(/^\d+/, '');
  // O acervo chama os materiais granulares de "Rachão", enquanto a
  // planilha usa a aba MACADAME. Sem esse alias todas essas cartas eram
  // simplesmente ignoradas pela varredura.
  if (key.includes('RACHAO')) return 'MACADAME';
  return [...inventorySheets].find((sheet) => key.includes(sheet)) || '';
}

function listFilesRecursively(folder, depth = 0) {
  const result = [];
  try {
    for (const entry of readdirSync(folder, { withFileTypes: true })) {
      const filePath = path.join(folder, entry.name);
      if (entry.isDirectory()) {
        result.push(...listFilesRecursively(filePath, depth + 1));
      } else if (entry.isFile()) {
        result.push({ filePath, fileName: entry.name, depth });
      }
    }
  } catch (error) {
    // Um arquivo do OneDrive ainda hidratando não pode interromper a leitura
    // dos outros 200+ documentos do acervo.
    console.error(`Falha ao ler a pasta ${folder}:`, error.message);
  }
  return result;
}

function buildLocalPdfIndex(libraryPath) {
  const pdfs = [];
  for (const [statusFolder, status] of inventoryStatusFolders) {
    const statusPath = path.join(libraryPath, statusFolder);
    if (!existsSync(statusPath)) continue;
    for (const file of listFilesRecursively(statusPath)) {
      if (!file.fileName.toLowerCase().endsWith('.pdf')) continue;
      const relativePath = path.relative(statusPath, file.filePath);
      const segments = relativePath.split(path.sep).filter(Boolean);
      const documentId = createHash('sha256')
        .update(file.filePath)
        .digest('hex')
        .slice(0, 24);
      pdfs.push({
        ...file,
        documentId,
        status,
        relativePath,
        segmentKeys: segments.map(inventoryComparable),
        fileKey: inventoryComparable(path.basename(file.fileName, path.extname(file.fileName))),
        relativeKey: inventoryComparable(relativePath),
      });
    }
  }
  return pdfs;
}

function localPdfScore(document, traceCode) {
  const code = inventoryComparable(traceCode);
  if (code.length < 3) return -1;
  let score = -1;
  if (document.fileKey === code) score = 700;
  else if (code.length >= 4 && document.fileKey.startsWith(code)) score = 620;

  for (const segment of document.segmentKeys) {
    if (segment === code) score = Math.max(score, 680);
    else if (code.length >= 4 && segment.startsWith(code))
      score = Math.max(score, 560);
  }
  if (score < 0 && code.length >= 4 && document.relativeKey.includes(code))
    score = 320;
  if (score < 0) return -1;

  // Prefere a carta propriamente dita a relatórios de ensaio, certificados
  // de calibração e documentos antigos encontrados na mesma árvore.
  if (/APROVAD|RESTRIT|ASSINAD|CARTA|TRACO/.test(document.fileKey)) score += 60;
  if (/EMAIL|ATA|CHECKLIST|RELATORIO|ENSAIO|RESIST|CIMENTO|FISPQ|CALIBRA|ANTIGO/.test(document.fileKey))
    score -= 90;
  score -= document.depth * 3;
  return score;
}

function findLocalPdfForCode(traceCode) {
  const exact = spreadsheetPdfByCode.get(inventoryComparable(traceCode));
  if (exact && existsSync(exact.filePath)) {
    inventoryDocuments.set(exact.documentId, exact);
    return exact;
  }
  return [...localPdfIndex]
    .map((document) => ({ document, score: localPdfScore(document, traceCode) }))
    .filter((item) => item.score >= 0)
    .sort(
      (left, right) =>
        right.score - left.score ||
        right.document.filePath.localeCompare(left.document.filePath, 'pt-BR'),
    )[0]?.document;
}

function primaryPdf(pdfs, traceFolder) {
  const traceKey = inventoryComparable(traceFolder);
  return [...pdfs].sort((left, right) => {
    const score = (item) => {
      const name = inventoryComparable(item.fileName);
      let value = -item.depth * 30;
      if (traceKey && (name.includes(traceKey) || traceKey.includes(name))) value += 80;
      if (/APROVAD|RESTRIT|NAOCONFORM|REPROVAD|ASSINAD/.test(name)) value += 25;
      if (/EMAIL|ATA|CHECKLIST|RELATORIO|ENSAIO|RESIST|CIMENTO|FISPQ|DOCUMENTO/.test(name))
        value -= 35;
      return value;
    };
    return score(right) - score(left) || left.fileName.localeCompare(right.fileName, 'pt-BR');
  })[0];
}

function spreadsheetMatch(folderName, spreadsheetRecords, sheet) {
  const folderKey = inventoryComparable(folderName);
  const candidates = spreadsheetRecords.filter((item) => item.sheet === sheet);
  return (
    candidates.find((item) => {
      const code = inventoryComparable(item.code);
      return code.length >= 3 && folderKey.startsWith(code);
    }) ||
    candidates.find((item) => {
      const trace = inventoryComparable(item.trace);
      return trace.length >= 6 && (folderKey.includes(trace) || trace.includes(folderKey));
    }) ||
    candidates.find((item) => {
      const contract = inventoryComparable(item.contract);
      return contract.length >= 6 && folderKey.includes(contract);
    })
  );
}

async function readTraceInventory() {
  const config = readSyncConfig();
  const libraryPath =
    config.traceLibraryPath ||
    (config.inventoryPath ? path.dirname(config.inventoryPath) : '');
  if (!libraryPath || !existsSync(libraryPath))
    throw new Error('Configure uma pasta válida para o acervo de cartas-traço.');

  let spreadsheetRecords = [];
  try {
    spreadsheetRecords = await readSpreadsheetInventory();
  } catch {}

  const records = [];
  const documents = new Map();
  const folders = new Map();
  // Este índice é propositalmente independente da planilha e das categorias
  // conhecidas. Assim todo PDF sincronizado pode ser associado a um traço já
  // existente no banco pelo seu código, inclusive em Rachão/Subleito e em
  // níveis extras de subpastas.
  localPdfIndex = buildLocalPdfIndex(libraryPath);
  for (const document of localPdfIndex)
    documents.set(document.documentId, document);
  spreadsheetPdfByCode = new Map();
  for (const record of spreadsheetRecords) {
    if (!record.localFilePath) continue;
    if (!record.localFilePath.toLowerCase().endsWith('.pdf')) continue;
    const documentId = createHash('sha256')
      .update(record.localFilePath)
      .digest('hex')
      .slice(0, 24);
    const document = {
      filePath: record.localFilePath,
      fileName: path.basename(record.localFilePath),
      depth: 0,
      documentId,
      status: record.status,
      relativePath: record.localFilePath,
      segmentKeys: record.localFilePath.split(path.sep).map(inventoryComparable),
      fileKey: inventoryComparable(path.basename(record.localFilePath, '.pdf')),
      relativeKey: inventoryComparable(record.localFilePath),
      mtimeMs: 0,
    };
    const codeKey = inventoryComparable(record.code || record.trace);
    if (codeKey) spreadsheetPdfByCode.set(codeKey, document);
  }
  for (const [statusFolder, status] of inventoryStatusFolders) {
    const statusPath = path.join(libraryPath, statusFolder);
    if (!existsSync(statusPath)) continue;
    for (const categoryEntry of readdirSync(statusPath, { withFileTypes: true })) {
      if (!categoryEntry.isDirectory()) continue;
      const sheet = inventoryCategory(categoryEntry.name);
      if (!sheet) continue;
      const categoryPath = path.join(statusPath, categoryEntry.name);
      for (const traceEntry of readdirSync(categoryPath, { withFileTypes: true })) {
        if (!traceEntry.isDirectory() && !traceEntry.name.toLowerCase().endsWith('.pdf'))
          continue;
        const traceFolder = traceEntry.isDirectory()
          ? traceEntry.name
          : path.basename(traceEntry.name, path.extname(traceEntry.name));
        const tracePath = path.join(categoryPath, traceEntry.name);
        if (inventoryHeaderKey(traceFolder).includes('ANTIGO')) continue;
        const files = traceEntry.isDirectory()
          ? listFilesRecursively(tracePath)
          : [{ filePath: tracePath, fileName: traceEntry.name, depth: 0 }];
        const pdfs = files.filter((file) => file.fileName.toLowerCase().endsWith('.pdf'));
        const primary = pdfs.length ? primaryPdf(pdfs, traceFolder) : null;
        const documentId = primary
          ? createHash('sha256').update(primary.filePath).digest('hex').slice(0, 24)
          : '';
        if (primary) documents.set(documentId, primary);
        const matched = spreadsheetMatch(traceFolder, spreadsheetRecords, sheet) || {};
        const codeFromFolder =
          traceFolder.match(/^(?:[A-Z]{1,8}[\s_-]*\d{1,8}|\d{6,})/i)?.[0] || '';
        if (!codeFromFolder && !matched.code) continue;
        const folderPath = traceEntry.isDirectory() ? tracePath : categoryPath;
        const folderId = createHash('sha256')
          .update(folderPath)
          .digest('hex')
          .slice(0, 24);
        folders.set(folderId, folderPath);
        const folderCode = codeFromFolder.replace(/[\s_]+/g, '-');
        const isContractFolder = /^\d{6,}$/.test(inventoryComparable(folderCode));
        records.push({
          id: `${statusFolder}-${categoryEntry.name}-${traceFolder}`,
          sheet,
          code: (isContractFolder ? folderCode : matched.code || folderCode) || traceFolder,
          trace: isContractFolder ? traceFolder : matched.trace || traceFolder,
          type: matched.type || sheet,
          contract: matched.contract || '',
          company: matched.company || '',
          plant: matched.plant || '',
          status,
          approvalDate: matched.approvalDate || '',
          validityDate: matched.validityDate || '',
          fileName: primary?.fileName || '',
          link: matched.link || '',
          documentId,
          documentCount: pdfs.length,
          folderId,
          fileCount: files.length,
          _mtimeMs: primary
            ? statSync(primary.filePath).mtimeMs
            : statSync(folderPath).mtimeMs,
        });
      }
    }
  }
  inventoryDocuments = documents;
  inventoryFolders = folders;
  const currentRecords = new Map();
  for (const record of records) {
    const key = `${record.sheet}:${inventoryComparable(record.code)}`;
    const current = currentRecords.get(key);
    if (!current || record._mtimeMs > current._mtimeMs)
      currentRecords.set(key, record);
  }
  // A linha da planilha é a associação autoritativa código -> PDF. A pasta
  // ainda define o status quando existe, mas nunca mais pode emprestar o PDF
  // de outro código por semelhança de nome.
  for (const sheetRecord of spreadsheetRecords) {
    if (!sheetRecord.localFilePath) continue;
    if (!sheetRecord.localFilePath.toLowerCase().endsWith('.pdf')) continue;
    const code = String(sheetRecord.code || sheetRecord.trace || '').trim();
    if (!code) continue;
    const key = `${sheetRecord.sheet}:${inventoryComparable(code)}`;
    const current = currentRecords.get(key);
    const documentId = createHash('sha256')
      .update(sheetRecord.localFilePath)
      .digest('hex')
      .slice(0, 24);
    const folderPath = path.dirname(sheetRecord.localFilePath);
    const folderId = createHash('sha256')
      .update(folderPath)
      .digest('hex')
      .slice(0, 24);
    const indexedDocument = localPdfIndex.find(
      (item) =>
        item.filePath.toLocaleLowerCase('pt-BR') ===
        sheetRecord.localFilePath.toLocaleLowerCase('pt-BR'),
    );
    if (indexedDocument) {
      documents.set(documentId, indexedDocument);
      folders.set(folderId, folderPath);
    }
    currentRecords.set(key, {
      ...sheetRecord,
      ...current,
      id: current?.id || sheetRecord.id,
      code,
      status: current?.status || sheetRecord.status,
      fileName: path.basename(sheetRecord.localFilePath),
      link: sheetRecord.link,
      documentId: indexedDocument ? documentId : '',
      documentCount: current?.documentCount || 1,
      folderId: indexedDocument ? folderId : '',
      fileCount: current?.fileCount || 1,
      _mtimeMs: indexedDocument?.mtimeMs || current?._mtimeMs || 0,
    });
  }
  inventoryDocuments = documents;
  inventoryFolders = folders;
  return [...currentRecords.values()].map(({ _mtimeMs, ...record }) => record).sort((a, b) =>
    a.code.localeCompare(b.code, 'pt-BR', { numeric: true }),
  );
}

function send(res, status, body) {
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Access-Control-Allow-Origin': origin,
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Access-Control-Allow-Methods': 'GET, POST, PATCH, DELETE, OPTIONS',
  });
  res.end(JSON.stringify(body));
}
async function readBody(req, limit = 1_000_000) {
  let raw = '';
  for await (const chunk of req) {
    raw += chunk;
    if (raw.length > limit) {
      const mb = Math.round(limit / 1_000_000);
      throw new Error(`Arquivo muito grande para enviar (limite de ${mb}MB).`);
    }
  }
  return raw ? JSON.parse(raw) : {};
}
// Formata a linha do banco (snake_case) no formato que o front-end usa
// (camelCase), calculando as iniciais junto — usado no login, na sessão
// salva em disco e nas rotas de administração de usuários.
function userToApi(row) {
  return {
    id: row.id,
    name: row.name,
    email: row.email,
    role: row.role,
    isAdmin: !!row.is_admin,
    sites: Array.isArray(row.sites) ? row.sites : [],
    active: row.active !== false,
    initials: String(row.name || '')
      .split(/\s+/)
      .filter(Boolean)
      .map((x) => x[0])
      .slice(0, 2)
      .join('')
      .toUpperCase(),
  };
}
function userFrom(req) {
  const token = req.headers.authorization?.replace(/^Bearer /, '');
  if (token === 'local-demo') {
    return {
      id: 'local-demo',
      name: 'Administrador',
      email: 'admin@qualimatch.local',
      role: 'Administrador',
      isAdmin: true,
      sites: [],
      active: true,
      initials: 'AD',
    };
  }
  const saved = token ? sessions.get(token) : null;
  if (!saved) return null;
  const isAdministrator = inventoryComparable(saved.role).includes('ADMINISTRADOR');
  return isAdministrator && !saved.isAdmin
    ? { ...saved, isAdmin: true }
    : saved;
}
// Um usuário comum só enxerga/mexe em traços das Sedes atribuídas a ele;
// administrador (isAdmin) não tem essa restrição.
function canAccessUnit(user, unit) {
  return !!user.isAdmin || (Array.isArray(user.sites) && user.sites.includes(unit));
}
function traceFromRow(row, history = []) {
  return {
    id: row.id,
    code: row.code,
    unit: row.unit,
    company: row.company,
    contract: row.contract,
    category: row.category,
    material: row.material,
    place: row.place,
    status: row.status,
    updated: new Date(row.updated_at).toLocaleString('pt-BR'),
    owner: row.owner,
    note: row.note || '',
    history,
  };
}

function databaseStatus(value) {
  const key = inventoryComparable(value);
  if (key.includes('APROV')) return 'Aprovado';
  if (key.includes('RESTRIT')) return 'Restrito';
  if (key.includes('NAOCONFORM') || key.includes('REPROV'))
    return 'Não conforme';
  if (key.includes('CANCEL')) return 'Cancelado';
  if (key.includes('SOLICIT') || key.includes('PENDENT')) return 'Solicitado';
  return 'Em análise';
}

function databaseCategory(sheet) {
  if (['CBUQ', 'MRAF', 'TSD', 'PMF'].includes(sheet))
    return 'Misturas asfálticas';
  if (['BGS', 'MACADAME'].includes(sheet)) return 'Agregados';
  return 'Camadas cimentícias';
}

async function readAllTraceSources() {
  let spreadsheetRecords = [];
  let folderRecords = [];
  try {
    spreadsheetRecords = await readSpreadsheetInventory();
  } catch {}
  try {
    folderRecords = await readTraceInventory();
  } catch {}
  const combined = new Map();
  for (const record of spreadsheetRecords) {
    const code = String(record.code || record.trace || '').trim();
    const key = inventoryComparable(code);
    if (key.length >= 3) combined.set(key, { ...record, code });
  }
  // A pasta é a fonte oficial para o status e prevalece sobre a planilha.
  for (const record of folderRecords) {
    const key = inventoryComparable(record.code || record.trace);
    if (key.length >= 3)
      combined.set(key, { ...combined.get(key), ...record });
  }
  return [...combined.values()];
}

async function syncOfficialTraces(changedBy) {
  if (!pool) return;
  const sources = await readAllTraceSources();
  const client = await pool.connect();
  try {
    await client.query('begin');
    for (const source of sources) {
      const code = String(source.code || source.trace || '').trim();
      if (!code) continue;
      const status = databaseStatus(source.status);
      const category = databaseCategory(source.sheet);
      const material = String(source.type || source.sheet || 'Não informado');
      const company = String(source.company || 'Não informado');
      const contract = String(source.contract || '');
      const place = String(source.plant || 'Acervo oficial');
      let current = await client.query(
        'select id,status,note from traces where code=$1',
        [code],
      );
      if (!current.rowCount) {
        const inserted = await client.query(
          "insert into traces(id,code,unit,company,contract,category,material,place,status,owner,note) values($1,$2,'PRVias',$3,$4,$5,$6,$7,$8,$9,$10) on conflict(code) do nothing returning id,status,note",
          [
            randomUUID(),
            code,
            company,
            contract,
            category,
            material,
            place,
            status,
            'Acervo oficial',
            'Sincronizado automaticamente do acervo oficial.',
          ],
        );
        current = inserted.rowCount
          ? inserted
          : await client.query('select id,status,note from traces where code=$1', [
              code,
            ]);
        if (inserted.rowCount)
          await client.query(
            'insert into trace_history(trace_id,status,changed_by) values($1,$2,$3)',
            [inserted.rows[0].id, status, changedBy],
          );
        continue;
      }

      const imported = /(?:Sincronizado|Importado) automaticamente/i.test(
        current.rows[0].note || '',
      );
      if (!imported) continue;
      const previousStatus = current.rows[0].status;
      await client.query(
        'update traces set company=$1,contract=$2,category=$3,material=$4,place=$5,status=$6,updated_at=case when status<>$6 then now() else updated_at end where id=$7',
        [
          company,
          contract,
          category,
          material,
          place,
          status,
          current.rows[0].id,
        ],
      );
      if (previousStatus !== status)
        await client.query(
          'insert into trace_history(trace_id,status,changed_by) values($1,$2,$3)',
          [current.rows[0].id, status, changedBy],
        );
    }
    await client.query('commit');
  } catch (error) {
    await client.query('rollback');
    throw error;
  } finally {
    client.release();
  }
}

const server = createServer(async (req, res) => {
  if (req.method === 'OPTIONS') return send(res, 204, {});
  if (req.url === '/health') {
    if (!pool)
      return send(res, 200, {
        ok: true,
        app: 'controle-tracos',
        database: false,
        schemaReady: true,
        message: 'DATABASE_URL não configurada',
      });
    try {
      await pool.query('select 1');
      return send(res, 200, {
        ok: true,
        app: 'controle-tracos',
        database: true,
        schemaReady: true,
      });
    } catch {
      return send(res, 200, {
        ok: true,
        app: 'controle-tracos',
        database: false,
        schemaReady: false,
        message: 'PostgreSQL indisponível',
      });
    }
  }
  if (req.url === '/api/config' && req.method === 'GET') {
    return send(res, 200, readSyncConfig());
  }
  if (req.url === '/api/config' && req.method === 'POST') {
    try {
      const body = await readBody(req);
      const current = readSyncConfig();
      const sharePointPath = String(body.sharePointPath || '').trim();
      const config = {
        sharePointPath,
        certificatesPath: String(
          body.certificatesPath ?? sharePointPath ?? current.certificatesPath ?? '',
        ).trim(),
        inventoryPath: String(
          body.inventoryPath ?? current.inventoryPath ?? '',
        ).trim(),
        traceLibraryPath: String(
          body.traceLibraryPath ?? current.traceLibraryPath ?? '',
        ).trim(),
        sitePaths: Object.fromEntries(
          Object.entries(body.sitePaths ?? current.sitePaths ?? {})
            .map(([site, folder]) => [site, String(folder || '').trim()])
            .filter(([, folder]) => folder),
        ),
      };
      writeSyncConfig(config);
      return send(res, 200, config);
    } catch (error) {
      return send(res, 500, { error: error.message });
    }
  }
  if (req.url === '/api/sso-login' && req.method === 'POST') {
    // Login automático pedido pelo QualiMatch: a pessoa já se autenticou lá,
    // então em vez de mostrar a tela de login de novo aqui, o QualiMatch
    // assina o e-mail dela com a chave compartilhada e a gente confere.
    try {
      const { email, name, access, timestamp, signature } = await readBody(req);
      const ts = Number(timestamp);
      if (!email || !signature || !Number.isFinite(ts))
        return send(res, 400, { error: 'Requisição de SSO incompleta.' });
      if (Math.abs(Date.now() - ts) > 60_000)
        return send(res, 401, { error: 'Requisição de SSO expirada.' });
      const normalizedEmail = String(email).trim().toLowerCase();
      const normalizedName = String(name || normalizedEmail.split('@', 1)[0]).trim();
      const normalizedAccess = String(access || 'VIEWER').trim().toUpperCase();
      const expected = createHmac('sha256', QUALIMATCH_SSO_SECRET)
        .update(
          `${normalizedEmail}|${normalizedName}|${normalizedAccess}|${ts}`,
        )
        .digest('hex');
      if (expected !== signature)
        return send(res, 401, { error: 'Assinatura de SSO inválida.' });
      if (!pool) {
        const apiUser = {
          id: 'local-demo', name: normalizedName || 'Administrador Demo',
          email: normalizedEmail, role: normalizedAccess === 'ADMIN' ? 'Administrador' : 'Analista',
          isAdmin: normalizedAccess === 'ADMIN', sites: [], active: true,
          initials: (normalizedName || 'AD').split(/\s+/).map((x) => x[0]).slice(0, 2).join('').toUpperCase(),
        };
        return send(res, 200, { token: 'local-demo', user: apiUser });
      }
      const result = await pool.query(
        'select id, name, email, role, is_admin, sites from app_users where lower(email)=lower($1) and active=true',
        [email],
      );
      if (!result.rowCount)
        return send(res, 404, {
          error:
            'Nenhum usuário ativo cadastrado no Controle de Traços com este e-mail. Peça ao administrador para criar um usuário aqui com o mesmo e-mail do QualiMatch.',
        });
      const apiUser = userToApi(result.rows[0]);
      const token = randomUUID();
      sessions.set(token, apiUser);
      persistSessions();
      return send(res, 200, { token, user: apiUser });
    } catch (error) {
      return send(res, 500, { error: error.message });
    }
  }
  if (req.url === '/api/login' && req.method === 'POST') {
    if (!pool) return send(res, 503, { error: 'Banco não configurado' });
    try {
      const { email, password } = await readBody(req);
      const result = await pool.query(
        'select id, name, email, role, is_admin, sites from app_users where lower(email)=lower($1) and active=true and password_hash=crypt($2,password_hash)',
        [email, password],
      );
      if (!result.rowCount)
        return send(res, 401, { error: 'E-mail ou senha inválidos' });
      const apiUser = userToApi(result.rows[0]);
      const token = randomUUID();
      sessions.set(token, apiUser);
      persistSessions();
      return send(res, 200, { token, user: apiUser });
    } catch (error) {
      return send(res, 500, { error: error.message });
    }
  }
  const user = userFrom(req);
  if (!user) return send(res, 401, { error: 'Sessão inválida' });
  const isFileRoute = /^\/api\/traces\/[^/]+\/files(?:\/[^/]+)?$/.test(
    req.url || '',
  );
  const isInventoryFileRoute = /^\/api\/inventory\/files\/[a-f0-9]{24}$/.test(
    req.url || '',
  );
  const isInventoryFolderRoute =
    /^\/api\/inventory\/folders\/[a-f0-9]{24}\/open$/.test(req.url || '');
  const isDatabaseFreeRoute =
    isFileRoute ||
    isInventoryFileRoute ||
    isInventoryFolderRoute ||
    req.url === '/api/inventory';
  if (!pool && !isDatabaseFreeRoute)
    return send(res, 503, { error: 'Banco não configurado' });
  try {
    if (req.url === '/api/inventory' && req.method === 'GET') {
      const records = await readTraceInventory();
      return send(res, 200, {
        records,
        sheets: [...inventorySheets],
        updatedAt: new Date().toISOString(),
      });
    }
    if (isInventoryFileRoute && req.method === 'GET') {
      const documentId = req.url.split('/').pop();
      const document = inventoryDocuments.get(documentId);
      if (!document || !existsSync(document.filePath))
        return send(res, 404, {
          error: 'Documento não encontrado. Atualize o inventário.',
        });
      const content = readFileSync(document.filePath);
      const downloadName = document.fileName.replace(/["\r\n]/g, '_');
      res.writeHead(200, {
        'Content-Type': 'application/pdf',
        'Content-Disposition': `attachment; filename*=UTF-8''${encodeURIComponent(downloadName)}`,
        'Content-Length': content.length,
        'Access-Control-Allow-Origin': origin,
      });
      return res.end(content);
    }
    if (isInventoryFolderRoute && req.method === 'POST') {
      const folderId = req.url.split('/').at(-2);
      const folderPath = inventoryFolders.get(folderId);
      if (!folderPath || !existsSync(folderPath))
        return send(res, 404, {
          error: 'Pasta não encontrada. Atualize o inventário.',
        });
      const explorer = spawn('explorer.exe', [folderPath], {
        detached: true,
        stdio: 'ignore',
      });
      explorer.unref();
      return send(res, 200, { opened: true });
    }
    if (req.url === '/api/certificates/sync' && req.method === 'POST') {
      const { certificatesPath, sharePointPath } = readSyncConfig();
      const sourcePath = certificatesPath || sharePointPath;
      if (!sourcePath || !existsSync(sourcePath))
        return send(res, 400, {
          error: 'Configure uma pasta de certificados válida.',
        });
      const validStatuses = [
        'Aprovado',
        'Não conforme',
        'Restrito',
        'Cancelado',
        'Em análise',
        'Solicitado',
      ];
      let imported = 0;
      let updated = 0;
      let filesLinked = 0;
      const client = await pool.connect();
      try {
        await client.query('begin');
        for (const status of validStatuses) {
          const statusDir = path.join(sourcePath, status);
          if (!existsSync(statusDir)) continue;
          const pdfs = listCertificatePdfs(statusDir);
          for (const { code, fileName, filePath } of pdfs) {
            const trace = await client.query(
              'select id,status from traces where code=$1',
              [code],
            );
            let traceId;
            if (!trace.rowCount) {
              traceId = randomUUID();
              await client.query(
                'insert into traces(id,code,unit,company,contract,category,material,place,status,owner,note) values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)',
                [
                  traceId,
                  code,
                  'PRVias',
                  'Acervo importado',
                  'Acervo de certificados',
                  'Misturas asfálticas',
                  'CBUQ',
                  'Pasta de certificados',
                  status,
                  user.name,
                  `Importado automaticamente de ${status}`,
                ],
              );
              await client.query(
                'insert into trace_history(trace_id,status,changed_by) values($1,$2,$3)',
                [traceId, status, user.name],
              );
              imported += 1;
            } else {
              traceId = trace.rows[0].id;
              if (trace.rows[0].status !== status) {
                await client.query(
                  'update traces set status=$1,updated_at=now() where id=$2',
                  [status, traceId],
                );
                updated += 1;
              }
            }
            const traceDir = path.join(uploadsRoot, traceId);
            mkdirSync(traceDir, { recursive: true });
            const target = path.join(traceDir, `trace-${safeName(fileName)}`);
            if (!existsSync(target)) {
              copyFileSync(filePath, target);
              filesLinked += 1;
            }
          }
        }
        await client.query('commit');
      } catch (error) {
        await client.query('rollback');
        throw error;
      } finally {
        client.release();
      }
      return send(res, 200, { imported, updated, filesLinked });
    }
    if (req.url === '/api/traces' && req.method === 'GET') {
      await syncOfficialTraces(user.name);
      const rows = user.isAdmin
        ? await pool.query('select * from traces order by updated_at desc')
        : await pool.query(
            'select * from traces where unit = any($1) order by updated_at desc',
            [user.sites || []],
          );
      const histories = await pool.query(
        'select trace_id, status, changed_by as owner, created_at from trace_history order by created_at',
      );
      return send(
        res,
        200,
        rows.rows.map((row) =>
          traceFromRow(
            row,
            histories.rows
              .filter((h) => h.trace_id === row.id)
              .map((h) => ({
                status: h.status,
                owner: h.owner,
                date: new Date(h.created_at).toLocaleString('pt-BR'),
              })),
          ),
        ),
      );
    }
    if (req.url === '/api/traces' && req.method === 'POST') {
      const body = await readBody(req);
      if (!canAccessUnit(user, body.unit))
        return send(res, 403, {
          error: 'Você não tem permissão para registrar traços dessa Sede.',
        });
      const client = await pool.connect();
      try {
        await client.query('begin');
        const result = await client.query(
          "insert into traces(id,code,unit,company,contract,category,material,place,status,owner,note) values($1,$2,$3,$4,$5,$6,$7,$8,'Solicitado',$9,$10) returning *",
          [
            body.id || randomUUID(),
            body.code,
            body.unit,
            body.company,
            body.contract,
            body.category,
            body.material,
            body.place,
            body.owner || user.name,
            body.note || '',
          ],
        );
        await client.query(
          "insert into trace_history(trace_id,status,changed_by) values($1,'Solicitado',$2)",
          [result.rows[0].id, user.name],
        );
        mirrorToSharePoint(
          result.rows[0].id,
          result.rows[0].status,
          result.rows[0],
        );
        await client.query('commit');
        return send(
          res,
          201,
          traceFromRow(result.rows[0], [
            {
              status: 'Solicitado',
              owner: user.name,
              date: new Date().toLocaleString('pt-BR'),
            },
          ]),
        );
      } catch (error) {
        await client.query('rollback');
        throw error;
      } finally {
        client.release();
      }
    }
    const statusMatch = req.url?.match(/^\/api\/traces\/([^/]+)\/status$/);
    if (statusMatch && req.method === 'PATCH') {
      if (!user.isAdmin) {
        const owned = await pool.query('select unit from traces where id=$1', [
          statusMatch[1],
        ]);
        if (!owned.rowCount || !canAccessUnit(user, owned.rows[0].unit))
          return send(res, 403, {
            error: 'Você não tem permissão para alterar esse traço.',
          });
      }
      const { status } = await readBody(req);
      const client = await pool.connect();
      try {
        await client.query('begin');
        const result = await client.query(
          'update traces set status=$1,updated_at=now() where id=$2 returning *',
          [status, statusMatch[1]],
        );
        if (!result.rowCount) throw new Error('Traço não encontrado');
        await client.query(
          'insert into trace_history(trace_id,status,changed_by) values($1,$2,$3)',
          [statusMatch[1], status, user.name],
        );
        mirrorToSharePoint(statusMatch[1], status, result.rows[0]);
        await client.query('commit');
        return send(res, 200, traceFromRow(result.rows[0]));
      } catch (error) {
        await client.query('rollback');
        throw error;
      } finally {
        client.release();
      }
    }
    const filesMatch = req.url?.match(/^\/api\/traces\/([^/]+)\/files$/);
    if (filesMatch && req.method === 'GET') {
      const traceId = safeTraceId(filesMatch[1]);
      if (!traceId) return send(res, 400, { error: 'Identificador inválido' });
      const traceDir = path.join(uploadsRoot, traceId);
      const names = existsSync(traceDir) ? readdirSync(traceDir) : [];
      return send(
        res,
        200,
        names
          .map((name) => {
            const info = statSync(path.join(traceDir, name));
            return {
              name,
              kind: name.startsWith('checklist-') ? 'checklist' : 'trace',
              size: info.size,
              updatedAt: info.mtime.toISOString(),
            };
          })
          .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)),
      );
    }
    if (filesMatch && req.method === 'POST') {
      const traceId = safeTraceId(filesMatch[1]);
      if (!traceId) return send(res, 400, { error: 'Identificador inválido' });
      // Limite generoso (60MB em base64, ~45MB de arquivo real) — cartas
      // traço escaneadas podem ser pesadas. O erro agora também é claro
      // em vez de um 500 genérico.
      const body = await readBody(req, 60_000_000);
      const kind = body.kind === 'checklist' ? 'checklist' : 'trace';
      const files = Array.isArray(body.files) ? body.files : [];
      const traceDir = path.join(uploadsRoot, traceId);
      mkdirSync(traceDir, { recursive: true });
      const saved = [];
      const failed = [];
      for (const file of files) {
        if (!file?.name || !file?.dataBase64) continue;
        const fileName = `${kind}-${safeName(file.name)}`;
        try {
          writeFileSync(
            path.join(traceDir, fileName),
            Buffer.from(file.dataBase64, 'base64'),
          );
          saved.push(fileName);
        } catch (error) {
          failed.push({ name: file.name, error: error.message });
        }
      }
      // A atualização da pasta sincronizada é só um "bônus" pós-salvamento —
      // se ela falhar (traço sem status ainda, banco temporariamente
      // instável, etc.) isso NUNCA pode fazer o upload em si ser reportado
      // como falha para quem está anexando o PDF.
      if (pool) {
        try {
          const current = await pool.query(
            'select status,unit,code,category,material from traces where id=$1',
            [traceId],
          );
          if (current.rows[0]?.status)
            mirrorToSharePoint(
              traceId,
              current.rows[0].status,
              current.rows[0],
            );
        } catch (error) {
          console.error('Falha ao espelhar para a pasta sincronizada:', error);
        }
      }
      if (!saved.length && failed.length)
        return send(res, 500, {
          error: failed[0].error || 'Não foi possível salvar o arquivo.',
          failed,
        });
      return send(res, 200, { saved, failed });
    }
    const localMatchRoute = req.url?.match(
      /^\/api\/traces\/([^/]+)\/local-match$/,
    );
    if (localMatchRoute && req.method === 'GET') {
      // O acervo local (mesma pasta configurada em "Documentos sincronizados")
      // já é varrido para o inventário — aqui só reaproveita esse resultado
      // para achar, pelo código do traço, um PDF que ainda não foi anexado.
      const traceId = safeTraceId(localMatchRoute[1]);
      if (!traceId) return send(res, 400, { error: 'Identificador inválido' });
      const current = await pool.query('select code from traces where id=$1', [traceId]);
      if (!current.rowCount) return send(res, 404, { error: 'Traço não encontrado.' });
      const code = inventoryComparable(current.rows[0].code);
      if (!code) return send(res, 200, { match: null });
      try {
        await readTraceInventory();
      } catch {
        return send(res, 200, { match: null });
      }
      const found = findLocalPdfForCode(current.rows[0].code);
      if (!found) return send(res, 200, { match: null });
      const traceDir = path.join(uploadsRoot, traceId);
      const alreadyAttached =
        existsSync(traceDir) &&
        readdirSync(traceDir).some(
          (name) => name === `trace-${safeName(found.fileName)}`,
        );
      return send(res, 200, {
        match: alreadyAttached
          ? null
          : { documentId: found.documentId, fileName: found.fileName },
      });
    }
    const localMatchAttachRoute = req.url?.match(
      /^\/api\/traces\/([^/]+)\/local-match\/attach$/,
    );
    if (localMatchAttachRoute && req.method === 'POST') {
      const traceId = safeTraceId(localMatchAttachRoute[1]);
      if (!traceId) return send(res, 400, { error: 'Identificador inválido' });
      const { documentId } = await readBody(req);
      const document = inventoryDocuments.get(documentId);
      if (!document || !existsSync(document.filePath))
        return send(res, 404, {
          error: 'Arquivo não encontrado. Atualize o inventário e tente de novo.',
        });
      const traceDir = path.join(uploadsRoot, traceId);
      mkdirSync(traceDir, { recursive: true });
      const fileName = `trace-${safeName(document.fileName)}`;
      copyFileSync(document.filePath, path.join(traceDir, fileName));
      if (pool) {
        try {
          const current = await pool.query(
            'select status,unit,code,category,material from traces where id=$1',
            [traceId],
          );
          if (current.rows[0]?.status)
            mirrorToSharePoint(traceId, current.rows[0].status, current.rows[0]);
        } catch (error) {
          console.error('Falha ao espelhar para a pasta sincronizada:', error);
        }
      }
      return send(res, 200, { attached: fileName });
    }
    const fileContentMatch = req.url?.match(
      /^\/api\/traces\/([^/]+)\/files\/([^/]+)$/,
    );
    if (fileContentMatch && req.method === 'GET') {
      const traceId = safeTraceId(fileContentMatch[1]);
      if (!traceId) return send(res, 400, { error: 'Identificador inválido' });
      const traceDir = path.join(uploadsRoot, traceId);
      const fileName = safeName(decodeURIComponent(fileContentMatch[2]));
      const filePath = path.join(traceDir, fileName);
      if (!filePath.startsWith(traceDir + path.sep) || !existsSync(filePath))
        return send(res, 404, { error: 'Arquivo não encontrado' });
      const ext = path.extname(fileName).toLowerCase();
      const type =
        ext === '.pdf'
          ? 'application/pdf'
          : ext === '.png'
            ? 'image/png'
            : ext === '.jpg' || ext === '.jpeg'
              ? 'image/jpeg'
              : 'application/octet-stream';
      res.writeHead(200, {
        'Content-Type': type,
        'Access-Control-Allow-Origin': origin,
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        'Access-Control-Allow-Methods': 'GET, POST, PATCH, DELETE, OPTIONS',
      });
      return res.end(readFileSync(filePath));
    }
    if (fileContentMatch && req.method === 'DELETE') {
      const traceId = safeTraceId(fileContentMatch[1]);
      if (!traceId) return send(res, 400, { error: 'Identificador inválido' });
      const traceDir = path.join(uploadsRoot, traceId);
      const fileName = safeName(decodeURIComponent(fileContentMatch[2]));
      const filePath = path.join(traceDir, fileName);
      if (!filePath.startsWith(traceDir + path.sep) || !existsSync(filePath))
        return send(res, 404, { error: 'Arquivo não encontrado' });
      try {
        unlinkSync(filePath);
      } catch (error) {
        return send(res, 500, {
          error: error.message || 'Não foi possível remover o arquivo.',
        });
      }
      if (pool) {
        try {
          const current = await pool.query(
            'select status,unit,code,category,material from traces where id=$1',
            [traceId],
          );
          if (current.rows[0]?.status)
            mirrorToSharePoint(
              traceId,
              current.rows[0].status,
              current.rows[0],
            );
        } catch (error) {
          console.error('Falha ao atualizar a pasta sincronizada:', error);
        }
      }
      return send(res, 200, { removed: fileName });
    }
    const ownerMatch = req.url?.match(/^\/api\/traces\/([^/]+)\/owner$/);
    if (ownerMatch && req.method === 'PATCH') {
      if (!user.isAdmin) {
        const owned = await pool.query('select unit from traces where id=$1', [
          ownerMatch[1],
        ]);
        if (!owned.rowCount || !canAccessUnit(user, owned.rows[0].unit))
          return send(res, 403, {
            error: 'Você não tem permissão para alterar esse traço.',
          });
      }
      const { owner } = await readBody(req);
      if (!owner) return send(res, 400, { error: 'Informe o responsável' });
      const result = await pool.query(
        'update traces set owner=$1 where id=$2 returning *',
        [owner, ownerMatch[1]],
      );
      if (!result.rowCount)
        return send(res, 404, { error: 'Traço não encontrado' });
      return send(res, 200, traceFromRow(result.rows[0]));
    }
    if (req.url === '/api/users' && req.method === 'GET') {
      const result = await pool.query(
        'select id,name,email,role,is_admin,sites,active from app_users where active=true order by name',
      );
      return send(res, 200, result.rows.map(userToApi));
    }
    // Rotas de administração de usuários — só para quem é administrador.
    // Ficam sob /api/admin/users para não expor por engano dados sensíveis
    // (e-mail/Sede de contas inativas, por exemplo) na listagem comum acima.
    if (req.url === '/api/admin/users' && req.method === 'GET') {
      if (!user.isAdmin)
        return send(res, 403, { error: 'Acesso restrito ao administrador.' });
      const result = await pool.query(
        'select id,name,email,role,is_admin,sites,active from app_users order by active desc, name',
      );
      return send(res, 200, result.rows.map(userToApi));
    }
    if (req.url === '/api/admin/users' && req.method === 'POST') {
      if (!user.isAdmin)
        return send(res, 403, { error: 'Acesso restrito ao administrador.' });
      const body = await readBody(req);
      const name = String(body.name || '').trim();
      const email = String(body.email || '').trim();
      const password = String(body.password || '');
      if (!name || !email || !password)
        return send(res, 400, {
          error: 'Informe nome, e-mail e senha do novo usuário.',
        });
      const role = String(body.role || 'Analista').trim() || 'Analista';
      const isAdmin = !!body.isAdmin;
      const sites = Array.isArray(body.sites)
        ? body.sites.filter((s) => typeof s === 'string')
        : [];
      try {
        const result = await pool.query(
          'insert into app_users(name,email,password_hash,role,is_admin,sites) values($1,$2,crypt($3,gen_salt($4)),$5,$6,$7) returning id,name,email,role,is_admin,sites,active',
          [name, email, password, 'bf', role, isAdmin, sites],
        );
        return send(res, 201, userToApi(result.rows[0]));
      } catch (error) {
        if (error.code === '23505')
          return send(res, 409, { error: 'Já existe um usuário com esse e-mail.' });
        throw error;
      }
    }
    const adminUserMatch = req.url?.match(/^\/api\/admin\/users\/([^/]+)$/);
    if (adminUserMatch && req.method === 'PATCH') {
      if (!user.isAdmin)
        return send(res, 403, { error: 'Acesso restrito ao administrador.' });
      const body = await readBody(req);
      const fields = [];
      const values = [];
      let index = 1;
      if (body.name !== undefined) {
        fields.push(`name=$${index++}`);
        values.push(String(body.name).trim());
      }
      if (body.email !== undefined) {
        fields.push(`email=$${index++}`);
        values.push(String(body.email).trim());
      }
      if (body.role !== undefined) {
        fields.push(`role=$${index++}`);
        values.push(String(body.role).trim() || 'Analista');
      }
      if (body.isAdmin !== undefined) {
        fields.push(`is_admin=$${index++}`);
        values.push(!!body.isAdmin);
      }
      if (body.sites !== undefined) {
        fields.push(`sites=$${index++}`);
        values.push(
          Array.isArray(body.sites)
            ? body.sites.filter((s) => typeof s === 'string')
            : [],
        );
      }
      if (body.active !== undefined) {
        fields.push(`active=$${index++}`);
        values.push(!!body.active);
      }
      if (body.password) {
        fields.push(`password_hash=crypt($${index++},gen_salt('bf'))`);
        values.push(String(body.password));
      }
      if (!fields.length)
        return send(res, 400, { error: 'Nada para atualizar.' });
      values.push(adminUserMatch[1]);
      try {
        const result = await pool.query(
          `update app_users set ${fields.join(',')} where id=$${index} returning id,name,email,role,is_admin,sites,active`,
          values,
        );
        if (!result.rowCount)
          return send(res, 404, { error: 'Usuário não encontrado.' });
        return send(res, 200, userToApi(result.rows[0]));
      } catch (error) {
        if (error.code === '23505')
          return send(res, 409, { error: 'Já existe um usuário com esse e-mail.' });
        throw error;
      }
    }
    return send(res, 404, { error: 'Rota não encontrada' });
  } catch (error) {
    return send(res, 500, { error: error.message });
  }
});
server.listen(port, '127.0.0.1', () =>
  console.log(`API local em http://127.0.0.1:${port}`),
);
