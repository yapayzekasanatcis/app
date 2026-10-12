import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API_BASE,
  withCredentials: true,
});

let csrfToken = null;
let csrfPromise = null;
const unsafeMethods = new Set(["post", "put", "patch", "delete"]);

const clearCsrfToken = () => {
  csrfToken = null;
  csrfPromise = null;
};

const getCsrfToken = async () => {
  if (csrfToken) return csrfToken;
  if (!csrfPromise) {
    csrfPromise = axios.get(`${API_BASE}/auth/csrf`, { withCredentials: true })
      .then(response => {
        csrfToken = response.data.csrf_token;
        return csrfToken;
      })
      .finally(() => { csrfPromise = null; });
  }
  return csrfPromise;
};

api.interceptors.request.use(async config => {
  const method = (config.method || "get").toLowerCase();
  const isSessionExchange = String(config.url || "").endsWith("/auth/session");
  if (unsafeMethods.has(method) && !isSessionExchange) {
    config.headers = config.headers || {};
    config.headers["X-CSRF-Token"] = await getCsrfToken();
  }
  return config;
});

api.interceptors.response.use(
  response => response,
  async error => {
    const config = error.config;
    const detail = error.response?.data?.detail;
    if (error.response?.status === 401) clearCsrfToken();
    if (error.response?.status === 403 && detail === "CSRF doğrulaması başarısız" && config && !config._csrfRetry) {
      config._csrfRetry = true;
      clearCsrfToken();
      config.headers["X-CSRF-Token"] = await getCsrfToken();
      return api.request(config);
    }
    return Promise.reject(error);
  }
);

export const authApi = {
  me: () => api.get("/auth/me").then(r => r.data),
  session: async (session_id) => {
    clearCsrfToken();
    return api.post("/auth/session", { session_id }).then(r => r.data);
  },
  logout: async () => {
    try { return await api.post("/auth/logout").then(r => r.data); }
    finally { clearCsrfToken(); }
  },
};

export const chatApi = {
  send: (message, conversation_id = "default", source = "text") =>
    api.post("/chat", { message, conversation_id, source }).then(r => r.data),
  history: (conversation_id = "default") =>
    api.get("/chat/history", { params: { conversation_id } }).then(r => r.data),
};

export const briefingApi = {
  today: () => api.get("/briefing/today").then(r => r.data),
};

export const workspaceApi = {
  snapshot: () => api.get("/workspace/snapshot").then(r => r.data),
};

export const tasksApi = {
  list: (params = {}) => api.get("/tasks", { params }).then(r => r.data),
  create: (data) => api.post("/tasks", data).then(r => r.data),
  update: (id, data) => api.patch(`/tasks/${id}`, data).then(r => r.data),
  remove: (id) => api.delete(`/tasks/${id}`).then(r => r.data),
};

export const notesApi = {
  list: (params = {}) => api.get("/notes", { params }).then(r => r.data),
  create: (data) => api.post("/notes", data).then(r => r.data),
  remove: (id) => api.delete(`/notes/${id}`).then(r => r.data),
};

export const eventsApi = {
  list: (params = {}) => api.get("/events", { params }).then(r => r.data),
  create: (data) => api.post("/events", data).then(r => r.data),
  remove: (id) => api.delete(`/events/${id}`).then(r => r.data),
};

export const voiceApi = {
  stt: (blob) => {
    const fd = new FormData();
    fd.append("file", blob, "audio.webm");
    return api.post("/voice/stt", fd, { headers: { "Content-Type": "multipart/form-data" } }).then(r => r.data);
  },
  tts: async (text) => {
    const fd = new FormData();
    fd.append("text", text);
    const r = await api.post("/voice/tts", fd, { responseType: "blob" });
    return r.data;
  },
};


export const attachmentApi = {
  analyze: (files, instruction = "") => {
    const fd = new FormData();
    files.forEach(file => fd.append("files", file));
    fd.append("instruction", instruction);
    return api.post("/attachments/analyze", fd, {
      headers: { "Content-Type": "multipart/form-data" },
    }).then(r => r.data);
  },
};
