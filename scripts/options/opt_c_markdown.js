// OPTION C — Markdown viewer/editor frontend
// Requires: <script src="https://cdn.jsdelivr.net/npm/marked@9/marked.min.js"></script>
//
// HTML needed:
//   <div id="md-toolbar">
//     <button onclick="mdNav(-1)">← Back</button>
//     <button onclick="mdNav(1)">Forward →</button>
//     <span id="md-path"></span>
//     <button onclick="mdToggleEdit()">Edit</button>
//     <button id="md-save-btn" onclick="mdSave()" style="display:none">Save</button>
//   </div>
//   <div id="md-view"></div>
//   <textarea id="md-editor" style="display:none"></textarea>

const mdState = {
  agentName: null,
  stack:     [],    // [{path, content}]
  index:     -1,
  editing:   false,
};

async function loadMarkdown(agentName, rootPath) {
  mdState.agentName = agentName;
  const data = await fetch(`/api/files/${encodeURIComponent(rootPath)}`).then(r => r.json());
  mdState.stack = [{ path: rootPath, content: data.content || '' }];
  mdState.index = 0;
  mdState.editing = false;
  _renderMd();
}

function _renderMd() {
  const entry = mdState.stack[mdState.index];
  if (!entry) return;

  document.getElementById('md-path').textContent = entry.path;

  if (mdState.editing) {
    document.getElementById('md-view').style.display    = 'none';
    document.getElementById('md-editor').style.display  = 'block';
    document.getElementById('md-editor').value          = entry.content;
    document.getElementById('md-save-btn').style.display = 'inline';
  } else {
    document.getElementById('md-editor').style.display  = 'none';
    document.getElementById('md-save-btn').style.display = 'none';
    const el = document.getElementById('md-view');
    el.style.display = 'block';
    el.innerHTML = typeof marked !== 'undefined'
      ? marked.parse(entry.content || '*(empty)*')
      : `<pre>${esc(entry.content)}</pre>`;

    // Intercept relative .md link clicks → in-pane navigation
    el.querySelectorAll('a[href]').forEach(a => {
      const href = a.getAttribute('href');
      if (!href || href.startsWith('http') || href.startsWith('#') || !href.endsWith('.md')) return;
      a.addEventListener('click', e => {
        e.preventDefault();
        const dir      = entry.path.split('/').slice(0, -1).join('/');
        const resolved = _resolvePath(dir, href);
        _mdNavTo(resolved);
      });
    });
  }
}

function _resolvePath(base, rel) {
  return (base ? base + '/' + rel : rel)
    .split('/')
    .reduce((out, p) => {
      if (p === '..') out.pop();
      else if (p && p !== '.') out.push(p);
      return out;
    }, [])
    .join('/');
}

async function _mdNavTo(path) {
  const data = await fetch(`/api/files/${encodeURIComponent(path)}`).then(r => r.json());
  // Truncate forward history before pushing
  mdState.stack = mdState.stack.slice(0, mdState.index + 1);
  mdState.stack.push({ path, content: data.content || '' });
  mdState.index++;
  mdState.editing = false;
  _renderMd();
}

function mdNav(delta) {
  const newIndex = mdState.index + delta;
  if (newIndex < 0 || newIndex >= mdState.stack.length) return;
  mdState.index   = newIndex;
  mdState.editing = false;
  _renderMd();
}

function mdToggleEdit() {
  mdState.editing = !mdState.editing;
  _renderMd();
}

async function mdSave() {
  const entry   = mdState.stack[mdState.index];
  const content = document.getElementById('md-editor').value;
  await fetch(`/api/files/${encodeURIComponent(entry.path)}`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ content }),
  });
  entry.content   = content;
  mdState.editing = false;
  _renderMd();
}
