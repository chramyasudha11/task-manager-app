/*
  Member 6: JavaScript and API Integration
  Connects Member 5's UI to the Flask task APIs.
*/

const API_ENABLED = true;
const STORAGE_KEY = "taskspace_member5_tasks";

const CATEGORIES = [
  "Work",
  "Personal",
  "Education",
  "Project",
  "Coding",
  "Meeting",
  "Assignment",
  "Other"
];

let tasks = [];
let editingId = null;

const selected = new Set();

const filters = {
  search: "",
  category: "",
  priority: "",
  status: "",
  sort: "newest",
  view: "all"
};

const $ = id => document.getElementById(id);

function esc(value = "") {
  return String(value).replace(
    /[&<>"']/g,
    c => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    })[c]
  );
}

function makeId() {
  return window.crypto && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function localDateISO(date = new Date()) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");

  return `${y}-${m}-${d}`;
}

// Convert backend fields into the format used by the UI.
function normalise(task) {
  let labels = task.labels || [];

  if (typeof labels === "string") {
    labels = labels
      .split(",")
      .map(s => s.trim())
      .filter(Boolean);
  }

  const rawCompleted =
    task.completed ?? task.is_completed ?? false;

  const completed =
    rawCompleted === true ||
    rawCompleted === 1 ||
    rawCompleted === "1" ||
    rawCompleted === "true";

  return {
    id: String(task.id ?? task.task_id ?? makeId()),
    title: task.title || "",
    description: task.description || "",
    category: CATEGORIES.includes(task.category)
      ? task.category
      : "Other",
    priority: ["High", "Medium", "Low"].includes(task.priority)
      ? task.priority
      : "Medium",
    due_date: task.due_date || task.dueDate || "",
    notes: task.notes || "",
    labels,
    completed,
    created_at: task.created_at || new Date().toISOString()
  };
}

function toast(message, error = false) {
  const el = document.createElement("div");

  el.className = `toast${error ? " error" : ""}`;
  el.textContent = message;

  $("toast-region").appendChild(el);

  setTimeout(() => el.remove(), 3000);
}

function localSave() {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify(tasks)
  );
}

function initCategoryOptions() {
  $("task-category").innerHTML = CATEGORIES
    .map(c => `<option>${esc(c)}</option>`)
    .join("");

  $("category-filter").innerHTML =
    `<option value="">All categories</option>` +
    CATEGORIES
      .map(c => `<option>${esc(c)}</option>`)
      .join("");
}

// Load tasks through api.js.
async function loadTasks() {
  if (API_ENABLED) {
    try {
      const result = await window.TaskAPI.getTasks();

      tasks = result.map(normalise);

      const currentIds = new Set(
        tasks.map(task => task.id)
      );

      for (const id of selected) {
        if (!currentIds.has(id)) {
          selected.delete(id);
        }
      }
    } catch (error) {
      tasks = [];

      toast(
        `Could not load tasks: ${error.message}`,
        true
      );
    }
  } else {
    tasks = JSON.parse(
      localStorage.getItem(STORAGE_KEY) || "[]"
    ).map(normalise);
  }

  render();
}

function overdue(task) {
  if (!task.due_date || task.completed) {
    return false;
  }

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const due = new Date(
    `${task.due_date}T00:00:00`
  );

  return (
    !Number.isNaN(due.getTime()) &&
    due < today
  );
}

function dateText(date) {
  if (!date) {
    return "No due date";
  }

  const d = new Date(`${date}T00:00:00`);

  return Number.isNaN(d.getTime())
    ? esc(date)
    : d.toLocaleDateString("en-IN", {
        day: "numeric",
        month: "short",
        year: "numeric"
      });
}

function visibleTasks() {
  let list = [...tasks];

  if (filters.category) {
    list = list.filter(
      t => t.category === filters.category
    );
  }

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);

  if (filters.view === "today") {
    list = list.filter(
      t => !t.completed &&
        t.due_date === localDateISO(today)
    );
  }

  if (filters.view === "upcoming") {
    list = list.filter(
      t => !t.completed &&
        t.due_date &&
        new Date(`${t.due_date}T00:00:00`) >= tomorrow
    );
  }

  if (filters.view === "overdue") {
    list = list.filter(overdue);
  }

  if (filters.view === "completed") {
    list = list.filter(t => t.completed);
  }

  if (filters.search) {
    const q = filters.search.toLowerCase();

    list = list.filter(t =>
      [
        t.title,
        t.description,
        t.category,
        t.priority,
        t.notes,
        ...t.labels
      ]
        .join(" ")
        .toLowerCase()
        .includes(q)
    );
  }

  if (filters.priority) {
    list = list.filter(
      t => t.priority === filters.priority
    );
  }

  if (filters.status === "completed") {
    list = list.filter(t => t.completed);
  }

  if (filters.status === "pending") {
    list = list.filter(t => !t.completed);
  }

  if (filters.status === "overdue") {
    list = list.filter(overdue);
  }

  const time = t =>
    new Date(t.created_at || 0).getTime() || 0;

  list.sort((a, b) => {
    if (filters.sort === "title") {
      return a.title.localeCompare(b.title);
    }

    if (filters.sort === "priority") {
      const rank = {
        High: 3,
        Medium: 2,
        Low: 1
      };

      return rank[b.priority] - rank[a.priority];
    }

    if (filters.sort === "due") {
      return (a.due_date || "9999-12-31")
        .localeCompare(b.due_date || "9999-12-31");
    }

    if (filters.sort === "oldest") {
      return time(a) - time(b);
    }

    return time(b) - time(a);
  });

  return list;
}

function renderSidebarCategories() {
  const counts = Object.fromEntries(
    CATEGORIES.map(c => [
      c,
      tasks.filter(t => t.category === c).length
    ])
  );

  $("sidebar-categories").innerHTML =
    CATEGORIES.map(c => `
      <button
        class="category-item ${filters.category === c ? "active" : ""}"
        data-category="${esc(c)}"
      >
        <span class="dot"></span>
        <span>${esc(c)}</span>
        <b>${counts[c]}</b>
      </button>
    `).join("");
}

function renderTask(t) {
  const labelHtml = t.labels.length
    ? `<div class="labels">
        ${t.labels.map(x =>
          `<span class="label-chip">${esc(x)}</span>`
        ).join("")}
       </div>`
    : "";

  return `
    <article class="task-card ${t.completed ? "done" : ""}">
      <input
        class="task-select"
        type="checkbox"
        data-select="${esc(t.id)}"
        aria-label="Select task"
        ${selected.has(t.id) ? "checked" : ""}
      >

      <button
        class="complete-btn"
        data-action="complete"
        data-id="${esc(t.id)}"
        title="Toggle completion"
        aria-label="Toggle completion"
      >${t.completed ? "✓" : ""}</button>

      <div class="task-body">
        <div class="task-title-row">
          <h3 class="task-title">${esc(t.title)}</h3>
          <span class="priority ${t.priority.toLowerCase()}">
            ${esc(t.priority)}
          </span>
        </div>

        ${t.description
          ? `<p class="task-description">${esc(t.description)}</p>`
          : ""}

        <div class="task-meta">
          <span class="category-tag">${esc(t.category)}</span>

          <span class="${overdue(t) ? "overdue" : ""}">
            ${overdue(t) ? "Overdue -+ " : "Due -+ "}
            ${dateText(t.due_date)}
          </span>

          ${t.completed ? "<span>✓ Completed</span>" : ""}
        </div>

        ${labelHtml}

        ${t.notes
          ? `<p class="task-notes">Notes: ${esc(t.notes)}</p>`
          : ""}
      </div>

      <div class="task-actions">
        <button data-action="edit" data-id="${esc(t.id)}">
          Edit
        </button>

        <button data-action="delete" data-id="${esc(t.id)}">
          Delete
        </button>
      </div>
    </article>
  `;
}

function updateViewHeading() {
  const views = {
    all: [
      "All tasks",
      "A little progress every day adds up to big results."
    ],
    today: [
      "Due today",
      "Tasks that need your attention today."
    ],
    upcoming: [
      "Upcoming tasks",
      "Plan ahead with tasks due in the coming days."
    ],
    overdue: [
      "Overdue tasks",
      "Tasks past their due date that need attention."
    ],
    completed: [
      "Completed tasks",
      "A record of the work you have finished."
    ]
  };

  let [title, subtitle] =
    views[filters.view] || views.all;

  if (filters.category) {
    title = filters.category;
    subtitle = `Tasks filed under ${filters.category}.`;
  }

  $("view-title").innerHTML =
    `${esc(title)}<span>.</span>`;

  $("view-subtitle").textContent = subtitle;

  $("view-eyebrow").textContent =
    filters.category
      ? "— CATEGORY VIEW"
      : filters.view === "all"
        ? "— YOUR DAY, YOUR PACE"
        : "— WORKSPACE VIEW";

  const panelTitle = filters.category
    ? `${filters.category} tasks`
    : views[filters.view]
      ? views[filters.view][0]
      : "Your task list";

  document.querySelector(".panel-title h2").textContent =
    panelTitle;
}

function render() {
  updateViewHeading();

  const list = visibleTasks();

  const emptyTitle = tasks.length
    ? "No matching tasks."
    : filters.view === "today"
      ? "Nothing due today."
      : filters.view === "upcoming"
        ? "No upcoming tasks."
        : filters.view === "overdue"
          ? "You're all caught up."
          : filters.view === "completed"
            ? "No completed tasks yet."
            : "A fresh start.";

  const emptyText = tasks.length
    ? "Try changing your search or filters."
    : filters.view === "overdue"
      ? "Great — you have no overdue tasks."
      : filters.view === "completed"
        ? "Complete a task and it will appear here."
        : filters.view === "today"
          ? "Tasks with today's due date will appear here."
          : filters.view === "upcoming"
            ? "Add a future due date to see upcoming work here."
            : "Your list is clear. Add your first task and get things moving.";

  $("task-list").innerHTML = list.length
    ? list.map(renderTask).join("")
    : `
      <div class="empty-state">
        <div class="empty-icon">📋</div>
        <h3>${emptyTitle}</h3>
        <p>${emptyText}</p>
        <button class="btn btn-primary" data-action="new">
          + New task
        </button>
      </div>
    `;

  const completed = tasks.filter(t => t.completed).length;

  $("total-count").textContent = tasks.length;
  $("progress-count").textContent = tasks.length - completed;
  $("completed-count").textContent = completed;
  $("overdue-count").textContent =
    tasks.filter(overdue).length;

  $("visible-count").textContent = list.length;
  $("nav-all-count").textContent = tasks.length;
  $("nav-completed-count").textContent = completed;

  document.querySelectorAll("[data-view]").forEach(b => {
    b.classList.toggle(
      "active",
      b.dataset.view === filters.view && !filters.category
    );
  });

  $("selected-count").textContent = selected.size;
  $("bulk-bar").hidden = selected.size === 0;

  $("select-all").checked =
    list.length > 0 &&
    list.every(t => selected.has(t.id));

  renderSidebarCategories();
}

function openModal(task = null) {
  editingId = task ? task.id : null;

  $("task-form").reset();

  $("modal-title").textContent =
    task ? "Edit task" : "Create a new task";

  const vals = {
    title: task?.title || "",
    description: task?.description || "",
    category: task?.category || CATEGORIES[0],
    priority: task?.priority || "Medium",
    due_date: task?.due_date || "",
    labels: (task?.labels || []).join(", "),
    notes: task?.notes || ""
  };

  Object.entries(vals).forEach(([key, val]) => {
    $("task-form").elements.namedItem(key).value = val;
  });

  $("task-form").elements.namedItem("completed").checked =
    Boolean(task?.completed);

  $("task-modal").hidden = false;

  $("task-form").elements.namedItem("title").focus();
}

function closeModal() {
  $("task-modal").hidden = true;
  editingId = null;
}

// Create and update tasks.
async function saveTask(event) {
  event.preventDefault();

  const data = new FormData(event.currentTarget);

  const payload = {
    title: String(data.get("title") || "").trim(),
    description: String(data.get("description") || "").trim(),
    category: String(data.get("category") || "Other"),
    priority: String(data.get("priority") || "Medium"),
    due_date: String(data.get("due_date") || ""),
    status: data.get("completed") === "on"
      ? "Completed"
      : (
          editingId &&
          tasks.find(task => String(task.id) === String(editingId))?.completed
            ? "Completed"
            : "Pending"
        )
  };

  if (!payload.title) {
    return toast("Task title is required.", true);
  }

  const id = editingId;

  $("save-btn").disabled = true;
  $("save-btn").textContent = "Saving...";

  try {
    if (API_ENABLED) {
      if (id) {
        await window.TaskAPI.updateTask(id, payload);
      } else {
        await window.TaskAPI.createTask(payload);
      }

      await loadTasks();
    } else {
      const localPayload = {
        ...payload,
        completed: payload.status === "Completed",
        labels: String(data.get("labels") || "")
          .split(",")
          .map(x => x.trim())
          .filter(Boolean),
        notes: String(data.get("notes") || "").trim()
      };


      if (id) {
        tasks = tasks.map(task =>
          String(task.id) === String(id)
            ? normalise({ ...task, ...localPayload, id })
            : task
        );
      } else {
        tasks.unshift(
          normalise({
            ...localPayload,
            id: makeId(),
            created_at: new Date().toISOString()
          })
        );
      }

      localSave();
      render();
    }

    closeModal();

    toast(id ? "Task updated." : "Task created.");
  } catch (error) {
    toast(`Could not save task: ${error.message}`, true);
  } finally {
    $("save-btn").disabled = false;
    $("save-btn").textContent = "Save task";
  }
}

// Mark a task completed or pending.
async function completeTask(id) {
  const task = tasks.find(
    item => String(item.id) === String(id)
  );

  if (!task) return;

  try {
    if (API_ENABLED) {
      await window.TaskAPI.toggleTaskCompletion(id, !task.completed);
      await loadTasks();
    } else {
      tasks = tasks.map(item =>
        String(item.id) === String(id)
          ? { ...item, completed: !item.completed }
          : item
      );

      localSave();
      render();
    }
  } catch (error) {
    toast(`Could not update task: ${error.message}`, true);
  }
}

// Delete a single task.
async function deleteTask(id) {
  if (!confirm("Delete this task?")) return;

  try {
    if (API_ENABLED) {
      await window.TaskAPI.deleteTask(id);

      selected.delete(String(id));

      await loadTasks();
    } else {
      tasks = tasks.filter(
        task => String(task.id) !== String(id)
      );

      selected.delete(String(id));

      localSave();
      render();
    }

    toast("Task deleted.");
  } catch (error) {
    toast(`Could not delete task: ${error.message}`, true);
  }
}

// Complete all selected pending tasks.
async function bulkComplete() {
  const chosen = tasks.filter(
    task => selected.has(task.id)
  );

  if (!chosen.length) return;

  try {
    if (API_ENABLED) {
      // Assumes PATCH toggles completion.
      // Do not toggle tasks that are already completed.
      for (const task of chosen) {
        if (!task.completed) {
          await window.TaskAPI.toggleTaskCompletion(task.id, true);
        }
      }

      selected.clear();

      await loadTasks();
    } else {
      tasks = tasks.map(task =>
        selected.has(task.id)
          ? { ...task, completed: true }
          : task
      );

      selected.clear();

      localSave();
      render();
    }

    toast("Selected tasks completed.");
  } catch (error) {
    toast(`Bulk action failed: ${error.message}`, true);
  }
}

// Delete all selected tasks.
async function bulkDelete() {
  if (
    !selected.size ||
    !confirm(`Delete ${selected.size} selected tasks?`)
  ) {
    return;
  }

  const ids = [...selected];

  try {
    if (API_ENABLED) {
      for (const id of ids) {
        await window.TaskAPI.deleteTask(id);
      }

      selected.clear();

      await loadTasks();
    } else {
      tasks = tasks.filter(
        task => !selected.has(task.id)
      );

      selected.clear();

      localSave();
      render();
    }

    toast("Selected tasks deleted.");
  } catch (error) {
    toast(`Could not delete selected tasks: ${error.message}`, true);
  }
}

// =========================================================================
// EVENT LISTENERS & INITIALIZATION
// =========================================================================

function setupEventListeners() {
  // 1. New Task Modal Open & Close
  $("new-task-btn")?.addEventListener("click", () => openModal());
  $("close-modal")?.addEventListener("click", closeModal);
  $("cancel-modal")?.addEventListener("click", closeModal);
  $("task-modal")?.addEventListener("click", (e) => {
    if (e.target.id === "task-modal") closeModal();
  });

  // 2. Task Form Submit
  $("task-form")?.addEventListener("submit", saveTask);

  // 3. Search Filter & Shortcut
  $("search")?.addEventListener("input", (e) => {
    filters.search = e.target.value;
    render();
  });
  window.addEventListener("keydown", (e) => {
    if (e.key === "/" && document.activeElement !== $("search") && !document.querySelector("input:focus, textarea:focus")) {
      e.preventDefault();
      $("search")?.focus();
    }
    if (e.key === "Escape" && !$("task-modal")?.hidden) {
      closeModal();
    }
  });

  // 4. Dropdown Filters
  $("category-filter")?.addEventListener("change", (e) => {
    filters.category = e.target.value;
    render();
  });
  $("priority-filter")?.addEventListener("change", (e) => {
    filters.priority = e.target.value;
    render();
  });
  $("status-filter")?.addEventListener("change", (e) => {
    filters.status = e.target.value;
    render();
  });
  $("sort-filter")?.addEventListener("change", (e) => {
    filters.sort = e.target.value;
    render();
  });

  // 5. Workspace Nav (All tasks, Due today, Upcoming, Overdue, Completed)
  $("workspace-nav")?.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-view]");
    if (!btn) return;
    filters.view = btn.dataset.view;
    filters.category = "";
    render();
  });

  // 6. Sidebar Categories
  $("sidebar-categories")?.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-category]");
    if (!btn) return;
    const cat = btn.dataset.category;
    filters.category = filters.category === cat ? "" : cat;
    render();
  });

  // 7. Task List Actions (Complete, Edit, Delete, Select)
  $("task-list")?.addEventListener("click", (e) => {
    const actionBtn = e.target.closest("[data-action]");
    if (actionBtn) {
      const action = actionBtn.dataset.action;
      const id = actionBtn.dataset.id;
      if (action === "complete") {
        completeTask(id);
      } else if (action === "edit") {
        const t = tasks.find(item => String(item.id) === String(id));
        if (t) openModal(t);
      } else if (action === "delete") {
        deleteTask(id);
      }
      return;
    }

    const checkEl = e.target.closest(".task-select");
    if (checkEl) {
      const id = checkEl.dataset.select;
      if (checkEl.checked) {
        selected.add(id);
      } else {
        selected.delete(id);
      }
      $("selected-count").textContent = selected.size;
      $("bulk-bar").hidden = selected.size === 0;
      const list = visibleTasks();
      $("select-all").checked = list.length > 0 && list.every(t => selected.has(t.id));
    }
  });

  // 8. Select All Checkbox
  $("select-all")?.addEventListener("change", (e) => {
    const list = visibleTasks();
    if (e.target.checked) {
      list.forEach(t => selected.add(t.id));
    } else {
      list.forEach(t => selected.delete(t.id));
    }
    $("selected-count").textContent = selected.size;
    $("bulk-bar").hidden = selected.size === 0;
    render();
  });

  // 9. Bulk Complete & Bulk Delete
  $("bulk-complete")?.addEventListener("click", bulkComplete);
  $("bulk-delete")?.addEventListener("click", bulkDelete);

  // 10. Export CSV
  $("export-btn")?.addEventListener("click", exportTasksCSV);

  // 11. Format Today's Date
  const todayDateEl = $("today-date");
  if (todayDateEl) {
    todayDateEl.textContent = new Date().toLocaleDateString("en-US", {
      weekday: "short",
      day: "numeric",
      month: "short"
    });
  }
}

// Global Export function
function exportTasksCSV() {
  if (!tasks.length) return toast("No tasks to export.", true);
  const headers = ["ID", "Title", "Description", "Category", "Priority", "Status", "Due Date", "Created At"];
  const rows = tasks.map(t => [
    `"${t.id}"`,
    `"${(t.title || "").replace(/"/g, '""')}"`,
    `"${(t.description || "").replace(/"/g, '""')}"`,
    `"${t.category}"`,
    `"${t.priority}"`,
    `"${t.completed ? "Completed" : "Pending"}"`,
    `"${t.due_date || ""}"`,
    `"${t.created_at || ""}"`
  ]);
  const csv = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows.map(r => r.join(","))].join("\n");
  const link = document.createElement("a");
  link.href = encodeURI(csv);
  link.download = `taskspace_tasks_${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  toast("Tasks exported to CSV.");
}

// Initial Boot on DOM Ready
document.addEventListener("DOMContentLoaded", async () => {
  initCategoryOptions();
  setupEventListeners();
  await loadTasks();
});
