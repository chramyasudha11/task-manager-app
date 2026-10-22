'use strict';
/* TaskFlow UI (Member 4 pages: People, Projects · Member 5 pages: Tasks + dashboards).
   Plain JS, no build step. Served by Flask at "/", so the session cookie just works. */
const S = {user: null, page: null, tab: 'employees', ef: {}, tf: {}, emps: [], tasks: [], projects: [], people: []};
const STATUS = {pending: 'Assigned', in_progress: 'In Progress', completed: 'Completed'};
const NAV = {
  ADMIN: [['admin', 'Admin Dashboard'], ['people', 'Employees & Teams'], ['projects', 'Projects'], ['tasks', 'Tasks']],
  MANAGER: [['manager', 'Manager Dashboard'], ['projects', 'Projects'], ['tasks', 'Tasks']],
  EMPLOYEE: [['mine', 'My Dashboard'], ['projects', 'Projects'], ['tasks', 'Tasks']],
};
const $ = s => document.querySelector(s);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const val = id => ($('#' + id) || {}).value || '';
const canManage = () => S.user && S.user.role !== 'EMPLOYEE';

async function api(path, method = 'GET', data) {
  const res = await fetch(path, {method, credentials: 'same-origin',
    headers: data !== undefined ? {'Content-Type': 'application/json'} : {},
    body: data !== undefined ? JSON.stringify(data) : undefined});
  let json = {};
  try { json = await res.json(); } catch (e) { /* empty body */ }
  if (res.status === 401 && path !== '/api/login') { S.user = null; render(); throw new Error(json.error || 'Please login'); }
  if (!res.ok) throw new Error(json.error || 'Request failed');
  return json;
}
function toast(msg, bad) {
  const t = $('#toast'); t.textContent = msg; t.className = 'show' + (bad ? ' bad' : '');
  clearTimeout(toast.t); toast.t = setTimeout(() => t.className = '', 2600);
}
const badge = (kind, text) => `<span class="badge b-${kind}">${esc(text)}</span>`;
const statusBadge = s => badge(s, STATUS[s] || s);
const prioBadge = p => badge(String(p).toLowerCase(), p);
const fmt = d => d ? new Date(d + 'T00:00:00').toLocaleDateString('en-GB', {day: 'numeric', month: 'short'}) : '—';
const bar = (pct, cls = '') => `<div class="bar ${cls}"><i style="width:${pct}%"></i></div>`;
const opts = (list, sel, blank) => (blank !== undefined ? `<option value="">${esc(blank)}</option>` : '') +
  list.map(x => `<option value="${x.id}" ${String(x.id) === String(sel) ? 'selected' : ''}>${esc(x.name)}</option>`).join('');
const stat = (n, l, warn) => `<div class="card stat ${warn && n ? 'warn' : ''}"><div class="n">${n}</div><div class="l">${esc(l)}</div></div>`;
const head = (title, sub, right = '') => `<div class="head"><div><h1>${esc(title)}</h1><div class="sub">${esc(sub)}</div></div><div>${right}</div></div>`;
const empty = t => `<div class="empty">${esc(t)}</div>`;
const dist = rows => { const tot = rows.reduce((a, r) => a + r[1], 0) || 1;
  return rows.map(r => `<div class="row"><span class="lab">${r[0]}</span>${bar(Math.round(r[1] * 100 / tot), r[2])}<span class="val">${r[1]}</span></div>`).join(''); };

function modal(title, inner, onSave, saveLabel = 'Save') {
  $('#modal-root').innerHTML = `<div class="overlay" onmousedown="if(event.target===this)closeModal()"><div class="modal"><h2>${esc(title)}</h2>${inner}
    <div class="err" id="m-err"></div><div class="foot"><button class="btn ghost" onclick="closeModal()">${onSave ? 'Cancel' : 'Close'}</button>
    ${onSave ? `<button class="btn" id="m-save">${esc(saveLabel)}</button>` : ''}</div></div></div>`;
  if (onSave) $('#m-save').onclick = async () => {
    $('#m-err').textContent = '';
    try { await onSave(); closeModal(); await refresh(); } catch (e) { $('#m-err').textContent = e.message; }
  };
}
window.closeModal = () => { $('#modal-root').innerHTML = ''; };
const field = (label, html) => `<div class="field"><label>${esc(label)}</label>${html}</div>`;

/* ---------- shell ---------- */
function loginView() {
  $('#app').innerHTML = `<div class="login"><div class="card"><h1>Task<span>Flow</span></h1><div class="sub">Sign in to manage your team's work</div>
    ${field('Email', '<input id="l-email" type="email" autocomplete="username">')}${field('Password', '<input id="l-pass" type="password" autocomplete="current-password">')}
    <div class="err" id="l-err"></div><button class="btn" style="width:100%;margin-top:8px" id="l-go">Sign in</button></div></div>`;
  const go = async () => {
    try {
      const r = await api('/api/login', 'POST', {email: val('l-email'), password: val('l-pass')});
      S.user = r.user; S.page = NAV[S.user.role][0][0]; render();
    } catch (e) { $('#l-err').textContent = e.message; }
  };
  $('#l-go').onclick = go;
  $('#l-pass').onkeydown = e => { if (e.key === 'Enter') go(); };
}
async function render() {
  if (!S.user) return loginView();
  const nav = NAV[S.user.role].map(([k, l]) => `<button class="nav ${S.page === k ? 'active' : ''}" onclick="A.go('${k}')">${l}</button>`).join('');
  $('#app').innerHTML = `<div class="layout"><aside class="side"><div class="brand">Task<span>Flow</span></div>${nav}
    <div class="me">${esc(S.user.name)}<small>${esc(S.user.role)}</small><button class="link" onclick="A.logout()">Sign out</button></div></aside>
    <main class="main" id="main">${empty('Loading…')}</main></div>`;
  await refresh();
}
async function refresh() {
  if (!S.user || !$('#main')) return;
  try { $('#main').innerHTML = await PAGES[S.page](); }
  catch (e) { if (S.user) $('#main').innerHTML = empty(e.message); }
}

/* ---------- dashboards (3) ---------- */
const miniTasks = list => list.length ? `<div class="tablewrap"><table><tr><th>Task</th><th>Employee</th><th>Project</th><th>Due</th></tr>${list.map(t =>
  `<tr><td>${esc(t.title)}</td><td>${esc(t.assignee_name || '—')}</td><td>${esc(t.project_name || '—')}</td><td class="${t.is_overdue ? 'overdue' : ''}">${fmt(t.due_date)}</td></tr>`).join('')}</table></div>` : empty('Nothing here');
const projProgress = ps => ps.length ? ps.map(p => `<div style="margin:12px 0"><div style="display:flex;justify-content:space-between"><b>${esc(p.name)}</b>
  <span class="mini">${p.progress.completed}/${p.progress.total} tasks · ${p.progress.percent}%</span></div>${bar(p.progress.percent)}</div>`).join('') : empty('No projects yet');
const statusDist = t => dist([['Assigned', t.pending, 'amber'], ['In Progress', t.in_progress, 'violet'], ['Completed', t.completed, '']]);

async function pAdmin() {
  const o = await api('/api/overview'), t = o.tasks;
  return head('Admin Dashboard', `Welcome back, ${o.name.split(' ')[0]}`) +
    `<div class="grid g4">${stat(o.people.active, `Active employees (of ${o.people.total})`)}${stat(o.teams, 'Teams')}${stat(o.projects.length, 'Projects')}${stat(t.total, 'Tasks')}${stat(t.overdue, 'Overdue tasks', true)}</div>
    <div class="grid g2" style="margin-top:16px"><div class="card"><h3>Tasks by status</h3>${statusDist(t)}</div>
    <div class="card"><h3>Tasks by priority</h3>${dist([['High', t.priority.High, 'red'], ['Medium', t.priority.Medium, 'amber'], ['Low', t.priority.Low, '']])}</div>
    <div class="card"><h3>Project progress</h3>${projProgress(o.projects)}</div>
    <div class="card"><h3>Overdue tasks</h3>${miniTasks(o.overdue_tasks)}</div></div>`;
}
async function pManager() {
  const o = await api('/api/overview'), t = o.tasks, mx = Math.max(1, ...o.workload.map(w => w.open));
  return head('Manager Dashboard', `Your projects and team workload, ${o.name.split(' ')[0]}`) +
    `<div class="grid g4">${stat(t.total, 'Tasks in your projects')}${stat(t.in_progress, 'In progress')}${stat(t.completed, 'Completed')}${stat(t.overdue, 'Overdue', true)}</div>
    <div class="grid g2" style="margin-top:16px"><div class="card"><h3>Project progress</h3>${projProgress(o.projects)}</div>
    <div class="card"><h3>Team workload (open tasks)</h3>${o.workload.length ? o.workload.map(w => `<div class="row"><span class="lab" style="width:120px">${esc(w.name)}</span>${bar(Math.round(w.open * 100 / mx), w.overdue ? 'red' : '')}<span class="val">${w.open}</span></div>`).join('') : empty('No open tasks')}</div>
    <div class="card"><h3>Status split</h3>${statusDist(t)}</div><div class="card"><h3>Overdue</h3>${miniTasks(o.overdue_tasks)}</div></div>`;
}
async function pMine() {
  const o = await api('/api/overview'), t = o.tasks;
  const rows = o.upcoming.length ? `<div class="tablewrap"><table><tr><th>Task</th><th>Project</th><th>Due</th><th>Status</th></tr>${o.upcoming.map(x =>
    `<tr><td>${esc(x.title)}</td><td>${esc(x.project_name || '—')}</td><td class="${x.is_overdue ? 'overdue' : ''}">${fmt(x.due_date)}</td><td>${statusSelect(x)}</td></tr>`).join('')}</table></div>` : empty('You are all caught up');
  return head('My Dashboard', `Hi ${o.name.split(' ')[0]}, here is your work`) +
    `<div class="grid g4">${stat(t.pending, 'Assigned')}${stat(t.in_progress, 'In progress')}${stat(t.completed, 'Completed')}${stat(t.overdue, 'Overdue', true)}</div>
    <div class="grid g2" style="margin-top:16px"><div class="card"><h3>Up next</h3>${rows}</div><div class="card"><h3>My projects</h3>${projProgress(o.projects)}</div></div>`;
}

/* ---------- employees & teams (Member 4) ---------- */
async function pPeople() {
  const right = S.tab === 'employees' ? '<button class="btn" onclick="A.empForm()">+ Add Employee</button>' : '<button class="btn" onclick="A.teamForm()">+ Create Team</button>';
  const tabs = ['employees', 'teams'].map(k => `<button class="tab ${S.tab === k ? 'active' : ''}" onclick="A.tab('${k}')">${k === 'employees' ? 'Employees' : 'Teams'}</button>`).join('');
  return head('Employees & Teams', 'Manage your organisation structure', right) + `<div class="tabs">${tabs}</div>` + (S.tab === 'employees' ? await empTable() : await teamCards());
}
async function empTable() {
  const f = S.ef, q = new URLSearchParams(Object.entries(f).filter(([, v]) => v));
  S.emps = await api('/api/employees?' + q);
  const sel = (k, list) => `<select onchange="A.ef('${k}',this.value)">${list.map(([v, l]) => `<option value="${v}" ${f[k] === v ? 'selected' : ''}>${l}</option>`).join('')}</select>`;
  const rows = S.emps.map(e => `<tr><td><b>${esc(e.name)}</b><div class="mini">${esc(e.designation || '')}</div></td><td>${esc(e.email)}</td><td>${badge('role', e.role)}</td><td>${esc(e.department || '—')}</td>
    <td>${e.is_active ? badge('active', 'Active') : badge('inactive', 'Deactivated')}</td><td><div class="actions">
    <button class="btn ghost sm" onclick="A.empView(${e.id})">View</button><button class="btn ghost sm" onclick="A.empForm(${e.id})">Edit</button>
    <button class="btn ${e.is_active ? 'danger' : ''} sm" onclick="A.toggleEmp(${e.id},${!e.is_active})">${e.is_active ? 'Deactivate' : 'Activate'}</button></div></td></tr>`).join('');
  return `<div class="filters"><input placeholder="Search name or email" value="${esc(f.q || '')}" onchange="A.ef('q',this.value)">
    ${sel('role', [['', 'All roles'], ['ADMIN', 'Admin'], ['MANAGER', 'Manager'], ['EMPLOYEE', 'Employee']])}${sel('active', [['', 'Any status'], ['1', 'Active'], ['0', 'Deactivated']])}</div>
    <div class="card tablewrap"><table><tr><th>Name</th><th>Email</th><th>Role</th><th>Department</th><th>Status</th><th>Action</th></tr>${rows || `<tr><td colspan="6">${empty('No employees found')}</td></tr>`}</table></div>`;
}
async function teamCards() {
  const [teams, people] = await Promise.all([api('/api/teams'), api('/api/employees/options')]);
  S.people = people; S.teams = teams;
  const managers = people.filter(p => p.role !== 'EMPLOYEE');
  if (!teams.length) return `<div class="card">${empty('No teams yet. Create your first team.')}</div>`;
  return `<div class="grid g2">${teams.map(t => {
    const inTeam = new Set(t.members.map(m => m.id));
    return `<div class="card"><div class="head" style="margin-bottom:8px"><h3 style="margin:0">${esc(t.name)} <span class="mini">· ${t.member_count} members</span></h3>
      <button class="btn danger sm" onclick="A.delTeam(${t.id})">Delete</button></div>
      <label style="margin-top:0">Manager</label><select style="width:100%" onchange="A.teamMgr(${t.id},this.value)">${opts(managers, t.manager_id, '— No manager —')}</select>
      <label>Members</label><div>${t.members.map(m => `<span class="chip">${esc(m.name)}<button title="Remove" onclick="A.rmMember(${t.id},${m.id})">×</button></span>`).join('') || '<span class="mini">No members yet</span>'}</div>
      <div class="filters" style="margin:12px 0 0"><select id="add-${t.id}" style="flex:1">${opts(people.filter(p => !inTeam.has(p.id)), '', 'Add member…')}</select>
      <button class="btn sm" onclick="A.addMember(${t.id})">Add</button></div></div>`;
  }).join('')}</div>`;
}

/* ---------- projects (Member 4) ---------- */
async function pProjects() {
  S.projects = await api('/api/projects');
  const admin = S.user.role === 'ADMIN';
  const cards = S.projects.map(p => `<div class="card projcard"><div class="top"><div><h3 style="margin:0">${esc(p.name)}</h3>
    <div class="mini">Manager: ${esc(p.manager ? p.manager.name : '—')} · Team: ${esc(p.team_name || '—')} (${p.member_ids.length})</div></div>${badge(p.status, p.status.replace('_', ' '))}</div>
    <div>${bar(p.progress.percent)}<div class="mini" style="margin-top:5px">${p.progress.completed}/${p.progress.total} tasks done · ${p.progress.percent}%</div></div>
    <div class="actions"><button class="btn ghost sm" onclick="A.projView(${p.id})">View</button>${admin ? `<button class="btn ghost sm" onclick="A.projForm(${p.id})">Edit / Assign</button>` : ''}</div></div>`).join('');
  return head('Projects', admin ? 'Create projects, assign teams and managers' : 'Projects you are part of', admin ? '<button class="btn" onclick="A.projForm()">+ New Project</button>' : '') +
    (cards ? `<div class="grid g2">${cards}</div>` : `<div class="card">${empty('No projects to show')}</div>`);
}

/* ---------- tasks (Member 5) ---------- */
const statusSelect = t => `<select onchange="A.setStatus(${t.id},this.value)">${Object.entries(STATUS).map(([k, l]) => `<option value="${k}" ${t.status === k ? 'selected' : ''}>${l}</option>`).join('')}</select>`;
async function pTasks() {
  const f = S.tf, q = new URLSearchParams(Object.entries(f).filter(([, v]) => v));
  const [tasks, projects] = await Promise.all([api('/api/task-board?' + q), api('/api/projects')]);
  S.tasks = tasks; S.projects = projects;
  const m = canManage();
  const sel = (k, list) => `<select onchange="A.tf('${k}',this.value)">${list.map(([v, l]) => `<option value="${v}" ${String(f[k] || '') === String(v) ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>`;
  const rows = tasks.map(t => `<tr><td><b>${esc(t.title)}</b></td><td>${esc(t.assignee_name || 'Unassigned')}</td><td>${esc(t.project_name || '—')}</td><td>${prioBadge(t.priority)}</td>
    <td class="${t.is_overdue ? 'overdue' : ''}">${fmt(t.due_date)}${t.is_overdue ? ' !' : ''}</td><td>${statusSelect(t)}</td><td><div class="actions">
    <button class="btn ghost sm" onclick="A.taskView(${t.id})">View</button>${m ? `<button class="btn ghost sm" onclick="A.taskForm(${t.id})">Edit</button>
    <button class="btn ghost sm" onclick="A.assign(${t.id})">Assign</button><button class="btn danger sm" onclick="A.delTask(${t.id})">Delete</button>` : ''}</div></td></tr>`).join('');
  return head('Tasks', m ? 'Create, assign and track work' : 'Tasks assigned to you', m ? '<button class="btn" onclick="A.taskForm()">+ Create Task</button>' : '') +
    `<div class="filters"><input placeholder="Search tasks" value="${esc(f.search || '')}" onchange="A.tf('search',this.value)">
    ${sel('status', [['', 'All statuses'], ...Object.entries(STATUS)])}${sel('priority', [['', 'All priorities'], ['High', 'High'], ['Medium', 'Medium'], ['Low', 'Low']])}
    ${sel('project_id', [['', 'All projects'], ...projects.map(p => [p.id, p.name])])}</div>
    <div class="card tablewrap"><table><tr><th>Task</th><th>Employee</th><th>Project</th><th>Priority</th><th>Due Date</th><th>Status</th><th>Action</th></tr>${rows || `<tr><td colspan="7">${empty('No tasks found')}</td></tr>`}</table></div>`;
}
async function pickers(task) {
  const [people, projects] = await Promise.all([api('/api/employees/options'), api('/api/projects')]);
  S.people = people; S.projects = projects;
  return {
    emp: field('Employee', `<select id="t-emp" onchange="A.hint()">${opts(people, task && task.assigned_to, 'Unassigned')}</select>`),
    proj: field('Project', `<select id="t-proj" onchange="A.hint()">${opts(projects, task && task.project_id, 'No project')}</select><div class="hint" id="t-hint"></div>`),
  };
}
const numOrNull = id => val(id) ? Number(val(id)) : null;
async function applyAssignment(id, task) {
  const emp = numOrNull('t-emp'), proj = numOrNull('t-proj');
  if (!task || emp !== task.assigned_to) await api(`/api/tasks/${id}/assign`, 'PATCH', {assigned_to: emp});
  if ((task ? task.project_id : null) !== proj) await api(`/api/task-board/${id}/project`, 'PATCH', {project_id: proj});
}

/* ---------- actions ---------- */
const PAGES = {admin: pAdmin, manager: pManager, mine: pMine, people: pPeople, projects: pProjects, tasks: pTasks};
const A = window.A = {
  go(p) { S.page = p; render(); },
  async logout() { try { await api('/api/logout', 'POST', {}); } catch (e) { /* ignore */ } S.user = null; render(); },
  tab(t) { S.tab = t; refresh(); },
  ef(k, v) { S.ef[k] = v; refresh(); },
  tf(k, v) { S.tf[k] = v; refresh(); },
  async setStatus(id, status) {
    try { await api(`/api/tasks/${id}/status`, 'PATCH', {status}); toast('Status updated'); refresh(); } catch (e) { toast(e.message, true); refresh(); }
  },
  async delTask(id) {
    if (!confirm('Delete this task?')) return;
    try { await api(`/api/tasks/${id}`, 'DELETE'); toast('Task deleted'); refresh(); } catch (e) { toast(e.message, true); }
  },
  taskView(id) {
    const t = S.tasks.find(x => x.id === id) || (S.upcomingCache || []).find(x => x.id === id);
    if (!t) return;
    modal(t.title, `<p>${esc(t.description || 'No description')}</p><table>${[['Employee', t.assignee_name || 'Unassigned'], ['Project', t.project_name || '—'],
      ['Priority', t.priority], ['Due date', fmt(t.due_date)], ['Status', STATUS[t.status]], ['Created by', t.created_by_name || '—']].map(r => `<tr><td class="mini">${r[0]}</td><td>${esc(r[1])}</td></tr>`).join('')}</table>`);
  },
  async taskForm(id) {
    const task = id ? S.tasks.find(x => x.id === id) : null, p = await pickers(task);
    modal(task ? 'Edit Task' : 'Create Task', field('Title', `<input id="t-title" value="${esc(task ? task.title : '')}">`) +
      field('Description', `<textarea id="t-desc" rows="3">${esc(task ? task.description : '')}</textarea>`) + p.emp + p.proj +
      `<div class="two">${field('Priority', `<select id="t-prio">${['High', 'Medium', 'Low'].map(x => `<option ${(task ? task.priority : 'Medium') === x ? 'selected' : ''}>${x}</option>`).join('')}</select>`)}
      ${field('Due date', `<input id="t-due" type="date" value="${esc(task ? task.due_date || '' : '')}">`)}</div>` +
      (task ? field('Status', `<select id="t-status">${Object.entries(STATUS).map(([k, l]) => `<option value="${k}" ${task.status === k ? 'selected' : ''}>${l}</option>`).join('')}</select>`) : ''),
      async () => {
        const base = {title: val('t-title'), description: val('t-desc'), priority: val('t-prio'), due_date: val('t-due') || null};
        if (task) { await api(`/api/tasks/${id}`, 'PUT', {...base, status: val('t-status')}); await applyAssignment(id, task); toast('Task updated'); }
        else {
          const created = await api('/api/tasks', 'POST', {...base, category: 'Work', assigned_to: numOrNull('t-emp')});
          if (numOrNull('t-proj')) await api(`/api/task-board/${created.id}/project`, 'PATCH', {project_id: numOrNull('t-proj')});
          toast('Task created and assigned');
        }
      }, task ? 'Save changes' : 'Assign');
    A.hint();
  },
  async assign(id) {
    const task = S.tasks.find(x => x.id === id), p = await pickers(task);
    modal('Assign Task', `<div class="sub"><b>${esc(task.title)}</b></div>` + p.emp + p.proj,
      async () => { await applyAssignment(id, task); toast('Assignment updated'); }, 'Assign');
    A.hint();
  },
  hint() {
    const h = $('#t-hint'); if (!h) return;
    const p = S.projects.find(x => String(x.id) === val('t-proj')), e = val('t-emp');
    const person = S.people.find(x => String(x.id) === e);
    h.textContent = p && e && !p.member_ids.includes(Number(e)) ? `Heads up: ${person ? person.name : 'this person'} is not in ${p.name}'s team.` : '';
  },
  /* employees */
  empForm(id) {
    const e = id ? S.emps.find(x => x.id === id) : null;
    modal(e ? 'Edit Employee' : 'Add Employee', field('Full name', `<input id="e-name" value="${esc(e ? e.name : '')}">`) + field('Email', `<input id="e-email" type="email" value="${esc(e ? e.email : '')}">`) +
      `<div class="two">${field('Role', `<select id="e-role">${['EMPLOYEE', 'MANAGER', 'ADMIN'].map(r => `<option ${(e ? e.role : 'EMPLOYEE') === r ? 'selected' : ''}>${r}</option>`).join('')}</select>`)}
      ${field('Department', `<input id="e-dept" value="${esc(e ? e.department : '')}">`)}</div>` + field('Designation', `<input id="e-desig" value="${esc(e ? e.designation : '')}">`) +
      field(e ? 'New password (leave blank to keep)' : 'Password (min 8 characters)', '<input id="e-pass" type="password" autocomplete="new-password">'),
      async () => {
        const d = {name: val('e-name'), email: val('e-email'), role: val('e-role'), department: val('e-dept'), designation: val('e-desig')};
        if (val('e-pass') || !e) d.password = val('e-pass');
        await api(e ? `/api/employees/${id}` : '/api/employees', e ? 'PUT' : 'POST', d); toast(e ? 'Employee updated' : 'Employee added');
      });
  },
  async empView(id) {
    const e = await api(`/api/employees/${id}`);
    modal(e.name, `<table>${[['Email', e.email], ['Role', e.role], ['Department', e.department || '—'], ['Designation', e.designation || '—'],
      ['Status', e.is_active ? 'Active' : 'Deactivated'], ['Teams', e.teams.map(t => t.name).join(', ') || '—'], ['Open tasks', e.open_tasks]].map(r => `<tr><td class="mini">${r[0]}</td><td>${esc(r[1])}</td></tr>`).join('')}</table>`);
  },
  async toggleEmp(id, active) {
    if (!confirm(active ? 'Activate this employee?' : 'Deactivate this employee? They will not be able to log in.')) return;
    try { await api(`/api/employees/${id}/${active ? 'activate' : 'deactivate'}`, 'PATCH'); toast(active ? 'Employee activated' : 'Employee deactivated'); refresh(); } catch (e) { toast(e.message, true); }
  },
  /* teams */
  async teamForm() {
    const people = await api('/api/employees/options');
    modal('Create Team', field('Team name', '<input id="tm-name">') + field('Manager', `<select id="tm-mgr">${opts(people.filter(p => p.role !== 'EMPLOYEE'), '', '— No manager —')}</select>`) +
      field('Members (hold Ctrl / Cmd to pick several)', `<select id="tm-members" multiple size="6" style="width:100%">${opts(people, '')}</select>`),
      async () => { await api('/api/teams', 'POST', {name: val('tm-name'), manager_id: numOrNull('tm-mgr'), member_ids: [...$('#tm-members').selectedOptions].map(o => Number(o.value))}); toast('Team created'); });
  },
  async teamMgr(id, v) { try { await api(`/api/teams/${id}/manager`, 'PATCH', {manager_id: v ? Number(v) : null}); toast('Manager updated'); } catch (e) { toast(e.message, true); } refresh(); },
  async addMember(id) {
    const v = val('add-' + id); if (!v) return;
    try { await api(`/api/teams/${id}/members`, 'POST', {user_id: Number(v)}); toast('Member added'); } catch (e) { toast(e.message, true); } refresh();
  },
  async rmMember(t, u) { try { await api(`/api/teams/${t}/members/${u}`, 'DELETE'); toast('Member removed'); } catch (e) { toast(e.message, true); } refresh(); },
  async delTeam(id) { if (!confirm('Delete this team? Projects keep existing but lose their team.')) return; try { await api(`/api/teams/${id}`, 'DELETE'); toast('Team deleted'); } catch (e) { toast(e.message, true); } refresh(); },
  /* projects */
  async projForm(id) {
    const p = id ? S.projects.find(x => x.id === id) : null;
    const [teams, people] = await Promise.all([api('/api/teams'), api('/api/employees/options')]);
    modal(p ? 'Edit / Assign Project' : 'New Project', field('Project name', `<input id="p-name" value="${esc(p ? p.name : '')}">`) +
      field('Description', `<textarea id="p-desc" rows="3">${esc(p ? p.description : '')}</textarea>`) +
      `<div class="two">${field('Team', `<select id="p-team">${opts(teams, p && p.team_id, '— No team —')}</select>`)}${field('Manager', `<select id="p-mgr">${opts(people.filter(x => x.role !== 'EMPLOYEE'), p && p.manager_id, '— Use team manager —')}</select>`)}</div>
      <div class="two">${field('Start date', `<input id="p-start" type="date" value="${esc(p ? p.start_date || '' : '')}">`)}${field('End date', `<input id="p-end" type="date" value="${esc(p ? p.end_date || '' : '')}">`)}</div>` +
      field('Status', `<select id="p-status">${['active', 'on_hold', 'completed'].map(s => `<option value="${s}" ${(p ? p.status : 'active') === s ? 'selected' : ''}>${s.replace('_', ' ')}</option>`).join('')}</select>`),
      async () => {
        const d = {name: val('p-name'), description: val('p-desc'), status: val('p-status'), start_date: val('p-start') || null, end_date: val('p-end') || null};
        if (!p) { await api('/api/projects', 'POST', {...d, team_id: numOrNull('p-team'), manager_id: numOrNull('p-mgr')}); toast('Project created'); return; }
        await api(`/api/projects/${id}`, 'PUT', d);
        if (numOrNull('p-team') !== p.team_id) await api(`/api/projects/${id}/team`, 'PATCH', {team_id: numOrNull('p-team')});
        if (val('p-mgr') && numOrNull('p-mgr') !== p.manager_id) await api(`/api/projects/${id}/manager`, 'PATCH', {manager_id: numOrNull('p-mgr')});
        toast('Project updated');
      });
  },
  async projView(id) {
    const p = await api(`/api/projects/${id}`), m = p.team ? p.team.members : [], g = p.progress;
    const tree = [`Project: ${p.name}`, `Manager: ${p.manager ? p.manager.name : '—'}`, `Team: ${p.team_name || '—'}`,
      ...m.map((x, i) => ` ${i === m.length - 1 ? '└──' : '├──'} ${x.name}`)].join('\n');
    modal(p.name, `<p>${esc(p.description || '')}</p><pre class="tree">${esc(tree)}</pre><div style="margin-top:14px">${bar(g.percent)}
      <div class="mini" style="margin-top:6px">${g.completed} completed · ${g.in_progress} in progress · ${g.pending} assigned · ${g.percent}% done</div></div>`);
  },
};

(async () => {
  try { S.user = (await api('/api/me')).user; S.page = NAV[S.user.role][0][0]; } catch (e) { S.user = null; }
  render();
})();
