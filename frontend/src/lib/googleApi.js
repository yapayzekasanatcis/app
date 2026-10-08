import { api } from "@/lib/api";

export const googleApi = {
  status: () => api.get("/google/status").then(r => r.data),
  connect: () => api.get("/google/connect").then(r => r.data),
  disconnect: () => api.post("/google/disconnect").then(r => r.data),
  calendarToday: () => api.get("/google/calendar/today").then(r => r.data),
  calendarDate: (dateValue) => api.get("/google/calendar/date", { params: { date_value: dateValue } }).then(r => r.data),
  sheets: () => api.get("/google/sheets").then(r => r.data),
  drive: () => api.get("/google/drive").then(r => r.data),
  doc: () => api.get("/google/doc").then(r => r.data),
  verify: () => api.get("/google/verify").then(r => r.data),
};
