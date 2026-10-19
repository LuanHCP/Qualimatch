const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('frontend/static/app.js', 'utf8');
const apiSource = source.slice(source.indexOf('const pendingReads='), source.indexOf('function toast('));
let calls = 0;
const releases = [];
const context = vm.createContext({
  fetch: () => { calls++; return new Promise(resolve => releases.push(() => resolve({ok:true,text:async()=>'{}'}))); },
});
vm.runInContext(apiSource, context);
(async () => {
  const first = context.api('/api/certificates');
  const second = context.api('/api/certificates');
  assert.equal(calls, 1, 'Concurrent reads must share one network request');
  releases.shift()();
  await Promise.all([first, second]);
  const fresh = context.api('/api/certificates');
  assert.equal(calls, 2, 'Completed responses must not be cached');
  releases.shift()();
  await fresh;
  const oldRead = context.api('/api/certificates');
  const write = context.api('/api/certificates/1', {method:'PUT'});
  const afterWrite = context.api('/api/certificates');
  assert.equal(calls, 5, 'Writes must invalidate in-flight read deduplication');
  releases.splice(0).forEach(release => release());
  await Promise.all([oldRead, write, afterWrite]);
  const cardSource = source.slice(source.indexOf('function folderFileCard('), source.indexOf('function renderContractorFolderBrowser('));
  context.esc = String;
  context.humanSize = String;
  vm.runInContext(cardSource, context);
  const card = context.folderFileCard({id:1,extension:'.pdf',file_name:'test.pdf',size:100});
  assert(!card.includes('<iframe'), 'PDF cards must not load a PDF viewer automatically');
  assert(card.includes('previewKitDocument(1)'), 'Explicit PDF preview remains available');
  console.log('Frontend performance checks passed');
})().catch(error => { console.error(error); process.exitCode=1; });
