const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('frontend/static/app.js', 'utf8');
const html = fs.readFileSync('frontend/index.html', 'utf8');
const nav = [...html.matchAll(/<button data-page="([^"]+)" data-portal="([^"]+)"/g)]
  .map(([, page, portal]) => ({dataset:{page, portal}, classList:{toggle(){}}}));
assert.deepEqual([...html.matchAll(/data-portal-card="([^"]+)"/g)].map(x=>x[1]), ['BV','CONTRACTOR','TRACES','NC','ADMIN']);
assert(!html.includes('my-space') && !html.includes('Meu espaço'));
assert.deepEqual(nav.filter(x=>x.dataset.portal==='TRACES').map(x=>x.dataset.page), ['quality-overview','quality-approved','quality-traces']);
assert.deepEqual(nav.filter(x=>x.dataset.portal==='NC').map(x=>x.dataset.page), ['quality-nc-overview','quality-nc-list']);
let opened, denied = 0;
const context = vm.createContext({
  $: selector => {
    const page = selector.match(/data-page="([^"]+)"/), portal = selector.match(/data-portal="([^"]+)"/);
    return page ? nav.find(x=>x.dataset.page===page[1] && (!portal || x.dataset.portal===portal[1])) : {classList:{toggle(){}}};
  },
  $$: () => nav,
  toast: () => denied++,
  openPage: page => {opened = page;},
  refreshNotifications(){},
});
vm.runInContext(source.slice(source.indexOf('let currentUser='), source.indexOf('const contractorScopes=')), context);
vm.runInContext(source.slice(source.indexOf('function applyPortalUI('), source.indexOf('async function refreshSetupStatus(')), context);
context.showApp = context.applyRoleUI = () => {};
function run(code){return vm.runInContext(code, context);}
run("currentUser={role:'USER',access_quality_general:1}");
for(const portal of ['TRACES','NC']) assert(run(`canAccessPortal('${portal}')`));
run("enterPortal('TRACES')");assert.equal(opened,'quality-overview');
run("enterPortal('NC')");assert.equal(opened,'quality-nc-overview');
run("enterPortal('NC','quality-nc-list')");assert.equal(opened,'quality-nc-list');
run("enterPortal('QUALITY','quality-nc-list')");assert.equal(opened,'quality-nc-list');assert.equal(run('currentPortal'),'NC');
run("enterPortal('QUALITY','quality-approved')");assert.equal(opened,'quality-approved');assert.equal(run('currentPortal'),'TRACES');
run("enterPortal('TRACES','quality-nc-list')");assert.equal(opened,'quality-overview');
run("currentUser={role:'USER',access_quality_general:0}");
for(const portal of ['TRACES','NC','PERSONAL']) assert(!run(`canAccessPortal('${portal}')`));
run("enterPortal('NC')");assert.equal(denied,1);
run("currentUser={role:'ADMIN'}");
for(const portal of ['BV','CONTRACTOR','TRACES','NC','ADMIN']) assert(run(`canAccessPortal('${portal}')`));
assert(!run("canAccessPortal('PERSONAL')"));
run('currentUser=null');assert(!run("canAccessPortal('TRACES')"));
console.log('Portal navigation, legacy links and permission checks passed');
