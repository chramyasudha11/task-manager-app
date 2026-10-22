/**
 * Member 6 — Admin + Manager Dashboard Controller
 * Manages KPI metrics, 7 Chart.js visualizations, 48-employee table,
 * and dedicated Manager View.
 */

let chartInstances = {};
let allEmployees = [];
let filteredEmployees = [];
let currentPage = 1;
const pageSize = 10;
let sortField = "assigned";
let sortAsc = false;
let currentTab = "admin"; // 'admin', 'manager', 'employees'

// Document Ready
document.addEventListener("DOMContentLoaded", async () => {
  initTheme();
  setupEventListeners();
  await initSessionUser();
  await loadDashboardData();
});

// Theme Management
function initTheme() {
  const saved = localStorage.getItem("taskspace_theme");
  if (saved === "dark") {
    document.body.classList.add("dark");
  }
}

function toggleTheme() {
  document.body.classList.toggle("dark");
  const isDark = document.body.classList.contains("dark");
  localStorage.setItem("taskspace_theme", isDark ? "dark" : "light");
  
  // Re-render charts with theme-adjusted colors
  updateChartThemes(isDark);
}

// Session & Role Switching
async function initSessionUser() {
  try {
    const res = await fetch("/api/dashboard/current-user");
    const data = await res.json();
    if (data.authenticated && data.user) {
      updateUserPersonaUI(data.user);
    }
  } catch (err) {
    console.warn("Could not check current user:", err);
  }
}

function updateUserPersonaUI(user) {
  const nameEl = document.getElementById("active-user-name");
  const roleEl = document.getElementById("active-user-role");
  const avatarEl = document.getElementById("active-user-avatar");
  const selectEl = document.getElementById("persona-role-select");

  if (nameEl) nameEl.textContent = user.name;
  if (roleEl) roleEl.textContent = `${user.role} • ${user.team || 'Management'}`;
  if (avatarEl) {
    const initials = user.name.split(" ").map(n => n[0]).join("").slice(0, 2).toUpperCase();
    avatarEl.textContent = initials;
  }
  if (selectEl) {
    selectEl.value = user.role.toUpperCase();
  }
}

async function handleRoleSwitch(targetRole) {
  try {
    const res = await fetch("/api/dashboard/switch-role", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role: targetRole })
    });
    const data = await res.json();
    if (res.ok && data.user) {
      updateUserPersonaUI(data.user);
      showToast(`Switched profile to ${data.user.name} (${data.user.role})`);
      
      // Auto switch view tab if manager is selected
      if (targetRole === "MANAGER" && currentTab !== "manager") {
        switchTab("manager");
      } else if (targetRole === "ADMIN" && currentTab === "manager") {
        switchTab("admin");
      }
    }
  } catch (err) {
    showToast("Error switching role", true);
  }
}

// Setup DOM Event Listeners
function setupEventListeners() {
  // Theme toggle
  document.getElementById("theme-toggle")?.addEventListener("click", toggleTheme);

  // Refresh
  document.getElementById("refresh-btn")?.addEventListener("click", async () => {
    showToast("Refreshing live analytics...");
    await loadDashboardData();
  });

  // Export
  document.getElementById("export-csv-btn")?.addEventListener("click", exportEmployeesCSV);

  // Tab switching
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const tab = btn.getAttribute("data-tab");
      switchTab(tab);
    });
  });

  // Role selector
  document.getElementById("persona-role-select")?.addEventListener("change", (e) => {
    handleRoleSwitch(e.target.value);
  });

  // Employee Table controls
  document.getElementById("emp-search")?.addEventListener("input", (e) => {
    filterEmployees(e.target.value, document.getElementById("team-filter")?.value, document.getElementById("overdue-toggle")?.checked);
  });

  document.getElementById("team-filter")?.addEventListener("change", (e) => {
    filterEmployees(document.getElementById("emp-search")?.value, e.target.value, document.getElementById("overdue-toggle")?.checked);
  });

  document.getElementById("overdue-toggle")?.addEventListener("change", (e) => {
    filterEmployees(document.getElementById("emp-search")?.value, document.getElementById("team-filter")?.value, e.target.checked);
  });

  // Modal close
  document.getElementById("close-modal-btn")?.addEventListener("click", () => {
    document.getElementById("emp-modal")?.classList.remove("open");
  });
  document.getElementById("emp-modal")?.addEventListener("click", (e) => {
    if (e.target.id === "emp-modal") {
      document.getElementById("emp-modal").classList.remove("open");
    }
  });
}

function switchTab(tab) {
  currentTab = tab;
  document.querySelectorAll(".tab-btn").forEach(b => {
    b.classList.toggle("active", b.getAttribute("data-tab") === tab);
  });

  const adminSec = document.getElementById("admin-charts-section");
  const mgrSec = document.getElementById("manager-view-section");
  const empSec = document.getElementById("employee-table-section");

  if (tab === "admin") {
    if (adminSec) adminSec.style.display = "flex";
    if (mgrSec) mgrSec.style.display = "none";
    if (empSec) empSec.style.display = "block";
  } else if (tab === "manager") {
    if (adminSec) adminSec.style.display = "none";
    if (mgrSec) mgrSec.style.display = "flex";
    if (empSec) empSec.style.display = "none";
  } else if (tab === "employees") {
    if (adminSec) adminSec.style.display = "none";
    if (mgrSec) mgrSec.style.display = "none";
    if (empSec) empSec.style.display = "block";
    empSec.scrollIntoView({ behavior: "smooth" });
  }
}

// Load All Dashboard Data
async function loadDashboardData() {
  try {
    const [kpiRes, chartsRes, empRes, mgrRes] = await Promise.all([
      fetch("/api/dashboard/kpi"),
      fetch("/api/dashboard/charts"),
      fetch("/api/dashboard/employees"),
      fetch("/api/dashboard/manager-view")
    ]);

    const kpi = await kpiRes.json();
    const charts = await chartsRes.json();
    const empData = await empRes.json();
    const mgrData = await mgrRes.json();

    renderKPIs(kpi);
    renderCharts(charts);
    initEmployeesTable(empData.employees || []);
    renderManagerView(mgrData);

  } catch (err) {
    console.error("Dashboard data load error:", err);
    showToast("Error loading dashboard data", true);
  }
}

// Render KPI Cards
function renderKPIs(kpi) {
  document.getElementById("kpi-total-employees").textContent = kpi.total_employees;
  document.getElementById("kpi-total-tasks").textContent = kpi.total_tasks;
  document.getElementById("kpi-completed-tasks").textContent = kpi.completed;
  document.getElementById("kpi-overdue-tasks").textContent = kpi.overdue;

  // Secondary counts
  document.getElementById("aux-in-progress").textContent = kpi.in_progress;
  document.getElementById("aux-pending").textContent = kpi.pending_active;
  document.getElementById("aux-completion-rate").textContent = `${kpi.completion_rate}%`;
  document.getElementById("aux-velocity-score").textContent = `${kpi.team_velocity_score}%`;

  // Badges
  document.getElementById("badge-completion-rate").textContent = `${kpi.completion_rate}% Completed`;
  document.getElementById("badge-overdue-rate").textContent = `${kpi.overdue_rate}% of Total`;
}

// Chart.js Theme Helpers
function getChartThemeColors(isDark) {
  return {
    textColor: isDark ? "#a3a192" : "#737367",
    gridColor: isDark ? "#33352b" : "#e5dfd0",
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
  };
}

function updateChartThemes(isDark) {
  const theme = getChartThemeColors(isDark);
  Object.values(chartInstances).forEach(chart => {
    if (chart && chart.options) {
      if (chart.options.scales) {
        Object.values(chart.options.scales).forEach(scale => {
          if (scale.ticks) scale.ticks.color = theme.textColor;
          if (scale.grid) scale.grid.color = theme.gridColor;
        });
      }
      if (chart.options.plugins && chart.options.plugins.legend) {
        chart.options.plugins.legend.labels.color = theme.textColor;
      }
      chart.update();
    }
  });
}

// Render All 7 Charts
function renderCharts(data) {
  const isDark = document.body.classList.contains("dark");
  const theme = getChartThemeColors(isDark);

  // 1. Task Completion Trend
  renderTrendChart(data.trend, theme);

  // 2. Pending vs Completed
  renderPendingVsCompletedChart(data.pending_vs_completed, theme);

  // 3. Tasks by Priority
  renderPriorityChart(data.tasks_by_priority, theme);

  // 4. Tasks by Project
  renderProjectChart(data.tasks_by_project, theme);

  // 5. Tasks by Team
  renderTeamChart(data.tasks_by_team, theme);

  // 6. Employee Workload
  renderWorkloadChart(data.employee_workload, theme);

  // 7. Employee Performance
  renderPerformanceChart(data.employee_performance, theme);
}

// 1. Trend Chart
function renderTrendChart(trend, theme) {
  const ctx = document.getElementById("chart-completion-trend")?.getContext("2d");
  if (!ctx) return;
  if (chartInstances.trend) chartInstances.trend.destroy();

  chartInstances.trend = new Chart(ctx, {
    type: "line",
    data: {
      labels: trend.labels,
      datasets: [
        {
          label: "Completed Tasks",
          data: trend.completed,
          borderColor: "#10b981",
          backgroundColor: "rgba(16, 185, 129, 0.12)",
          fill: true,
          tension: 0.35,
          borderWidth: 3,
          pointRadius: 4,
          pointHoverRadius: 6
        },
        {
          label: "Total Created Tasks",
          data: trend.created,
          borderColor: "#69764b",
          backgroundColor: "transparent",
          borderDash: [5, 5],
          tension: 0.35,
          borderWidth: 2,
          pointRadius: 3
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: "top",
          labels: { color: theme.textColor, font: { family: theme.fontFamily, size: 12 } }
        },
        tooltip: {
          backgroundColor: "rgba(30,30,25,0.9)",
          padding: 10,
          cornerRadius: 8
        }
      },
      scales: {
        x: {
          grid: { color: theme.gridColor },
          ticks: { color: theme.textColor, font: { family: theme.fontFamily } }
        },
        y: {
          beginAtZero: true,
          grid: { color: theme.gridColor },
          ticks: { color: theme.textColor, font: { family: theme.fontFamily } }
        }
      }
    }
  });
}

// 2. Pending vs Completed Donut Chart
function renderPendingVsCompletedChart(pvc, theme) {
  const ctx = document.getElementById("chart-pending-completed")?.getContext("2d");
  if (!ctx) return;
  if (chartInstances.pvc) chartInstances.pvc.destroy();

  chartInstances.pvc = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: pvc.labels,
      datasets: [{
        data: pvc.data,
        backgroundColor: ["#10b981", "#f59e0b", "#6b7280", "#ef4444"],
        borderWidth: 0,
        hoverOffset: 4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "74%",
      plugins: {
        legend: {
          position: "bottom",
          labels: { color: theme.textColor, font: { size: 11, family: theme.fontFamily }, boxWidth: 12 }
        }
      }
    }
  });
}

// 3. Priority Chart
function renderPriorityChart(priority, theme) {
  const ctx = document.getElementById("chart-tasks-priority")?.getContext("2d");
  if (!ctx) return;
  if (chartInstances.priority) chartInstances.priority.destroy();

  chartInstances.priority = new Chart(ctx, {
    type: "bar",
    data: {
      labels: priority.labels,
      datasets: [{
        label: "Tasks Count",
        data: priority.data,
        backgroundColor: ["#ef4444", "#f59e0b", "#10b981"],
        borderRadius: 8,
        borderSkipped: false
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: theme.textColor, font: { family: theme.fontFamily, weight: "bold" } }
        },
        y: {
          beginAtZero: true,
          grid: { color: theme.gridColor },
          ticks: { color: theme.textColor, font: { family: theme.fontFamily } }
        }
      }
    }
  });
}

// 4. Project Chart
function renderProjectChart(projects, theme) {
  const ctx = document.getElementById("chart-tasks-project")?.getContext("2d");
  if (!ctx) return;
  if (chartInstances.project) chartInstances.project.destroy();

  chartInstances.project = new Chart(ctx, {
    type: "bar",
    data: {
      labels: projects.labels,
      datasets: [{
        label: "Tasks",
        data: projects.data,
        backgroundColor: "#69764b",
        borderRadius: 6
      }]
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false }
      },
      scales: {
        x: {
          beginAtZero: true,
          grid: { color: theme.gridColor },
          ticks: { color: theme.textColor }
        },
        y: {
          grid: { display: false },
          ticks: { color: theme.textColor, font: { size: 11 } }
        }
      }
    }
  });
}

// 5. Team Chart
function renderTeamChart(teams, theme) {
  const ctx = document.getElementById("chart-tasks-team")?.getContext("2d");
  if (!ctx) return;
  if (chartInstances.team) chartInstances.team.destroy();

  chartInstances.team = new Chart(ctx, {
    type: "bar",
    data: {
      labels: teams.labels,
      datasets: [{
        label: "Assigned Tasks",
        data: teams.data,
        backgroundColor: ["#3b82f6", "#10b981", "#8b5cf6", "#f59e0b", "#ec4899", "#69764b"],
        borderRadius: 8
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: theme.textColor, font: { size: 11 } }
        },
        y: {
          beginAtZero: true,
          grid: { color: theme.gridColor },
          ticks: { color: theme.textColor }
        }
      }
    }
  });
}

// 6. Workload Chart
function renderWorkloadChart(workload, theme) {
  const ctx = document.getElementById("chart-employee-workload")?.getContext("2d");
  if (!ctx) return;
  if (chartInstances.workload) chartInstances.workload.destroy();

  chartInstances.workload = new Chart(ctx, {
    type: "bar",
    data: {
      labels: workload.labels,
      datasets: [
        {
          label: "Active / Pending",
          data: workload.active,
          backgroundColor: "#f59e0b",
          borderRadius: 6
        },
        {
          label: "Completed",
          data: workload.completed,
          backgroundColor: "#10b981",
          borderRadius: 6
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          stacked: true,
          grid: { display: false },
          ticks: { color: theme.textColor, font: { size: 10 } }
        },
        y: {
          stacked: true,
          beginAtZero: true,
          grid: { color: theme.gridColor },
          ticks: { color: theme.textColor }
        }
      },
      plugins: {
        legend: {
          position: "top",
          labels: { color: theme.textColor, font: { size: 11 } }
        }
      }
    }
  });
}

// 7. Performance Chart
function renderPerformanceChart(performance, theme) {
  const ctx = document.getElementById("chart-employee-performance")?.getContext("2d");
  if (!ctx) return;
  if (chartInstances.performance) chartInstances.performance.destroy();

  chartInstances.performance = new Chart(ctx, {
    type: "bar",
    data: {
      labels: performance.labels,
      datasets: [{
        label: "Completion Rate (%)",
        data: performance.rates,
        backgroundColor: "#10b981",
        borderRadius: 6
      }]
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => ` ${ctx.raw}% On-Time Delivery`
          }
        }
      },
      scales: {
        x: {
          min: 0,
          max: 100,
          grid: { color: theme.gridColor },
          ticks: {
            color: theme.textColor,
            callback: v => `${v}%`
          }
        },
        y: {
          grid: { display: false },
          ticks: { color: theme.textColor, font: { size: 11 } }
        }
      }
    }
  });
}

// =========================================================================
// EMPLOYEE TABLE LOGIC
// =========================================================================

function initEmployeesTable(employees) {
  allEmployees = employees;
  filteredEmployees = [...employees];
  currentPage = 1;
  renderTable();
}

function filterEmployees(query = "", team = "", onlyOverdue = false) {
  const q = query.trim().toLowerCase();
  filteredEmployees = allEmployees.filter(emp => {
    const matchesQ = !q ||
      emp.name.toLowerCase().includes(q) ||
      emp.email.toLowerCase().includes(q) ||
      emp.team.toLowerCase().includes(q) ||
      emp.job_title.toLowerCase().includes(q);

    const matchesTeam = !team || emp.team === team;
    const matchesOverdue = !onlyOverdue || emp.overdue > 0;

    return matchesQ && matchesTeam && matchesOverdue;
  });

  currentPage = 1;
  renderTable();
}

function sortTableBy(field) {
  if (sortField === field) {
    sortAsc = !sortAsc;
  } else {
    sortField = field;
    sortAsc = false;
  }

  filteredEmployees.sort((a, b) => {
    let valA = a[field];
    let valB = b[field];

    if (typeof valA === "string") {
      return sortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
    }
    return sortAsc ? valA - valB : valB - valA;
  });

  renderTable();
}

function renderTable() {
  const tbody = document.getElementById("employee-table-body");
  if (!tbody) return;

  const total = filteredEmployees.length;
  const totalPages = Math.ceil(total / pageSize) || 1;
  if (currentPage > totalPages) currentPage = totalPages;

  const start = (currentPage - 1) * pageSize;
  const pageItems = filteredEmployees.slice(start, start + pageSize);

  document.getElementById("emp-count-badge").textContent = `${total} Employees`;
  document.getElementById("showing-range").textContent = total > 0 ? `${start + 1} - ${Math.min(start + pageSize, total)}` : "0";
  document.getElementById("total-emp-count").textContent = total;

  if (pageItems.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:32px;color:var(--text-muted)">No matching employees found.</td></tr>`;
    renderPagination(totalPages);
    return;
  }

  tbody.innerHTML = pageItems.map(emp => {
    const initials = emp.name.split(" ").map(n => n[0]).join("").slice(0, 2).toUpperCase();
    const teamClass = `team-${emp.team.toLowerCase().replace(/[^a-z]/g, "")}`;
    const overdueClass = emp.overdue > 0 ? "num-pill overdue-alert" : "num-pill";

    return `
      <tr data-emp-id="${emp.id}">
        <td>
          <div class="employee-cell">
            <div class="emp-avatar">${initials}</div>
            <div class="emp-details">
              <b>${emp.name}</b>
              <small>${emp.email}</small>
            </div>
          </div>
        </td>
        <td><span class="badge-tag ${teamClass}">${emp.team}</span></td>
        <td><span class="num-pill">${emp.assigned}</span></td>
        <td><span class="num-pill" style="color:var(--green-text);font-weight:700;">${emp.completed}</span></td>
        <td><span class="num-pill">${emp.pending}</span></td>
        <td><span class="${overdueClass}">${emp.overdue}</span></td>
        <td>
          <div class="progress-bar-cell">
            <div class="progress-track">
              <div class="progress-fill" style="width: ${emp.completion_pct}%"></div>
            </div>
            <span style="font-weight:700;font-size:12px;">${emp.completion_pct}%</span>
          </div>
        </td>
      </tr>
    `;
  }).join("");

  // Attach click listeners for employee modal
  tbody.querySelectorAll("tr").forEach(tr => {
    tr.style.cursor = "pointer";
    tr.addEventListener("click", () => {
      const id = parseInt(tr.getAttribute("data-emp-id"), 10);
      const emp = allEmployees.find(e => e.id === id);
      if (emp) openEmployeeModal(emp);
    });
  });

  renderPagination(totalPages);
}

function renderPagination(totalPages) {
  const container = document.getElementById("pagination-btns");
  if (!container) return;

  let html = `
    <button class="page-btn" ${currentPage === 1 ? 'disabled' : ''} onclick="changePage(${currentPage - 1})">Prev</button>
  `;

  for (let p = 1; p <= totalPages; p++) {
    if (p === 1 || p === totalPages || (p >= currentPage - 1 && p <= currentPage + 1)) {
      html += `<button class="page-btn ${p === currentPage ? 'active' : ''}" onclick="changePage(${p})">${p}</button>`;
    } else if (p === currentPage - 2 || p === currentPage + 2) {
      html += `<span style="padding:0 4px;color:var(--text-muted)">...</span>`;
    }
  }

  html += `
    <button class="page-btn" ${currentPage === totalPages ? 'disabled' : ''} onclick="changePage(${currentPage + 1})">Next</button>
  `;

  container.innerHTML = html;
}

window.changePage = function(page) {
  currentPage = page;
  renderTable();
};

window.sortTableBy = sortTableBy;

function openEmployeeModal(emp) {
  const modal = document.getElementById("emp-modal");
  if (!modal) return;

  const initials = emp.name.split(" ").map(n => n[0]).join("").slice(0, 2).toUpperCase();

  document.getElementById("modal-emp-avatar").textContent = initials;
  document.getElementById("modal-emp-name").textContent = emp.name;
  document.getElementById("modal-emp-title").textContent = `${emp.job_title} • ${emp.team}`;
  document.getElementById("modal-emp-email").textContent = emp.email;

  document.getElementById("modal-assigned").textContent = emp.assigned;
  document.getElementById("modal-completed").textContent = emp.completed;
  document.getElementById("modal-pending").textContent = emp.pending;
  document.getElementById("modal-overdue").textContent = emp.overdue;
  document.getElementById("modal-score").textContent = `${emp.performance_score}/100`;

  modal.classList.add("open");
}

function exportEmployeesCSV() {
  if (!allEmployees.length) return;
  const headers = ["Employee Name", "Email", "Role", "Team", "Job Title", "Assigned", "Completed", "Pending", "Overdue", "Completion %"];
  const rows = allEmployees.map(e => [
    `"${e.name}"`,
    `"${e.email}"`,
    `"${e.role}"`,
    `"${e.team}"`,
    `"${e.job_title}"`,
    e.assigned,
    e.completed,
    e.pending,
    e.overdue,
    `"${e.completion_pct}%"`
  ]);

  const csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows.map(r => r.join(","))].join("\n");
  const encodedUri = encodeURI(csvContent);
  const link = document.createElement("a");
  link.setAttribute("href", encodedUri);
  link.setAttribute("download", `taskspace_employees_report_${new Date().toISOString().split("T")[0]}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  showToast("CSV report exported successfully!");
}

// =========================================================================
// MANAGER VIEW LOGIC
// =========================================================================

function renderManagerView(data) {
  // 1. Team Progress Cards
  const progressGrid = document.getElementById("team-progress-grid");
  if (progressGrid && data.team_progress) {
    progressGrid.innerHTML = data.team_progress.map(t => {
      const isOk = t.status === "On Track";
      return `
        <div class="team-card">
          <div class="team-card-top">
            <div>
              <h4>${t.team}</h4>
              <span class="team-lead-text">Lead: ${t.lead} (${t.member_count} members)</span>
            </div>
            <span class="badge-tag" style="background:${isOk ? 'var(--green)' : 'var(--red)'};color:${isOk ? 'var(--green-text)' : 'var(--red-text)'};font-weight:700;">
              ${t.status}
            </span>
          </div>

          <div class="team-stats-row">
            <div><small style="color:var(--text-muted)">Total</small><b>${t.total_tasks}</b></div>
            <div><small style="color:var(--text-muted)">Done</small><b style="color:var(--green-text)">${t.completed}</b></div>
            <div><small style="color:var(--text-muted)">Pending</small><b>${t.pending}</b></div>
            <div><small style="color:var(--text-muted)">Overdue</small><b style="color:${t.overdue > 0 ? 'var(--red-text)' : 'inherit'}">${t.overdue}</b></div>
          </div>

          <div>
            <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px;">
              <span>Completion Rate</span>
              <b>${t.completion_pct}%</b>
            </div>
            <div class="progress-track">
              <div class="progress-fill" style="width:${t.completion_pct}%;background:${isOk ? 'var(--olive)' : '#ef4444'}"></div>
            </div>
          </div>
        </div>
      `;
    }).join("");
  }

  // 2. Team Workload & Capacity Meters
  const workloadList = document.getElementById("team-workload-meters");
  if (workloadList && data.team_workload) {
    workloadList.innerHTML = data.team_workload.map(w => {
      const fillClass = w.capacity_pct >= 85 ? "heavy" : (w.capacity_pct >= 75 ? "high" : "balanced");
      return `
        <div class="workload-item">
          <div>
            <b style="font-size:14px;">${w.team}</b>
            <small style="display:block;color:var(--text-muted);font-size:11px;">${w.active_tasks} active tasks</small>
          </div>
          <div class="meter-track">
            <div class="meter-fill ${fillClass}" style="width:${w.capacity_pct}%"></div>
          </div>
          <div style="text-align:right;">
            <b style="font-size:13px;">${w.capacity_pct}%</b>
            <small style="display:block;font-size:11px;color:var(--text-muted)">${w.load_level}</small>
          </div>
        </div>
      `;
    }).join("");
  }

  // 3. Overdue Tasks Alert List (31 Overdue Tasks)
  const overdueTable = document.getElementById("overdue-tasks-table-body");
  if (overdueTable && data.overdue_tasks) {
    document.getElementById("mgr-overdue-count").textContent = `${data.overdue_tasks.length} Critical Tasks`;
    overdueTable.innerHTML = data.overdue_tasks.map(task => {
      const pClass = task.priority === "High" ? "priority-high-badge" : (task.priority === "Medium" ? "priority-medium-badge" : "priority-low-badge");
      return `
        <tr>
          <td>
            <b style="display:block;font-size:13px;">${task.title}</b>
            <small style="color:var(--text-muted)">Project: ${task.project}</small>
          </td>
          <td><span class="${pClass}">${task.priority}</span></td>
          <td>
            <span style="color:var(--red-text);font-weight:700;">${task.due_date}</span>
            <small style="display:block;color:var(--red-text);font-size:11px;">${task.days_overdue} days late</small>
          </td>
          <td>
            <b>${task.assignee_name}</b>
            <small style="display:block;color:var(--text-muted);font-size:11px;">${task.assignee_team}</small>
          </td>
          <td>
            <button class="btn btn-light" style="padding:4px 8px;font-size:11px;" onclick="pingAssignee('${task.assignee_name}', '${task.title}')">
              🔔 Ping
            </button>
          </td>
        </tr>
      `;
    }).join("");
  }

  // 4. High Priority Tasks
  const highPriorityTable = document.getElementById("high-priority-table-body");
  if (highPriorityTable && data.high_priority_tasks) {
    highPriorityTable.innerHTML = data.high_priority_tasks.map(task => {
      const isDone = task.status === "Completed";
      return `
        <tr>
          <td>
            <b>${task.title}</b>
            <small style="display:block;color:var(--text-muted)">${task.project}</small>
          </td>
          <td>
            <span class="badge-tag" style="background:${isDone ? 'var(--green)' : 'var(--yellow)'};color:${isDone ? 'var(--green-text)' : 'var(--yellow-text)'};font-weight:700;">
              ${task.status}
            </span>
          </td>
          <td>${task.due_date || 'No date'}</td>
          <td>${task.assignee_name} (${task.assignee_team})</td>
        </tr>
      `;
    }).join("");
  }
}

window.pingAssignee = function(name, taskTitle) {
  showToast(`Reminder ping sent to ${name} for "${taskTitle.slice(0, 25)}..."`);
};

// Toast notification helper
function showToast(message, isError = false) {
  let shelf = document.getElementById("toast-shelf");
  if (!shelf) {
    shelf = document.createElement("div");
    shelf.id = "toast-shelf";
    shelf.className = "toast-shelf";
    document.body.appendChild(shelf);
  }

  const toast = document.createElement("div");
  toast.className = `dash-toast${isError ? ' error' : ''}`;
  toast.innerHTML = `
    <span>${isError ? '⚠️' : '✓'}</span>
    <span>${message}</span>
  `;

  shelf.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, 3200);
}
