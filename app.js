"use strict";

const app = document.querySelector("#app");
const toastRegion = document.querySelector("#toast-region");

const state = {
  user: null,
  page: "login",
  loginRole: "ADMIN",
  notice: null,
  mobileNavOpen: false,
  accessMessage: "",
  currentEmployeeId: null,
  modal: null,
  search: "",
  statusFilter: "All",

  taskView: "kanban",
  selectedTaskIds: new Set(),
  priorityFilter: "All",
  projectFilter: "All",
  activeTaskDetail: null,
  taskDetailComments: [],
  taskDetailActivities: [],

  departmentFilter: "All",
  employeeViewMode: "table", // "table" or "department"
  teamViewMode: "grid", // "grid" or "table"
  selectedProjectId: null,
  assigningTeamId: null,
  selectedMemberIds: new Set(),
  assignmentSearch: "",
  assignmentDeptFilter: "All",
  taskComments: [],
  taskAuditLogs: [],
  taskActivities: [],
  taskDetailTab: "comments",

};

const workspaceData = { employees: [], teams: [], projects: [], tasks: [] };

const featureDetails = {
  employees: {
    title: "Employee management",
    description: "Manage employee profiles, departments, and workspace access.",
    icon: "♙",
  },
  teams: {
    title: "Team management",
    description: "Organize people into teams, assign managers, and manage members.",
    icon: "♧",
  },
  projects: {
    title: "Project Management",
    description: "Track project ownership, milestones, status, and progress.",
    icon: "▧",
  },
  tasks: {
    title: "Tasks",
    description: "Review work items and their current status.",
    icon: "✓",
  },
};

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function apiRequest(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  headers.set("Accept", "application/json");

  let response;
  try {
    response = await fetch(path, {
      ...options,
      headers,
      credentials: "include",
    });
  } catch (error) {
    throw new ApiError("Could not reach the server. Check your connection and try again.");
  }

  const responseText = await response.text();
  let data = null;
  if (responseText) {
    try {
      data = JSON.parse(responseText);
    } catch {
      data = null;
    }
  }

  if (!response.ok) {
    const serverMessage = data && (data.error || data.message);
    const fallback = response.status === 401
      ? "Your session has expired. Please sign in again."
      : response.status === 403
        ? "You do not have permission to do that."
        : response.status === 501
          ? "This API route is not implemented by the Flask backend yet."
        : `The request failed (${response.status}). Please try again.`;
    throw new ApiError(typeof serverMessage === "string" ? serverMessage : fallback, response.status);
  }

  if (responseText && data === null) {
    throw new ApiError("The server returned an unexpected response. Please try again.", response.status);
  }

  return data;
}

async function loadWorkspaceData() {
  const data = await apiRequest("/api/workspace");
  for (const key of ["employees", "teams", "projects", "tasks"]) {
    if (!Array.isArray(data?.[key])) {
      throw new ApiError(`The server did not return a valid ${key} list.`);
    }
    workspaceData[key] = data[key];
  }
  state.currentEmployeeId = Number.isInteger(data.currentEmployeeId) ? data.currentEmployeeId : null;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

function getInitials(name) {
  const parts = String(name || "User").trim().split(/\s+/).filter(Boolean);
  return parts.slice(0, 2).map((part) => part[0].toUpperCase()).join("");
}

function normalizeRole(role) {
  return String(role || "").trim().toUpperCase();
}

function getUserFromResponse(data) {
  if (!data || typeof data !== "object") return null;
  const user = data.user && typeof data.user === "object" ? data.user : data;
  if (!user.email || !user.role) return null;
  return {
    id: user.id,
    name: user.name || user.email,
    email: user.email,
    role: normalizeRole(user.role),
  };
}

function showToast(message, kind = "info") {
  const toast = document.createElement("div");
  toast.className = `toast ${kind}`;
  toast.textContent = message;
  toastRegion.append(toast);
  window.setTimeout(() => toast.remove(), 4200);
}

function setPage(page, options = {}) {
  if (state.user && state.user.role !== "ADMIN" && page !== "tasks" && page !== "login") {
    state.page = "tasks";
  } else {
    state.page = page;
  }
  if (options.projectId !== undefined) {
    state.selectedProjectId = options.projectId;
  }
  state.mobileNavOpen = false;
  state.search = "";
  state.statusFilter = "All";

  state.selectedTaskIds.clear();
  state.priorityFilter = "All";
  state.projectFilter = "All";

  state.departmentFilter = "All";
 
  render();
}

function authMessageMarkup() {
  if (!state.notice) return "";
  return `<div class="form-message ${escapeHtml(state.notice.kind)}" role="status">${escapeHtml(state.notice.text)}</div>`;
}

function authPanelMarkup() {
  const signup = state.page === "signup";
  const title = signup
    ? state.loginRole === "ADMIN" ? "Create your admin account" : "Create your employee account"
    : state.loginRole === "ADMIN" ? "Admin Login" : "Employee Login";
  const subtitle = signup
    ? state.loginRole === "ADMIN"
      ? "Create an administrator account to manage the workspace."
      : "Set up your employee account to join your team's workspace."
    : state.loginRole === "ADMIN"
      ? "Sign in to manage employees, teams, projects, and tasks."
      : "Sign in to view your assigned tasks and update their status.";
  const fields = signup
    ? `
      <div class="form-field">
        <label for="full-name">Full name</label>
        <input id="full-name" name="name" type="text" autocomplete="name" placeholder="e.g. Alex Morgan" required maxlength="120">
      </div>
      <div class="form-field">
        <label for="email">Email address</label>
        <input id="email" name="email" type="email" autocomplete="email" placeholder="you@company.com" required>
      </div>
      <div class="form-field">
        <label for="password">Password</label>
        <div class="password-wrap">
          <input id="password" name="password" type="password" autocomplete="new-password" placeholder="At least 8 characters" minlength="8" required>
          <button class="password-toggle" type="button" data-toggle-password="password" aria-label="Show password">Show</button>
        </div>
      </div>
      <div class="form-field">
        <label for="confirm-password">Confirm password</label>
        <div class="password-wrap">
          <input id="confirm-password" name="confirmPassword" type="password" autocomplete="new-password" placeholder="Enter your password again" required>
          <button class="password-toggle" type="button" data-toggle-password="confirm-password" aria-label="Show confirm password">Show</button>
        </div>
      </div>`
    : `
      <div class="form-field">
        <label for="email">Email address</label>
        <input id="email" name="email" type="email" autocomplete="email" placeholder="you@company.com" required>
      </div>
      <div class="form-field">
        <label for="password">Password</label>
        <div class="password-wrap">
          <input id="password" name="password" type="password" autocomplete="current-password" placeholder="Enter your password" required>
          <button class="password-toggle" type="button" data-toggle-password="password" aria-label="Show password">Show</button>
        </div>
      </div>`;

  return `
    <main id="main" class="auth-page">
      <section class="auth-brand-panel" aria-label="About Teamspace">
        <a class="brand-lockup" href="#login" data-page="login" aria-label="Teamspace sign in">
          <span class="brand-mark" aria-hidden="true">T</span>
          <strong>teamspace</strong>
        </a>
        <div class="brand-copy">
          <span class="eyebrow">A better way to work together</span>
          <h1>Good work happens when teams connect.</h1>
          <p>Bring your people and projects together in one calm, focused workspace.</p>
        </div>
        <div class="brand-footer">Your team's work, all in one place.</div>
      </section>
      <section class="auth-form-side">
        <div class="auth-card">
          <span class="eyebrow">${signup ? "GET STARTED" : "YOUR WORKSPACE"}</span>
          <h2>${title}</h2>
          <p class="auth-subtitle">${subtitle}</p>
          ${signup ? "" : `<div class="login-role-switch" aria-label="Choose login type">
            <button class="login-role-button ${state.loginRole === "ADMIN" ? "active" : ""}" type="button" data-login-role="ADMIN" aria-pressed="${state.loginRole === "ADMIN"}">Admin Login</button>
            <button class="login-role-button ${state.loginRole === "EMPLOYEE" ? "active" : ""}" type="button" data-login-role="EMPLOYEE" aria-pressed="${state.loginRole === "EMPLOYEE"}">Employee Login</button>
          </div>`}
          ${authMessageMarkup()}
          <form id="auth-form" novalidate>
            ${fields}
            <button class="button button-primary auth-submit" type="submit">
              <span class="button-label">${signup ? "Create account" : "Sign in"}</span>
            </button>
          </form>
          <p class="auth-switch">${signup
            ? 'Already have an account? <a href="#login" data-page="login">Sign in</a>'
            : 'New to Teamspace? <a href="#signup" data-page="signup">Create an account</a>'}</p>
        </div>
      </section>
    </main>`;
}

function visibleFeatures() {
  if (state.user?.role !== "ADMIN") return [["tasks", featureDetails.tasks]];
  return Object.entries(featureDetails);
}

function canManage(entity) {
  return state.user?.role === "ADMIN";
}

function employeeById(id) {
  return workspaceData.employees.find((employee) => employee.id === Number(id));
}

function teamById(id) {
  return workspaceData.teams.find((team) => team.id === Number(id));
}

function projectById(id) {
  return workspaceData.projects.find((project) => project.id === Number(id));
}

function labelForEmployee(id) {
  if (state.user?.role === "EMPLOYEE" && Number(id) === state.currentEmployeeId) return "You";
  return employeeById(id)?.name || "Unassigned";
}

function labelForTeam(id) {
  return teamById(id)?.name || "No team";
}

function labelForProject(id) {
  return projectById(id)?.name || "No project";
}

function actionButton(action, id, label, kind = "") {
  return `<button class="table-action ${kind}" type="button" data-action="${action}" data-id="${escapeHtml(id)}">${escapeHtml(label)}</button>`;
}

function employeeOptions(selectedId = "", managerOnly = false) {
  const employees = workspaceData.employees.filter((employee) => employee.status === "Active"
    && (!managerOnly || ["ADMIN", "MANAGER"].includes(employee.role)));
  return `<option value="">${managerOnly ? "No manager" : "Unassigned"}</option>${employees.map((employee) => `
    <option value="${employee.id}" ${Number(selectedId) === employee.id ? "selected" : ""}>${escapeHtml(employee.name)}${managerOnly ? ` — ${escapeHtml(employee.role.toLowerCase())}` : ""}</option>`).join("")}`;
}

function teamOptions(selectedId = "") {
  return `<option value="">No team</option>${workspaceData.teams.map((team) => `
    <option value="${team.id}" ${Number(selectedId) === team.id ? "selected" : ""}>${escapeHtml(team.name)}</option>`).join("")}`;
}

function projectOptions(selectedId = "") {
  return `<option value="">No project</option>${workspaceData.projects.map((project) => `
    <option value="${project.id}" ${Number(selectedId) === project.id ? "selected" : ""}>${escapeHtml(project.name)}</option>`).join("")}`;
}

function employeeNameOptions(selectedId = "") {
  return `<option value="">Unassigned</option>${workspaceData.employees.filter((employee) => employee.status === "Active").map((employee) => `
    <option value="${employee.id}" ${Number(selectedId) === employee.id ? "selected" : ""}>${escapeHtml(employee.name)}</option>`).join("")}`;
}

function memberCheckboxes(selectedIds = []) {
  return workspaceData.employees.filter((employee) => employee.status === "Active").map((employee) => `
    <label class="check-option">
      <input type="checkbox" name="memberIds" value="${employee.id}" ${selectedIds.includes(employee.id) ? "checked" : ""}>
      <span>${escapeHtml(employee.name)} <small>${escapeHtml(employee.department)}</small></span>
    </label>`).join("");
}

function rowMarkup(cells, searchText) {
  return `<tr data-search-text="${escapeHtml(searchText.toLowerCase())}">${cells.map((cell) => `<td>${cell}</td>`).join("")}</tr>`;
}

async function openModal(entity, id = null, view = false) {
  state.modal = { entity, id: id === null ? null : Number(id), view };
  if (entity === "task" && view && id !== null) {
    state.taskDetailTab = state.taskDetailTab || "comments";
    render();
    await loadTaskDetails(Number(id));
  }
  render();
  document.querySelector(".modal-card input:not([type=checkbox]), .modal-card select, .modal-card textarea")?.focus();
}

function openTeamAssignmentModal(teamId) {
  const team = teamById(teamId);
  if (!team) return;
  state.assigningTeamId = Number(teamId);
  state.selectedMemberIds = new Set(team.memberIds || []);
  state.assignmentSearch = "";
  state.assignmentDeptFilter = "All";
  state.modal = { entity: "team-assignment", id: Number(teamId) };
  render();
}

function openQuickProgressModal(projectId) {
  const project = projectById(projectId);
  if (!project) return;
  state.modal = { entity: "project-progress", id: Number(projectId), currentProgress: project.progress };
  render();
  document.querySelector("#quick-progress-slider")?.focus();
}

function menuMarkup(activePage) {
  const icons = { dashboard: "⌂", employees: "♙", teams: "♧", projects: "▧", tasks: "✓" };
  const isAdmin = state.user.role === "ADMIN";
  const items = [
    ...(isAdmin ? [["dashboard", "Management Dashboard"]] : []),
    ...visibleFeatures().map(([key, details]) => [key, details.title]),
  ];
  const highlightedPage = activePage === "project-detail" ? "projects" : activePage;

  return `
    <button class="mobile-scrim ${state.mobileNavOpen ? "is-visible" : ""}" type="button" data-action="close-nav" aria-label="Close navigation"></button>
    <aside class="sidebar ${state.mobileNavOpen ? "is-open" : ""}" aria-label="Main navigation">
      <a class="brand-lockup" href="#${isAdmin ? "dashboard" : "tasks"}" data-page="${isAdmin ? "dashboard" : "tasks"}" aria-label="Teamspace ${isAdmin ? "dashboard" : "tasks"}">
        <span class="brand-mark" aria-hidden="true">T</span>
        <strong>teamspace</strong>
      </a>
      <div class="nav-label">Workspace</div>
      <nav class="side-nav">
        ${items.map(([key, label]) => `
          <button class="nav-link ${highlightedPage === key ? "active" : ""}" type="button" data-page="${key}" ${highlightedPage === key ? 'aria-current="page"' : ""}>
            <span class="nav-icon" aria-hidden="true">${icons[key]}</span>${escapeHtml(label)}
          </button>`).join("")}
      </nav>
      <div class="sidebar-spacer"></div>
      <div class="sidebar-user">
        <span class="avatar" aria-hidden="true">${escapeHtml(getInitials(state.user.name))}</span>
        <div class="user-meta">
          <strong>${escapeHtml(state.user.name)}</strong>
          <span>${escapeHtml(state.user.role.toLowerCase())}</span>
        </div>
        <button class="logout-icon" type="button" data-action="open-password-modal" aria-label="Change password" title="Change password">🔑</button>
        <button class="logout-icon" type="button" data-action="logout" aria-label="Sign out" title="Sign out">↪</button>
      </div>
    </aside>`;
}

function dashboardPageMarkup() {
  const activeTasks = workspaceData.tasks.filter((task) => task.status !== "Completed");
  const stats = [
    ["Employees", workspaceData.employees.filter((employee) => employee.status === "Active").length, "♙", "employees"],
    ["Teams", workspaceData.teams.length, "♧", "teams"],
    ["Projects", workspaceData.projects.length, "▧", "projects"],
    ["Open tasks", activeTasks.length, "✓", "tasks"],
  ];
  const projectPreview = workspaceData.projects.slice(0, 4);
  const taskPreview = workspaceData.tasks.slice(0, 4);
  const managementFeatures = visibleFeatures();
  const workflowIcons = { employees: "♙", teams: "♧", projects: "▧", tasks: "✓" };
  const workflowDescriptions = {
    employees: ["Manage your people", "Add, edit, view profiles, departments, and activation status."],
    teams: ["Organize your teams", "Create teams, assign managers, and manage team membership."],
    projects: ["Deliver projects", "Track project details, edit progress, and monitor tasks."],
    tasks: ["Track the work", "Assign tasks, set priorities, and update progress."],
  };

  return `
    <div class="page-heading">
      <div>
        <span class="eyebrow">WORKSPACE</span>
        <h1>Management Dashboard</h1>
        <p>Your team's people, projects, and progress in one place.</p>
      </div>
      <span class="role-badge">${escapeHtml(state.user.role)}</span>
    </div>
    <section class="welcome-panel" aria-label="Welcome">
      <div class="welcome-panel-content">
        <span class="eyebrow">YOUR WORKSPACE</span>
        <h2>Welcome back, ${escapeHtml(state.user.name.split(/\s+/)[0])}!</h2>
        <p>Choose an area below to get started.</p>
      </div>
      <button class="button" type="button" data-page="projects">Manage projects <span aria-hidden="true">→</span></button>
    </section>
    <div class="section-title-row">
      <h2>At a glance</h2>
      <span>Live data from your database</span>
    </div>
    <section class="stats-grid" aria-label="Workspace metrics">
      ${stats.map(([label, value, icon, page]) => `
        <button class="stat-card stat-card-button" type="button" data-page="${page}">
          <div class="stat-card-label">${escapeHtml(label)}<span class="stat-icon" aria-hidden="true">${icon}</span></div>
          <div class="stat-number">${escapeHtml(value)}</div>
        </button>`).join("")}
    </section>
    <div class="section-title-row">
      <h2>Management</h2>
      <span>Choose a workspace area</span>
    </div>
    <section class="management-workflow-grid" aria-label="Management areas">
      ${managementFeatures.map(([key]) => `
        <article class="workflow-card">
          <span class="workflow-icon ${key}" aria-hidden="true">${workflowIcons[key]}</span>
          <strong>${escapeHtml(featureDetails[key].title)}</strong>
          <span>${escapeHtml(workflowDescriptions[key][1])}</span>
          <div class="workflow-actions">
            <button class="text-button" type="button" data-page="${key}">Open section</button>
            <button class="button button-quiet workflow-add-button" type="button" data-action="create-record" data-entity="${key.slice(0, -1)}">+ Add ${key === "employees" ? "employee" : key === "teams" ? "team" : key === "projects" ? "project" : "task"}</button>
          </div>
        </article>`).join("")}
    </section>
    <section class="dashboard-bottom">
      <article class="surface-card">
        <div class="section-title-row section-title-tight"><h3>Recent projects</h3><button class="text-button" type="button" data-page="projects">View all</button></div>
        ${projectPreview.length ? `<div class="mini-project-list">
          ${projectPreview.map((project) => `
            <button class="mini-project" type="button" data-action="view-project-page" data-id="${project.id}">
              <span>${escapeHtml(project.name)}<small>${escapeHtml(labelForTeam(project.teamId))} · ${escapeHtml(project.status)}</small></span>
              <span class="progress-track"><span style="width:${Number(project.progress)}%"></span></span>
              <strong>${Number(project.progress)}%</strong>
            </button>`).join("")}
          </div>` : `<div class="empty-state compact-empty"><p>No projects yet.</p><button class="text-button" type="button" data-page="projects">Open project management</button></div>`}
      </article>
      <article class="surface-card">
        <div class="section-title-row section-title-tight"><h3>Task overview</h3><button class="text-button" type="button" data-page="tasks">View tasks</button></div>
        ${taskPreview.length ? `<div class="mini-task-list">
          ${taskPreview.map((task) => `
            <div class="mini-task">
              <span class="task-dot ${task.status === "Completed" ? "is-done" : ""}" aria-hidden="true"></span>
              <span class="mini-task-name">${escapeHtml(task.name)}</span>
              <span class="status-badge">${escapeHtml(task.status)}</span>
            </div>`).join("")}
          </div>` : `<div class="empty-state compact-empty"><p>No tasks yet.</p><button class="text-button" type="button" data-page="tasks">Open task management</button></div>`}
      </article>
    </section>`;
}



function kanbanCardMarkup(task) {
  const isSelected = state.selectedTaskIds.has(task.id);
  const isCompleted = task.status === "Completed";
  const today = new Date().toISOString().slice(0, 10);
  const isOverdue = !isCompleted && task.dueDate && task.dueDate < today;
  const assigneeName = labelForEmployee(task.assigneeId);
  const project = projectById(task.projectId);
  const projectName = task.projectName || project?.name || "";

  return `
    <article class="kanban-card ${isCompleted ? "is-completed" : ""} ${isSelected ? "is-selected" : ""}"
             draggable="true"
             data-task-id="${task.id}"
             data-search-text="${escapeHtml((task.name + " " + (task.description || "") + " " + projectName + " " + assigneeName + " " + task.priority).toLowerCase())}">
      <div class="kanban-card-top">
        <label class="card-checkbox-wrap" title="Select task for bulk action">
          <input type="checkbox" class="task-checkbox" data-action="toggle-select-task" data-id="${task.id}" ${isSelected ? "checked" : ""} aria-label="Select task ${escapeHtml(task.name)}">
        </label>
        <span class="priority-badge priority-${escapeHtml(task.priority.toLowerCase())}">${escapeHtml(task.priority)}</span>
        ${task.isRecurring ? `<span class="recurrence-badge" title="Recurring: ${escapeHtml(task.recurrenceInterval)}">🔁 ${escapeHtml(task.recurrenceInterval)}</span>` : ""}
        <div class="card-top-spacer"></div>
        <button class="card-quick-view" type="button" data-action="view-task" data-id="${task.id}" title="View details" aria-label="View task details">⋯</button>
      </div>
      <h4 class="kanban-card-title" data-action="view-task" data-id="${task.id}">${escapeHtml(task.name)}</h4>
      ${task.description ? `<p class="kanban-card-desc">${escapeHtml(task.description.length > 95 ? task.description.slice(0, 95) + "…" : task.description)}</p>` : ""}
      ${projectName ? `<div class="kanban-card-project"><span class="project-tag"><span class="tag-icon" aria-hidden="true">▧</span> ${escapeHtml(projectName)}</span></div>` : ""}
      <div class="kanban-card-footer">
        <div class="card-footer-left">
          ${task.dueDate ? `<span class="kanban-card-due ${isOverdue ? "is-overdue" : ""}" title="${isOverdue ? "Overdue!" : "Due date"}"><span aria-hidden="true">📅</span> ${escapeHtml(task.dueDate)}</span>` : ""}
          <span class="kanban-card-comments" data-action="view-task" data-id="${task.id}" title="${task.commentsCount || 0} comments"><span aria-hidden="true">💬</span> ${task.commentsCount || 0}</span>
        </div>
        <div class="card-footer-right">
          <span class="avatar avatar-sm" title="${escapeHtml(assigneeName)}">${escapeHtml(getInitials(assigneeName))}</span>
        </div>
      </div>
    </article>
  `;
}

function taskWorkspaceMarkup(details) {
  const canEdit = canManage("task");
  const q = state.search.trim().toLowerCase();

  const filteredTasks = workspaceData.tasks.filter((task) => {
    const proj = projectById(task.projectId);
    const projName = task.projectName || proj?.name || "";
    const empName = labelForEmployee(task.assigneeId);
    const searchBlob = `${task.name} ${task.description || ""} ${projName} ${empName} ${task.priority} ${task.status}`.toLowerCase();
    const matchesSearch = !q || searchBlob.includes(q);
    const matchesPriority = state.priorityFilter === "All" || task.priority === state.priorityFilter;
    const matchesProject = state.projectFilter === "All" || String(task.projectId) === state.projectFilter;
    const matchesStatus = state.statusFilter === "All" || task.status === state.statusFilter;
    return matchesSearch && matchesPriority && matchesProject && (state.taskView === "kanban" || matchesStatus);
  });

  const todoTasks = filteredTasks.filter((t) => t.status === "Not Started" || t.status === "To Do");
  const inProgressTasks = filteredTasks.filter((t) => t.status === "In Progress");
  const completedTasks = filteredTasks.filter((t) => t.status === "Completed");

  const allVisibleSelected = filteredTasks.length > 0 && filteredTasks.every((t) => state.selectedTaskIds.has(t.id));

  return `
    <div class="page-heading">
      <div>
        <span class="eyebrow">WORKSPACE</span>
        <h1>Tasks</h1>
        <p>Interactive Kanban board, task tracking, and work assignments.</p>
      </div>
      <span class="role-badge">${escapeHtml(state.user.role)}</span>
    </div>

    <section class="surface-card feature-panel">
      <div class="section-title-row section-title-tight">
        <div style="display: flex; align-items: center; gap: 12px; flex-wrap: wrap;">
          <h2>Task Workspace</h2>
          <span class="count-pill">${filteredTasks.length} task${filteredTasks.length === 1 ? "" : "s"}</span>
        </div>
        <div class="view-toggle" role="group" aria-label="Task view mode">
          <button class="view-toggle-btn ${state.taskView === "kanban" ? "active" : ""}" type="button" data-action="set-task-view" data-view="kanban" aria-pressed="${state.taskView === "kanban"}">
            <span aria-hidden="true">▦</span> Kanban Board
          </button>
          <button class="view-toggle-btn ${state.taskView === "list" ? "active" : ""}" type="button" data-action="set-task-view" data-view="list" aria-pressed="${state.taskView === "list"}">
            <span aria-hidden="true">☷</span> List Table
          </button>
        </div>
      </div>

      <div class="feature-toolbar">
        <div class="toolbar-filters">
          <input class="search-box" type="search" data-search="true" aria-label="Search tasks" placeholder="Search tasks, descriptions, assignees..." value="${escapeHtml(state.search)}">
          <select class="filter-select" aria-label="Filter by priority" data-action="filter-priority">
            <option value="All" ${state.priorityFilter === "All" ? "selected" : ""}>All priorities</option>
            <option value="High" ${state.priorityFilter === "High" ? "selected" : ""}>High priority</option>
            <option value="Medium" ${state.priorityFilter === "Medium" ? "selected" : ""}>Medium priority</option>
            <option value="Low" ${state.priorityFilter === "Low" ? "selected" : ""}>Low priority</option>
          </select>
          <select class="filter-select" aria-label="Filter by project" data-action="filter-project">
            <option value="All" ${state.projectFilter === "All" ? "selected" : ""}>All projects</option>
            ${workspaceData.projects.map((p) => `<option value="${p.id}" ${state.projectFilter === String(p.id) ? "selected" : ""}>${escapeHtml(p.name)}</option>`).join("")}
          </select>
          ${state.taskView === "list" ? `
            <select class="filter-select" aria-label="Filter by status" data-action="filter-status">
              <option value="All" ${state.statusFilter === "All" ? "selected" : ""}>All statuses</option>
              <option value="Not Started" ${state.statusFilter === "Not Started" ? "selected" : ""}>Not Started</option>
              <option value="In Progress" ${state.statusFilter === "In Progress" ? "selected" : ""}>In Progress</option>
              <option value="Completed" ${state.statusFilter === "Completed" ? "selected" : ""}>Completed</option>
            </select>
          ` : ""}
        </div>
        ${canEdit ? `<button class="button button-primary" type="button" data-action="create-record" data-entity="task">+ Add task</button>` : ""}
      </div>

      ${state.selectedTaskIds.size > 0 ? `
        <div class="bulk-actions-bar" role="toolbar" aria-label="Bulk actions toolbar">
          <div class="bulk-selection-info">
            <span class="bulk-count-pill">${state.selectedTaskIds.size}</span>
            <strong>task${state.selectedTaskIds.size === 1 ? "" : "s"} selected</strong>
          </div>
          <div class="bulk-action-buttons">
            <span class="bulk-label">Move to:</span>
            <button class="button button-sm button-quiet" type="button" data-action="bulk-status" data-status="Not Started">To Do</button>
            <button class="button button-sm button-quiet" type="button" data-action="bulk-status" data-status="In Progress">In Progress</button>
            <button class="button button-sm button-quiet" type="button" data-action="bulk-status" data-status="Completed">Completed</button>
            ${canEdit ? `
              <select class="bulk-assign-select" data-action="bulk-assign" aria-label="Reassign selected tasks">
                <option value="">Reassign to…</option>
                ${employeeNameOptions()}
              </select>
              <button class="button button-sm button-danger" type="button" data-action="bulk-delete">Delete</button>
            ` : ""}
            <button class="button button-sm button-quiet" type="button" data-action="clear-selection">Clear</button>
          </div>
        </div>
      ` : ""}

      ${state.taskView === "kanban" ? `
        <div class="kanban-board" role="region" aria-label="Kanban board">
          <div class="kanban-column" data-status-column="Not Started">
            <div class="kanban-column-header">
              <div class="kanban-column-title-group">
                <span class="kanban-status-dot status-todo" aria-hidden="true"></span>
                <h3>To Do</h3>
                <span class="kanban-column-count">${todoTasks.length}</span>
              </div>
              ${canEdit ? `<button class="kanban-quick-add" type="button" data-action="create-record" data-entity="task" title="Add task to To Do">+</button>` : ""}
            </div>
            <div class="kanban-column-body" data-status="Not Started" role="region" aria-label="To Do column">
              ${todoTasks.length ? todoTasks.map(kanbanCardMarkup).join("") : `<div class="kanban-empty"><span class="kanban-empty-icon">✓</span><p>No tasks to do</p></div>`}
            </div>
          </div>

          <div class="kanban-column" data-status-column="In Progress">
            <div class="kanban-column-header">
              <div class="kanban-column-title-group">
                <span class="kanban-status-dot status-inprogress" aria-hidden="true"></span>
                <h3>In Progress</h3>
                <span class="kanban-column-count">${inProgressTasks.length}</span>
              </div>
            </div>
            <div class="kanban-column-body" data-status="In Progress" role="region" aria-label="In Progress column">
              ${inProgressTasks.length ? inProgressTasks.map(kanbanCardMarkup).join("") : `<div class="kanban-empty"><span class="kanban-empty-icon">⏳</span><p>No tasks in progress</p></div>`}
            </div>
          </div>

          <div class="kanban-column" data-status-column="Completed">
            <div class="kanban-column-header">
              <div class="kanban-column-title-group">
                <span class="kanban-status-dot status-completed" aria-hidden="true"></span>
                <h3>Completed</h3>
                <span class="kanban-column-count">${completedTasks.length}</span>
              </div>
            </div>
            <div class="kanban-column-body" data-status="Completed" role="region" aria-label="Completed column">
              ${completedTasks.length ? completedTasks.map(kanbanCardMarkup).join("") : `<div class="kanban-empty"><span class="kanban-empty-icon">🎉</span><p>No completed tasks</p></div>`}
            </div>
          </div>
        </div>
      ` : `
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th scope="col" class="table-select-cell">
                  <input type="checkbox" data-action="toggle-select-all" ${allVisibleSelected ? "checked" : ""} aria-label="Select all visible tasks">
                </th>
                <th scope="col">Task</th>
                <th scope="col">Project</th>
                <th scope="col">Assignee</th>
                <th scope="col">Due date</th>
                <th scope="col">Priority</th>
                <th scope="col">Status</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody id="record-table">
              ${filteredTasks.map((task) => `
                <tr data-search-text="${escapeHtml((task.name + " " + (task.projectName || labelForProject(task.projectId)) + " " + labelForEmployee(task.assigneeId) + " " + task.priority + " " + task.status).toLowerCase())}" class="${state.selectedTaskIds.has(task.id) ? "is-selected-row" : ""}">
                  <td class="table-select-cell">
                    <input type="checkbox" data-action="toggle-select-task" data-id="${task.id}" ${state.selectedTaskIds.has(task.id) ? "checked" : ""} aria-label="Select ${escapeHtml(task.name)}">
                  </td>
                  <td>
                    <strong>${escapeHtml(task.name)}</strong>
                    ${task.isRecurring ? `<span class="recurrence-badge" title="Recurring: ${escapeHtml(task.recurrenceInterval)}">🔁 ${escapeHtml(task.recurrenceInterval)}</span>` : ""}
                    ${task.description ? `<small class="cell-description">${escapeHtml(task.description.length > 60 ? task.description.slice(0, 60) + "…" : task.description)}</small>` : ""}
                  </td>
                  <td>${escapeHtml(task.projectName || labelForProject(task.projectId))}</td>
                  <td>${escapeHtml(labelForEmployee(task.assigneeId))}</td>
                  <td>${escapeHtml(task.dueDate || "Not set")}</td>
                  <td><span class="priority-${escapeHtml(task.priority.toLowerCase())}">${escapeHtml(task.priority)}</span></td>
                  <td>
                    ${state.user.role === "EMPLOYEE" ? `
                      <select class="task-status-select" aria-label="Status for ${escapeHtml(task.name)}" data-task-status="${task.id}">
                        ${["Not Started", "In Progress", "Completed"].map((status) => `<option ${task.status === status ? "selected" : ""}>${status}</option>`).join("")}
                      </select>
                    ` : `<span class="status-badge ${task.status === "Completed" ? "status-good" : ""}">${escapeHtml(task.status)}</span>`}
                  </td>
                  <td>
                    <div class="row-actions">
                      <button class="table-action" type="button" data-action="view-task" data-id="${task.id}">View</button>
                      ${state.user.role === "EMPLOYEE" ? `
                        <button class="table-action" type="button" data-action="save-task-status" data-id="${task.id}">Save status</button>
                      ` : `
                        ${task.status !== "Completed" ? actionButton("complete-task", task.id, "Complete") : ""}
                        ${actionButton("edit-task", task.id, "Edit")}
                        ${actionButton("delete-task", task.id, "Delete", "danger")}
                      `}
                    </div>
                  </td>
                </tr>
              `).join("")}
            </tbody>
          </table>
          <div class="empty-state table-empty" ${filteredTasks.length ? "hidden" : ""}>
            <span class="empty-state-icon" aria-hidden="true">${details.icon}</span>
            <h3>${workspaceData.tasks.length ? "No matching tasks" : "No tasks yet"}</h3>
            <p>${workspaceData.tasks.length ? "Try another search, priority, or project filter." : canEdit ? "Create your first task to get started." : "There are no tasks to display yet."}</p>
          </div>
        </div>
      `}
    </section>

function projectDetailPageMarkup(projectId) {
  const project = projectById(projectId);
  if (!project) {
    return `
      <div class="page-heading">
        <div>
          <button class="back-link-btn" type="button" data-action="back-to-projects">← Back to Projects</button>
          <h1>Project not found</h1>
        </div>
      </div>
      <div class="surface-card empty-state">
        <p>This project may have been deleted.</p>
        <button class="button button-primary" type="button" data-action="back-to-projects">Back to Projects</button>
      </div>
    `;
  }

  const team = teamById(project.teamId);
  const manager = employeeById(project.managerId);
  const teamMembers = team ? team.memberIds.map(employeeById).filter(Boolean) : [];
  const projectTasks = workspaceData.tasks.filter((t) => t.projectId === project.id);
  const completedTasks = projectTasks.filter((t) => t.status === "Completed");
  const inProgressTasks = projectTasks.filter((t) => t.status === "In Progress");
  const notStartedTasks = projectTasks.filter((t) => t.status === "Not Started");
  const taskProgressPercent = projectTasks.length ? Math.round((completedTasks.length / projectTasks.length) * 100) : 0;
  const canEdit = canManage("project");

  return `
    <div class="project-detail-shell">
      <div class="project-nav-row">
        <button class="back-link-btn" type="button" data-action="back-to-projects">← Back to Projects</button>
        <div class="project-header-actions">
          ${canEdit ? `<button class="button button-quiet" type="button" data-action="edit-project" data-id="${project.id}">Edit Project</button>` : ""}
          ${canEdit ? `<button class="button button-danger" type="button" data-action="delete-project" data-id="${project.id}">Delete Project</button>` : ""}
        </div>
      </div>

      <header class="project-hero surface-card">
        <div class="project-hero-title">
          <span class="eyebrow">${escapeHtml(labelForTeam(project.teamId)).toUpperCase()}</span>
          <h1>${escapeHtml(project.name)}</h1>
          <p class="project-hero-desc">${escapeHtml(project.description || "No project description provided.")}</p>
        </div>
        <div class="project-hero-status">
          <span class="status-badge ${project.status === "On Track" ? "status-good" : project.status === "At Risk" ? "status-warn" : project.status === "Completed" ? "status-good" : ""}">${escapeHtml(project.status)}</span>
        </div>
      </header>

      <!-- Project Progress Editing Card -->
      <section class="surface-card project-progress-card" aria-label="Project Progress Editing">
        <div class="section-title-row section-title-tight">
          <div>
            <h3>Project Progress & Completion</h3>
            <span class="progress-sub">Directly adjust and update the completion percentage for this project</span>
          </div>
          <span class="progress-big-number">${Number(project.progress)}%</span>
        </div>

        <div class="progress-track big-track" aria-hidden="true">
          <span style="width: ${Number(project.progress)}%"></span>
        </div>

        ${canEdit ? `
          <form class="progress-editor-form" data-project-id="${project.id}" onsubmit="event.preventDefault();">
            <div class="progress-controls-row">
              <div class="slider-field">
                <label for="detail-slider">Completion slider: <strong id="slider-val-label">${Number(project.progress)}%</strong></label>
                <input id="detail-slider" type="range" min="0" max="100" value="${Number(project.progress)}" data-action="slide-detail-progress">
              </div>
              <div class="number-field">
                <label for="detail-number">Percentage</label>
                <div class="number-input-wrap">
                  <input id="detail-number" type="number" min="0" max="100" value="${Number(project.progress)}" data-action="input-detail-progress">
                  <span>%</span>
                </div>
              </div>
              <button class="button button-primary" type="button" data-action="save-detail-progress" data-id="${project.id}">Save Progress</button>
            </div>
            <div class="progress-presets">
              <span class="presets-label">Quick presets:</span>
              <button class="preset-btn" type="button" data-action="set-progress-preset" data-val="0">0%</button>
              <button class="preset-btn" type="button" data-action="set-progress-preset" data-val="25">25%</button>
              <button class="preset-btn" type="button" data-action="set-progress-preset" data-val="50">50%</button>
              <button class="preset-btn" type="button" data-action="set-progress-preset" data-val="75">75%</button>
              <button class="preset-btn" type="button" data-action="set-progress-preset" data-val="100">100%</button>
            </div>
          </form>
        ` : `
          <p class="muted-copy">Completion is currently set to ${Number(project.progress)}%.</p>
        `}

        <div class="progress-comparison-box">
          <span class="comp-icon" aria-hidden="true">📊</span>
          <div class="comp-text">
            <strong>Task completion tracker:</strong>
            <span>${completedTasks.length} of ${projectTasks.length} project tasks completed (${taskProgressPercent}%). Enter project completion progress above.</span>
          </div>
        </div>
      </section>

      <!-- Key Metadata Grid -->
      <section class="project-info-grid">
        <article class="surface-card meta-block">
          <span class="meta-block-label">Assigned Team</span>
          <strong>${escapeHtml(labelForTeam(project.teamId))}</strong>
          <span class="meta-block-sub">${team ? `${team.memberIds.length} members` : "No team assigned"}</span>
          ${team ? `<button class="text-button" type="button" data-action="view-team" data-id="${team.id}">View team details →</button>` : ""}
        </article>

        <article class="surface-card meta-block">
          <span class="meta-block-label">Project Manager</span>
          ${manager ? `
            <div class="manager-meta">
              <span class="avatar mini">${escapeHtml(getInitials(manager.name))}</span>
              <div>
                <strong>${escapeHtml(manager.name)}</strong>
                <span class="meta-block-sub">${escapeHtml(manager.title)} · ${escapeHtml(manager.department)}</span>
              </div>
            </div>
          ` : `<strong>Unassigned</strong><span class="meta-block-sub">No project manager designated</span>`}
        </article>

        <article class="surface-card meta-block">
          <span class="meta-block-label">Timeline & Dates</span>
          <div class="timeline-meta">
            <div><span>Start:</span> <strong>${escapeHtml(project.startDate || "Not set")}</strong></div>
            <div><span>Due:</span> <strong>${escapeHtml(project.dueDate || "Not set")}</strong></div>
          </div>
        </article>

        <article class="surface-card meta-block">
          <span class="meta-block-label">Project Status</span>
          ${canEdit ? `
            <div class="status-selector-wrap">
              <select class="filter-select" aria-label="Update project status" data-action="quick-change-status" data-id="${project.id}">
                ${["On Track", "In Progress", "At Risk", "Completed"].map((s) => `<option ${project.status === s ? "selected" : ""}>${s}</option>`).join("")}
              </select>
            </div>
          ` : `<strong>${escapeHtml(project.status)}</strong>`}
        </article>
      </section>

      <!-- Team Members on this Project -->
      <section class="surface-card">
        <div class="section-title-row section-title-tight">
          <h3>Team Members</h3>
          <span class="count-pill">${teamMembers.length} ${teamMembers.length === 1 ? "member" : "members"}</span>
        </div>
        ${teamMembers.length ? `
          <div class="project-team-grid">
            ${teamMembers.map((member) => `
              <div class="project-member-chip">
                <span class="avatar mini">${escapeHtml(getInitials(member.name))}</span>
                <div class="member-chip-info">
                  <strong>${escapeHtml(member.name)}</strong>
                  <small>${escapeHtml(member.title)} · ${escapeHtml(member.department)}</small>
                </div>
                <button class="table-action" type="button" data-action="view-employee" data-id="${member.id}">Profile</button>
              </div>
            `).join("")}
          </div>
        ` : `
          <p class="muted-copy">No team members assigned to this project yet.</p>
        `}
      </section>

      <!-- Project Tasks -->
      <section class="surface-card">
        <div class="section-title-row section-title-tight">
          <div>
            <h3>Project Tasks (${projectTasks.length})</h3>
            <span class="progress-sub">${completedTasks.length} Completed · ${inProgressTasks.length} In Progress · ${notStartedTasks.length} Not Started</span>
          </div>
          ${canEdit ? `<button class="button button-quiet" type="button" data-action="create-task-for-project" data-id="${project.id}">+ Add task</button>` : ""}
        </div>
        ${projectTasks.length ? `
          <div class="table-wrap">
            <table class="data-table">
              <thead><tr><th>Task</th><th>Assignee</th><th>Due Date</th><th>Priority</th><th>Status</th><th>Actions</th></tr></thead>
              <tbody>
                ${projectTasks.map((task) => `
                  <tr>
                    <td><strong>${escapeHtml(task.name)}</strong></td>
                    <td>${escapeHtml(labelForEmployee(task.assigneeId))}</td>
                    <td>${escapeHtml(task.dueDate || "Not set")}</td>
                    <td><span class="priority-${escapeHtml(task.priority.toLowerCase())}">${escapeHtml(task.priority)}</span></td>
                    <td><span class="status-badge ${task.status === "Completed" ? "status-good" : ""}">${escapeHtml(task.status)}</span></td>
                    <td>
                      <div class="row-actions">
                        ${canEdit && task.status !== "Completed" ? actionButton("complete-task", task.id, "Complete") : ""}
                        ${canEdit ? actionButton("edit-task", task.id, "Edit") : ""}
                        ${canEdit ? actionButton("delete-task", task.id, "Delete", "danger") : ""}
                      </div>
                    </td>
                  </tr>
                `).join("")}
              </tbody>
            </table>
          </div>
        ` : `
          <div class="empty-state compact-empty">
            <p>No tasks associated with this project yet.</p>
            ${canEdit ? `<button class="button button-primary" type="button" data-action="create-task-for-project" data-id="${project.id}">Create First Task</button>` : ""}
          </div>
        `}
      </section>
    </div>

  `;
}

function featurePageMarkup(key) {
  const details = featureDetails[key];
  if (!details || (state.user.role !== "ADMIN" && key !== "tasks")) {
    return `<div class="form-message error" role="alert">You do not have access to this workspace area.</div>`;
  }

  if (key === "tasks") {
    return taskWorkspaceMarkup(details);
  }

  const labels = {
    employees: "employee",
    teams: "team",
    projects: "project",
    tasks: "task",
  };
  const entity = key.slice(0, -1);
  const buttonLabel = labels[key];
  const canEdit = canManage(entity);

  // === EMPLOYEES PAGE ===
  if (key === "employees") {
    const departments = ["All", ...Array.from(new Set(workspaceData.employees.map((e) => e.department).filter(Boolean))).sort()];
    const filteredEmployees = workspaceData.employees.filter((emp) => {
      const matchesStatus = state.statusFilter === "All" || emp.status === state.statusFilter;
      const matchesDept = state.departmentFilter === "All" || emp.department === state.departmentFilter;
      const q = state.search.trim().toLowerCase();
      const matchesSearch = !q || `${emp.name} ${emp.email} ${emp.department} ${emp.title} ${emp.role} ${emp.status}`.toLowerCase().includes(q);
      return matchesStatus && matchesDept && matchesSearch;
    });

    // Grouping by department
    const deptGroups = {};
    for (const emp of filteredEmployees) {
      const dept = emp.department || "General";
      if (!deptGroups[dept]) deptGroups[dept] = [];
      deptGroups[dept].push(emp);
    }
    const deptEntries = Object.entries(deptGroups).sort(([a], [b]) => a.localeCompare(b));

    const tableRows = filteredEmployees.map((employee) => rowMarkup([
      `<div class="person-cell"><span class="avatar ${employee.status === "Inactive" ? "avatar-muted" : ""}">${escapeHtml(getInitials(employee.name))}</span><span><strong>${escapeHtml(employee.name)}</strong><small>${escapeHtml(employee.email)}</small></span></div>`,
      escapeHtml(employee.department),
      escapeHtml(employee.title),
      `<span class="status-badge">${escapeHtml(employee.role)}</span>`,
      `<span class="status-badge ${employee.status === "Active" ? "status-good" : "status-muted"}">${escapeHtml(employee.status)}</span>`,
      `<div class="row-actions">
        ${actionButton("view-employee", employee.id, "Profile")}
        ${canEdit ? actionButton("edit-employee", employee.id, "Edit") : ""}
        ${canEdit ? `<button class="table-action ${employee.status === "Active" ? "danger" : "success"}" type="button" data-action="toggle-employee" data-id="${employee.id}" title="${employee.status === "Active" ? "Deactivate employee" : "Activate employee"}">${employee.status === "Active" ? "Deactivate" : "Activate"}</button>` : ""}
      </div>`,
    ], `${employee.name} ${employee.email} ${employee.department} ${employee.title} ${employee.role} ${employee.status}`)).join("");

    return `
      <div class="page-heading">
        <div>
          <span class="eyebrow">WORKSPACE</span>
          <h1>${escapeHtml(details.title)}</h1>
          <p>${escapeHtml(details.description)}</p>
        </div>
        <span class="role-badge">${escapeHtml(state.user.role)}</span>
      </div>

      <section class="surface-card feature-panel">
        <div class="section-title-row section-title-tight">
          <div class="view-switch-row">
            <div class="view-switch" role="tablist" aria-label="Employee view mode">
              <button class="view-tab ${state.employeeViewMode === "table" ? "active" : ""}" type="button" data-action="set-employee-view" data-mode="table" role="tab" aria-selected="${state.employeeViewMode === "table"}">All Employees</button>
              <button class="view-tab ${state.employeeViewMode === "department" ? "active" : ""}" type="button" data-action="set-employee-view" data-mode="department" role="tab" aria-selected="${state.employeeViewMode === "department"}">By Department</button>
            </div>
            <span class="count-pill">${filteredEmployees.length} of ${workspaceData.employees.length} employees</span>
          </div>
          ${canEdit ? `<button class="button button-primary" type="button" data-action="create-record" data-entity="employee">+ Add employee</button>` : ""}
        </div>

        <div class="feature-toolbar">
          <div class="toolbar-filters">
            <input class="search-box" type="search" data-search="true" aria-label="Search employees" placeholder="Search employees by name, title, department…" value="${escapeHtml(state.search)}">
            <select class="filter-select" aria-label="Filter by department" data-action="filter-department">
              ${departments.map((d) => `<option value="${escapeHtml(d)}" ${state.departmentFilter === d ? "selected" : ""}>${escapeHtml(d === "All" ? "All Departments" : d)}</option>`).join("")}
            </select>
            <select class="filter-select" aria-label="Filter by status" data-action="filter-status">
              ${["All", "Active", "Inactive"].map((s) => `<option ${state.statusFilter === s ? "selected" : ""}>${escapeHtml(s === "All" ? "All Statuses" : s)}</option>`).join("")}
            </select>
          </div>
        </div>

        ${state.employeeViewMode === "department" ? `
          <div class="department-view-container">
            ${deptEntries.length ? deptEntries.map(([deptName, emps]) => {
              const activeCount = emps.filter((e) => e.status === "Active").length;
              const inactiveCount = emps.filter((e) => e.status === "Inactive").length;
              return `
                <div class="department-group-card surface-card">
                  <div class="department-group-header">
                    <div>
                      <h3 class="department-group-title">${escapeHtml(deptName)}</h3>
                      <span class="department-group-sub">${emps.length} members · ${activeCount} active, ${inactiveCount} inactive</span>
                    </div>
                  </div>
                  <div class="department-cards-grid">
                    ${emps.map((emp) => `
                      <div class="employee-card ${emp.status === "Inactive" ? "is-inactive" : ""}">
                        <div class="employee-card-top">
                          <span class="avatar ${emp.status === "Inactive" ? "avatar-muted" : ""}">${escapeHtml(getInitials(emp.name))}</span>
                          <div class="employee-card-info">
                            <strong>${escapeHtml(emp.name)}</strong>
                            <span>${escapeHtml(emp.title)}</span>
                            <small>${escapeHtml(emp.email)}</small>
                          </div>
                        </div>
                        <div class="employee-card-badges">
                          <span class="status-badge">${escapeHtml(emp.role)}</span>
                          <span class="status-badge ${emp.status === "Active" ? "status-good" : "status-muted"}">${escapeHtml(emp.status)}</span>
                        </div>
                        <div class="employee-card-actions">
                          <button class="table-action" type="button" data-action="view-employee" data-id="${emp.id}">Profile</button>
                          ${canEdit ? `<button class="table-action" type="button" data-action="edit-employee" data-id="${emp.id}">Edit</button>` : ""}
                          ${canEdit ? `<button class="table-action ${emp.status === "Active" ? "danger" : "success"}" type="button" data-action="toggle-employee" data-id="${emp.id}">${emp.status === "Active" ? "Deactivate" : "Activate"}</button>` : ""}
                        </div>
                      </div>
                    `).join("")}
                  </div>
                </div>
              `;
            }).join("") : `
              <div class="empty-state">
                <span class="empty-state-icon" aria-hidden="true">♙</span>
                <h3>No employees match the filters</h3>
                <p>Try clearing your search or changing the department filter.</p>
              </div>
            `}
          </div>
        ` : `
          <div class="table-wrap">
            <table class="data-table">
              <thead><tr><th scope="col">Employee</th><th scope="col">Department</th><th scope="col">Job Title</th><th scope="col">Role</th><th scope="col">Status</th><th scope="col">Actions</th></tr></thead>
              <tbody id="record-table">${tableRows}</tbody>
            </table>
            <div class="empty-state table-empty" ${tableRows ? "hidden" : ""}>
              <span class="empty-state-icon" aria-hidden="true">♙</span>
              <h3>No matching employees</h3>
              <p>Try another search or status/department filter.</p>
            </div>
          </div>
        `}
      </section>
    `;
  }

  // === TEAMS PAGE ===
  if (key === "teams") {
    const q = state.search.trim().toLowerCase();
    const filteredTeams = workspaceData.teams.filter((team) => {
      if (!q) return true;
      const managerName = labelForEmployee(team.managerId);
      const memberNames = team.memberIds.map(labelForEmployee).join(" ");
      return `${team.name} ${team.description} ${managerName} ${memberNames}`.toLowerCase().includes(q);
    });

    const tableRows = filteredTeams.map((team) => rowMarkup([
      `<strong>${escapeHtml(team.name)}</strong><small class="cell-description">${escapeHtml(team.description)}</small>`,
      escapeHtml(labelForEmployee(team.managerId)),
      `<span class="count-pill">${team.memberIds.length} ${team.memberIds.length === 1 ? "member" : "members"}</span>`,
      `<div class="row-actions">
        ${actionButton("view-team", team.id, "View")}
        ${canEdit ? `<button class="table-action button-accent" type="button" data-action="assign-team-members" data-id="${team.id}">Assign Members</button>` : ""}
        ${canEdit ? actionButton("edit-team", team.id, "Edit") : ""}
        ${canEdit ? actionButton("delete-team", team.id, "Delete", "danger") : ""}
      </div>`,
    ], `${team.name} ${team.description} ${labelForEmployee(team.managerId)} ${team.memberIds.map(labelForEmployee).join(" ")}`)).join("");

    return `
      <div class="page-heading">
        <div>
          <span class="eyebrow">WORKSPACE</span>
          <h1>${escapeHtml(details.title)}</h1>
          <p>${escapeHtml(details.description)}</p>
        </div>
        <span class="role-badge">${escapeHtml(state.user.role)}</span>
      </div>

      <section class="surface-card feature-panel">
        <div class="section-title-row section-title-tight">
          <div class="view-switch-row">
            <div class="view-switch" role="tablist" aria-label="Team view mode">
              <button class="view-tab ${state.teamViewMode === "grid" ? "active" : ""}" type="button" data-action="set-team-view" data-mode="grid" role="tab" aria-selected="${state.teamViewMode === "grid"}">Team Cards</button>
              <button class="view-tab ${state.teamViewMode === "table" ? "active" : ""}" type="button" data-action="set-team-view" data-mode="table" role="tab" aria-selected="${state.teamViewMode === "table"}">Table View</button>
            </div>
            <span class="count-pill">${filteredTeams.length} of ${workspaceData.teams.length} teams</span>
          </div>
          ${canEdit ? `<button class="button button-primary" type="button" data-action="create-record" data-entity="team">+ Add team</button>` : ""}
        </div>

        <div class="feature-toolbar">
          <div class="toolbar-filters">
            <input class="search-box" type="search" data-search="true" aria-label="Search teams" placeholder="Search teams by name, description, manager, or member…" value="${escapeHtml(state.search)}">
          </div>
        </div>

        ${state.teamViewMode === "grid" ? `
          <div class="team-cards-grid">
            ${filteredTeams.length ? filteredTeams.map((team) => {
              const manager = employeeById(team.managerId);
              const members = team.memberIds.map(employeeById).filter(Boolean);
              const teamProjects = workspaceData.projects.filter((p) => p.teamId === team.id);
              return `
                <div class="team-card surface-card">
                  <div class="team-card-header">
                    <div>
                      <h3 class="team-card-title">${escapeHtml(team.name)}</h3>
                      <p class="team-card-desc">${escapeHtml(team.description || "No description provided.")}</p>
                    </div>
                  </div>
                  <div class="team-card-meta">
                    <div class="team-meta-row">
                      <span class="team-meta-label">Manager:</span>
                      <strong>${manager ? `${escapeHtml(manager.name)} <small>(${escapeHtml(manager.department)})</small>` : "No manager assigned"}</strong>
                    </div>
                    <div class="team-meta-row">
                      <span class="team-meta-label">Members (${members.length}):</span>
                      <div class="member-avatar-stack">
                        ${members.slice(0, 6).map((m) => `<span class="avatar mini" title="${escapeHtml(m.name)}">${escapeHtml(getInitials(m.name))}</span>`).join("")}
                        ${members.length > 6 ? `<span class="count-pill">+${members.length - 6}</span>` : ""}
                        ${members.length === 0 ? `<span class="muted-copy">No members assigned</span>` : ""}
                      </div>
                    </div>
                    ${teamProjects.length ? `
                      <div class="team-meta-row">
                        <span class="team-meta-label">Active projects (${teamProjects.length}):</span>
                        <div class="team-project-pills">
                          ${teamProjects.map((p) => `<span class="project-pill">${escapeHtml(p.name)} (${p.progress}%)</span>`).join("")}
                        </div>
                      </div>
                    ` : ""}
                  </div>
                  <div class="team-card-actions">
                    <button class="table-action" type="button" data-action="view-team" data-id="${team.id}">View Details</button>
                    ${canEdit ? `<button class="table-action button-accent" type="button" data-action="assign-team-members" data-id="${team.id}">Assign Members</button>` : ""}
                    ${canEdit ? `<button class="table-action" type="button" data-action="edit-team" data-id="${team.id}">Edit</button>` : ""}
                    ${canEdit ? `<button class="table-action danger" type="button" data-action="delete-team" data-id="${team.id}">Delete</button>` : ""}
                  </div>
                </div>
              `;
            }).join("") : `
              <div class="empty-state">
                <span class="empty-state-icon" aria-hidden="true">♧</span>
                <h3>No teams match your search</h3>
                <p>Try searching with another keyword or create a new team.</p>
              </div>
            `}
          </div>
        ` : `
          <div class="table-wrap">
            <table class="data-table">
              <thead><tr><th scope="col">Team</th><th scope="col">Manager</th><th scope="col">Members</th><th scope="col">Actions</th></tr></thead>
              <tbody id="record-table">${tableRows}</tbody>
            </table>
            <div class="empty-state table-empty" ${tableRows ? "hidden" : ""}>
              <span class="empty-state-icon" aria-hidden="true">♧</span>
              <h3>No matching teams</h3>
              <p>Try another search or add a team.</p>
            </div>
          </div>
        `}
      </section>
    `;
  }

  // === PROJECTS PAGE ===
  if (key === "projects") {
    const q = state.search.trim().toLowerCase();
    const filteredProjects = workspaceData.projects.filter((project) => {
      const matchesStatus = state.statusFilter === "All" || project.status === state.statusFilter;
      const teamName = labelForTeam(project.teamId);
      const matchesSearch = !q || `${project.name} ${project.description} ${teamName} ${project.status}`.toLowerCase().includes(q);
      return matchesStatus && matchesSearch;
    });

    const rows = filteredProjects.map((project) => rowMarkup([
      `<a class="project-title-link" href="#project-detail" data-action="view-project-page" data-id="${project.id}"><strong>${escapeHtml(project.name)}</strong></a><small class="cell-description">${escapeHtml(project.description)}</small>`,
      escapeHtml(labelForTeam(project.teamId)),
      escapeHtml(project.dueDate || "Not set"),
      `<div class="table-progress">
        <span class="progress-track"><span style="width:${Number(project.progress)}%"></span></span>
        <strong>${Number(project.progress)}%</strong>
        ${canEdit ? `<button class="quick-edit-btn" type="button" data-action="quick-edit-progress" data-id="${project.id}" title="Edit completion progress" aria-label="Edit progress for ${escapeHtml(project.name)}">✎</button>` : ""}
      </div>`,
      `<span class="status-badge ${project.status === "On Track" || project.status === "Completed" ? "status-good" : project.status === "At Risk" ? "status-warn" : ""}">${escapeHtml(project.status)}</span>`,
      `<div class="row-actions">
        <button class="table-action button-primary-quiet" type="button" data-action="view-project-page" data-id="${project.id}">View Details</button>
        ${canEdit ? actionButton("edit-project", project.id, "Edit") : ""}
        ${canEdit ? actionButton("delete-project", project.id, "Delete", "danger") : ""}
      </div>`,
    ], `${project.name} ${project.description} ${labelForTeam(project.teamId)} ${project.status}`)).join("");

    return `
      <div class="page-heading">
        <div>
          <span class="eyebrow">WORKSPACE</span>
          <h1>${escapeHtml(details.title)}</h1>
          <p>${escapeHtml(details.description)}</p>
        </div>
        <span class="role-badge">${escapeHtml(state.user.role)}</span>
      </div>

      <section class="surface-card feature-panel">
        <div class="section-title-row section-title-tight">
          <h2>${escapeHtml(details.title)}</h2>
          <span>${filteredProjects.length} of ${workspaceData.projects.length} projects</span>
        </div>

        <div class="feature-toolbar">
          <div class="toolbar-filters">
            <input class="search-box" type="search" data-search="true" aria-label="Search projects" placeholder="Search projects by name, description, team…" value="${escapeHtml(state.search)}">
            <select class="filter-select" aria-label="Filter by status" data-action="filter-status">
              ${["All", "On Track", "In Progress", "At Risk", "Completed"].map((s) => `<option ${state.statusFilter === s ? "selected" : ""}>${escapeHtml(s)}</option>`).join("")}
            </select>
          </div>
          ${canEdit ? `<button class="button button-primary" type="button" data-action="create-record" data-entity="project">+ Add project</button>` : ""}
        </div>

        <div class="table-wrap">
          <table class="data-table">
            <thead><tr><th scope="col">Project</th><th scope="col">Team</th><th scope="col">Due date</th><th scope="col">Progress</th><th scope="col">Status</th><th scope="col">Actions</th></tr></thead>
            <tbody id="record-table">${rows}</tbody>
          </table>
          <div class="empty-state table-empty" ${rows ? "hidden" : ""}>
            <span class="empty-state-icon" aria-hidden="true">▧</span>
            <h3>No matching projects</h3>
            <p>Try another search or status filter.</p>
          </div>
        </div>
      </section>
    `;
  }

  


  // === TASKS PAGE ===
  const q = state.search.trim().toLowerCase();
  const filteredTasks = workspaceData.tasks.filter((task) => {
    const matchesStatus = state.statusFilter === "All" || task.status === state.statusFilter;
    const projName = task.projectName || labelForProject(task.projectId);
    const assigneeName = labelForEmployee(task.assigneeId);
    const matchesSearch = !q || `${task.name} ${projName} ${assigneeName} ${task.priority} ${task.status}`.toLowerCase().includes(q);
    return matchesStatus && matchesSearch;
  });

  const headings = ["Task", "Project", "Assignee", "Due date", "Priority", "Status", "Actions"];
  const rows = filteredTasks.map((task) => rowMarkup([
    `<strong>${escapeHtml(task.name)}</strong>`,
    escapeHtml(task.projectName || labelForProject(task.projectId)),
    escapeHtml(labelForEmployee(task.assigneeId)),
    escapeHtml(task.dueDate || "Not set"),
    `<span class="priority-${escapeHtml(task.priority.toLowerCase())}">${escapeHtml(task.priority)}</span>`,
    `${state.user.role === "EMPLOYEE" ? `<select class="task-status-select" aria-label="Status for ${escapeHtml(task.name)}" data-task-status="${task.id}">${["Not Started", "In Progress", "Completed"].map((status) => `<option ${task.status === status ? "selected" : ""}>${status}</option>`).join("")}</select>` : `<span class="status-badge ${task.status === "Completed" ? "status-good" : ""}">${escapeHtml(task.status)}</span>`}`,
    `<div class="row-actions">${state.user.role === "EMPLOYEE" ? `<button class="table-action" type="button" data-action="save-task-status" data-id="${task.id}">Save status</button>` : `${task.status !== "Completed" ? actionButton("complete-task", task.id, "Complete") : ""}${actionButton("edit-task", task.id, "Edit")}${actionButton("delete-task", task.id, "Delete", "danger")}`}</div>`,
  ], `${task.name} ${task.projectName || labelForProject(task.projectId)} ${labelForEmployee(task.assigneeId)} ${task.priority} ${task.status}`)).join("");

  return `
    <div class="page-heading">
      <div>
        <span class="eyebrow">WORKSPACE</span>
        <h1>${escapeHtml(details.title)}</h1>
        <p>${escapeHtml(details.description)}</p>
      </div>
      <span class="role-badge">${escapeHtml(state.user.role)}</span>
    </div>
    <section class="surface-card feature-panel">
      <div class="section-title-row section-title-tight">
        <h2>${escapeHtml(details.title)}</h2>
        <span>${filteredTasks.length} ${buttonLabel}${filteredTasks.length === 1 ? "" : "s"}</span>
      </div>
      <div class="feature-toolbar">
        <div class="toolbar-filters">
          <input class="search-box" type="search" data-search="true" aria-label="Search ${escapeHtml(details.title.toLowerCase())}" placeholder="Search ${escapeHtml(details.title.toLowerCase())}" value="${escapeHtml(state.search)}">
          <select class="filter-select" aria-label="Filter by status" data-action="filter-status">
            ${["All", "Not Started", "In Progress", "Completed"].map((item) => `<option ${state.statusFilter === item ? "selected" : ""}>${escapeHtml(item)}</option>`).join("")}
          </select>
        </div>
        ${canEdit ? `<button class="button button-primary" type="button" data-action="create-record" data-entity="${entity}">+ Add ${buttonLabel}</button>` : ""}
      </div>
      <div class="table-wrap">
        <table class="data-table">
          <thead><tr>${headings.map((heading) => `<th scope="col">${escapeHtml(heading)}</th>`).join("")}</tr></thead>
          <tbody id="record-table">${rows}</tbody>
        </table>
        <div class="empty-state table-empty" ${rows ? "hidden" : ""}>
          <span class="empty-state-icon" aria-hidden="true">${details.icon}</span>
          <h3>No matching records</h3>
          <p>Try another search or status filter.</p>
        </div>
      </div>
    </section>`;
}

function fieldMarkup(label, name, value = "", type = "text", attributes = "") {
  return `<div class="form-field"><label for="modal-${name}">${escapeHtml(label)}</label><input id="modal-${name}" name="${escapeHtml(name)}" type="${escapeHtml(type)}" value="${escapeHtml(value)}" ${attributes}></div>`;
}

function selectFieldMarkup(label, name, options) {
  return `<div class="form-field"><label for="modal-${name}">${escapeHtml(label)}</label><select id="modal-${name}" name="${escapeHtml(name)}">${options}</select></div>`;
}

function modalFormFields(entity, record = {}) {
  if (entity === "employee") {
    return `
      <div class="form-grid">
        ${fieldMarkup("Full name", "name", record.name || "", "text", 'required maxlength="100"')}
        ${fieldMarkup("Email", "email", record.email || "", "email", 'required')}
        ${fieldMarkup("Department", "department", record.department || "", "text", 'required')}
        ${fieldMarkup("Job title", "title", record.title || "", "text", 'required')}
        ${selectFieldMarkup("Role", "role", ["EMPLOYEE", "MANAGER", "ADMIN"].map((role) => `<option ${record.role === role ? "selected" : ""}>${role}</option>`).join(""))}
        ${selectFieldMarkup("Status", "status", ["Active", "Inactive"].map((status) => `<option ${record.status === status ? "selected" : ""}>${status}</option>`).join(""))}
        ${fieldMarkup("Start date", "startDate", record.startDate || "", "date")}
      </div>`;
  }
  if (entity === "team") {
    return `
      ${fieldMarkup("Team name", "name", record.name || "", "text", 'required maxlength="100"')}
      <div class="form-field"><label for="modal-description">Description</label><textarea id="modal-description" name="description" rows="3">${escapeHtml(record.description || "")}</textarea></div>
      ${selectFieldMarkup("Manager", "managerId", employeeOptions(record.managerId, true))}
      <fieldset class="member-fieldset"><legend>Team members</legend><div class="member-picker">${memberCheckboxes(record.memberIds || [])}</div></fieldset>`;
  }
  if (entity === "project") {
    return `
      <div class="form-grid">
        ${fieldMarkup("Project name", "name", record.name || "", "text", 'required maxlength="120"')}
        ${selectFieldMarkup("Team", "teamId", teamOptions(record.teamId))}
        <div class="form-field form-field-full"><label for="modal-description">Description</label><textarea id="modal-description" name="description" rows="3">${escapeHtml(record.description || "")}</textarea></div>
        ${selectFieldMarkup("Project manager", "managerId", employeeOptions(record.managerId, true))}
        ${selectFieldMarkup("Status", "status", ["On Track", "In Progress", "At Risk", "Completed"].map((status) => `<option ${record.status === status ? "selected" : ""}>${status}</option>`).join(""))}
        ${fieldMarkup("Start date", "startDate", record.startDate || "", "date")}
        ${fieldMarkup("Due date", "dueDate", record.dueDate || "", "date")}
        <div class="form-field form-field-full">
          <label for="modal-progress">Completion (${Number(record.progress ?? 0)}%)</label>
          <div class="modal-slider-wrap">
            <input id="modal-progress" name="progress" type="range" min="0" max="100" value="${record.progress ?? 0}" oninput="document.getElementById('modal-progress-val').value = this.value">
            <input id="modal-progress-val" type="number" min="0" max="100" value="${record.progress ?? 0}" oninput="document.getElementById('modal-progress').value = this.value" style="width: 70px;">
          </div>
        </div>
      </div>`;
  }
  return `
    <div class="form-grid">
      ${fieldMarkup("Task name", "name", record.name || "", "text", 'required maxlength="140"')}
      ${selectFieldMarkup("Project", "projectId", projectOptions(record.projectId))}
      ${selectFieldMarkup("Assignee", "assigneeId", employeeNameOptions(record.assigneeId))}
      ${fieldMarkup("Due date", "dueDate", record.dueDate || "", "date")}
      ${selectFieldMarkup("Priority", "priority", ["Low", "Medium", "High"].map((priority) => `<option ${record.priority === priority ? "selected" : ""}>${priority}</option>`).join(""))}
      ${selectFieldMarkup("Status", "status", ["Not Started", "In Progress", "Completed"].map((status) => `<option ${record.status === status ? "selected" : ""}>${status}</option>`).join(""))}
      <div class="form-field form-field-full">
        <label for="modal-description">Description</label>
        <textarea id="modal-description" name="description" rows="3" placeholder="Add task instructions or details…">${escapeHtml(record.description || "")}</textarea>
      </div>
      <div class="form-field form-field-full recurrence-control-group">
        <label class="check-option">
          <input type="checkbox" id="modal-isRecurring" name="isRecurring" value="1" ${record.isRecurring ? "checked" : ""} data-action="toggle-recurrence-options">
          <span><strong>Recurring task (Repeat automatically)</strong></span>
        </label>
        <div id="recurrence-subfields" class="recurrence-subfields ${record.isRecurring ? "" : "is-hidden"}">
          <div class="form-grid form-grid-compact">
            <div class="form-field">
              <label for="modal-recurrenceInterval">Frequency</label>
              <select id="modal-recurrenceInterval" name="recurrenceInterval">
                <option value="daily" ${record.recurrenceInterval === "daily" ? "selected" : ""}>Daily (Every day)</option>
                <option value="weekly" ${record.recurrenceInterval === "weekly" || !record.recurrenceInterval || record.recurrenceInterval === "none" ? "selected" : ""}>Weekly (Every 7 days)</option>
                <option value="biweekly" ${record.recurrenceInterval === "biweekly" ? "selected" : ""}>Bi-weekly (Every 14 days)</option>
                <option value="monthly" ${record.recurrenceInterval === "monthly" ? "selected" : ""}>Monthly</option>
              </select>
            </div>
            <div class="form-field">
              <label for="modal-recurrenceEndDate">Repeat until (Optional)</label>
              <input id="modal-recurrenceEndDate" name="recurrenceEndDate" type="date" value="${escapeHtml(record.recurrenceEndDate || "")}">
            </div>
          </div>
        </div>
      </div>
    </div>`;
}

function detailModalContent(entity, record) {
  if (!record) return `<p class="modal-description">This record is no longer available.</p>`;

  // === EMPLOYEE PROFILE DETAILS ===
  if (entity === "employee") {
    const assignedTeams = workspaceData.teams.filter((t) => (t.memberIds || []).includes(record.id));
    const managedTeams = workspaceData.teams.filter((t) => t.managerId === record.id);
    const managedProjects = workspaceData.projects.filter((p) => p.managerId === record.id);
    const assignedTasks = workspaceData.tasks.filter((t) => t.assigneeId === record.id);
    const completedTasks = assignedTasks.filter((t) => t.status === "Completed");
    const inProgressTasks = assignedTasks.filter((t) => t.status === "In Progress");

    return `
      <div class="employee-profile-detail">
        <header class="profile-header-card">
          <div class="profile-avatar-large ${record.status === "Inactive" ? "avatar-muted" : ""}">
            ${escapeHtml(getInitials(record.name))}
          </div>
          <div class="profile-title-block">
            <h2>${escapeHtml(record.name)}</h2>
            <p class="profile-sub">${escapeHtml(record.title)} · <span class="dept-badge">${escapeHtml(record.department)}</span></p>
            <div class="profile-badges-row">
              <span class="status-badge">${escapeHtml(record.role)}</span>
              <span class="status-badge ${record.status === "Active" ? "status-good" : "status-muted"}">${escapeHtml(record.status)}</span>
              ${record.userId ? `<span class="count-pill">Account linked</span>` : `<span class="count-pill muted">No login account</span>`}
            </div>
          </div>
          <div class="profile-header-action">
            ${canManage("employee") ? `
              <button class="table-action ${record.status === "Active" ? "danger" : "success"}" type="button" data-action="toggle-employee" data-id="${record.id}">
                ${record.status === "Active" ? "Deactivate Employee" : "Activate Employee"}
              </button>
            ` : ""}
          </div>
        </header>

        <h3 class="modal-section-title">Profile Information</h3>
        <div class="detail-grid">
          <div><span>Full Name</span><strong>${escapeHtml(record.name)}</strong></div>
          <div><span>Email</span><strong>${escapeHtml(record.email)}</strong></div>
          <div><span>Department</span><strong>${escapeHtml(record.department)}</strong></div>
          <div><span>Job Title</span><strong>${escapeHtml(record.title)}</strong></div>
          <div><span>Workspace Role</span><strong>${escapeHtml(record.role)}</strong></div>
          <div><span>Account Status</span><strong class="${record.status === "Active" ? "text-good" : "text-muted"}">${escapeHtml(record.status)}</strong></div>
          <div><span>Start Date</span><strong>${escapeHtml(record.startDate || "Not specified")}</strong></div>
          <div><span>System ID</span><strong>#${record.id}</strong></div>
        </div>

        <h3 class="modal-section-title">Team Affiliations</h3>
        ${assignedTeams.length || managedTeams.length ? `
          <div class="profile-teams-list">
            ${assignedTeams.map((t) => `
              <div class="profile-team-chip">
                <span>♧ ${escapeHtml(t.name)}</span>
                <small>${t.memberIds.length} members</small>
              </div>
            `).join("")}
            ${managedTeams.map((t) => `
              <div class="profile-team-chip is-manager">
                <span>⭐ ${escapeHtml(t.name)}</span>
                <small>Team Manager</small>
              </div>
            `).join("")}
          </div>
        ` : `
          <p class="muted-copy">This employee is not currently assigned to any teams.</p>
        `}

        ${managedProjects.length ? `
          <h3 class="modal-section-title">Managed Projects (${managedProjects.length})</h3>
          <div class="profile-projects-list">
            ${managedProjects.map((p) => `
              <div class="profile-project-item">
                <span>${escapeHtml(p.name)}</span>
                <div class="table-progress">
                  <span class="progress-track"><span style="width:${Number(p.progress)}%"></span></span>
                  <strong>${Number(p.progress)}%</strong>
                </div>
              </div>
            `).join("")}
          </div>
        ` : ""}

        <h3 class="modal-section-title">Assigned Tasks (${assignedTasks.length})</h3>
        ${assignedTasks.length ? `
          <div class="task-summary-pills">
            <span class="count-pill">${completedTasks.length} Completed</span>
            <span class="count-pill">${inProgressTasks.length} In Progress</span>
            <span class="count-pill">${assignedTasks.length - completedTasks.length - inProgressTasks.length} Not Started</span>
          </div>
          <ul class="project-task-list">
            ${assignedTasks.slice(0, 6).map((task) => `
              <li>
                <span class="task-dot ${task.status === "Completed" ? "is-done" : ""}"></span>
                <span>${escapeHtml(task.name)} <small>(${escapeHtml(task.projectName || "No project")})</small></span>
                <span class="priority-${escapeHtml(task.priority.toLowerCase())}">${escapeHtml(task.priority)}</span>
                <small class="status-badge">${escapeHtml(task.status)}</small>
              </li>
            `).join("")}
          </ul>
        ` : `
          <p class="muted-copy">No tasks currently assigned to this employee.</p>
        `}
      </div>
    `;
  }

  // === TEAM DETAILS ===
  if (entity === "team") {
    const members = (record.memberIds || []).map(employeeById).filter(Boolean);
    const manager = employeeById(record.managerId);
    const teamProjects = workspaceData.projects.filter((p) => p.teamId === record.id);

    return `
      <p class="modal-description">${escapeHtml(record.description || "No description provided.")}</p>
      <div class="detail-grid">
        <div><span>Team Manager</span><strong>${manager ? escapeHtml(manager.name) : "No manager assigned"}</strong></div>
        <div><span>Total Members</span><strong>${members.length}</strong></div>
      </div>

      <div class="team-members-header-row">
        <h3 class="modal-section-title">Assigned Members (${members.length})</h3>
        ${canManage("team") ? `<button class="button button-quiet" type="button" data-action="assign-team-members" data-id="${record.id}">+ Manage Assignments</button>` : ""}
      </div>

      ${members.length ? `
        <div class="team-members-list-grid">
          ${members.map((employee) => `
            <div class="team-member-row">
              <span class="avatar mini">${escapeHtml(getInitials(employee.name))}</span>
              <div class="team-member-info">
                <strong>${escapeHtml(employee.name)}</strong>
                <small>${escapeHtml(employee.title)} · ${escapeHtml(employee.department)}</small>
              </div>
              ${canManage("team") ? `
                <button class="table-action danger mini-btn" type="button" data-action="quick-remove-team-member" data-team-id="${record.id}" data-emp-id="${employee.id}" title="Remove member">✕</button>
              ` : ""}
            </div>
          `).join("")}
        </div>
      ` : `<p class="muted-copy">No members assigned to this team yet.</p>`}

      ${teamProjects.length ? `
        <h3 class="modal-section-title">Team Projects (${teamProjects.length})</h3>
        <div class="mini-project-list">
          ${teamProjects.map((p) => `
            <div class="mini-project">
              <span>${escapeHtml(p.name)}<small>${escapeHtml(p.status)}</small></span>
              <span class="progress-track"><span style="width:${Number(p.progress)}%"></span></span>
              <strong>${Number(p.progress)}%</strong>
            </div>
          `).join("")}
        </div>
      ` : ""}
    `;
  }

  // === PROJECT MODAL VIEW (fallback for quick modal) ===
  if (entity === "project") {
    const projectTasks = workspaceData.tasks.filter((task) => task.projectId === record.id);
    const team = teamById(record.teamId);
    const members = team ? team.memberIds.map(employeeById).filter(Boolean) : [];
    return `
      <p class="modal-description">${escapeHtml(record.description || "No description provided.")}</p>
      <div class="project-progress-detail">
        <div><strong>${Number(record.progress)}%</strong><span>complete</span></div>
        <div class="progress-track"><span style="width:${Number(record.progress)}%"></span></div>
      </div>
      <div class="detail-grid">
        <div><span>Team</span><strong>${escapeHtml(labelForTeam(record.teamId))}</strong></div>
        <div><span>Manager</span><strong>${escapeHtml(labelForEmployee(record.managerId))}</strong></div>
        <div><span>Status</span><strong>${escapeHtml(record.status)}</strong></div>
        <div><span>Timeline</span><strong>${escapeHtml(record.startDate || "Not set")} → ${escapeHtml(record.dueDate || "Not set")}</strong></div>
      </div>
      <h3 class="modal-section-title">Team members</h3>
      <p class="muted-copy">${members.length ? members.map((employee) => escapeHtml(employee.name)).join(", ") : "No team members assigned."}</p>
      <h3 class="modal-section-title">Project tasks</h3>
      ${projectTasks.length ? `<ul class="project-task-list">${projectTasks.map((task) => `<li><span class="task-dot ${task.status === "Completed" ? "is-done" : ""}"></span><span>${escapeHtml(task.name)}</span><small>${escapeHtml(task.status)}</small></li>`).join("")}</ul>` : `<p class="muted-copy">No tasks assigned to this project yet.</p>`}
      <div class="modal-jump-row">
        <button class="button button-primary" type="button" data-action="view-project-page" data-id="${record.id}">Open Full Project Page →</button>
      </div>
    `;
  }


  if (entity === "task") {
    const task = state.activeTaskDetail || record;
    const project = projectById(task.projectId);
    const assignee = employeeById(task.assigneeId);
    const assigneeName = labelForEmployee(task.assigneeId);
    const projectName = task.projectName || project?.name || "No project";
    const comments = state.taskDetailComments || [];
    const activities = state.taskDetailActivities || [];
    const isCompleted = task.status === "Completed";
    const canMove = state.user.role === "ADMIN" || (state.user.role === "EMPLOYEE" && task.assigneeId === state.currentEmployeeId);

    return `
      <div class="task-detail-modal">
        <div class="task-detail-top">
          <div class="task-detail-badges">
            <span class="status-badge ${isCompleted ? "status-good" : ""}">${escapeHtml(task.status)}</span>
            <span class="priority-badge priority-${escapeHtml((task.priority || "Medium").toLowerCase())}">${escapeHtml(task.priority)} priority</span>
            ${task.isRecurring ? `<span class="recurrence-pill" title="Interval: ${escapeHtml(task.recurrenceInterval)}">🔁 Repeats ${escapeHtml(task.recurrenceInterval)}</span>` : '<span class="recurrence-pill muted">Not recurring</span>'}
          </div>
          ${canMove ? `
            <div class="task-quick-status-group">
              <span class="task-quick-label">Move to:</span>
              <button class="button button-sm button-quiet ${task.status === "Not Started" ? "is-active" : ""}" type="button" data-action="quick-move-task" data-id="${task.id}" data-status="Not Started">To Do</button>
              <button class="button button-sm button-quiet ${task.status === "In Progress" ? "is-active" : ""}" type="button" data-action="quick-move-task" data-id="${task.id}" data-status="In Progress">In Progress</button>
              <button class="button button-sm button-quiet ${task.status === "Completed" ? "is-active" : ""}" type="button" data-action="quick-move-task" data-id="${task.id}" data-status="Completed">Completed</button>
            </div>
          ` : ""}
        </div>

        <div class="detail-grid">
          <div><span>Project</span><strong>${escapeHtml(projectName)}</strong></div>
          <div><span>Assignee</span><strong>${escapeHtml(assigneeName)}${assignee?.department ? ` (${escapeHtml(assignee.department)})` : ""}</strong></div>
          <div><span>Due date</span><strong>${escapeHtml(task.dueDate || "Not set")}</strong></div>
          <div><span>Recurrence</span><strong>${task.isRecurring ? `Every ${escapeHtml(task.recurrenceInterval)}${task.recurrenceEndDate ? ` until ${escapeHtml(task.recurrenceEndDate)}` : ""}` : "None"}</strong></div>
        </div>

        <div class="task-detail-desc-block">
          <span class="detail-block-title">Description</span>
          <p class="modal-description">${escapeHtml(task.description || "No description provided.")}</p>
        </div>

        <div class="task-detail-sections">
          <div class="task-comments-section">
            <h3 class="modal-section-title">Comments (${comments.length})</h3>
            <div class="comments-list">
              ${comments.length ? comments.map((c) => `
                <div class="comment-bubble">
                  <div class="comment-header">
                    <span class="avatar avatar-xs">${escapeHtml(getInitials(c.authorName))}</span>
                    <strong>${escapeHtml(c.authorName)}</strong>
                    <span class="role-pill">${escapeHtml(c.authorRole)}</span>
                    <small class="comment-time">${escapeHtml(c.createdAt || "")}</small>
                  </div>
                  <div class="comment-body">${escapeHtml(c.content)}</div>
                </div>
              `).join("") : '<p class="muted-copy">No comments yet. Leave a note below.</p>'}
            </div>
            <form id="task-comment-form" data-task-id="${task.id}" class="task-comment-form">
              <div class="form-field">
                <label for="new-comment-input">Add a comment</label>
                <textarea id="new-comment-input" name="content" rows="2" placeholder="Write a comment or status update…" required maxlength="2000"></textarea>
              </div>
              <button class="button button-primary button-sm" type="submit">Post comment</button>
            </form>
          </div>

          <div class="task-activities-section">
            <h3 class="modal-section-title">Activity Timeline</h3>
            <div class="activity-timeline">
              ${activities.length ? activities.map((a) => `
                <div class="timeline-entry">
                  <span class="timeline-dot ${a.action.includes("completed") ? "dot-success" : ""}"></span>
                  <div class="timeline-content">
                    <div class="timeline-text">
                      <strong>${escapeHtml(a.actorName)}</strong>: ${escapeHtml(a.details || a.action)}
                    </div>
                    <small class="timeline-time">${escapeHtml(a.createdAt || "")}</small>
                  </div>
                </div>
              `).join("") : '<p class="muted-copy">No activity logged yet.</p>'}
            </div>
          </div>
        </div>
      </div>
    `;
  }



  if (entity === "task") {
    const comments = state.taskComments || [];
    const auditLogs = state.taskAuditLogs || [];
    const activities = state.taskActivities || [];
    return `
      <div class="detail-grid">
        <div><span>Task</span><strong>${escapeHtml(record.name)}</strong></div>
        <div><span>Project</span><strong>${escapeHtml(record.projectName || labelForProject(record.projectId))}</strong></div>
        <div><span>Assignee</span><strong>${escapeHtml(labelForEmployee(record.assigneeId))}</strong></div>
        <div><span>Priority</span><strong class="priority-${escapeHtml((record.priority || "").toLowerCase())}">${escapeHtml(record.priority || "Medium")}</strong></div>
        <div><span>Status</span><strong>${escapeHtml(record.status || "Not Started")}</strong></div>
        <div><span>Due date</span><strong>${escapeHtml(record.dueDate || "Not set")}</strong></div>
      </div>

      <div class="task-tabs">
        <button type="button" class="tab-button ${state.taskDetailTab === "comments" ? "is-active" : ""}" data-action="set-task-tab" data-tab="comments">Discussion (${comments.length})</button>
        <button type="button" class="tab-button ${state.taskDetailTab === "audit" ? "is-active" : ""}" data-action="set-task-tab" data-tab="audit">Audit Logs (${auditLogs.length})</button>
        <button type="button" class="tab-button ${state.taskDetailTab === "history" ? "is-active" : ""}" data-action="set-task-tab" data-tab="history">Activity History (${activities.length})</button>
      </div>

      <div class="task-tab-content">
        ${state.taskDetailTab === "comments" ? `
          <div class="comments-section">
            <ul class="comments-list">
              ${comments.length ? comments.map((c) => `
                <li class="comment-item">
                  <div class="comment-header">
                    <span class="avatar">${escapeHtml(getInitials(c.userName))}</span>
                    <div>
                      <strong>${escapeHtml(c.userName)}</strong>
                      <small class="muted-copy">${escapeHtml(c.createdAt)}</small>
                    </div>
                    ${(c.userId === state.user.id || state.user.role === "ADMIN") ? `
                      <button type="button" class="table-action button-danger" data-action="delete-comment" data-task-id="${record.id}" data-comment-id="${c.id}">Delete</button>
                    ` : ""}
                  </div>
                  <p class="comment-body">${escapeHtml(c.content)}</p>
                </li>
              `).join("") : `<p class="muted-copy">No comments yet. Start the discussion below.</p>`}
            </ul>
            <form id="add-comment-form" class="comment-form" data-task-id="${record.id}">
              <textarea id="comment-content" name="content" rows="2" placeholder="Write a comment or discussion update…" required maxlength="2000"></textarea>
              <button class="button button-primary" type="submit">Post comment</button>
            </form>
          </div>
        ` : state.taskDetailTab === "audit" ? `
          <div class="audit-section">
            ${auditLogs.length ? `
              <ul class="timeline-list">
                ${auditLogs.map((l) => `
                  <li class="timeline-item">
                    <div class="timeline-dot"></div>
                    <div class="timeline-content">
                      <div class="timeline-header">
                        <span class="badge-change badge-${escapeHtml(l.changeType)}">${escapeHtml(l.changeType.toUpperCase())}</span>
                        <small class="muted-copy">${escapeHtml(l.createdAt)}</small>
                      </div>
                      <p class="timeline-text">
                        <strong>${escapeHtml(l.oldValue || "None")}</strong> → <strong>${escapeHtml(l.newValue || "None")}</strong>
                      </p>
                      <small class="muted-copy">Changed by ${escapeHtml(l.userName)}</small>
                    </div>
                  </li>
                `).join("")}
              </ul>
            ` : `<p class="muted-copy">No audit logs recorded for this task yet.</p>`}
          </div>
        ` : `
          <div class="history-section">
            ${activities.length ? `
              <ul class="timeline-list">
                ${activities.map((a) => `
                  <li class="timeline-item">
                    <div class="timeline-dot"></div>
                    <div class="timeline-content">
                      <div class="timeline-header">
                        <strong>${escapeHtml(a.action.replace(/_/g, " "))}</strong>
                        <small class="muted-copy">${escapeHtml(a.createdAt)}</small>
                      </div>
                      <p class="timeline-text">${escapeHtml(a.details)}</p>
                      <small class="muted-copy">By ${escapeHtml(a.userName)}</small>
                    </div>
                  </li>
                `).join("")}
              </ul>
            ` : `<p class="muted-copy">No activity recorded for this task yet.</p>`}
          </div>
        `}
      </div>
    `;
  }
 main

  return "";
}

function teamMemberAssignmentModalMarkup() {
  const team = teamById(state.assigningTeamId);
  if (!team) return "";

  const assigned = Array.from(state.selectedMemberIds).map(employeeById).filter(Boolean);
  const q = (state.assignmentSearch || "").trim().toLowerCase();
  const deptFilter = state.assignmentDeptFilter || "All";

  const available = workspaceData.employees.filter((emp) => {
    if (state.selectedMemberIds.has(emp.id)) return false;
    if (emp.status !== "Active") return false;
    if (deptFilter !== "All" && emp.department !== deptFilter) return false;
    if (q && !`${emp.name} ${emp.title} ${emp.department}`.toLowerCase().includes(q)) return false;
    return true;
  });

  const departments = ["All", ...Array.from(new Set(workspaceData.employees.map((e) => e.department).filter(Boolean))).sort()];

  return `
    <div class="modal-backdrop" data-action="backdrop-close">
      <section class="modal-card assignment-modal-card" role="dialog" aria-modal="true" aria-labelledby="assign-modal-title">
        <header class="modal-header">
          <div>
            <span class="eyebrow">TEAM MANAGEMENT</span>
            <h2 id="assign-modal-title">Assign Members: ${escapeHtml(team.name)}</h2>
          </div>
          <button class="modal-close" type="button" data-action="close-modal" aria-label="Close dialog">×</button>
        </header>

        <div class="modal-content">
          <p class="modal-description">Add or remove active employees for this team. Changes will be saved to the database.</p>

          <div class="assignment-toolbar">
            <input class="search-box" type="search" placeholder="Search employees to add…" value="${escapeHtml(state.assignmentSearch)}" data-action="search-assignment">
            <select class="filter-select" data-action="filter-assignment-dept">
              ${departments.map((d) => `<option value="${escapeHtml(d)}" ${deptFilter === d ? "selected" : ""}>${escapeHtml(d === "All" ? "All Departments" : d)}</option>`).join("")}
            </select>
          </div>

          <div class="assignment-dual-grid">
            <!-- Left: Current Members -->
            <div class="assignment-col">
              <div class="assignment-col-header">
                <strong>Assigned Members (${assigned.length})</strong>
                ${assigned.length ? `<button class="text-button text-danger" type="button" data-action="assignment-remove-all">Remove All</button>` : ""}
              </div>
              <div class="assignment-item-list">
                ${assigned.length ? assigned.map((emp) => `
                  <div class="assignment-item">
                    <span class="avatar mini">${escapeHtml(getInitials(emp.name))}</span>
                    <div class="assignment-item-info">
                      <strong>${escapeHtml(emp.name)}</strong>
                      <small>${escapeHtml(emp.title)} · ${escapeHtml(emp.department)}</small>
                    </div>
                    <button class="assignment-action-btn remove-btn" type="button" data-action="assignment-remove-one" data-id="${emp.id}" title="Remove member">✕</button>
                  </div>
                `).join("") : `<div class="empty-col"><p>No members currently assigned.</p></div>`}
              </div>
            </div>

            <!-- Right: Available to Add -->
            <div class="assignment-col">
              <div class="assignment-col-header">
                <strong>Available Active Employees (${available.length})</strong>
                ${available.length ? `<button class="text-button" type="button" data-action="assignment-add-all">Add All</button>` : ""}
              </div>
              <div class="assignment-item-list">
                ${available.length ? available.map((emp) => `
                  <div class="assignment-item">
                    <span class="avatar mini">${escapeHtml(getInitials(emp.name))}</span>
                    <div class="assignment-item-info">
                      <strong>${escapeHtml(emp.name)}</strong>
                      <small>${escapeHtml(emp.title)} · ${escapeHtml(emp.department)}</small>
                    </div>
                    <button class="assignment-action-btn add-btn" type="button" data-action="assignment-add-one" data-id="${emp.id}" title="Add to team">+</button>
                  </div>
                `).join("") : `<div class="empty-col"><p>No more matching active employees.</p></div>`}
              </div>
            </div>
          </div>
        </div>

        <footer class="modal-footer">
          <button class="button button-quiet" type="button" data-action="close-modal">Cancel</button>
          <button class="button button-primary" type="button" data-action="save-team-assignment" data-id="${team.id}">Save Assignments (${assigned.length})</button>
        </footer>
      </section>
    </div>
  `;
}

function quickProgressModalMarkup() {
  const { id } = state.modal;
  const project = projectById(id);
  if (!project) return "";

  return `
    <div class="modal-backdrop" data-action="backdrop-close">
      <section class="modal-card quick-progress-modal" role="dialog" aria-modal="true" aria-labelledby="qp-modal-title">
        <header class="modal-header">
          <div>
            <span class="eyebrow">PROJECT PROGRESS EDITING</span>
            <h2 id="qp-modal-title">Edit Progress: ${escapeHtml(project.name)}</h2>
          </div>
          <button class="modal-close" type="button" data-action="close-modal" aria-label="Close dialog">×</button>
        </header>

        <div class="modal-content">
          <div class="quick-progress-header">
            <span class="qp-label">Current Completion</span>
            <span class="qp-val" id="qp-val-label">${Number(project.progress)}%</span>
          </div>

          <div class="modal-slider-wrap">
            <input id="quick-progress-slider" type="range" min="0" max="100" value="${Number(project.progress)}" oninput="document.getElementById('quick-progress-number').value = this.value; document.getElementById('qp-val-label').textContent = this.value + '%'">
            <input id="quick-progress-number" type="number" min="0" max="100" value="${Number(project.progress)}" oninput="document.getElementById('quick-progress-slider').value = this.value; document.getElementById('qp-val-label').textContent = this.value + '%'">
          </div>

          <div class="progress-presets">
            <span class="presets-label">Presets:</span>
            <button class="preset-btn" type="button" onclick="document.getElementById('quick-progress-slider').value=0;document.getElementById('quick-progress-number').value=0;document.getElementById('qp-val-label').textContent='0%'">0%</button>
            <button class="preset-btn" type="button" onclick="document.getElementById('quick-progress-slider').value=25;document.getElementById('quick-progress-number').value=25;document.getElementById('qp-val-label').textContent='25%'">25%</button>
            <button class="preset-btn" type="button" onclick="document.getElementById('quick-progress-slider').value=50;document.getElementById('quick-progress-number').value=50;document.getElementById('qp-val-label').textContent='50%'">50%</button>
            <button class="preset-btn" type="button" onclick="document.getElementById('quick-progress-slider').value=75;document.getElementById('quick-progress-number').value=75;document.getElementById('qp-val-label').textContent='75%'">75%</button>
            <button class="preset-btn" type="button" onclick="document.getElementById('quick-progress-slider').value=100;document.getElementById('quick-progress-number').value=100;document.getElementById('qp-val-label').textContent='100%'">100%</button>
          </div>
        </div>

        <footer class="modal-footer">
          <button class="button button-quiet" type="button" data-action="close-modal">Cancel</button>
          <button class="button button-primary" type="button" data-action="save-quick-progress" data-id="${project.id}">Save Progress</button>
        </footer>
      </section>
    </div>
  `;
}

function modalMarkup() {
  if (!state.modal) return "";
  if (state.modal.entity === "team-assignment") {
    return teamMemberAssignmentModalMarkup();
  }
  if (state.modal.entity === "project-progress") {
    return quickProgressModalMarkup();
  }

  const { entity, id, view } = state.modal;
  if (entity === "password") {
    return `<div class="modal-backdrop" data-action="backdrop-close">
    <section class="modal-card" role="dialog" aria-modal="true" aria-labelledby="password-modal-title">
      <header class="modal-header"><div><span class="eyebrow">SECURITY</span><h2 id="password-modal-title">Change Password</h2></div><button class="modal-close" type="button" data-action="close-modal" aria-label="Close dialog">×</button></header>
      <form id="password-form">
        <div class="modal-content">
          <div id="password-form-message"></div>
          <div class="form-grid">
            <div class="form-field form-field-full">
              <label for="modal-currentPassword">Current password</label>
              <input id="modal-currentPassword" name="currentPassword" type="password" autocomplete="current-password" placeholder="Enter current password" required>
            </div>
            <div class="form-field form-field-full">
              <label for="modal-newPassword">New password</label>
              <input id="modal-newPassword" name="newPassword" type="password" autocomplete="new-password" placeholder="At least 8 characters" minlength="8" required>
            </div>
            <div class="form-field form-field-full">
              <label for="modal-confirmPassword">Confirm new password</label>
              <input id="modal-confirmPassword" name="confirmPassword" type="password" autocomplete="new-password" placeholder="Re-enter new password" required>
            </div>
          </div>
        </div>
        <footer class="modal-footer"><button class="button button-quiet" type="button" data-action="close-modal">Cancel</button><button class="button button-primary" type="submit">Update password</button></footer>
      </form>
    </section>
  </div>`;
  }
  const pluralKey = `${entity}s`;
  const record = id === null ? {} : workspaceData[pluralKey]?.find((item) => item.id === id);
  const titleNames = { employee: "employee", team: "team", project: "project", task: "task" };
  const titleName = titleNames[entity] || entity;
  const title = view
    ? `${entity === "employee" ? "Employee Profile" : entity[0].toUpperCase() + entity.slice(1) + " Details"}`
    : `${id === null ? "Add" : "Edit"} ${titleName}`;

  return `<div class="modal-backdrop" data-action="backdrop-close">
    <section class="modal-card ${entity === "employee" && view ? "profile-modal-card" : ""}" role="dialog" aria-modal="true" aria-labelledby="record-modal-title">
      <header class="modal-header">
        <div>
          <span class="eyebrow">${view ? "RECORD DETAILS" : "WORKSPACE"}</span>
          <h2 id="record-modal-title">${escapeHtml(title)}</h2>
        </div>
        <button class="modal-close" type="button" data-action="close-modal" aria-label="Close dialog">×</button>
      </header>
      ${view ? `
        <div class="modal-content">${detailModalContent(entity, record)}</div>
        <footer class="modal-footer">
          <button class="button button-quiet" type="button" data-action="close-modal">Close</button>
          ${canManage(entity) ? `<button class="button button-primary" type="button" data-action="edit-${entity}" data-id="${id}">Edit ${titleName}</button>` : ""}
        </footer>
      ` : `
        <form id="record-form" data-entity="${entity}" data-id="${id === null ? "" : id}">
          <div class="modal-content">${modalFormFields(entity, record)}</div>
          <footer class="modal-footer">
            <button class="button button-quiet" type="button" data-action="close-modal">Cancel</button>
            <button class="button button-primary" type="submit">${id === null ? "Create" : "Save changes"}</button>
          </footer>
        </form>
      `}
    </section>
  </div>`;
}

function mainContentMarkup() {
  const page = state.user.role === "ADMIN" ? state.page : "tasks";
  const title = page === "dashboard"
    ? "Management Dashboard"
    : page === "project-detail"
      ? "Project Details"
      : featureDetails[page]?.title || "Management Dashboard";

  return `
    <div class="dashboard-shell">
      ${menuMarkup(state.page)}
      <div class="main-column">
        <header class="topbar">
          <div class="topbar-left">
            <button class="mobile-menu-button" type="button" data-action="toggle-nav" aria-expanded="${state.mobileNavOpen}" aria-label="Open navigation">☰</button>
            <span class="breadcrumb">Workspace&nbsp; / &nbsp;</span>
            <span class="topbar-title">${escapeHtml(title)}</span>
          </div>
          <div class="topbar-right">
            <span class="welcome">Signed in as ${escapeHtml(state.user.name)}</span>
            <button class="button button-quiet" type="button" data-action="open-password-modal" style="font-size:12px;padding:4px 10px;">Change password</button>
            <span class="avatar" aria-hidden="true">${escapeHtml(getInitials(state.user.name))}</span>
          </div>
        </header>
        <main id="main" class="content">
          ${state.accessMessage ? `<div class="form-message error" role="alert">${escapeHtml(state.accessMessage)}</div>` : ""}
          ${page === "dashboard" ? dashboardPageMarkup() : page === "project-detail" ? projectDetailPageMarkup(state.selectedProjectId) : featurePageMarkup(page)}
        </main>
      </div>
    </div>
    ${modalMarkup()}`;
}


async function openTaskDetail(taskId) {
  state.modal = { entity: "task", id: Number(taskId), view: true };
  state.activeTaskDetail = null;
  state.taskDetailComments = [];
  state.taskDetailActivities = [];
  render();

  try {
    const data = await apiRequest(`/api/tasks/${taskId}`);
    if (state.modal && state.modal.entity === "task" && state.modal.id === Number(taskId)) {
      state.activeTaskDetail = data.task;
      state.taskDetailComments = data.task.comments || [];
      state.taskDetailActivities = data.task.activities || [];
      render();
    }
  } catch (error) {
    showToast(error.message || "Could not load task details.", "error");
  }
}

async function moveTaskStatus(taskId, targetStatus) {
  const task = workspaceData.tasks.find((t) => t.id === taskId);
  if (!task) return;

  const currentNormalized = (task.status === "To Do" ? "Not Started" : task.status);
  const targetNormalized = (targetStatus === "To Do" ? "Not Started" : targetStatus);
  if (currentNormalized === targetNormalized) return;

  if (state.user.role === "EMPLOYEE" && task.assigneeId !== state.currentEmployeeId) {
    showToast("You can only update tasks assigned to you.", "error");
    return;
  }

  const prevStatus = task.status;
  task.status = targetStatus;
  render();

  try {
    await apiRequest(`/api/tasks/${taskId}`, {
      method: "PATCH",
      body: JSON.stringify({ status: targetStatus }),
    });
    showToast(`Task moved to ${targetStatus === "Not Started" ? "To Do" : targetStatus}.`, "success");
    await loadWorkspaceData();
    render();
  } catch (error) {
    task.status = prevStatus;
    render();
    showToast(error.message || "Failed to move task.", "error");
  }
}

function attachDragAndDropListeners() {
  const cards = document.querySelectorAll('.kanban-card[draggable="true"]');
  const columns = document.querySelectorAll(".kanban-column-body");

  cards.forEach((card) => {
    card.addEventListener("dragstart", (e) => {
      e.dataTransfer.setData("text/plain", card.dataset.taskId);
      e.dataTransfer.effectAllowed = "move";
      card.classList.add("is-dragging");
    });

    card.addEventListener("dragend", () => {
      card.classList.remove("is-dragging");
      document.querySelectorAll(".kanban-column-body").forEach((col) => {
        col.classList.remove("drag-over");
      });
    });
  });

  columns.forEach((column) => {
    column.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      column.classList.add("drag-over");
    });

    column.addEventListener("dragleave", (e) => {
      if (!column.contains(e.relatedTarget)) {
        column.classList.remove("drag-over");
      }
    });

    column.addEventListener("drop", async (e) => {
      e.preventDefault();
      column.classList.remove("drag-over");
      const taskId = Number(e.dataTransfer.getData("text/plain"));
      const targetStatus = column.dataset.status;
      if (!taskId || !targetStatus) return;
      await moveTaskStatus(taskId, targetStatus);
    });
  });
}

async function handleBulkStatus(status) {
  const taskIds = Array.from(state.selectedTaskIds);
  if (!taskIds.length) return;

  try {
    await apiRequest("/api/tasks/bulk", {
      method: "POST",
      body: JSON.stringify({ taskIds, action: "status", status }),
    });
    state.selectedTaskIds.clear();
    await loadWorkspaceData();
    render();
    showToast(`Updated ${taskIds.length} tasks to ${status === "Not Started" ? "To Do" : status}.`, "success");
  } catch (error) {
    showToast(error.message || "Bulk status update failed.", "error");
  }
}

async function handleBulkAssign(assigneeId) {
  const taskIds = Array.from(state.selectedTaskIds);
  if (!taskIds.length) return;
  const parsedAssignee = assigneeId ? Number(assigneeId) : null;

  try {
    await apiRequest("/api/tasks/bulk", {
      method: "POST",
      body: JSON.stringify({ taskIds, action: "assign", assigneeId: parsedAssignee }),
    });
    state.selectedTaskIds.clear();
    await loadWorkspaceData();
    render();
    showToast(`Reassigned ${taskIds.length} tasks.`, "success");
  } catch (error) {
    showToast(error.message || "Bulk assign failed.", "error");
  }
}

async function handleBulkDelete() {
  const taskIds = Array.from(state.selectedTaskIds);
  if (!taskIds.length) return;
  if (!window.confirm(`Are you sure you want to delete ${taskIds.length} selected tasks?`)) return;

  try {
    await apiRequest("/api/tasks/bulk", {
      method: "POST",
      body: JSON.stringify({ taskIds, action: "delete" }),
    });
    state.selectedTaskIds.clear();
    await loadWorkspaceData();
    render();
    showToast(`Deleted ${taskIds.length} tasks.`, "success");
  } catch (error) {
    showToast(error.message || "Bulk delete failed.", "error");
  }
}

async function handleCommentSubmit(event) {
  event.preventDefault();
  const form = event.target;
  const taskId = form.dataset.taskId;
  const content = String(form.content.value || "").trim();
  if (!content) return;

  const button = form.querySelector('button[type="submit"]');
  if (button) button.disabled = true;

  try {
    await apiRequest(`/api/tasks/${taskId}/comments`, {
      method: "POST",
      body: JSON.stringify({ content }),
    });
    form.reset();
    showToast("Comment posted.", "success");
    await openTaskDetail(taskId);
    await loadWorkspaceData();
  } catch (error) {
    showToast(error.message || "Failed to post comment.", "error");
  } finally {
    if (button) button.disabled = false;
  }
}

function render() {
  if (state.user) {
    app.innerHTML = mainContentMarkup();
    if (state.page === "tasks" && state.taskView === "kanban") {
      attachDragAndDropListeners();
    }
  } else {
    app.innerHTML = authPanelMarkup();
  }
}

function setFormBusy(form, isBusy, label) {
  const button = form.querySelector('button[type="submit"]');
  if (!button) return;
  button.disabled = isBusy;
  button.innerHTML = isBusy
    ? `<span class="spinner" aria-hidden="true"></span><span class="button-label">${label}</span>`
    : `<span class="button-label">${label === "Creating account…" ? "Create account" : "Sign in"}</span>`;
}

function setAuthFormMessage(form, message, kind = "error") {
  document.querySelector(".auth-card .form-message")?.remove();
  const box = document.createElement("div");
  box.className = `form-message ${kind}`;
  box.setAttribute("role", kind === "error" ? "alert" : "status");
  box.textContent = message;
  form.parentElement.insertBefore(box, form);
}

async function saveRecord(form) {
  const entity = form.dataset.entity;
  const id = form.dataset.id ? Number(form.dataset.id) : null;
  const formData = new FormData(form);
  const record = Object.fromEntries(formData.entries());
  const collection = workspaceData[`${entity}s`];

  if (!collection) {
    showToast("This record type is not supported.", "error");
    return;
  }

  if (entity === "employee") {
    record.email = String(record.email || "").trim().toLowerCase();
    if (collection.some((employee) => employee.email.toLowerCase() === record.email && employee.id !== id)) {
      showToast("An employee with that email already exists.", "error");
      return;
    }
    record.name = String(record.name || "").trim();
    record.department = String(record.department || "").trim();
    record.title = String(record.title || "").trim();
  } else if (entity === "team") {
    record.name = String(record.name || "").trim();
    record.managerId = record.managerId ? Number(record.managerId) : null;
    record.memberIds = formData.getAll("memberIds").map(Number);
  } else if (entity === "project") {
    record.name = String(record.name || "").trim();
    record.teamId = record.teamId ? Number(record.teamId) : null;
    record.managerId = record.managerId ? Number(record.managerId) : null;
    record.progress = Number(record.progress);
    if (record.startDate && record.dueDate && record.startDate > record.dueDate) {
      showToast("The due date must be on or after the start date.", "error");
      return;
    }
    if (!Number.isFinite(record.progress) || record.progress < 0 || record.progress > 100) {
      showToast("Project completion must be between 0 and 100.", "error");
      return;
    }
  } else if (entity === "task") {
    record.name = String(record.name || "").trim();
    record.description = String(record.description || "").trim();
    record.projectId = record.projectId ? Number(record.projectId) : null;
    record.assigneeId = record.assigneeId ? Number(record.assigneeId) : null;
    record.isRecurring = formData.get("isRecurring") === "1";
    record.recurrenceInterval = record.isRecurring ? (record.recurrenceInterval || "weekly") : "none";
    record.recurrenceEndDate = record.isRecurring && record.recurrenceEndDate ? record.recurrenceEndDate : null;
  }

  if (!record.name) {
    showToast("Please provide a name.", "error");
    return;
  }

  const submitButton = form.querySelector('button[type="submit"]');
  submitButton.disabled = true;
  try {
    const endpoint = `/api/${entity === "employee" ? "employees" : `${entity}s`}${id === null ? "" : `/${id}`}`;
    await apiRequest(endpoint, {
      method: id === null ? "POST" : "PATCH",
      body: JSON.stringify(record),
    });
    await loadWorkspaceData();
    state.modal = null;
    render();
    showToast(`${entity[0].toUpperCase()}${entity.slice(1)} ${id === null ? "created" : "updated"}.`, "success");
  } catch (error) {
    showToast(error.message || "The record could not be saved.", "error");
    submitButton.disabled = false;
  }
}

function openEdit(entity, id) {
  if (!canManage(entity)) {
    showToast("You do not have permission to edit this record.", "error");
    return;
  }
  openModal(entity, id);
}

async function handleRecordAction(action, id) {
  const entity = action.slice(action.indexOf("-") + 1).replace(/-task$/, "");
  const recordId = Number(id);

  if (action === "view-task") {
    openTaskDetail(recordId);
    return;
  } else if (action.startsWith("view-")) {
    openModal(entity, recordId, true);
  } else if (action.startsWith("edit-")) {
    openEdit(entity, recordId);
  } else if (action === "toggle-employee") {
    const employee = employeeById(recordId);
    if (!employee) return;
    const nextStatus = employee.status === "Active" ? "Inactive" : "Active";
    if (!window.confirm(`${nextStatus === "Inactive" ? "Deactivate" : "Activate"} employee "${employee.name}"?`)) return;
    try {
      await apiRequest(`/api/employees/${recordId}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status: nextStatus }),
      });
      await loadWorkspaceData();
      if (state.modal && state.modal.entity === "employee" && state.modal.id === recordId) {
        // Refresh modal content
      }
      render();
      showToast(`${employee.name} has been ${nextStatus.toLowerCase()}d.`, "success");
    } catch (error) {
      showToast(error.message || "Employee status could not be changed.", "error");
    }
  } else if (action === "complete-task") {
    const task = workspaceData.tasks.find((item) => item.id === recordId);
    if (!task) return;
    try {
      await apiRequest(`/api/tasks/${recordId}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "Completed" }),
      });
      await loadWorkspaceData();
      render();
      showToast("Task marked complete.", "success");
    } catch (error) {
      showToast(error.message || "Task could not be completed.", "error");
    }
  } else if (["delete-task", "delete-team", "delete-project"].includes(action)) {
    const collection = workspaceData[`${entity}s`];
    const record = collection.find((item) => item.id === recordId);
    if (!record || !window.confirm(`Delete "${record.name}"?`)) return;
    try {
      await apiRequest(`/api/${entity === "team" ? "teams" : `${entity}s`}/${recordId}`, {
        method: "DELETE",
      });
      await loadWorkspaceData();
      if (state.page === "project-detail" && entity === "project" && state.selectedProjectId === recordId) {
        state.page = "projects";
      }
      render();
      showToast(`${entity[0].toUpperCase()}${entity.slice(1)} deleted.`, "success");
    } catch (error) {
      showToast(error.message || `${entity} could not be deleted.`, "error");
    }
  }
}

async function saveAssignedTaskStatus(taskId) {
  const task = workspaceData.tasks.find((item) => item.id === Number(taskId));
  const select = document.querySelector(`[data-task-status="${CSS.escape(String(taskId))}"]`);
  if (!task || !select || (state.user.role === "EMPLOYEE" && task.assigneeId !== state.currentEmployeeId)) {
    showToast("You can only update the status of tasks assigned to you.", "error");
    return;
  }
  const nextStatus = select.value;
  const button = document.querySelector(`[data-action="save-task-status"][data-id="${CSS.escape(String(taskId))}"]`);
  if (!button) return;
  button.disabled = true;
  try {
    await apiRequest(`/api/tasks/${taskId}`, {
      method: "PATCH",
      body: JSON.stringify({ status: nextStatus }),
    });
    await loadWorkspaceData();
    render();
    showToast("Task status updated.", "success");
  } catch (error) {
    button.disabled = false;
    showToast(error.message || "Task status could not be updated.", "error");
  }
}

 feature/member4-management-ui
async function saveProjectProgress(projectId, progressValue) {
  const parsed = Number(progressValue);
  if (!Number.isInteger(parsed) || parsed < 0 || parsed > 100) {
    showToast("Project completion must be a whole number between 0 and 100.", "error");
    return;
  }
  try {
    await apiRequest(`/api/projects/${projectId}/progress`, {
      method: "PATCH",
      body: JSON.stringify({ progress: parsed }),
    });
    await loadWorkspaceData();
    state.modal = null;
    render();
    showToast(`Project progress updated to ${parsed}%.`, "success");
  } catch (error) {
    showToast(error.message || "Could not update project progress.", "error");
  }
}

async function saveTeamAssignments(teamId) {
  const memberIds = Array.from(state.selectedMemberIds);
  try {
    await apiRequest(`/api/teams/${teamId}/members`, {
      method: "PATCH",
      body: JSON.stringify({ memberIds }),
    });
    await loadWorkspaceData();
    state.modal = null;
    render();
    showToast(`Team members updated (${memberIds.length} members assigned).`, "success");
  } catch (error) {
    showToast(error.message || "Could not update team members.", "error");

async function handlePasswordSubmit(form) {
  const formData = new FormData(form);
  const currentPassword = String(formData.get("currentPassword") || "");
  const newPassword = String(formData.get("newPassword") || "");
  const confirmPassword = String(formData.get("confirmPassword") || "");

  const msgBox = form.querySelector("#password-form-message");
  if (msgBox) msgBox.innerHTML = "";

  if (!currentPassword || !newPassword) {
    if (msgBox) msgBox.innerHTML = '<div class="form-message error">Current password and new password are required.</div>';
    return;
  }
  if (newPassword.length < 8) {
    if (msgBox) msgBox.innerHTML = '<div class="form-message error">Password must contain at least 8 characters.</div>';
    return;
  }
  if (newPassword !== confirmPassword) {
    if (msgBox) msgBox.innerHTML = '<div class="form-message error">New passwords do not match.</div>';
    return;
  }
  if (currentPassword === newPassword) {
    if (msgBox) msgBox.innerHTML = '<div class="form-message error">New password cannot be the same as the current password.</div>';
    return;
  }

  const submitButton = form.querySelector('button[type="submit"]');
  submitButton.disabled = true;
  submitButton.textContent = "Updating...";

  try {
    const res = await apiRequest("/api/account/password", {
      method: "POST",
      body: JSON.stringify({ currentPassword, newPassword, confirmPassword }),
    });
    state.modal = null;
    render();
    showToast(res.message || "Password updated successfully.", "success");
  } catch (error) {
    if (msgBox) {
      msgBox.innerHTML = `<div class="form-message error">${escapeHtml(error.message || "Failed to update password.")}</div>`;
    } else {
      showToast(error.message || "Failed to update password.", "error");
    }
    submitButton.disabled = false;
    submitButton.textContent = "Update password";
main
  }
}

async function handleAuthSubmit(event) {
  event.preventDefault();
  const form = event.target;
  const values = new FormData(form);
  const email = String(values.get("email") || "").trim();
  const password = String(values.get("password") || "");
  const signup = state.page === "signup";
  const name = String(values.get("name") || "").trim();
  const confirmPassword = String(values.get("confirmPassword") || "");

  if (!email || !password || (signup && !name)) {
    setAuthFormMessage(form, "Please fill in all required fields.");
    return;
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    setAuthFormMessage(form, "Please enter a valid email address.");
    return;
  }
  if (signup && password.length < 8) {
    setAuthFormMessage(form, "Your password must contain at least 8 characters.");
    return;
  }
  if (signup && password !== confirmPassword) {
    setAuthFormMessage(form, "The passwords do not match.");
    return;
  }

  const submitLabel = signup ? "Creating account…" : "Signing in…";
  setFormBusy(form, true, submitLabel);
  try {
    if (signup) {
      const data = await apiRequest("/api/signup", {
        method: "POST",
        body: JSON.stringify({
          name,
          email,
          password,
          accountType: state.loginRole,
        }),
      });
      const createdUser = getUserFromResponse(data);
      if (!createdUser) {
        throw new ApiError("The server response did not include the created account.");
      }
      state.loginRole = createdUser.role === "ADMIN" ? "ADMIN" : "EMPLOYEE";
      state.page = "login";
      state.notice = {
        kind: "success",
        text: `${createdUser.role === "ADMIN" ? "Administrator" : "Employee"} account created. You can now sign in.`,
      };
      render();
      document.querySelector("#email")?.focus();
      return;
    }

    const data = await apiRequest("/api/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    const user = getUserFromResponse(data);
    if (!user) {
      throw new ApiError("The server response did not include a valid user account.");
    }
    if (user.role !== state.loginRole) {
      await apiRequest("/api/logout", { method: "POST" });
      throw new ApiError(`This account is not registered for ${state.loginRole === "ADMIN" ? "admin" : "employee"} login.`);
    }
    state.user = user;
    state.notice = null;
    state.accessMessage = "";
    state.page = user.role === "ADMIN" ? "dashboard" : "tasks";
    try {
      await loadWorkspaceData();
    } catch (error) {
      showToast(`Signed in, but workspace data could not be loaded: ${error.message}`, "error");
    }
    render();
    await validateDashboardAccess();
  } catch (error) {
    const message = error instanceof ApiError
      ? error.message
      : "Something went wrong. Please try again.";
    setAuthFormMessage(form, message);
    setFormBusy(form, false, submitLabel);
  }
}

async function validateDashboardAccess() {
  const roleEndpoints = {
    ADMIN: "/api/admin/dashboard",
    MANAGER: "/api/manager/dashboard",
    EMPLOYEE: "/api/employee/dashboard",
  };
  const endpoint = roleEndpoints[state.user?.role];
  if (!endpoint) {
    showToast("Your account has an unrecognized role. Please contact an administrator.", "error");
    return;
  }
  try {
    await apiRequest(endpoint);
  } catch (error) {
    if (error.status === 401) {
      handleUnauthorized(error.message);
    } else if (error.status === 403) {
      state.accessMessage = error.message;
      render();
    } else {
      showToast(`Signed in, but the role access check failed: ${error.message}`, "error");
    }
  }
}

function handleUnauthorized(message) {
  state.user = null;
  state.currentEmployeeId = null;
  state.page = "login";
  state.mobileNavOpen = false;
  state.notice = { kind: "info", text: message || "Your session has expired. Please sign in again." };
  state.accessMessage = "";
  render();
}

async function logout() {
  try {
    await apiRequest("/api/logout", { method: "POST" });
    state.user = null;
    state.currentEmployeeId = null;
    state.page = "login";
    state.notice = { kind: "success", text: "You have been signed out." };
    state.accessMessage = "";
    render();
  } catch (error) {
    if (error.status === 401) {
      handleUnauthorized("You are already signed out.");
      return;
    }
    if (error.status === 403) {
      showToast(error.message, "error");
      return;
    }
    showToast(`Could not sign out: ${error.message}`, "error");
  }
}

async function restoreSession() {
  try {
    const data = await apiRequest("/api/me");
    const user = getUserFromResponse(data);
    if (!user) {
      throw new ApiError("The server response did not include a valid user account.");
    }
    state.user = user;
    state.page = user.role === "ADMIN" ? "dashboard" : "tasks";
    try {
      await loadWorkspaceData();
    } catch (error) {
      showToast(`Signed in, but workspace data could not be loaded: ${error.message}`, "error");
    }
    render();
    await validateDashboardAccess();
  } catch (error) {
    if (error.status === 401 || error.status === 404 || error.status === 501) {
      state.user = null;
      state.page = "login";
      state.notice = null;
      render();
      return;
    }
    state.user = null;
    state.page = "login";
    state.notice = {
      kind: "error",
      text: `Could not restore your session: ${error.message}`,
    };
    render();
  }
}

 
// === GLOBAL EVENT LISTENERS ===


async function loadTaskDetails(taskId) {
  try {
    const [commentsRes, auditRes, historyRes] = await Promise.allSettled([
      apiRequest(`/api/tasks/${taskId}/comments`),
      apiRequest(`/api/tasks/${taskId}/audit-logs`),
      apiRequest(`/api/tasks/${taskId}/history`),
    ]);
    state.taskComments = commentsRes.status === "fulfilled" ? (commentsRes.value.comments || []) : [];
    state.taskAuditLogs = auditRes.status === "fulfilled" ? (auditRes.value.auditLogs || []) : [];
    state.taskActivities = historyRes.status === "fulfilled" ? (historyRes.value.activities || []) : [];
  } catch {
    state.taskComments = [];
    state.taskAuditLogs = [];
    state.taskActivities = [];
  }
}

async function handleCommentSubmit(form) {
  const taskId = Number(form.dataset.taskId);
  const textarea = form.querySelector('textarea[name="content"]');
  const content = textarea?.value?.trim();
  if (!content) return;
  const submitButton = form.querySelector('button[type="submit"]');
  if (submitButton) submitButton.disabled = true;
  try {
    await apiRequest(`/api/tasks/${taskId}/comments`, {
      method: "POST",
      body: JSON.stringify({ content }),
    });
    textarea.value = "";
    await loadTaskDetails(taskId);
    render();
    showToast("Comment posted.", "success");
  } catch (error) {
    if (submitButton) submitButton.disabled = false;
    showToast(error.message || "Could not post comment.", "error");
  }
}

async function deleteTaskComment(taskId, commentId) {
  if (!window.confirm("Delete this comment?")) return;
  try {
    await apiRequest(`/api/tasks/${taskId}/comments/${commentId}`, {
      method: "DELETE",
    });
    await loadTaskDetails(taskId);
    render();
    showToast("Comment deleted.", "success");
  } catch (error) {
    showToast(error.message || "Could not delete comment.", "error");
  }
}

app.addEventListener("submit", (event) => {
  if (event.target.id === "auth-form") {
    handleAuthSubmit(event);
  } else if (event.target.id === "record-form") {
    event.preventDefault();
    saveRecord(event.target);

  } else if (event.target.id === "task-comment-form") {
    handleCommentSubmit(event);

  } else if (event.target.id === "add-comment-form") {
    event.preventDefault();
    handleCommentSubmit(event.target);
  } else if (event.target.id === "password-form") {
    event.preventDefault();
    handlePasswordSubmit(event.target);

  }
});

app.addEventListener("click", (event) => {
  const toggle = event.target.closest("[data-toggle-password]");
  if (toggle) {
    const input = document.getElementById(toggle.dataset.togglePassword);
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    toggle.textContent = show ? "Hide" : "Show";
    toggle.setAttribute("aria-label", `${show ? "Hide" : "Show"} ${input.id.replace("-", " ")}`);
    return;
  }

  const loginRoleButton = event.target.closest("[data-login-role]");
  if (loginRoleButton) {
    state.loginRole = loginRoleButton.dataset.loginRole;
    state.notice = null;
    render();
    return;
  }

  const pageButton = event.target.closest("[data-page]");
  if (pageButton) {
    event.preventDefault();
    const nextPage = pageButton.dataset.page;
    if (nextPage === "login" || nextPage === "signup") {
      state.notice = null;
      setPage(nextPage);
      return;
    }
    if (state.user?.role !== "ADMIN" && nextPage !== "tasks") {
      state.accessMessage = "";
      setPage("tasks");
      return;
    }
    if (nextPage !== "dashboard" && !featureDetails[nextPage]) {
      state.accessMessage = "You do not have permission to access that workspace area.";
      render();
      return;
    }
    state.accessMessage = "";
    setPage(nextPage);
    return;
  }

  const actionButtonElement = event.target.closest("[data-action]");
  const action = actionButtonElement?.dataset.action;
  if (!action) return;

  if (action === "logout") {
    logout();
  } else if (action === "save-task-status") {
    saveAssignedTaskStatus(actionButtonElement.dataset.id);
  } else if (action === "set-task-tab") {
    state.taskDetailTab = actionButtonElement.dataset.tab;
    render();
  } else if (action === "delete-comment") {
    const taskId = Number(actionButtonElement.dataset.taskId);
    const commentId = Number(actionButtonElement.dataset.commentId);
    deleteTaskComment(taskId, commentId);
  } else if (action === "toggle-nav") {
    state.mobileNavOpen = !state.mobileNavOpen;
    render();
  } else if (action === "close-nav") {
    state.mobileNavOpen = false;
    render();
  } else if (action === "open-password-modal") {
    state.modal = { entity: "password" };
    render();
    document.getElementById("modal-currentPassword")?.focus();
  } else if (action === "create-record") {
    const entity = actionButtonElement.dataset.entity;
    if (canManage(entity)) openModal(entity);
    else showToast("You do not have permission to create this type of record.", "error");
  } else if (action === "create-task-for-project") {
    const projId = Number(actionButtonElement.dataset.id);
    state.modal = { entity: "task", id: null, view: false };
    render();
    setTimeout(() => {
      const projSelect = document.querySelector("#modal-projectId");
      if (projSelect) projSelect.value = projId;
    }, 50);
  } else if (action === "close-modal") {
    state.modal = null;
    render();
  } else if (action === "backdrop-close" && event.target === actionButtonElement) {
    state.modal = null;
    render();

  } else if (action === "set-task-view") {
    state.taskView = actionButtonElement.dataset.view;
    render();
  } else if (action === "toggle-select-task") {
    const id = Number(actionButtonElement.dataset.id);
    if (state.selectedTaskIds.has(id)) {
      state.selectedTaskIds.delete(id);
    } else {
      state.selectedTaskIds.add(id);
    }
    render();
  } else if (action === "toggle-select-all") {
    const q = state.search.trim().toLowerCase();
    const visibleTasks = workspaceData.tasks.filter((task) => {
      const proj = projectById(task.projectId);
      const projName = task.projectName || proj?.name || "";
      const empName = labelForEmployee(task.assigneeId);
      const searchBlob = `${task.name} ${task.description || ""} ${projName} ${empName} ${task.priority} ${task.status}`.toLowerCase();
      const matchesSearch = !q || searchBlob.includes(q);
      const matchesPriority = state.priorityFilter === "All" || task.priority === state.priorityFilter;
      const matchesProject = state.projectFilter === "All" || String(task.projectId) === state.projectFilter;
      const matchesStatus = state.statusFilter === "All" || task.status === state.statusFilter;
      return matchesSearch && matchesPriority && matchesProject && (state.taskView === "kanban" || matchesStatus);
    });
    if (visibleTasks.every((t) => state.selectedTaskIds.has(t.id))) {
      visibleTasks.forEach((t) => state.selectedTaskIds.delete(t.id));
    } else {
      visibleTasks.forEach((t) => state.selectedTaskIds.add(t.id));
    }
    render();
  } else if (action === "clear-selection") {
    state.selectedTaskIds.clear();
    render();
  } else if (action === "bulk-status") {
    handleBulkStatus(actionButtonElement.dataset.status);
  } else if (action === "bulk-delete") {
    handleBulkDelete();
  } else if (action === "view-task") {
    openTaskDetail(actionButtonElement.dataset.id);
  } else if (action === "quick-move-task") {
    moveTaskStatus(Number(actionButtonElement.dataset.id), actionButtonElement.dataset.status);
  } else if (action === "toggle-recurrence-options") {
    const subfields = document.getElementById("recurrence-subfields");
    if (subfields) {
      subfields.classList.toggle("is-hidden", !actionButtonElement.checked);
    }


  } else if (action === "view-project-page") {
    event.preventDefault();
    const pid = Number(actionButtonElement.dataset.id);
    state.modal = null;
    setPage("project-detail", { projectId: pid });
  } else if (action === "back-to-projects") {
    setPage("projects");
  } else if (action === "set-employee-view") {
    state.employeeViewMode = actionButtonElement.dataset.mode;
    render();
  } else if (action === "set-team-view") {
    state.teamViewMode = actionButtonElement.dataset.mode;
    render();
  } else if (action === "assign-team-members") {
    openTeamAssignmentModal(actionButtonElement.dataset.id);
  } else if (action === "quick-remove-team-member") {
    const teamId = Number(actionButtonElement.dataset.teamId);
    const empId = Number(actionButtonElement.dataset.empId);
    const team = teamById(teamId);
    if (!team) return;
    const newMembers = team.memberIds.filter((id) => id !== empId);
    apiRequest(`/api/teams/${teamId}/members`, {
      method: "PATCH",
      body: JSON.stringify({ memberIds: newMembers }),
    }).then(async () => {
      await loadWorkspaceData();
      render();
      showToast("Member removed from team.", "success");
    }).catch((err) => showToast(err.message, "error"));
  } else if (action === "quick-edit-progress") {
    openQuickProgressModal(actionButtonElement.dataset.id);
  } else if (action === "save-quick-progress") {
    const pid = Number(actionButtonElement.dataset.id);
    const inputVal = document.querySelector("#quick-progress-number")?.value;
    saveProjectProgress(pid, inputVal);
  } else if (action === "save-detail-progress") {
    const pid = Number(actionButtonElement.dataset.id);
    const inputVal = document.querySelector("#detail-number")?.value;
    saveProjectProgress(pid, inputVal);
  } else if (action === "set-progress-preset") {
    const val = Number(actionButtonElement.dataset.val);
    const slider = document.querySelector("#detail-slider");
    const numInput = document.querySelector("#detail-number");
    const label = document.querySelector("#slider-val-label");
    if (slider) slider.value = val;
    if (numInput) numInput.value = val;
    if (label) label.textContent = `${val}%`;
  } else if (action === "assignment-add-one") {
    state.selectedMemberIds.add(Number(actionButtonElement.dataset.id));
    render();
  } else if (action === "assignment-remove-one") {
    state.selectedMemberIds.delete(Number(actionButtonElement.dataset.id));
    render();
  } else if (action === "assignment-add-all") {
    const deptFilter = state.assignmentDeptFilter || "All";
    const q = (state.assignmentSearch || "").trim().toLowerCase();
    workspaceData.employees.forEach((emp) => {
      if (emp.status === "Active" && (deptFilter === "All" || emp.department === deptFilter)) {
        if (!q || `${emp.name} ${emp.title} ${emp.department}`.toLowerCase().includes(q)) {
          state.selectedMemberIds.add(emp.id);
        }
      }
    });
    render();
  } else if (action === "assignment-remove-all") {
    state.selectedMemberIds.clear();
    render();
  } else if (action === "save-team-assignment") {
    saveTeamAssignments(actionButtonElement.dataset.id);
 main
  } else if (["view-employee", "edit-employee", "toggle-employee", "view-team", "edit-team", "delete-team", "view-project", "edit-project", "delete-project", "edit-task", "complete-task", "delete-task"].includes(action)) {

  } else if (["view-employee", "edit-employee", "toggle-employee", "view-team", "edit-team", "delete-team", "view-project", "edit-project", "delete-project", "view-task", "edit-task", "complete-task", "delete-task"].includes(action)) {

    handleRecordAction(action, actionButtonElement.dataset.id);
  }
});

app.addEventListener("input", (event) => {
  const target = event.target;
  if (target.matches("[data-search]")) {
    state.search = target.value;
    const query = state.search.trim().toLowerCase();
    let visibleCount = 0;
    document.querySelectorAll("#record-table tr").forEach((row) => {
      const match = (row.dataset.searchText || "").includes(query);
      row.hidden = !match;
      if (match) visibleCount += 1;
    });
    const emptyState = document.querySelector(".table-empty");
    if (emptyState) emptyState.hidden = visibleCount > 0;
  } else if (target.matches('[data-action="search-assignment"]')) {
    state.assignmentSearch = target.value;
    render();
    const searchInput = document.querySelector('[data-action="search-assignment"]');
    if (searchInput) {
      searchInput.focus();
      searchInput.setSelectionRange(state.assignmentSearch.length, state.assignmentSearch.length);
    }
  } else if (target.matches('[data-action="slide-detail-progress"]')) {
    const val = target.value;
    const numInput = document.querySelector("#detail-number");
    const label = document.querySelector("#slider-val-label");
    if (numInput) numInput.value = val;
    if (label) label.textContent = `${val}%`;
  } else if (target.matches('[data-action="input-detail-progress"]')) {
    const val = Math.min(100, Math.max(0, Number(target.value) || 0));
    const slider = document.querySelector("#detail-slider");
    const label = document.querySelector("#slider-val-label");
    if (slider) slider.value = val;
    if (label) label.textContent = `${val}%`;
  }
});

app.addEventListener("change", (event) => {
  const target = event.target;
  if (target.matches('[data-action="filter-status"]')) {
    state.statusFilter = target.value;
    render();
  } else if (target.matches('[data-action="filter-department"]')) {
    state.departmentFilter = target.value;
    render();

  } else if (event.target.matches('[data-action="filter-priority"]')) {
    state.priorityFilter = event.target.value;
    render();
  } else if (event.target.matches('[data-action="filter-project"]')) {
    state.projectFilter = event.target.value;
    render();
  } else if (event.target.matches('[data-action="bulk-assign"]')) {
    if (event.target.value) {
      handleBulkAssign(event.target.value);
    }
  } else if (event.target.matches('[data-action="toggle-recurrence-options"]')) {
    const subfields = document.getElementById("recurrence-subfields");
    if (subfields) {
      subfields.classList.toggle("is-hidden", !event.target.checked);
    }

  } else if (target.matches('[data-action="filter-assignment-dept"]')) {
    state.assignmentDeptFilter = target.value;
    render();
  } else if (target.matches('[data-action="quick-change-status"]')) {
    const pid = Number(target.dataset.id);
    const newStatus = target.value;
    apiRequest(`/api/projects/${pid}`, {
      method: "PATCH",
      body: JSON.stringify({ status: newStatus }),
    }).then(async () => {
      await loadWorkspaceData();
      render();
      showToast("Project status updated.", "success");
    }).catch((err) => showToast(err.message, "error"));
 main
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && state.modal) {
    state.modal = null;
    render();
  }
});

restoreSession();
