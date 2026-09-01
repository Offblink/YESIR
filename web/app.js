/* OKSIR web UI */
marked.setOptions({ breaks: true, gfm: true });
const msgs = document.getElementById('messages'), input = document.getElementById('input'),
  btn = document.getElementById('send'), status = document.getElementById('status'),
  tray = document.getElementById('agent-tray');
let processing = false, currentSessionId = null, allSessions = [], sessionDirty = false;
let rawMessages = [];

/* ---------- helpers ---------- */
function escapeHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function addDiv(cls, html, id) {
  const d = document.createElement('div');
  d.className = 'msg ' + cls;
  if (id) d.id = id;
  if (html) d.innerHTML = html;
  msgs.appendChild(d);
  if (isNearBottom(msgs)) msgs.scrollTop = msgs.scrollHeight;
  updateScrollBtn();
  return d;
}
function isNearBottom(el) { return el.scrollHeight - el.scrollTop - el.clientHeight < 60; }
function updateScrollBtn() {
  const b = document.getElementById('scroll-bottom');
  if (!b) return;
  if (isNearBottom(msgs)) b.classList.remove('visible'); else b.classList.add('visible');
}
document.getElementById('scroll-bottom').addEventListener('click', () => { msgs.scrollTop = msgs.scrollHeight; updateScrollBtn(); });
msgs.addEventListener('scroll', updateScrollBtn);

function getSessionTitle(list) {
  const u = list.find(m => m.role === 'user');
  if (!u) return 'Empty';
  const t = String(u.content).replace(/\s+/g, ' ').trim();
  return t.length > 55 ? t.slice(0, 52) + '...' : t;
}

/* ---------- sessions ---------- */
async function loadSessions() {
  try {
    const r = await fetch('/sessions');
    if (!r.ok) throw new Error(r.status);
    allSessions = await r.json();
    renderSessionList();
  } catch (e) { console.error('loadSessions:', e); }
}
async function reloadSessionFromServer() {
  if (!currentSessionId) return;
  try {
    const r = await fetch('/session?id=' + encodeURIComponent(currentSessionId));
    if (!r.ok) return;
    const s = await r.json();
    rawMessages = s.messages || [];
    loadSessions();
  } catch (e) {}
}
async function closeCurrentSession() {
  if (!currentSessionId) return;
  if (!sessionDirty) { currentSessionId = null; return; }
  const list = rawMessages;
  if (!list || list.length <= 1) {
    try { await fetch('/session?id=' + encodeURIComponent(currentSessionId), { method: 'DELETE' }); } catch (e) {}
    currentSessionId = null;
  } else {
    const title = getSessionTitle(list);
    try {
      await fetch('/save', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: currentSessionId, title, messages: list }) });
    } catch (e) {}
  }
  loadSessions();
}
async function switchSession(id) {
  if (id === currentSessionId) return;
  await closeCurrentSession();
  sessionDirty = false;
  try {
    const r = await fetch('/session?id=' + encodeURIComponent(id));
    if (!r.ok) throw new Error(r.status);
    const s = await r.json();
    currentSessionId = s.id;
    rawMessages = s.messages || [];
    msgs.innerHTML = '';
    tray.innerHTML = '';
    registerArchived(s.subagents);
    let toolBlocks = {};
    for (const m of rawMessages) {
      if (m.role === 'user') addDiv('user', marked.parse(m.content || ''));
      else if (m.role === 'assistant') {
        if (m.reasoning) {
          const det = document.createElement('details');
          det.className = 'msg reasoning';
          det.innerHTML = '<summary>Thinking\u2026</summary><div style="white-space:pre-wrap;max-height:200px;overflow-y:auto">' + escapeHtml(m.reasoning) + '</div>';
          msgs.appendChild(det);
        }
        if (m.content) addDiv('assistant', marked.parse(m.content));
        if (m.tool_calls) m.tool_calls.forEach(tc => {
          const d = document.createElement('div');
          d.className = 'msg tool'; d.id = 'tool-' + tc.id;
          const args = tc.function?.arguments || '';
          const argsHtml = args ? ' <code style="font-size:0.82rem;opacity:0.7">' + escapeHtml(args.length > 80 ? args.slice(0, 80) + '...' : args) + '</code>' : '';
          d.innerHTML = '<div class="tool-label">&#x1F527; ' + escapeHtml(tc.function?.name || 'tool') + argsHtml + '</div><div class="tool-result"></div>';
          msgs.appendChild(d);
          if (tc.function?.name === 'spawn') makeSpawnBlockClickable(d, tc.id);
          toolBlocks[tc.id] = d;
        });
      } else if (m.role === 'tool') {
        const block = toolBlocks[m.tool_call_id];
        if (block) block.querySelector('.tool-result').innerHTML = '<pre>' + escapeHtml(m.content || '') + '</pre>';
        else addDiv('tool', '<pre>' + escapeHtml(m.content || '') + '</pre>');
      }
    }
    (s.asks || []).forEach(renderArchivedAsk);
    renderSessionList(); loadSessions();
  } catch (e) { console.error('switchSession:', e); }
}
async function newSession() {
  await closeCurrentSession();
  try {
    const r = await fetch('/new', { method: 'POST' });
    if (!r.ok) throw new Error(r.status);
    const { id } = await r.json();
    currentSessionId = id; rawMessages = []; msgs.innerHTML = ''; tray.innerHTML = '';
    sessionDirty = false;
    await loadSessions();
  } catch (e) { console.error('newSession:', e); }
}
async function deleteSession(id) {
  try {
    await fetch('/session?id=' + encodeURIComponent(id), { method: 'DELETE' });
    if (id === currentSessionId) { currentSessionId = null; msgs.innerHTML = ''; tray.innerHTML = ''; }
    document.getElementById('session-filter').value = '';
    await loadSessions();
  } catch (e) {}
}
function renderSessionList() {
  const list = document.getElementById('session-list');
  const empty = document.getElementById('session-list-empty');
  const filter = (document.getElementById('session-filter')?.value || '').trim().toLowerCase();
  const filtered = filter ? allSessions.filter(s => (s.title || '').toLowerCase().includes(filter)) : allSessions;
  list.querySelectorAll('.session-row').forEach(r => r.remove());
  if (filtered.length === 0) { empty.style.display = ''; empty.textContent = filter ? 'No matches.' : 'No sessions yet.'; return; }
  empty.style.display = 'none';
  filtered.forEach(s => {
    const row = document.createElement('div');
    row.className = 'session-row' + (s.id === currentSessionId ? ' active' : '');
    row.innerHTML = '<span class="session-row-title">' + escapeHtml(s.title || 'Untitled') + '</span>'
      + '<span class="session-row-meta">' + fmtDate(s.created) + '</span>'
      + '<span class="session-row-actions"><button class="session-row-act" title="Rename">&#9998;</button>'
      + '<button class="session-row-act del" title="Delete">&#10005;</button></span>';
    row.querySelector('.session-row-act.del').addEventListener('click', e => {
      e.stopPropagation();
      if (confirm('Delete "' + (s.title || 'Untitled') + '"?')) deleteSession(s.id);
    });
    row.querySelector('.session-row-act:not(.del)').addEventListener('click', e => { e.stopPropagation(); startRename(row, s); });
    row.addEventListener('click', () => switchSession(s.id));
    list.appendChild(row);
  });
}
function fmtDate(d) {
  if (!d) return '';
  const diff = Date.now() - new Date(d).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'now';
  if (m < 60) return m + 'm';
  const h = Math.floor(m / 60);
  if (h < 24) return h + 'h';
  const days = Math.floor(h / 24);
  if (days < 7) return days + 'd';
  return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}
function startRename(row, s) {
  const titleEl = row.querySelector('.session-row-title');
  const old = titleEl.textContent;
  const inp = document.createElement('input');
  inp.className = 'rename-input'; inp.value = old;
  inp.addEventListener('blur', () => finishRename(row, s, inp));
  inp.addEventListener('keydown', e => {
    if (e.key === 'Enter') finishRename(row, s, inp);
    if (e.key === 'Escape') { row.replaceChild(titleEl, inp); titleEl.textContent = old; }
  });
  row.replaceChild(inp, titleEl); inp.focus(); inp.select();
}
async function finishRename(row, s, inp) {
  const newTitle = inp.value.trim() || 'Untitled';
  try {
    await fetch('/save', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: s.id, title: newTitle, messages: [] }) });
  } catch (e) {}
  const titleEl = document.createElement('span');
  titleEl.className = 'session-row-title'; titleEl.textContent = newTitle;
  row.replaceChild(titleEl, inp); s.title = newTitle; renderSessionList();
}

/* ---------- sidebar wiring ---------- */
function toggleSidebar() { document.getElementById('sidebar').classList.toggle('collapsed'); }
document.getElementById('sidebar-toggle').addEventListener('click', toggleSidebar);
document.getElementById('hamburger-sidebar').addEventListener('click', toggleSidebar);
document.addEventListener('keydown', e => { if ((e.ctrlKey || e.metaKey) && e.key === 'b') { e.preventDefault(); toggleSidebar(); } });
document.getElementById('session-filter').addEventListener('input', renderSessionList);
document.getElementById('btn-new-session').addEventListener('click', () => newSession());

/* ---------- agent tray (bubbles while running) + replayable modal ---------- */
const agents = {};         // live spec id -> {layer, goal, replyFormat, status, history, eventsEl}
const specByCall = {};     // live tool_call id -> spec id
let archived = {};         // persisted spec id -> same shape as live (history = events)
const archivedByCall = {}; // persisted tool_call id -> spec id

function agentBubble(id) {
  const a = agents[id];
  const b = document.createElement('div');
  b.className = 'agent-bubble ' + (a.layer === 3 ? 'layer3' : '') + ' ' + a.status;
  b.id = 'bubble-' + id;
  b.title = (a.layer === 3 ? 'L3' : 'L2') + ': ' + a.goal;
  b.innerHTML = 'L' + a.layer + '<span class="agent-status-dot"></span>';
  b.addEventListener('click', () => openAgentModal(id));
  tray.appendChild(b);
  return b;
}
function setAgentStatus(id, st) {
  const a = agents[id];
  if (!a) return;
  a.status = st;
  const b = document.getElementById('bubble-' + id);
  if (b) {
    b.classList.remove('running', 'done', 'failed');
    b.classList.add(st);
    if (st === 'done' || st === 'failed') {
      // bubbles are transient: only visible while the subagent runs
      setTimeout(() => { b.remove(); }, 1500);
    }
  }
  if (a.eventsEl) {
    const label = { done: '\u2714 finished', failed: '\u2718 failed' }[st];
    if (label) a.eventsEl.insertAdjacentHTML('beforeend', '<div class="ev final-ev">' + label + '</div>');
  }
}
function agentEvent(id, ev) {
  const a = agents[id] || archived[id];
  if (!a || !a.eventsEl) return;
  const body = a.eventsEl;
  if (ev.type === 'text' || ev.type === 'reasoning') {
    let last = body.lastElementChild;
    if (!last || !last.classList.contains('stream-ev')) {
      body.insertAdjacentHTML('beforeend', '<div class="ev stream-ev"></div>');
      last = body.lastElementChild;
    }
    last.textContent += ev.content || '';
    body.scrollTop = body.scrollHeight;
  } else if (ev.type === 'tool') {
    body.insertAdjacentHTML('beforeend', '<div class="ev tool-ev">\u{1F527} ' + escapeHtml(ev.content.name) + ' ' + escapeHtml((ev.content.args || '').slice(0, 120)) + '</div>');
    body.scrollTop = body.scrollHeight;
  } else if (ev.type === 'tool_result') {
    const text = String(ev.content.content || '');
    body.insertAdjacentHTML('beforeend', '<div class="ev">' + escapeHtml(text.slice(0, 400)) + (text.length > 400 ? '...' : '') + '</div>');
    body.scrollTop = body.scrollHeight;
  } else if (ev.type === 'agent_spawn') {
    body.insertAdjacentHTML('beforeend', '<div class="ev tool-ev">\u{1F9E9} spawn L' + (ev.content.layer || '?') + ': ' + escapeHtml((ev.content.goal || '').slice(0, 120)) + '</div>');
    body.scrollTop = body.scrollHeight;
  } else if (ev.type === 'agent_status') {
    body.insertAdjacentHTML('beforeend', '<div class="ev">' + escapeHtml(ev.content.status) + '</div>');
    body.scrollTop = body.scrollHeight;
  } else if (ev.type === 'error') {
    body.insertAdjacentHTML('beforeend', '<div class="ev err-ev">\u26A0 ' + escapeHtml(ev.content) + '</div>');
    body.scrollTop = body.scrollHeight;
  }
}
function openAgentModal(id) {
  const a = agents[id] || archived[id];
  if (!a) return;
  const overlay = document.getElementById('agent-modal-overlay');
  overlay.innerHTML = '<div id="agent-modal">'
    + '<div class="agent-modal-head"><h3>' + (a.layer === 3 ? 'L3 Worker' : 'L2 Task Agent') + ' \u00B7 ' + escapeHtml((a.goal || '').slice(0, 60)) + '</h3>'
    + '<button id="agent-modal-close">\u2715</button></div>'
    + '<div class="agent-modal-taskspec"><b>Goal:</b> ' + escapeHtml(a.goal || '')
    + '<br><b>Reply format:</b> ' + escapeHtml(a.replyFormat || '(free)')
    + '<br><b>Status:</b> ' + escapeHtml(a.status || 'unknown') + '</div>'
    + '<div class="agent-modal-body"></div></div>';
  const bodyEl = overlay.querySelector('.agent-modal-body');
  a.eventsEl = bodyEl;
  (a.history || []).forEach(ev => agentEvent(id, ev));
  overlay.querySelector('#agent-modal-close').addEventListener('click', () => {
    overlay.classList.remove('show'); a.eventsEl = null;
  });
  overlay.classList.add('show');
}
function makeSpawnBlockClickable(el, callId) {
  el.classList.add('spawn-block');
  el.title = 'Click to view subagent details';
  el.addEventListener('click', () => {
    const id = specByCall[callId] || archivedByCall[callId];
    if (id) openAgentModal(id);
  });
}
function registerArchived(subs) {
  archived = {};
  for (const k of Object.keys(archivedByCall)) delete archivedByCall[k];
  (subs || []).forEach(r => {
    archived[r.id] = {
      layer: r.layer, goal: r.goal, replyFormat: r.reply_format,
      status: r.status, history: r.events || [],
    };
    if (r.call_id) archivedByCall[r.call_id] = r.id;
  });
}

/* ---------- send / stream ---------- */
let abortCtrl = null;
async function send() {
  const text = input.value.trim();
  if (!text || processing) return;
  processing = true;
  abortCtrl = new AbortController();
  if (!currentSessionId) {
    try {
      const r = await fetch('/new', { method: 'POST', signal: abortCtrl.signal });
      const { id } = await r.json();
      currentSessionId = id; loadSessions();
    } catch (e) {}
  }
  rawMessages.push({ role: 'user', content: text });
  sessionDirty = true;
  addDiv('user', marked.parse(text));
  input.value = ''; btn.disabled = true; status.textContent = '';
  const ad = addDiv('assistant', '', 'assistant-msg');
  let buffer = '';
  try {
    const resp = await fetch('/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, sessionId: currentSessionId }), signal: abortCtrl.signal });
    if (!resp.ok) { status.textContent = 'Error: ' + resp.status; processing = false; btn.disabled = false; return; }
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let leftover = '';
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      leftover += dec.decode(value, { stream: true });
      const lines = leftover.split('\n');
      leftover = lines.pop() || '';
      for (const line of lines) {
        if (!line) continue;
        let obj;
        try { obj = JSON.parse(line); } catch (e) { continue; }
        switch (obj.type) {
          case 'text': buffer += obj.content; ad.innerHTML = marked.parse(buffer); status.textContent = 'Writing...'; break;
          case 'reasoning_start': {
            const old = document.getElementById('reasoning-details');
            if (old) old.remove();
            const det = document.createElement('details');
            det.id = 'reasoning-details'; det.className = 'msg reasoning';
            det.innerHTML = '<summary>Thinking\u2026</summary><div id="reasoning-content"></div>';
            msgs.insertBefore(det, ad);
            break;
          }
          case 'reasoning': {
            const rc = document.getElementById('reasoning-content');
            if (rc) {
              rc.textContent += obj.content; rc.scrollTop = rc.scrollHeight;
              const d2 = document.getElementById('reasoning-details');
              if (d2) d2.open = true;
            }
            break;
          }
          case 'tool': {
            const d = document.createElement('div');
            d.className = 'msg tool'; d.id = 'tool-' + obj.content.id;
            const args = obj.content.args;
            const argsHtml = args ? ' <code style="font-size:0.82rem;opacity:0.7">' + escapeHtml(args.length > 80 ? args.slice(0, 80) + '...' : args) + '</code>' : '';
            d.innerHTML = '<div class="tool-label">&#x1F527; ' + escapeHtml(obj.content.name) + argsHtml + '</div><div class="tool-result"></div>';
            msgs.insertBefore(d, ad);
            if (obj.content.name === 'spawn') makeSpawnBlockClickable(d, obj.content.id);
            break;
          }
          case 'tool_result': {
            const tid = obj.content.id;
            let block = document.getElementById('tool-' + tid);
            if (!block) {
              const tools = msgs.querySelectorAll('.msg.tool');
              for (let i = tools.length - 1; i >= 0; i--) {
                const rd = tools[i].querySelector('.tool-result');
                if (rd && !rd.innerHTML) { block = tools[i]; break; }
              }
            }
            if (block) block.querySelector('.tool-result').innerHTML = '<pre>' + escapeHtml(obj.content.content) + '</pre>';
            else {
              const d = document.createElement('div');
              d.className = 'msg tool';
              d.innerHTML = '<pre>' + escapeHtml(obj.content.content) + '</pre>';
              msgs.insertBefore(d, ad);
            }
            break;
          }
          case 'agent_spawn': {
            agents[obj.content.id] = {
              layer: obj.content.layer, goal: obj.content.goal,
              replyFormat: obj.content.reply_format || '', status: 'running', history: [],
            };
            if (obj.content.call_id) specByCall[obj.content.call_id] = obj.content.id;
            agentBubble(obj.content.id);
            break;
          }
          case 'agent_status': setAgentStatus(obj.content.id, obj.content.status); break;
          case 'agent_event': {
            const aid = obj.content.id, ev = obj.content.event;
            if (agents[aid]) agents[aid].history.push(ev);
            agentEvent(aid, ev);
            break;
          }
          case 'ask': handleAsk(obj.content); break;
          case 'error': addDiv('error', '&#x26A0; ' + escapeHtml(obj.content)); break;
          case 'sessionId': currentSessionId = obj.content; break;
          case 'done': ad.innerHTML = marked.parse(buffer); status.textContent = ''; reloadSessionFromServer(); break;
        }
        if (isNearBottom(msgs)) msgs.scrollTop = msgs.scrollHeight;
        updateScrollBtn();
      }
    }
  } catch (e) {
    if (e.name === 'AbortError') status.textContent = 'Aborted.';
    else status.textContent = 'Error: ' + e.message;
  }
  processing = false; btn.disabled = false; input.focus();
}
input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  if (e.key === 'Escape' && abortCtrl) { abortCtrl.abort(); abortCtrl = null; }
});
btn.addEventListener("click", send);
document.getElementById('btn-browse').addEventListener('click', async () => {
  try {
    const r = await fetch('/pickfile', { method: 'POST' });
    const d = await r.json();
    if (d.path) { input.value = (input.value ? input.value + ' ' : '') + d.path; input.focus(); }
  } catch (e) {}
});
fetch('/model').then(r => r.json()).then(d => { document.getElementById('model-name').textContent = ' \u2014 ' + d.model; });
loadSessions();

/* ---------- ask card (Inquire) ---------- */
function handleAsk(content) {
  const existing = document.getElementById('ask-card');
  if (existing) existing.remove();
  const card = document.createElement('div');
  card.className = 'msg ask-card'; card.id = 'ask-card';
  const qs = content.questions || [];
  card._askId = content.id; card._askQuestions = qs;
  let html = '';
  qs.forEach((q, qi) => {
    const opts = (q.options || []).map(o =>
      '<button type="button" class="ask-option" data-q="' + qi + '"><b>' + escapeHtml(o.label) + '</b>'
      + (o.description ? '<br><span class="ask-desc">' + escapeHtml(o.description) + '</span>' : '') + '</button>').join('');
    html += '<div class="ask-q">\u2753 ' + escapeHtml(q.question) + '</div>'
      + '<div class="ask-options">' + opts + '</div>'
      + ((!opts || q.allow_custom !== false)
        ? '<input class="ask-input" data-q="' + qi + '" placeholder="' + (opts ? 'Or type your own...' : 'Your answer...') + '">'
        : '');
  });
  html += '<div class="ask-actions"><button id="ask-submit">Submit</button></div>';
  card.innerHTML = html;
  msgs.insertBefore(card, document.getElementById('assistant-msg') || null);
  msgs.scrollTop = msgs.scrollHeight;
  card.querySelectorAll('.ask-option').forEach(btn => {
    btn.addEventListener('click', () => {
      const qi = btn.dataset.q;
      card.querySelectorAll('.ask-option[data-q="' + qi + '"]').forEach(b => b.classList.remove('selected'));
      btn.classList.add('selected');
      const inp = card.querySelector('.ask-input[data-q="' + qi + '"]');
      if (inp) inp.value = '';
    });
  });
  card.querySelectorAll('.ask-input').forEach(inp => {
    inp.addEventListener('input', () => {
      const qi = inp.dataset.q;
      card.querySelectorAll('.ask-option[data-q="' + qi + '"]').forEach(b => b.classList.remove('selected'));
    });
    inp.addEventListener('keydown', e => { if (e.key === 'Enter') collectAskAnswers(card); });
  });
  card.querySelector('#ask-submit').addEventListener('click', () => collectAskAnswers(card));
}
function collectAskAnswers(card) {
  const qs = card._askQuestions || [];
  const vals = [];
  for (let qi = 0; qi < qs.length; qi++) {
    const sel = card.querySelector('.ask-option.selected[data-q="' + qi + '"]');
    const inp = card.querySelector('.ask-input[data-q="' + qi + '"]');
    const v = sel ? sel.querySelector('b').textContent : (inp ? inp.value.trim() : '');
    if (!v) { if (inp) { inp.focus(); inp.placeholder = 'Required'; } return; }
    vals.push(v);
  }
  submitAsk(card._askId, vals, card);
}
async function submitAsk(askId, value, card) {
  const qs = card._askQuestions || [];
  const arr = Array.isArray(value) ? value : [value];
  card.classList.add('answered');
  card.innerHTML = qs.map((q, i) =>
    '<div class="ask-q">\u2753 ' + escapeHtml(q.question) + '</div>'
    + '<div class="ask-a">\u2705 ' + escapeHtml(arr[i] ?? '') + '</div>').join('');
  try {
    await fetch('/answer', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: askId, value }) });
  } catch (e) {}
}
function renderArchivedAsk(rec) {
  const card = document.createElement('div');
  card.className = 'msg ask-card answered';
  const qs = rec.questions || [];
  const ans = Array.isArray(rec.answers) ? rec.answers
    : (rec.answers != null ? [rec.answers] : null);
  card.innerHTML = qs.map((q, i) =>
    '<div class="ask-q">\u2753 ' + escapeHtml(q.question) + '</div>'
    + '<div class="ask-a">' + (rec.status === 'timeout' || !ans ? '\u23F3 No answer' : '\u2705 ' + escapeHtml(ans[i] ?? '')) + '</div>'
  ).join('');
  msgs.appendChild(card);
}
/* ---------- config modal ---------- */
(async () => {
  try {
    const r = await fetch('/config-status');
    const d = await r.json();
    if (!d.configured) {
      document.getElementById('config-overlay').classList.add('show');
      document.getElementById('cfg-save').addEventListener('click', async () => {
        const api_key = document.getElementById('cfg-apikey').value.trim();
        const endpoint = document.getElementById('cfg-endpoint').value.trim();
        const model = document.getElementById('cfg-model').value.trim();
        if (!api_key) {
          const err = document.getElementById('cfg-err');
          err.textContent = 'API key is required.'; err.style.display = 'block';
          return;
        }
        try {
          const r2 = await fetch('/configure', { method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key, endpoint, model }) });
          const d2 = await r2.json();
          if (d2.ok) {
            document.getElementById('config-overlay').classList.remove('show');
            fetch('/model').then(r3 => r3.json()).then(d3 => {
              document.getElementById('model-name').textContent = ' \u2014 ' + d3.model;
            });
          }
        } catch (e) {}
      });
      document.getElementById('cfg-skip').addEventListener('click', () => {
        document.getElementById('config-overlay').classList.remove('show');
      });
    }
  } catch (e) {}
})();
