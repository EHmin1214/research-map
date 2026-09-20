// Research Map — status-bar entry point for the research-map skill.
// Everything real happens in the skill's Python scripts; this only finds them,
// picks a map, and runs the right command in a VS Code terminal so you can
// watch it (and so the --serve server stays alive while the page is open).
const vscode = require('vscode');
const fs = require('fs');
const os = require('os');
const path = require('path');

function cfg(key, dflt) {
  const v = vscode.workspace.getConfiguration('researchMap').get(key, dflt);
  return (typeof v === 'string' ? v.trim() : v) || dflt;
}

function home() {
  return cfg('home', '') || process.env.RESEARCH_MAP_HOME || path.join(os.homedir(), '.claude', 'research-map');
}

// Same search order as open-map.bat: personal skill dirs, then plugin caches.
function scriptsDir() {
  const fixed = cfg('scripts', '');
  if (fixed && fs.existsSync(path.join(fixed, 'render.py'))) return fixed;
  const h = os.homedir();
  const cands = [
    path.join(h, '.claude', 'skills', 'research-map', 'scripts'),
    path.join(h, '.codex', 'skills', 'research-map', 'scripts')
  ];
  for (const agent of ['.claude', '.codex']) {
    const cache = path.join(h, agent, 'plugins', 'cache');
    try {
      for (const mk of fs.readdirSync(cache)) {
        const p1 = path.join(cache, mk, 'research-map');
        if (!fs.existsSync(p1)) continue;
        for (const ver of fs.readdirSync(p1)) cands.push(path.join(p1, ver, 'skills', 'research-map', 'scripts'));
      }
    } catch { /* no cache */ }
  }
  return cands.find(c => fs.existsSync(path.join(c, 'render.py'))) || null;
}

function listMaps() {
  const root = path.join(home(), 'maps');
  const out = [];
  try {
    for (const name of fs.readdirSync(root)) {
      const d = path.join(root, name);
      const c = path.join(d, 'config.json');
      if (!fs.existsSync(c)) continue;
      let title = name, updated = '';
      try { title = JSON.parse(fs.readFileSync(c, 'utf8')).title || name; } catch { /* keep name */ }
      try { updated = JSON.parse(fs.readFileSync(path.join(d, 'map.json'), 'utf8')).updatedAt || ''; } catch { /* no map yet */ }
      out.push({ name, title, dir: d, updated, hasPage: fs.existsSync(path.join(d, 'index.html')) });
    }
  } catch { /* no maps dir */ }
  return out.sort((a, b) => (b.updated || '').localeCompare(a.updated || ''));
}

function q(s) { return `'${String(s).replace(/'/g, "''")}'`; }   // PowerShell single-quote

// One terminal per map so a running --serve server is easy to find again.
function terminalFor(name) {
  const title = `연구 지도: ${name}`;
  let t = vscode.window.terminals.find(x => x.name === title);
  if (!t) t = vscode.window.createTerminal({ name: title, shellPath: 'powershell.exe', shellArgs: ['-NoLogo', '-NoProfile', '-NoExit'] });
  t.show(true);
  return t;
}

function run(name, script, args) {
  const sd = scriptsDir();
  if (!sd) {
    vscode.window.showErrorMessage('research-map 스킬을 찾지 못했습니다. install.ps1 로 먼저 설치하세요 (설정 researchMap.scripts 로 직접 지정할 수도 있습니다).');
    return;
  }
  const t = terminalFor(name);
  const py = cfg('python', 'python');
  t.sendText(`$env:PYTHONIOENCODING='utf-8'; & ${q(py)} ${q(path.join(sd, script))} ${args.map(q).join(' ')}`, true);
}

async function pickMap(placeHolder) {
  const maps = listMaps();
  if (!maps.length) {
    const a = await vscode.window.showInformationMessage(`지도가 없습니다 (${home()}). 새로 만들까요?`, '새 지도');
    if (a === '새 지도') await vscode.commands.executeCommand('researchMap.new');
    return null;
  }
  if (maps.length === 1) return maps[0];
  const picked = await vscode.window.showQuickPick(maps.map(m => ({
    label: m.title, description: m.name, detail: m.updated ? `updated ${m.updated}` : '(아직 렌더 안 됨)', map: m
  })), { title: '연구 지도', placeHolder });
  return picked ? picked.map : null;
}

async function activate(context) {
  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 24);
  status.command = 'researchMap.pick';
  status.tooltip = '연구 지도 열기 · 갱신';
  status.show();
  const refresh = () => {
    const maps = listMaps();
    status.text = maps.length ? `$(type-hierarchy) 연구 지도 (${maps.length})` : '$(type-hierarchy) 연구 지도';
  };
  refresh();
  const timer = setInterval(refresh, 30000);
  context.subscriptions.push(status, { dispose: () => clearInterval(timer) });

  const reg = (id, fn) => context.subscriptions.push(vscode.commands.registerCommand(id, async (...a) => {
    try { await fn(...a); } catch (e) { vscode.window.showErrorMessage(`Research Map: ${e.message}`); }
  }));

  reg('researchMap.pick', async () => {
    const items = [
      { label: '$(globe) 열기 — 갱신·정정 버튼 켜서', description: '로컬 서버(127.0.0.1)로 페이지를 띄웁니다', cmd: 'researchMap.open' },
      { label: '$(file) 읽기 전용으로 열기', description: 'index.html 만 브라우저로', cmd: 'researchMap.openStatic' },
      { label: '$(search) 새 세션 확인', description: '기록만 훑습니다 — 공짜', cmd: 'researchMap.scan' },
      { label: '$(sparkle) 지도 갱신 (에이전트)', description: '카드·병합·렌더까지 — 토큰을 씁니다', cmd: 'researchMap.update' },
      { label: '$(export) 논문용 내보내기', description: '전체 Markdown 또는 철회 수치 체크리스트', cmd: 'researchMap.export' },
      { label: '$(add) 새 지도 만들기', description: '이름·제목만 정하면 됩니다', cmd: 'researchMap.new' }
    ];
    const p = await vscode.window.showQuickPick(items, { title: '연구 지도', placeHolder: '무엇을 할까요' });
    if (p) await vscode.commands.executeCommand(p.cmd);
  });

  reg('researchMap.open', async () => {
    const m = await pickMap('열 지도');
    if (!m) return;
    run(m.name, 'render.py', ['--map', m.name, '--serve']);
  });

  reg('researchMap.openStatic', async () => {
    const m = await pickMap('열 지도');
    if (!m) return;
    const p = path.join(m.dir, 'index.html');
    if (!fs.existsSync(p)) { vscode.window.showWarningMessage('아직 렌더된 페이지가 없습니다. 먼저 갱신하세요.'); return; }
    await vscode.env.openExternal(vscode.Uri.file(p));
  });

  reg('researchMap.scan', async () => {
    const m = await pickMap('확인할 지도');
    if (!m) return;
    run(m.name, 'extract.py', ['--map', m.name]);
  });

  reg('researchMap.update', async () => {
    const m = await pickMap('갱신할 지도');
    if (!m) return;
    const ok = await vscode.window.showWarningMessage(
      `'${m.title}' 를 에이전트로 갱신합니다. 카드 작성과 병합에 토큰이 듭니다.`, { modal: true }, '갱신');
    if (ok !== '갱신') return;
    run(m.name, 'rmserve.py', ['--map', m.name, '--update']);
  });

  reg('researchMap.export', async () => {
    const m = await pickMap('내보낼 지도');
    if (!m) return;
    const k = await vscode.window.showQuickPick([
      { label: '전체 Markdown', args: [] },
      { label: '철회 수치 체크리스트', args: ['--checklist'] }
    ], { title: '논문용 내보내기' });
    if (!k) return;
    run(m.name, 'rmexport.py', ['--map', m.name, ...k.args]);
  });

  reg('researchMap.new', async () => {
    const name = await vscode.window.showInputBox({
      title: '새 지도 — 폴더 이름', prompt: '영문 소문자·숫자·하이픈', value: 'mystudy',
      validateInput: v => /^[a-z0-9][a-z0-9-]{0,40}$/.test(v) ? null : '소문자·숫자·하이픈만'
    });
    if (!name) return;
    const title = await vscode.window.showInputBox({ title: '새 지도 — 제목', value: name });
    if (title === undefined) return;
    run(name, 'extract.py', ['--init', name, '--title', title || name]);
    vscode.window.showInformationMessage(`'${name}' 를 만들었습니다. 이제 config.json 의 include 로 세션을 고르고, 에이전트에게 "연구 지도 만들어줘" 라고 하면 됩니다.`);
    setTimeout(refresh, 3000);
  });
}

function deactivate() {}
module.exports = { activate, deactivate };
