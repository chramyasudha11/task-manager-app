const TASKS_URL = "/api/tasks";

async function apiRequest(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers
    }
  });

  const text = await response.text();
  let data = null;

  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { message: text };
    }
  }

  if (!response.ok) {
    throw new Error(
      data?.message ||
      data?.error ||
      `Request failed: ${response.status}`
    );
  }

  return data;
}

async function getTasks() {
  const data = await apiRequest(TASKS_URL);

  const tasks = Array.isArray(data)
    ? data
    : Array.isArray(data?.tasks)
      ? data.tasks
      : Array.isArray(data?.data)
        ? data.data
        : null;

  if (!Array.isArray(tasks)) {
    throw new Error(
      "Unexpected task API response. Expected an array or an object containing tasks."
    );
  }

  return tasks;
}

async function createTask(task) {
  return apiRequest(TASKS_URL, {
    method: "POST",
    body: JSON.stringify(task)
  });
}

async function updateTask(id, changes) {
  return apiRequest(
    `${TASKS_URL}/${encodeURIComponent(id)}`,
    {
      method: "PUT",
      body: JSON.stringify(changes)
    }
  );
}

async function deleteTask(id) {
  return apiRequest(
    `${TASKS_URL}/${encodeURIComponent(id)}`,
    {
      method: "DELETE"
    }
  );
}

// Assumes the backend toggles completion automatically
// when PATCH is sent without a request body.

async function toggleTaskCompletion(id, completed) {
  return apiRequest(
    `${TASKS_URL}/${encodeURIComponent(id)}/status`,
    {
      method: "PATCH",
      body: JSON.stringify({
        status: completed ? "Completed" : "Pending"
      })
    }
  );
}


function isTaskCompleted(task) {
  const value = task?.is_completed ?? task?.completed;

  return (
    value === true ||
    value === 1 ||
    value === "1" ||
    value === "true"
  );
}

window.TaskAPI = {
  getTasks,
  createTask,
  updateTask,
  deleteTask,
  toggleTaskCompletion,
  isTaskCompleted
};