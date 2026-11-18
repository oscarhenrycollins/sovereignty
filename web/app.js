"use strict";
const el = id => document.getElementById(id);
let state = { areas: [] };

function say(text, kind = '') {
  const s = el('status');
  s.classList.toggle('wz-sr', !kind);
  s.classList.toggle('note', kind === 'note');
  s.textContent = text;
}
async function load() {
  const r = await fetch('api/areas');
  let body = {}; try { body = await r.json(); } catch (e) {}
  if (!r.ok) throw new Error(body.error || 'Could not load your checklist. Try again.');
  return body;
}
function dots(level, levels) {
  const d = document.createElement('span');
  d.className = 'sv-dots l' + level; d.setAttribute('aria-hidden', 'true');
  for (let i = 1; i <= levels; i++) { const x = document.createElement('i'); if (i <= level) x.className = 'on'; d.append(x); }
  return d;
}
function nice(day) {
  if (!day) return '';
  const d = new Date(day + 'T12:00:00');
  return isNaN(d) ? day : d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
}

function render(data) {
  state = data;
  const levels = data.levels || 4;
  el('score').textContent = data.score;
  el('score-bar').style.setProperty('--v', data.score + '%');
  const top = data.areas.filter(a => a.level === levels).length;
  const rated = data.areas.filter(a => a.level > 0).length;
  el('score-note').textContent = top + ' of ' + data.areas.length + ' areas fully yours';
  el('checked').textContent = data.checked ? 'Checked ' + nice(data.checked) : 'Not checked yet';
  el('empty').hidden = rated > 0;

  const groups = new Map();
  for (const a of data.areas) { if (!groups.has(a.group)) groups.set(a.group, []); groups.get(a.group).push(a); }
  const root = el('groups'); root.replaceChildren();
  for (const [name, areas] of groups) {
    const sec = document.createElement('section'); sec.className = 'wz-sec';
    const h = document.createElement('h2'); h.className = 'wz-sec-h'; h.textContent = name;
    const ul = document.createElement('ul'); ul.className = 'wz-list';
    for (const a of areas) {
      const li = document.createElement('li');
      const row = document.createElement('button'); row.type = 'button'; row.className = 'wz-row';
      const rung = a.level ? a.rungs[a.level - 1] : 'Not set up';
      row.setAttribute('aria-label', a.name + ', step ' + a.level + ' of ' + levels + ': ' + rung);
      const main = document.createElement('span'); main.className = 'wz-main';
      const b = document.createElement('b'); b.textContent = a.name;
      const sm = document.createElement('small'); sm.textContent = a.via || rung;
      main.append(b, sm);
      row.append(main, dots(a.level, levels));
      row.onclick = () => openArea(a);
      li.append(row); ul.append(li);
    }
    sec.append(h, ul); root.append(sec);
  }
}

function openArea(a) {
  const levels = state.levels || 4;
  el('sheet-h').textContent = a.name;
  el('sheet-via').textContent = a.via || (a.level ? a.rungs[a.level - 1] : 'Not set up yet');
  const ol = el('sheet-ladder'); ol.replaceChildren();
  for (let i = levels; i >= 1; i--) {
    const li = document.createElement('li');
    li.className = i === a.level ? 'here' : (i < a.level ? 'below' : '');
    const n = document.createElement('b'); n.textContent = i;
    const t = document.createElement('span'); t.textContent = a.rungs[i - 1] || '';
    li.append(n, t);
    if (i === a.level) { const e = document.createElement('em'); e.textContent = 'You are here'; li.append(e); }
    ol.append(li);
  }
  const nx = el('sheet-next');
  nx.hidden = !a.next; nx.querySelector('p').textContent = a.next || '';
  el('sheet-evidence').textContent = a.evidence ? 'How we know: ' + a.evidence + (a.checked ? ' (' + nice(a.checked) + ')' : '') : '';
  WzSheet.open(el('sheet'));
}

if (!window.WizardApp || WizardApp.version !== 1) {
  say('Wizard system functions are unavailable. Open this preview through Wizard.', 'error');
} else {
  WizardApp.ready({ name: 'sovereignty', version: '0.2.0' });
  WizardApp.back.register({ canGoBack: () => false, back: () => false });
}
load().then(render).catch(e => say(e.message, 'error'));
document.addEventListener('visibilitychange', () => { if (!document.hidden) load().then(render).catch(() => {}); });
