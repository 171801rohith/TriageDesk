// DOM helpers, formatters and shared UI pieces.
//
// SECURITY: tickets contain customer-written text. Everything is rendered through
// `h()`, which only ever creates text nodes for strings — never `innerHTML` — so
// a ticket body like "<img onerror=...>" is displayed, not executed.

/** Create an element: h("a", { href, class, onClick }, ...children). */
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "value") el.value = value;
    else if (key.startsWith("on") && typeof value === "function") {
      el.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (value === true) el.setAttribute(key, "");
    else el.setAttribute(key, String(value));
  }
  el.append(...children.flat(Infinity).filter((c) => c !== null && c !== undefined && c !== false));
  return el;
}

// Stroke icons on a 24×24 grid (paths are geometry constants, not user data).
const ICONS = {
  inbox: ["M22 12h-6l-2 3h-4l-2-3H2", "M5.5 5.1 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.1z"],
  plus: ["M12 5v14", "M5 12h14"],
  book: ["M4 19.5A2.5 2.5 0 0 1 6.5 17H20V2H6.5A2.5 2.5 0 0 0 4 4.5z", "M4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5"],
  chart: ["M3 3v18h18", "M7 16v-4", "M12 16V8", "M17 16v-7"],
  refresh: ["M21 12a9 9 0 1 1-2.6-6.4L21 8", "M21 3v5h-5"],
  check: ["M20 6 9 17l-5-5"],
  x: ["M18 6 6 18", "M6 6l12 12"],
  alert: ["M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z", "M12 9v4", "M12 17h.01"],
  info: ["M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z", "M12 16v-4", "M12 8h.01"],
  back: ["M19 12H5", "M12 19l-7-7 7-7"],
  search: ["M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z", "M21 21l-4.3-4.3"],
  trash: ["M3 6h18", "M8 6V4h8v2", "M19 6l-1 14H6L5 6"],
  pencil: ["M12 20h9", "M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"],
};

export function icon(name) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "icon");
  svg.setAttribute("aria-hidden", "true");
  for (const d of ICONS[name] || []) {
    const path = document.createElementNS(ns, "path");
    path.setAttribute("d", d);
    svg.append(path);
  }
  return svg;
}

/** Replace `[data-icon]` placeholders in static HTML with real icons. */
export function hydrateIcons(root = document) {
  root.querySelectorAll("[data-icon]").forEach((el) => el.replaceWith(icon(el.dataset.icon)));
}

// ---------- Labels (API codes → words people read) ----------

export const STATUS = {
  pending: { label: "Pending", tone: "" },
  auto_ready: { label: "Auto-ready", tone: "good" },
  needs_review: { label: "Needs review", tone: "warn" },
  approved: { label: "Approved", tone: "info" },
  rejected: { label: "Rejected", tone: "crit" },
};
export const PRIORITY = {
  low: { label: "Low", tone: "" },
  medium: { label: "Medium", tone: "info" },
  high: { label: "High", tone: "warn" },
  urgent: { label: "Urgent", tone: "crit" },
};
export const REASONS = {
  urgent_priority: "Classified as urgent priority",
  negative_high_priority: "Negative sentiment on a high-priority ticket",
  low_confidence: "Draft confidence is below the threshold",
  unknown_citation: "Draft cites an article that wasn't retrieved",
  empty_reply: "Draft is empty or cites no article",
  no_relevant_kb: "No knowledge-base article was relevant enough",
  llm_error: "An LLM call failed — see run history",
};
export const CATEGORIES = ["billing", "technical", "account", "shipping", "other"];
export const REVIEWABLE = new Set(["auto_ready", "needs_review"]);
export const RETRIAGEABLE = new Set(["pending", "auto_ready", "needs_review"]);

export const capitalize = (s) => (s ? s[0].toUpperCase() + s.slice(1) : "");

export function statusBadge(status) {
  const s = STATUS[status] || { label: status, tone: "" };
  return h("span", { class: `badge ${s.tone}` }, s.label);
}
export function priorityBadge(priority) {
  if (!priority) return h("span", { class: "faint" }, "—");
  const p = PRIORITY[priority] || { label: priority, tone: "" };
  return h("span", { class: `badge ${p.tone}` }, p.label);
}

export function confidenceMeter(value) {
  if (value === null || value === undefined) return h("span", { class: "faint" }, "—");
  const pct = Math.round(value * 100);
  return h(
    "span",
    { class: "meter", title: `Draft confidence ${pct}%` },
    h("span", { class: "track" }, h("span", { class: "fill", style: `width:${pct}%` })),
    `${pct}%`,
  );
}

// ---------- Formatting ----------

const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
const UNITS = [
  ["year", 31536000], ["month", 2592000], ["week", 604800],
  ["day", 86400], ["hour", 3600], ["minute", 60], ["second", 1],
];

export function relativeTime(iso) {
  if (!iso) return "";
  const seconds = (new Date(iso).getTime() - Date.now()) / 1000;
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size || unit === "second") {
      return rtf.format(Math.round(seconds / size), unit);
    }
  }
  return "";
}
export const dateTime = (iso) =>
  iso ? new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "";
export const seconds = (ms) => (ms === null || ms === undefined ? "—" : `${(ms / 1000).toFixed(1)} s`);

/** <time> element showing relative time with the exact time on hover. */
export const timeAgo = (iso) => h("time", { datetime: iso, title: dateTime(iso) }, relativeTime(iso));

// ---------- Feedback ----------

export function toast(message, { error = false } = {}) {
  const el = h("div", { class: `toast${error ? " error" : ""}`, role: error ? "alert" : "status" },
    icon(error ? "alert" : "check"), h("span", {}, message));
  document.getElementById("toasts").append(el);
  setTimeout(() => el.remove(), error ? 7000 : 3500);
}

export function loading(text = "Loading…") {
  return h("div", { class: "loading" }, h("span", { class: "spinner" }), text);
}

export function errorState(err, retry) {
  return h("div", { class: "card" },
    h("div", { class: "empty" },
      h("h2", {}, err?.status === 404 ? "Not found" : "Something went wrong"),
      h("p", {}, err?.message || String(err)),
      retry ? h("div", { class: "row", style: "justify-content:center;margin-top:14px" },
        h("button", { class: "btn", onClick: retry }, icon("refresh"), "Try again")) : null));
}

/** Put a button into a busy state while `work()` runs; restores it afterwards. */
export async function withBusy(button, busyLabel, work) {
  const original = [...button.childNodes];
  button.disabled = true;
  button.replaceChildren(h("span", { class: "spinner" }), busyLabel);
  try {
    return await work();
  } finally {
    button.disabled = false;
    button.replaceChildren(...original);
  }
}

/**
 * Modal dialog built on <dialog>. Resolves with the form's values (object) when
 * confirmed, or null when cancelled.
 */
export function openDialog({ title, description, fields = [], confirmLabel = "Confirm", danger = false }) {
  return new Promise((resolve) => {
    const form = h("form", { method: "dialog" },
      h("div", { class: "dialog-head" }, h("h2", {}, title),
        description ? h("p", { class: "muted", style: "margin-top:6px" }, description) : null),
      fields.length ? h("div", { class: "dialog-body" }, fields) : h("div", { style: "height:14px" }),
      h("div", { class: "dialog-foot" },
        h("button", { class: "btn", value: "cancel", formnovalidate: true }, "Cancel"),
        h("button", { class: `btn ${danger ? "btn-danger" : "btn-primary"}`, value: "ok" }, confirmLabel)));
    const dialog = h("dialog", {}, form);
    dialog.addEventListener("close", () => {
      const ok = dialog.returnValue === "ok";
      const values = ok ? Object.fromEntries(new FormData(form)) : null;
      dialog.remove();
      resolve(values);
    });
    document.body.append(dialog);
    dialog.showModal();
  });
}

export function field({ label, name, hint, control }) {
  const id = `f-${name}-${Math.random().toString(36).slice(2, 7)}`;
  control.id = id;
  control.name = name;
  return h("div", { class: "field" }, h("label", { for: id }, label), control,
    hint ? h("span", { class: "hint" }, hint) : null);
}

export function pageHead(title, sub, ...actions) {
  return h("div", { class: "page-head" },
    h("div", {}, h("h1", {}, title), sub ? h("p", { class: "sub" }, sub) : null),
    actions.length ? h("div", { class: "row" }, actions) : null);
}
