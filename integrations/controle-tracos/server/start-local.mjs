import { execFileSync, spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const projectRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const appUrl = 'http://localhost:3000';
const apiUrl = 'http://127.0.0.1:3001/health';
const startupTimeoutMs = 5 * 60 * 1000;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchWithTimeout(url, timeoutMs = 3000) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { signal: controller.signal });
  } finally {
    clearTimeout(timeout);
  }
}

async function appIsReady() {
  try {
    const [webResponse, apiResponse] = await Promise.all([
      fetchWithTimeout(appUrl),
      fetchWithTimeout(apiUrl),
    ]);
    if (!webResponse.ok || !apiResponse.ok) return false;
    const html = await webResponse.text();
    const health = await apiResponse.json();
    return html.includes('Controle de Traços') && health?.ok === true;
  } catch {
    return false;
  }
}

async function apiIsReachable() {
  try {
    const response = await fetchWithTimeout(apiUrl);
    return response.ok;
  } catch {
    return false;
  }
}

async function waitForExistingApp(timeoutMs = 2 * 60 * 1000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await appIsReady()) return true;
    await sleep(1000);
  }
  return false;
}

function openBrowser() {
  execFileSync('rundll32.exe', ['url.dll,FileProtocolHandler', appUrl], {
    stdio: 'ignore',
    windowsHide: true,
  });
}

async function waitUntilReady(childExit) {
  const deadline = Date.now() + startupTimeoutMs;
  while (Date.now() < deadline) {
    const result = await Promise.race([
      appIsReady().then((ready) => ({ type: 'ready', ready })),
      childExit,
    ]);
    if (result.type === 'exit') return result;
    if (result.ready) return { type: 'ready', ready: true };
    await sleep(1000);
  }
  return { type: 'timeout' };
}

if (await appIsReady()) {
  console.log('[Controle de Traco] O sistema ja esta em execucao. Abrindo...');
  openBrowser();
  process.exit(0);
}

if (await apiIsReachable()) {
  console.log(
    '[Controle de Traco] Uma inicializacao anterior ainda esta em andamento. Aguardando...',
  );
  if (await waitForExistingApp()) {
    console.log('[Controle de Traco] Sistema pronto. Abrindo o navegador...');
    openBrowser();
    process.exit(0);
  }
  console.error(
    '[Controle de Traco] A porta 3001 esta ocupada, mas a interface nao iniciou. Feche a janela antiga e tente novamente.',
  );
  process.exit(1);
}

console.log('[Controle de Traco] Preparando interface e API local...');
console.log('[Controle de Traco] Na primeira execucao isso pode levar ate 2 minutos.');

const command = process.env.ComSpec || 'cmd.exe';
const server = spawn(command, ['/d', '/s', '/c', 'npm run dev'], {
  cwd: projectRoot,
  env: process.env,
  stdio: 'inherit',
  windowsHide: false,
});

const childExit = new Promise((resolve) => {
  server.once('exit', (code, signal) =>
    resolve({ type: 'exit', code: code ?? 1, signal }),
  );
});

const stopServer = () => {
  if (!server.killed) server.kill('SIGINT');
};
process.once('SIGINT', stopServer);
process.once('SIGTERM', stopServer);

const startup = await waitUntilReady(childExit);
if (startup.type === 'ready') {
  console.log('[Controle de Traco] Sistema pronto. Abrindo o navegador...');
  openBrowser();
  const finished = await childExit;
  process.exitCode = finished.code;
} else if (startup.type === 'exit') {
  console.error(
    `[Controle de Traco] O servidor encerrou antes de ficar pronto (codigo ${startup.code}).`,
  );
  process.exitCode = startup.code;
} else {
  console.error(
    '[Controle de Traco] O sistema nao respondeu em 5 minutos. Verifique os erros acima.',
  );
  stopServer();
  process.exitCode = 1;
}
