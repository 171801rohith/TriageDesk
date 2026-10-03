// Thin client for the TriageDesk REST API (same origin, so no CORS).
// Every call returns parsed JSON or throws ApiError with the server's `detail`.

const BASE = "/api/v1";

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

/** Turn FastAPI's `detail` (a string, or a list of 422 validation errors) into one line. */
function describe(detail) {
  if (!detail) return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((e) => {
        const field = (e.loc || []).filter((p) => p !== "body").join(".");
        return field ? `${field}: ${e.msg}` : e.msg;
      })
      .join("; ");
  }
  return JSON.stringify(detail);
}

async function request(method, path, body) {
  let response;
  try {
    response = await fetch(BASE + path, {
      method,
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Cannot reach the TriageDesk API.");
  }
  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(response.status, describe(data?.detail) || response.statusText);
  }
  return data;
}

/** Query string without empty values. */
function query(params) {
  const clean = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "");
  return clean.length ? `?${new URLSearchParams(clean)}` : "";
}

export const api = {
  health: () => request("GET", "/health"),
  stats: () => request("GET", "/stats"),

  listTickets: ({ status, category, limit, offset } = {}) =>
    request("GET", `/tickets${query({ status, category, limit, offset })}`),
  getTicket: (id) => request("GET", `/tickets/${id}`),
  listRuns: (id) => request("GET", `/tickets/${id}/runs`),
  createTicket: (ticket) => request("POST", "/tickets", ticket),
  retriage: (id) => request("POST", `/tickets/${id}/triage`),
  review: (id, review) => request("POST", `/tickets/${id}/review`, review),

  listArticles: ({ limit = 100, offset = 0 } = {}) =>
    request("GET", `/kb/articles${query({ limit, offset })}`),
  getArticle: (id) => request("GET", `/kb/articles/${id}`),
  createArticle: (article) => request("POST", "/kb/articles", article),
  deleteArticle: (id) => request("DELETE", `/kb/articles/${id}`),
  search: (q, k) => request("POST", "/kb/search", { query: q, k }),
  reindex: () => request("POST", "/kb/reindex"),
};
