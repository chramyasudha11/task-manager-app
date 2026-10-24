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
            <span aria-hidden="true">?</span> Kanban Board
          </button>
          <button class="view-toggle-btn ${state.taskView === "list" ? "active" : ""}" type="button" data-action="set-task-view" data-view="list" aria-pressed="${state.taskView === "list"}">
            <span aria-hidden="true">?</span> List Table
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
              ${todoTasks.length ? todoTasks.map(kanbanCardMarkup).join("") : `<div class="kanban-empty"><span class="kanban-empty-icon">?</span><p>No tasks to do</p></div>`}
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
              ${inProgressTasks.length ? inProgressTasks.map(kanbanCardMarkup).join("") : `<div class="kanban-empty"><span class="kanban-empty-icon">?</span><p>No tasks in progress</p></div>`}
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
              ${completedTasks.length ? completedTasks.map(kanbanCardMarkup).join("") : `<div class="kanban-empty"><span class="kanban-empty-icon">??</span><p>No completed tasks</p></div>`}
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
                    ${task.isRecurring ? `<span class="recurrence-badge" title="Recurring: ${escapeHtml(task.recurrenceInterval)}">?? ${escapeHtml(task.recurrenceInterval)}</span>` : ""}
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


