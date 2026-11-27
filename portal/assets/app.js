'use strict';
// No framework and nothing from a CDN: the party LAN is offline.

const $ = (id) => document.getElementById(id);

async function api(action, body, isForm) {
    const opt = { method: 'POST', headers: { 'X-CSRF': CSRF } };
    if (isForm) {
        opt.body = body;
    } else {
        opt.headers['Content-Type'] = 'application/json';
        opt.body = JSON.stringify(body || {});
    }
    const r = await fetch('api.php?do=' + action, opt);
    const j = await r.json().catch(() => ({ ok: false, error: 'bad response' }));
    if (!j.ok) { console.warn(action, j.error); }
    return j;
}

// ------------------------------------------------------------------- board
let SLOTS = [];
let MEMBERS = [];

function renderBoard(state) {
    SLOTS = state.slots || [];
    const stage = $('stage'), img = $('plan'), noplan = $('noplan');
    const path = state.board && state.board.image_path;
    if (path) {
        img.src = 'plan.php?v=' + (state.rev || 0);   // never data/, see plan.php
        img.hidden = false;
        noplan.hidden = true;
        stage.classList.remove('empty');
    } else {
        img.hidden = true;
        noplan.hidden = false;
        stage.classList.add('empty');
    }
    drawSlots();
}

function drawSlots() {
    const host = $('slots');
    host.textContent = '';
    for (const s of SLOTS) {
        const el = document.createElement('div');
        el.className = 'slot' + (s.kind === 'server' ? ' server' : '')
                     + (s.user_name ? ' taken' : '') + (ADMIN ? ' editable' : '');
        el.style.left = (s.x * 100) + '%';
        el.style.top = (s.y * 100) + '%';
        el.style.width = (s.w * 100) + '%';
        el.style.height = (s.h * 100) + '%';
        el.dataset.id = s.id;

        const who = document.createElement('div');
        who.className = 'who';
        who.textContent = s.user_name || '';
        const lbl = document.createElement('div');
        lbl.className = 'lbl';
        lbl.textContent = s.label || '';
        el.append(who, lbl);

        if (ADMIN) {
            const grip = document.createElement('div');
            grip.className = 'grip';
            el.append(grip);
            el.addEventListener('pointerdown', (e) => startDrag(e, s, e.target === grip));
            el.addEventListener('dblclick', () => renameSlot(s));
            el.addEventListener('contextmenu', (e) => { e.preventDefault(); slotMenu(s); });
        }
        host.append(el);
    }
}

// Drag and resize in stage-relative fractions, so what is stored is resolution
// independent. Pointer capture keeps it working if the cursor leaves the element.
function startDrag(e, slot, resizing) {
    if (e.button !== 0) return;
    e.preventDefault();
    const stage = $('stage').getBoundingClientRect();
    const el = e.currentTarget;
    const startX = e.clientX, startY = e.clientY;
    const ox = slot.x, oy = slot.y, ow = slot.w, oh = slot.h;
    el.setPointerCapture(e.pointerId);

    const move = (ev) => {
        const dx = (ev.clientX - startX) / stage.width;
        const dy = (ev.clientY - startY) / stage.height;
        if (resizing) {
            slot.w = Math.max(0.02, ow + dx);
            slot.h = Math.max(0.02, oh + dy);
        } else {
            slot.x = Math.min(1 - slot.w, Math.max(0, ox + dx));
            slot.y = Math.min(1 - slot.h, Math.max(0, oy + dy));
        }
        el.style.left = (slot.x * 100) + '%';
        el.style.top = (slot.y * 100) + '%';
        el.style.width = (slot.w * 100) + '%';
        el.style.height = (slot.h * 100) + '%';
    };
    const up = () => {
        el.removeEventListener('pointermove', move);
        el.removeEventListener('pointerup', up);
        // One write at the end, not per frame: every save bumps the revision and
        // pushes a board event to every connected client.
        api('slot.move', { id: slot.id, x: slot.x, y: slot.y, w: slot.w, h: slot.h });
    };
    el.addEventListener('pointermove', move);
    el.addEventListener('pointerup', up);
}

function addSlot() {
    const label = prompt('Slot name', 'Seat');
    if (label !== null) api('slot.create', { label });
}

function renameSlot(s) {
    const label = prompt('Slot name', s.label || '');
    if (label !== null) api('slot.label', { id: s.id, label });
}

function slotMenu(s) {
    const names = MEMBERS.map((m) => m.id + '=' + m.name).join(', ');
    const what = prompt(
        'Slot "' + (s.label || s.id) + '"' +
        (s.addrs && s.addrs.length ? '\naddresses: ' + s.addrs.join(', ') : '') +
        '\n\nassign <id>   (' + (names || 'no members yet') + ')' +
        '\nclear         free the seat' +
        '\naddr <ip>     add an address' +
        '\ndelete', '');
    if (!what) return;
    const [cmd, arg] = what.trim().split(/\s+/, 2);
    if (cmd === 'assign') api('slot.assign', { id: s.id, user_id: parseInt(arg, 10) || 0 });
    else if (cmd === 'clear') api('slot.assign', { id: s.id, user_id: 0 });
    else if (cmd === 'addr' && arg) api('slot.addr.add', { id: s.id, addr: arg });
    else if (cmd === 'delete' && confirm('Delete this slot?')) api('slot.delete', { id: s.id });
}

async function uploadPlan(e) {
    e.preventDefault();
    const j = await api('board.upload', new FormData(e.target), true);
    if (!j.ok) alert(j.error || 'upload failed');
    e.target.reset();
    return false;
}

// ----------------------------------------------------------------- members
function renderMembers(list) {
    MEMBERS = list;
    const ul = $('members');
    ul.textContent = '';
    for (const m of list) {
        const li = document.createElement('li');
        const dot = document.createElement('span');
        dot.className = 'dot' + (m.online ? ' on' : '');
        const name = document.createElement('span');
        name.textContent = m.name + (m.is_admin ? ' *' : '');
        li.append(dot, name);
        if (m.slot_label) {
            const seat = document.createElement('span');
            seat.className = 'seat';
            seat.textContent = m.slot_label;
            li.append(seat);
        }
        ul.append(li);
    }
}

// -------------------------------------------------------------------- chat
function addMessage(m) {
    const ul = $('log');
    const atBottom = ul.scrollHeight - ul.scrollTop - ul.clientHeight < 40;
    const li = document.createElement('li');
    const at = document.createElement('span');
    at.className = 'at';
    at.textContent = (m.created_at || '').slice(11, 16);
    const nick = document.createElement('span');
    nick.className = 'nick' + (m.user_name === ME ? ' me' : '');
    nick.textContent = (m.user_name || '?') + ': ';
    const body = document.createElement('span');
    body.textContent = m.body;            // textContent, never innerHTML
    li.append(at, nick, body);
    ul.append(li);
    if (atBottom) ul.scrollTop = ul.scrollHeight;
}

async function say(e) {
    e.preventDefault();
    const box = $('msg');
    const text = box.value.trim();
    if (!text) return false;
    box.value = '';
    await api('say', { body: text });     // it comes back via the stream, like everyone else's
    return false;
}

async function doLogout() {
    await api('logout', {});
    location.reload();
}

// --------------------------------------------------------------------- SSE
function connect() {
    const es = new EventSource('events.php');
    es.addEventListener('board',   (e) => renderBoard(JSON.parse(e.data)));
    es.addEventListener('members', (e) => renderMembers(JSON.parse(e.data).members));
    es.addEventListener('message', (e) => addMessage(JSON.parse(e.data)));
    // 'bye' is the server recycling the worker after 60 s; EventSource reconnects by
    // itself and replays Last-Event-ID, so nothing is missed and nothing to do here.
    es.onerror = () => { /* browser retries using the retry: hint */ };
}
connect();
