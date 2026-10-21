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
};

const workspaceData = { employees: [], teams: [], projects: [], tasks: [] };

const featureDetails = {
  employees: {
    title: "Employee management",
    description: "Manage employee profiles and their workspace access.",
    icon: "♙",
  },
  teams: {
    title: "Team management",
    description: "Organize people into teams and assign team managers.",
    icon: "♧",
  },
  projects: {
    title: "Project Management",
    description: "Track project ownership, status, and progress.",
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

function setPage(page) {
  if (state.user && state.user.role !== "ADMIN" && page !== "tasks" && page !== "login") {
    state.page = "tasks";
  } else {
    state.page = page;
  }
  state.mobileNavOpen = false;
  state.search = "";
  state.statusFilter = "All";
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

function openModal(entity, id = null, view = false) {
  state.modal = { entity, id: id === null ? null : Number(id), view };
  render();
  document.querySelector(".modal-card input:not([type=checkbox]), .modal-card select")?.focus();
}

function menuMarkup(activePage) {
  const icons = { dashboard: "⌂", employees: "♙", teams: "♧", projects: "▧", tasks: "✓" };
  const isAdmin = state.user.role === "ADMIN";
  const items = [
    ...(isAdmin ? [["dashboard", "Management Dashboard"]] : []),
    ...visibleFeatures().map(([key, details]) => [key, details.title]),
  ];

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
          <button class="nav-link ${activePage === key ? "active" : ""}" type="button" data-page="${key}" ${activePage === key ? 'aria-current="page"' : ""}>
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
    employees: ["Manage your people", "Add, edit, view, and deactivate employees."],
    teams: ["Organize your teams", "Create teams, assign managers, and manage members."],
    projects: ["Deliver projects", "Create projects, assign teams, and track status."],
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
            <button class="mini-project" type="button" data-action="view-project" data-id="${project.id}">
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

function featurePageMarkup(key) {
  const details = featureDetails[key];
  if (!details || (state.user.role !== "ADMIN" && key !== "tasks")) {
    return `<div class="form-message error" role="alert">You do not have access to this workspace area.</div>`;
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
  let headings = [];
  let rows = [];

  if (key === "employees") {
    headings = ["Employee", "Department", "Role", "Status", "Actions"];
    rows = workspaceData.employees.map((employee) => rowMarkup([
      `<div class="person-cell"><span class="avatar">${escapeHtml(getInitials(employee.name))}</span><span><strong>${escapeHtml(employee.name)}</strong><small>${escapeHtml(employee.email)}</small></span></div>`,
      escapeHtml(employee.department),
      `<span class="status-badge">${escapeHtml(employee.role)}</span>`,
      `<span class="status-badge ${employee.status === "Active" ? "status-good" : "status-muted"}">${escapeHtml(employee.status)}</span>`,
      `<div class="row-actions">${actionButton("view-employee", employee.id, "View")}${canEdit ? actionButton("edit-employee", employee.id, "Edit") : ""}${canEdit ? actionButton("toggle-employee", employee.id, employee.status === "Active" ? "Deactivate" : "Activate", employee.status === "Active" ? "danger" : "") : ""}</div>`,
    ], `${employee.name} ${employee.email} ${employee.department} ${employee.role} ${employee.status}`));
  } else if (key === "teams") {
    headings = ["Team", "Manager", "Members", "Actions"];
    rows = workspaceData.teams.map((team) => rowMarkup([
      `<strong>${escapeHtml(team.name)}</strong><small class="cell-description">${escapeHtml(team.description)}</small>`,
      escapeHtml(labelForEmployee(team.managerId)),
      `<span class="count-pill">${team.memberIds.length} ${team.memberIds.length === 1 ? "member" : "members"}</span>`,
      `<div class="row-actions">${actionButton("view-team", team.id, "View")}${canEdit ? actionButton("edit-team", team.id, "Edit") : ""}${canEdit ? actionButton("delete-team", team.id, "Delete", "danger") : ""}</div>`,
    ], `${team.name} ${team.description} ${labelForEmployee(team.managerId)} ${team.memberIds.map(labelForEmployee).join(" ")}`));
  } else if (key === "projects") {
    headings = ["Project", "Team", "Due date", "Progress", "Status", "Actions"];
    rows = workspaceData.projects.map((project) => rowMarkup([
      `<strong>${escapeHtml(project.name)}</strong><small class="cell-description">${escapeHtml(project.description)}</small>`,
      escapeHtml(labelForTeam(project.teamId)),
      escapeHtml(project.dueDate || "Not set"),
      `<div class="table-progress"><span class="progress-track"><span style="width:${Number(project.progress)}%"></span></span><strong>${Number(project.progress)}%</strong></div>`,
      `<span class="status-badge ${project.status === "On Track" ? "status-good" : project.status === "At Risk" ? "status-warn" : ""}">${escapeHtml(project.status)}</span>`,
      `<div class="row-actions">${actionButton("view-project", project.id, "View")}${canEdit ? actionButton("edit-project", project.id, "Edit") : ""}${canEdit ? actionButton("delete-project", project.id, "Delete", "danger") : ""}</div>`,
    ], `${project.name} ${project.description} ${labelForTeam(project.teamId)} ${project.status}`));
  } else {
    headings = ["Task", "Project", "Assignee", "Due date", "Priority", "Status", "Actions"];
    rows = workspaceData.tasks.map((task) => rowMarkup([
      `<strong>${escapeHtml(task.name)}</strong>`,
      escapeHtml(task.projectName || labelForProject(task.projectId)),
      escapeHtml(labelForEmployee(task.assigneeId)),
      escapeHtml(task.dueDate || "Not set"),
      `<span class="priority-${escapeHtml(task.priority.toLowerCase())}">${escapeHtml(task.priority)}</span>`,
      `${state.user.role === "EMPLOYEE" ? `<select class="task-status-select" aria-label="Status for ${escapeHtml(task.name)}" data-task-status="${task.id}">${["Not Started", "In Progress", "Completed"].map((status) => `<option ${task.status === status ? "selected" : ""}>${status}</option>`).join("")}</select>` : `<span class="status-badge ${task.status === "Completed" ? "status-good" : ""}">${escapeHtml(task.status)}</span>`}`,
      `<div class="row-actions">${state.user.role === "EMPLOYEE" ? `<button class="table-action" type="button" data-action="save-task-status" data-id="${task.id}">Save status</button>` : `${task.status !== "Completed" ? actionButton("complete-task", task.id, "Complete") : ""}${actionButton("edit-task", task.id, "Edit")}${actionButton("delete-task", task.id, "Delete", "danger")}`}</div>`,
    ], `${task.name} ${task.projectName || labelForProject(task.projectId)} ${labelForEmployee(task.assigneeId)} ${task.priority} ${task.status}`));
  }

  const filteredStatus = key === "employees" ? ["All", "Active", "Inactive"]
    : key === "projects" ? ["All", "On Track", "In Progress", "At Risk", "Completed"]
      : key === "tasks" ? ["All", "Not Started", "In Progress", "Completed"] : [];
  const statusKey = key === "employees" ? "status" : key === "projects" ? "status" : "status";
  const searchFilteredRows = rows.filter((row, index) => {
    const record = workspaceData[key][index];
    const matchesStatus = !filteredStatus.length || state.statusFilter === "All" || record[statusKey] === state.statusFilter;
    const matchesSearch = row.toLowerCase().includes(escapeHtml(state.search.trim().toLowerCase()));
    return matchesStatus && matchesSearch;
  }).join("");

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
        <span>${workspaceData[key].length} ${buttonLabel}${workspaceData[key].length === 1 ? "" : "s"}</span>
      </div>
      <div class="feature-toolbar">
        <div class="toolbar-filters">
          <input class="search-box" type="search" data-search="true" aria-label="Search ${escapeHtml(details.title.toLowerCase())}" placeholder="Search ${escapeHtml(details.title.toLowerCase())}" value="${escapeHtml(state.search)}">
          ${filteredStatus.length ? `<select class="filter-select" aria-label="Filter by status" data-action="filter-status">${filteredStatus.map((item) => `<option ${state.statusFilter === item ? "selected" : ""}>${escapeHtml(item)}</option>`).join("")}</select>` : ""}
        </div>
        ${canEdit ? `<button class="button button-primary" type="button" data-action="create-record" data-entity="${entity}">+ Add ${buttonLabel}</button>` : ""}
      </div>
      <div class="table-wrap">
        <table class="data-table">
          <thead><tr>${headings.map((heading) => `<th scope="col">${escapeHtml(heading)}</th>`).join("")}</tr></thead>
          <tbody id="record-table">${searchFilteredRows}</tbody>
        </table>
        <div class="empty-state table-empty" ${searchFilteredRows ? "hidden" : ""}>
          <span class="empty-state-icon" aria-hidden="true">${details.icon}</span>
          <h3>${workspaceData[key].length ? "No matching records" : `No ${escapeHtml(details.title.toLowerCase())} yet`}</h3>
          <p>${workspaceData[key].length ? "Try another search or status filter." : canEdit ? `Create your first ${buttonLabel} to get started.` : "There are no records to display yet."}</p>
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
        ${fieldMarkup("Completion (%)", "progress", record.progress ?? 0, "number", 'min="0" max="100" required')}
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
    </div>`;
}

function detailModalContent(entity, record) {
  if (!record) return `<p class="modal-description">This record is no longer available.</p>`;
  if (entity === "employee") {
    return `<div class="detail-grid">
      <div><span>Employee</span><strong>${escapeHtml(record.name)}</strong></div>
      <div><span>Email</span><strong>${escapeHtml(record.email)}</strong></div>
      <div><span>Department</span><strong>${escapeHtml(record.department)}</strong></div>
      <div><span>Job title</span><strong>${escapeHtml(record.title)}</strong></div>
      <div><span>Role</span><strong>${escapeHtml(record.role)}</strong></div>
      <div><span>Status</span><strong>${escapeHtml(record.status)}</strong></div>
      <div><span>Start date</span><strong>${escapeHtml(record.startDate || "Not set")}</strong></div>
    </div>`;
  }
  if (entity === "team") {
    const members = record.memberIds.map(employeeById).filter(Boolean);
    return `<p class="modal-description">${escapeHtml(record.description || "No description provided.")}</p>
      <div class="detail-grid">
        <div><span>Manager</span><strong>${escapeHtml(labelForEmployee(record.managerId))}</strong></div>
        <div><span>Members</span><strong>${members.length}</strong></div>
      </div>
      <h3 class="modal-section-title">Team members</h3>
      ${members.length ? `<ul class="member-list">${members.map((employee) => `<li><span class="avatar">${escapeHtml(getInitials(employee.name))}</span><span><strong>${escapeHtml(employee.name)}</strong><small>${escapeHtml(employee.title)}</small></span></li>`).join("")}</ul>` : `<p class="muted-copy">No members assigned yet.</p>`}`;
  }
  if (entity === "project") {
    const projectTasks = workspaceData.tasks.filter((task) => task.projectId === record.id);
    const team = teamById(record.teamId);
    const members = team ? team.memberIds.map(employeeById).filter(Boolean) : [];
    return `<p class="modal-description">${escapeHtml(record.description || "No description provided.")}</p>
      <div class="project-progress-detail"><div><strong>${Number(record.progress)}%</strong><span>complete</span></div><div class="progress-track"><span style="width:${Number(record.progress)}%"></span></div></div>
      <div class="detail-grid">
        <div><span>Team</span><strong>${escapeHtml(labelForTeam(record.teamId))}</strong></div>
        <div><span>Manager</span><strong>${escapeHtml(labelForEmployee(record.managerId))}</strong></div>
        <div><span>Status</span><strong>${escapeHtml(record.status)}</strong></div>
        <div><span>Timeline</span><strong>${escapeHtml(record.startDate || "Not set")} → ${escapeHtml(record.dueDate || "Not set")}</strong></div>
      </div>
      <h3 class="modal-section-title">Team members</h3>
      <p class="muted-copy">${members.length ? members.map((employee) => escapeHtml(employee.name)).join(", ") : "No team members assigned."}</p>
      <h3 class="modal-section-title">Project tasks</h3>
      ${projectTasks.length ? `<ul class="project-task-list">${projectTasks.map((task) => `<li><span class="task-dot ${task.status === "Completed" ? "is-done" : ""}"></span><span>${escapeHtml(task.name)}</span><small>${escapeHtml(task.status)}</small></li>`).join("")}</ul>` : `<p class="muted-copy">No tasks assigned to this project yet.</p>`}`;
  }
  return "";
}

function modalMarkup() {
  if (!state.modal) return "";
  const { entity, id, view } = state.modal;
  const pluralKey = `${entity}s`;
  const record = id === null ? {} : workspaceData[pluralKey]?.find((item) => item.id === id);
  const titleNames = { employee: "employee", team: "team", project: "project", task: "task" };
  const titleName = titleNames[entity] || entity;
  const title = view ? `${entity === "employee" ? "Employee" : entity[0].toUpperCase() + entity.slice(1)} details`
    : `${id === null ? "Add" : "Edit"} ${titleName}`;

  return `<div class="modal-backdrop" data-action="backdrop-close">
    <section class="modal-card" role="dialog" aria-modal="true" aria-labelledby="record-modal-title">
      <header class="modal-header"><div><span class="eyebrow">${view ? "RECORD DETAILS" : "WORKSPACE"}</span><h2 id="record-modal-title">${escapeHtml(title)}</h2></div><button class="modal-close" type="button" data-action="close-modal" aria-label="Close dialog">×</button></header>
      ${view ? `<div class="modal-content">${detailModalContent(entity, record)}</div>
        <footer class="modal-footer"><button class="button button-quiet" type="button" data-action="close-modal">Close</button>${canManage(entity) ? `<button class="button button-primary" type="button" data-action="edit-${entity}" data-id="${id}">Edit ${titleName}</button>` : ""}</footer>`
      : `<form id="record-form" data-entity="${entity}" data-id="${id === null ? "" : id}">
        <div class="modal-content">${modalFormFields(entity, record)}</div>
        <footer class="modal-footer"><button class="button button-quiet" type="button" data-action="close-modal">Cancel</button><button class="button button-primary" type="submit">${id === null ? "Create" : "Save changes"}</button></footer>
      </form>`}
    </section>
  </div>`;
}

function mainContentMarkup() {
  const page = state.user.role === "ADMIN" ? state.page : "tasks";
  const title = page === "dashboard" ? "Management Dashboard" : featureDetails[page]?.title || "Management Dashboard";
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
            <span class="avatar" aria-hidden="true">${escapeHtml(getInitials(state.user.name))}</span>
          </div>
        </header>
        <main id="main" class="content">
          ${state.accessMessage ? `<div class="form-message error" role="alert">${escapeHtml(state.accessMessage)}</div>` : ""}
          ${page === "dashboard" ? dashboardPageMarkup() : featurePageMarkup(page)}
        </main>
      </div>
    </div>
    ${modalMarkup()}`;
}

function render() {
  if (state.user) {
    app.innerHTML = mainContentMarkup();
  } else {
    app.innerHTML = authPanelMarkup();
  }
}

function setFormBusy(form, isBusy, label) {
  const button = form.querySelector('button[type="submit"]');
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
    record.projectId = record.projectId ? Number(record.projectId) : null;
    record.assigneeId = record.assigneeId ? Number(record.assigneeId) : null;
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
    state.search = "";
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

  if (action.startsWith("view-")) {
    openModal(entity, recordId, true);
  } else if (action.startsWith("edit-")) {
    openEdit(entity, recordId);
  } else if (action === "toggle-employee") {
    const employee = employeeById(recordId);
    if (!employee) return;
    const nextStatus = employee.status === "Active" ? "Inactive" : "Active";
    if (!window.confirm(`${nextStatus === "Inactive" ? "Deactivate" : "Activate"} ${employee.name}?`)) return;
    try {
      await apiRequest(`/api/employees/${recordId}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status: nextStatus }),
      });
      await loadWorkspaceData();
      render();
      showToast(`${employee.name} is now ${nextStatus.toLowerCase()}.`, "success");
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
    if (error.status === 401) {
      state.user = null;
      state.page = "login";
      state.notice = null;
      render();
      return;
    }
    if (error.status === 404 || error.status === 501) {
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

app.addEventListener("submit", (event) => {
  if (event.target.id === "auth-form") {
    handleAuthSubmit(event);
  } else if (event.target.id === "record-form") {
    event.preventDefault();
    saveRecord(event.target);
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
  if (action === "logout") {
    logout();
  } else if (action === "save-task-status") {
    saveAssignedTaskStatus(actionButtonElement.dataset.id);
  } else if (action === "toggle-nav") {
    state.mobileNavOpen = !state.mobileNavOpen;
    render();
  } else if (action === "close-nav") {
    state.mobileNavOpen = false;
    render();
  } else if (action === "create-record") {
    const entity = actionButtonElement.dataset.entity;
    if (canManage(entity)) openModal(entity);
    else showToast("You do not have permission to create this type of record.", "error");
  } else if (action === "close-modal") {
    state.modal = null;
    render();
  } else if (action === "backdrop-close" && event.target === actionButtonElement) {
    state.modal = null;
    render();
  } else if (["view-employee", "edit-employee", "toggle-employee", "view-team", "edit-team", "delete-team", "view-project", "edit-project", "delete-project", "edit-task", "complete-task", "delete-task"].includes(action)) {
    handleRecordAction(action, actionButtonElement.dataset.id);
  }
});

app.addEventListener("input", (event) => {
  if (!event.target.matches("[data-search]")) return;
  state.search = event.target.value;
  const query = state.search.trim().toLowerCase();
  let visibleCount = 0;
  document.querySelectorAll("#record-table tr").forEach((row) => {
    row.hidden = !row.dataset.searchText.includes(query);
    if (!row.hidden) visibleCount += 1;
  });
  const emptyState = document.querySelector(".table-empty");
  if (emptyState) emptyState.hidden = visibleCount > 0;
  const count = document.querySelector(".section-title-row > span");
  if (count) count.textContent = `${visibleCount} ${state.page === "employees" ? "employee" : state.page === "teams" ? "team" : state.page === "projects" ? "project" : "task"}${visibleCount === 1 ? "" : "s"}`;
});

app.addEventListener("change", (event) => {
  if (event.target.matches('[data-action="filter-status"]')) {
    state.statusFilter = event.target.value;
    render();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && state.modal) {
    state.modal = null;
    render();
  }
});

restoreSession();
