/*
 * Member 7 – Employee Productivity & Notifications (frontend module)
 *
 * This file is loaded by index.html AFTER app.js (defer order). It patches
 * the existing `state`, `featureDetails`, `visibleFeatures`, and the
 * main render/navigation logic to add the productivity pages for employees.
 *
 * Pages added: "productivity", "calendar", "week", "notifications"
 * Saved-filter UI is integrated into the tasks page for employees.
 */

"use strict";

// ---------------------------------------------------------------------------
// 1.  Extend app-level state
// ---------------------------------------------------------------------------
Object.assign(state, {
  notifications: [],
  unreadCount: 0,
  savedFilters: [],
  productivityData: null,
  weekData: null,
  calendarData: null,
  calendarYear: null,
  calendarMonth: null,
  notifLoaded: false,
  productivityLoaded: false,
});

// ---------------------------------------------------------------------------
// 2.  Register the new pages in featureDetails (employees see them via
//     visibleFeatures patch below)
// ---------------------------------------------------------------------------
featureDetails.productivity = {
  title: "My Productivity",
  description: "Your personal task summary and performance overview.",
  icon: "📊",
};
featureDetails.week = {
  title: "My Week",
  description: "Tasks assigned to you that are due this week.",
  icon: "📅",
};
featureDetails.calendar = {
  title: "Task Calendar",
  description: "All your tasks with due dates shown on a calendar.",
  icon: "🗓",
};
featureDetails.notifications = {
  title: "Notifications",
  description: "Assignment and deadline alerts for your tasks.",
  icon: "🔔",
};

// Patch visibleFeatures so employees see the productivity pages
const _originalVisibleFeatures = visibleFeatures;
window.visibleFeatures = function () {
  if (state.user?.role === "EMPLOYEE") {
    return [
      ["tasks", featureDetails.tasks],
      ["productivity", featureDetails.productivity],
      ["week", featureDetails.week],
      ["calendar", featureDetails.calendar],
      ["notifications", featureDetails.notifications],
    ];
  }
  return _originalVisibleFeatures();
};

// ---------------------------------------------------------------------------
// 3.  setPage: allow employees to navigate to productivity pages
// ---------------------------------------------------------------------------
const _originalSetPage = setPage;
window.setPage = function (page) {
  const productivityPages = new Set(["productivity", "week", "calendar", "notifications"]);
  if (state.user && state.user.role !== "ADMIN" && productivityPages.has(page)) {
    state.page = page;
    state.mobileNavOpen = false;
    state.search = "";
    state.statusFilter = "All";
    render();
    return;
  }
  _originalSetPage(page);
};

// ---------------------------------------------------------------------------
// 4.  API helpers
// ---------------------------------------------------------------------------
async function fetchProductivitySummary() {
  try {
    const data = await apiRequest("/api/productivity/summary");
    state.productivityData = data;
    state.productivityLoaded = true;
  } catch (e) {
    state.productivityData = null;
  }
}

async function fetchWeekData() {
  try {
    state.weekData = await apiRequest("/api/productivity/week");
  } catch (e) {
    state.weekData = null;
  }
}

async function fetchCalendarData() {
  const params = new URLSearchParams();
  if (state.calendarYear) params.set("year", state.calendarYear);
  if (state.calendarMonth) params.set("month", state.calendarMonth);
  const qs = params.toString() ? `?${params}` : "";
  try {
    state.calendarData = await apiRequest(`/api/productivity/calendar${qs}`);
  } catch (e) {
    state.calendarData = null;
  }
}

async function fetchNotifications() {
  try {
    const data = await apiRequest("/api/notifications");
    state.notifications = data.notifications || [];
    state.unreadCount = data.unreadCount || 0;
    state.notifLoaded = true;
  } catch (e) {
    state.notifications = [];
    state.unreadCount = 0;
  }
}

async function fetchSavedFilters() {
  try {
    const data = await apiRequest("/api/saved-filters");
    state.savedFilters = data.savedFilters || [];
  } catch (e) {
    state.savedFilters = [];
  }
}

// ---------------------------------------------------------------------------
// 5.  Page markup generators
// ---------------------------------------------------------------------------

function productivityPageMarkup() {
  const d = state.productivityData;
  if (!d) {
    return `<div class="prd-loading"><span class="spinner" aria-hidden="true"></span><p>Loading summary…</p></div>`;
  }
  const rate = d.completionRate ?? 0;
  const pc = d.priorityCounts || {};
  return `
    <div class="page-heading">
      <div>
        <span class="eyebrow">PRODUCTIVITY</span>
        <h1>My Productivity</h1>
        <p>Your personal task summary and performance overview.</p>
      </div>
      <span class="role-badge">${escapeHtml(state.user.role)}</span>
    </div>
    <section class="prd-stats-grid" aria-label="Productivity metrics">
      ${prdStat("Total tasks", d.totalTasks, "📋")}
      ${prdStat("Completed", d.completed, "✅")}
      ${prdStat("In progress", d.inProgress, "🔄")}
      ${prdStat("Not started", d.notStarted, "⭕")}
      ${prdStat("Overdue", d.overdueTasks, "⚠️")}
      ${prdStat("Due this week", d.upcomingDeadlines, "📅")}
    </section>
    <div class="prd-row">
      <section class="surface-card prd-card" aria-label="Completion rate">
        <div class="section-title-row section-title-tight"><h2>Completion rate</h2></div>
        <div class="prd-rate-wrap">
          <div class="prd-rate-circle" role="img" aria-label="${rate}% complete">
            <svg viewBox="0 0 36 36" class="prd-donut">
              <circle class="prd-donut-bg" cx="18" cy="18" r="15.9"/>
              <circle class="prd-donut-fill" cx="18" cy="18" r="15.9"
                stroke-dasharray="${rate} ${100 - rate}" stroke-dashoffset="25"/>
            </svg>
            <span class="prd-rate-label">${rate}%</span>
          </div>
          <div class="prd-rate-legend">
            <div><span class="prd-dot prd-dot-done"></span>Completed: ${d.completed}</div>
            <div><span class="prd-dot prd-dot-progress"></span>In progress: ${d.inProgress}</div>
            <div><span class="prd-dot prd-dot-new"></span>Not started: ${d.notStarted}</div>
          </div>
        </div>
      </section>
      <section class="surface-card prd-card" aria-label="Priority breakdown">
        <div class="section-title-row section-title-tight"><h2>Priority breakdown</h2></div>
        <div class="prd-priority-bars">
          ${prdPriorityBar("High", pc.High || 0, d.totalTasks, "priority-high")}
          ${prdPriorityBar("Medium", pc.Medium || 0, d.totalTasks, "priority-medium")}
          ${prdPriorityBar("Low", pc.Low || 0, d.totalTasks, "priority-low")}
        </div>
      </section>
    </div>`;
}

function prdStat(label, value, icon) {
  return `
    <div class="stat-card">
      <div class="stat-card-label">${escapeHtml(label)}<span class="stat-icon" aria-hidden="true">${icon}</span></div>
      <div class="stat-number" style="font-size:28px;font-weight:700;margin-top:12px;">${escapeHtml(String(value ?? 0))}</div>
    </div>`;
}

function prdPriorityBar(label, count, total, cls) {
  const pct = total ? Math.round((count / total) * 100) : 0;
  return `
    <div class="prd-bar-row">
      <span class="prd-bar-label ${cls}">${escapeHtml(label)}</span>
      <div class="prd-bar-track"><div class="prd-bar-fill ${cls}" style="width:${pct}%"></div></div>
      <span class="prd-bar-count">${count}</span>
    </div>`;
}

function weekPageMarkup() {
  const d = state.weekData;
  if (!d) {
    return `<div class="prd-loading"><span class="spinner" aria-hidden="true"></span><p>Loading week…</p></div>`;
  }
  const tasks = d.tasks || [];
  const fmt = (iso) => iso ? new Date(iso + "T00:00").toLocaleDateString(undefined, { weekday:"short", month:"short", day:"numeric" }) : "";
  return `
    <div class="page-heading">
      <div>
        <span class="eyebrow">MY WEEK</span>
        <h1>My Week</h1>
        <p>${escapeHtml(fmt(d.weekStart))} – ${escapeHtml(fmt(d.weekEnd))}</p>
      </div>
      <span class="role-badge">${escapeHtml(state.user.role)}</span>
    </div>
    <section class="surface-card feature-panel" aria-label="This week's tasks">
      <div class="section-title-row section-title-tight">
        <h2>Tasks due this week</h2>
        <span>${tasks.length} task${tasks.length !== 1 ? "s" : ""}</span>
      </div>
      ${tasks.length ? `
      <div class="table-wrap">
        <table class="data-table">
          <thead><tr>
            <th scope="col">Task</th>
            <th scope="col">Project</th>
            <th scope="col">Due date</th>
            <th scope="col">Priority</th>
            <th scope="col">Status</th>
          </tr></thead>
          <tbody>
            ${tasks.map(t => `<tr>
              <td><strong>${escapeHtml(t.name)}</strong></td>
              <td>${escapeHtml(t.projectName || "—")}</td>
              <td>${escapeHtml(t.dueDate || "—")}</td>
              <td><span class="priority-${escapeHtml(t.priority.toLowerCase())}">${escapeHtml(t.priority)}</span></td>
              <td><span class="status-badge ${t.status === "Completed" ? "status-good" : ""}">${escapeHtml(t.status)}</span></td>
            </tr>`).join("")}
          </tbody>
        </table>
      </div>` : `
      <div class="empty-state compact-empty">
        <span class="empty-state-icon" aria-hidden="true">📅</span>
        <h3>No tasks due this week</h3>
        <p>Enjoy the breathing room, or check the Task Calendar for upcoming work.</p>
      </div>`}
    </section>`;
}

function calendarPageMarkup() {
  const d = state.calendarData;
  if (!d) {
    return `<div class="prd-loading"><span class="spinner" aria-hidden="true"></span><p>Loading calendar…</p></div>`;
  }
  const now = new Date();
  const dispYear = state.calendarYear || now.getFullYear();
  const dispMonth = state.calendarMonth || (now.getMonth() + 1);
  const monthName = new Date(dispYear, dispMonth - 1, 1).toLocaleString(undefined, { month: "long", year: "numeric" });

  const entries = d.calendar || [];

  // Build day-indexed map for the month grid
  const tasksByDay = {};
  entries.forEach(e => {
    const day = parseInt(e.date.split("-")[2], 10);
    tasksByDay[day] = e.tasks;
  });

  // Calendar grid
  const daysInMonth = new Date(dispYear, dispMonth, 0).getDate();
  const firstDay = (new Date(dispYear, dispMonth - 1, 1).getDay() + 6) % 7; // Monday=0
  const cells = [];
  for (let i = 0; i < firstDay; i++) cells.push(`<div class="cal-cell cal-cell-empty"></div>`);
  const todayIso = new Date().toISOString().slice(0, 10);
  for (let day = 1; day <= daysInMonth; day++) {
    const iso = `${dispYear}-${String(dispMonth).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    const dayTasks = tasksByDay[day] || [];
    const isToday = iso === todayIso;
    cells.push(`
      <div class="cal-cell ${isToday ? "cal-cell-today" : ""}">
        <span class="cal-day-num">${day}</span>
        ${dayTasks.slice(0, 3).map(t => `
          <div class="cal-task-chip priority-${escapeHtml(t.priority.toLowerCase())}" title="${escapeHtml(t.name)}">
            ${escapeHtml(t.name.length > 18 ? t.name.slice(0, 17) + "…" : t.name)}
          </div>`).join("")}
        ${dayTasks.length > 3 ? `<div class="cal-task-chip cal-more">+${dayTasks.length - 3} more</div>` : ""}
      </div>`);
  }

  // Prev/next month
  const prevMonth = dispMonth === 1 ? 12 : dispMonth - 1;
  const prevYear = dispMonth === 1 ? dispYear - 1 : dispYear;
  const nextMonth = dispMonth === 12 ? 1 : dispMonth + 1;
  const nextYear = dispMonth === 12 ? dispYear + 1 : dispYear;

  return `
    <div class="page-heading">
      <div>
        <span class="eyebrow">CALENDAR</span>
        <h1>Task Calendar</h1>
        <p>All your tasks with due dates.</p>
      </div>
      <span class="role-badge">${escapeHtml(state.user.role)}</span>
    </div>
    <section class="surface-card feature-panel" aria-label="Task calendar">
      <div class="cal-nav">
        <button class="button button-quiet" type="button"
          data-action="cal-prev" data-year="${prevYear}" data-month="${prevMonth}">← Prev</button>
        <h2 class="cal-month-title">${escapeHtml(monthName)}</h2>
        <button class="button button-quiet" type="button"
          data-action="cal-next" data-year="${nextYear}" data-month="${nextMonth}">Next →</button>
      </div>
      <div class="cal-grid-header">
        ${["Mon","Tue","Wed","Thu","Fri","Sat","Sun"].map(d => `<div class="cal-head">${d}</div>`).join("")}
      </div>
      <div class="cal-grid">
        ${cells.join("")}
      </div>
      ${entries.length === 0 ? `<div class="empty-state compact-empty" style="margin-top:16px">
        <p>No tasks with due dates in this month.</p>
      </div>` : ""}
    </section>`;
}

function notificationsPageMarkup() {
  const notifs = state.notifications;
  const unread = state.unreadCount;
  return `
    <div class="page-heading">
      <div>
        <span class="eyebrow">NOTIFICATIONS</span>
        <h1>Notifications ${unread ? `<span class="notif-badge">${unread}</span>` : ""}</h1>
        <p>Assignment alerts and approaching-deadline reminders.</p>
      </div>
      <span class="role-badge">${escapeHtml(state.user.role)}</span>
    </div>
    <section class="surface-card feature-panel" aria-label="Notifications">
      <div class="section-title-row section-title-tight">
        <h2>${notifs.length} notification${notifs.length !== 1 ? "s" : ""}</h2>
        ${unread ? `<button class="text-button" type="button" data-action="notif-read-all">Mark all as read</button>` : ""}
      </div>
      ${notifs.length ? `<ul class="notif-list">
        ${notifs.map(n => `
          <li class="notif-item ${n.isRead ? "" : "notif-unread"}" data-notif-id="${n.id}">
            <span class="notif-kind-icon" aria-hidden="true">${n.kind === "deadline" ? "⏰" : "📌"}</span>
            <div class="notif-body">
              <p class="notif-msg">${escapeHtml(n.message)}</p>
              <small class="notif-meta">${escapeHtml(n.kind === "assignment" ? "Assignment" : "Deadline")} · ${escapeHtml(n.createdAt.slice(0, 10))}</small>
            </div>
            ${!n.isRead ? `<button class="table-action" type="button" data-action="notif-read" data-id="${n.id}" aria-label="Mark as read">✓</button>` : ""}
          </li>`).join("")}
      </ul>` : `
      <div class="empty-state compact-empty">
        <span class="empty-state-icon" aria-hidden="true">🔔</span>
        <h3>No notifications</h3>
        <p>You'll see assignment and deadline alerts here.</p>
      </div>`}
    </section>`;
}

// ---------------------------------------------------------------------------
// 6.  Saved-filter panel (shown inside the Tasks page for employees)
// ---------------------------------------------------------------------------
function savedFiltersPanel() {
  const filters = state.savedFilters;
  return `
    <section class="surface-card prd-card saved-filters-panel" aria-label="Saved filters" style="margin-top:16px">
      <div class="section-title-row section-title-tight">
        <h2>Saved filters</h2>
        <button class="text-button" type="button" data-action="save-current-filter">Save current filter</button>
      </div>
      ${filters.length ? `<ul class="saved-filter-list">
        ${filters.map(f => `
          <li class="saved-filter-item">
            <button class="text-button" type="button" data-action="apply-saved-filter"
              data-filter='${escapeHtml(JSON.stringify(f.filter))}'
              data-filter-name="${escapeHtml(f.name)}">
              ${escapeHtml(f.name)}
            </button>
            <button class="table-action danger" type="button" data-action="delete-saved-filter"
              data-id="${f.id}" aria-label="Delete ${escapeHtml(f.name)}">✕</button>
          </li>`).join("")}
      </ul>` : `<p class="muted-copy" style="margin:8px 0 0">No saved filters yet.</p>`}
    </section>`;
}

// ---------------------------------------------------------------------------
// 7.  Notification bell in topbar (patch mainContentMarkup)
// ---------------------------------------------------------------------------
const _originalMainContentMarkup = mainContentMarkup;
window.mainContentMarkup = function () {
  const html = _originalMainContentMarkup();
  if (!state.user || state.user.role !== "EMPLOYEE") return html;

  // Patch the topbar-right to insert a bell icon
  const badge = state.unreadCount > 0
    ? `<span class="notif-bell-badge" aria-hidden="true">${state.unreadCount}</span>` : "";
  const bell = `<div class="notif-bell-wrap">
    <button class="notif-bell-btn" type="button" data-page="notifications"
      aria-label="Notifications${state.unreadCount ? ` (${state.unreadCount} unread)` : ""}">
      🔔${badge}
    </button>
  </div>`;
  return html.replace(
    `<span class="welcome">Signed in as ${escapeHtml(state.user.name)}</span>`,
    `${bell}<span class="welcome">Signed in as ${escapeHtml(state.user.name)}</span>`
  );
};

// ---------------------------------------------------------------------------
// 8.  Patch render() to handle new pages + inject saved-filter panel
// ---------------------------------------------------------------------------
const _originalRender = render;
window.render = function () {
  if (!state.user) {
    _originalRender();
    return;
  }

  const productivityPages = new Set(["productivity", "week", "calendar", "notifications"]);
  if (productivityPages.has(state.page) && state.user.role === "EMPLOYEE") {
    // Build using the existing layout shell (sidebar + topbar) but swap content
    // We leverage mainContentMarkup's shell and swap just the inner content.
    app.innerHTML = buildProductivityShell(state.page);
  } else {
    _originalRender();
    // Inject saved-filter panel into the tasks page for employees
    if (state.user.role === "EMPLOYEE" && state.page === "tasks") {
      const content = document.getElementById("main");
      if (content) {
        const panel = document.createElement("div");
        panel.innerHTML = savedFiltersPanel();
        content.appendChild(panel.firstElementChild);
      }
    }
  }
};

function buildProductivityShell(page) {
  // Re-use the existing menuMarkup and topbar from the original code
  const icons = {
    dashboard: "⌂", employees: "♙", teams: "♧", projects: "▧", tasks: "✓",
    productivity: "📊", week: "📅", calendar: "🗓", notifications: "🔔",
  };
  const visFeatures = visibleFeatures();
  const items = visFeatures.map(([key, details]) => [key, details.title]);
  const title = featureDetails[page]?.title || "Workspace";

  const badge = state.unreadCount > 0
    ? `<span class="notif-bell-badge" aria-hidden="true">${state.unreadCount}</span>` : "";

  let pageContent = "";
  if (page === "productivity") pageContent = productivityPageMarkup();
  else if (page === "week") pageContent = weekPageMarkup();
  else if (page === "calendar") pageContent = calendarPageMarkup();
  else if (page === "notifications") pageContent = notificationsPageMarkup();

  return `
    <button class="mobile-scrim ${state.mobileNavOpen ? "is-visible" : ""}" type="button" data-action="close-nav" aria-label="Close navigation"></button>
    <div class="dashboard-shell">
      <aside class="sidebar ${state.mobileNavOpen ? "is-open" : ""}" aria-label="Main navigation">
        <a class="brand-lockup" href="#tasks" data-page="tasks" aria-label="Teamspace tasks">
          <span class="brand-mark" aria-hidden="true">T</span>
          <strong>teamspace</strong>
        </a>
        <div class="nav-label">Workspace</div>
        <nav class="side-nav">
          ${items.map(([key, label]) => `
            <button class="nav-link ${page === key ? "active" : ""}" type="button" data-page="${key}"
              ${page === key ? 'aria-current="page"' : ""}>
              <span class="nav-icon" aria-hidden="true">${icons[key] || "·"}</span>${escapeHtml(label)}
            </button>`).join("")}
        </nav>
        <div class="sidebar-spacer"></div>
        <div class="sidebar-user">
          <span class="avatar" aria-hidden="true">${escapeHtml(getInitials(state.user.name))}</span>
          <div class="user-meta">
            <strong>${escapeHtml(state.user.name)}</strong>
            <span>${escapeHtml(state.user.role.toLowerCase())}</span>
          </div>
          <button class="logout-icon" type="button" data-action="logout" aria-label="Sign out" title="Sign out">↪</button>
        </div>
      </aside>
      <div class="main-column">
        <header class="topbar">
          <div class="topbar-left">
            <button class="mobile-menu-button" type="button" data-action="toggle-nav"
              aria-expanded="${state.mobileNavOpen}" aria-label="Open navigation">☰</button>
            <span class="breadcrumb">Workspace&nbsp; / &nbsp;</span>
            <span class="topbar-title">${escapeHtml(title)}</span>
          </div>
          <div class="topbar-right">
            <div class="notif-bell-wrap">
              <button class="notif-bell-btn" type="button" data-page="notifications"
                aria-label="Notifications${state.unreadCount ? ` (${state.unreadCount} unread)` : ""}">
                🔔${badge}
              </button>
            </div>
            <span class="welcome">Signed in as ${escapeHtml(state.user.name)}</span>
            <span class="avatar" aria-hidden="true">${escapeHtml(getInitials(state.user.name))}</span>
          </div>
        </header>
        <main id="main" class="content">
          ${pageContent}
        </main>
      </div>
    </div>`;
}

// ---------------------------------------------------------------------------
// 9.  Event delegation for new actions
// ---------------------------------------------------------------------------
document.addEventListener("click", async (event) => {
  const btn = event.target.closest("[data-action]");
  if (!btn) return;
  const action = btn.dataset.action;

  if (action === "notif-read") {
    const id = Number(btn.dataset.id);
    try {
      await apiRequest(`/api/notifications/${id}/read`, { method: "POST" });
      const n = state.notifications.find(n => n.id === id);
      if (n) { n.isRead = true; state.unreadCount = Math.max(0, state.unreadCount - 1); }
      render();
    } catch (e) {
      showToast(e.message || "Could not mark notification as read.", "error");
    }
  } else if (action === "notif-read-all") {
    try {
      await apiRequest("/api/notifications/read-all", { method: "POST" });
      state.notifications.forEach(n => { n.isRead = true; });
      state.unreadCount = 0;
      render();
    } catch (e) {
      showToast(e.message || "Could not mark all as read.", "error");
    }
  } else if (action === "cal-prev" || action === "cal-next") {
    state.calendarYear = Number(btn.dataset.year);
    state.calendarMonth = Number(btn.dataset.month);
    state.calendarData = null;
    render();
    await fetchCalendarData();
    render();
  } else if (action === "apply-saved-filter") {
    let filter = {};
    try { filter = JSON.parse(btn.dataset.filter || "{}"); } catch { /* ignore */ }
    state.statusFilter = filter.status || "All";
    state.search = filter.search || "";
    state.page = "tasks";
    render();
    showToast(`Filter "${escapeHtml(btn.dataset.filterName || "")}" applied.`, "success");
  } else if (action === "delete-saved-filter") {
    const id = Number(btn.dataset.id);
    const f = state.savedFilters.find(f => f.id === id);
    if (!f || !window.confirm(`Delete saved filter "${f.name}"?`)) return;
    try {
      await apiRequest(`/api/saved-filters/${id}`, { method: "DELETE" });
      state.savedFilters = state.savedFilters.filter(f => f.id !== id);
      render();
      showToast("Saved filter deleted.", "success");
    } catch (e) {
      showToast(e.message || "Could not delete filter.", "error");
    }
  } else if (action === "save-current-filter") {
    const filterName = window.prompt("Name this filter:");
    if (!filterName || !filterName.trim()) return;
    const filter = {};
    if (state.statusFilter && state.statusFilter !== "All") filter.status = state.statusFilter;
    if (state.search && state.search.trim()) filter.search = state.search.trim();
    try {
      const data = await apiRequest("/api/saved-filters", {
        method: "POST",
        body: JSON.stringify({ name: filterName.trim(), filter }),
      });
      state.savedFilters.unshift(data.savedFilter);
      render();
      showToast(`Filter "${escapeHtml(filterName.trim())}" saved.`, "success");
    } catch (e) {
      showToast(e.message || "Could not save filter.", "error");
    }
  }
}, { capture: true });

// ---------------------------------------------------------------------------
// 10. Load productivity data when an employee logs in (patch restoreSession
//     and login flow via a MutationObserver / page-change hook)
// ---------------------------------------------------------------------------
async function loadProductivityData() {
  if (!state.user || state.user.role !== "EMPLOYEE") return;
  await Promise.all([
    fetchNotifications(),
    fetchSavedFilters(),
  ]);
}

// Patch render so the first time the user reaches a productivity page we
// auto-fetch the relevant data if it hasn't been loaded yet.
const _prdRender = window.render;
window.render = function () {
  _prdRender();

  if (!state.user || state.user.role !== "EMPLOYEE") return;

  if (state.page === "productivity" && !state.productivityLoaded) {
    state.productivityLoaded = true; // prevent double-fetch
    fetchProductivitySummary().then(() => _prdRender());
  }
  if (state.page === "week" && !state.weekData) {
    fetchWeekData().then(() => _prdRender());
  }
  if (state.page === "calendar" && !state.calendarData) {
    fetchCalendarData().then(() => _prdRender());
  }
  if (state.page === "notifications" && !state.notifLoaded) {
    // already handled in fetchNotifications seed; just reload on page open
    state.notifLoaded = true;
    fetchNotifications().then(() => _prdRender());
  }
};

// Hook into the app's restoreSession completion by observing state changes.
// We use a simple polling wait for state.user to be set, then load data.
(function waitForUser() {
  if (state.user) {
    loadProductivityData();
    return;
  }
  const id = setInterval(() => {
    if (state.user) {
      clearInterval(id);
      loadProductivityData();
    }
  }, 300);
})();
