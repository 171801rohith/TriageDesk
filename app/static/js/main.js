// App shell: hash router, nav highlighting, and the API/provider health indicator.
// Hash routing (#/tickets/42) needs no server config: FastAPI serves one index.html.

import { api } from "./api.js";
import { errorState, h, hydrateIcons } from "./dom.js";
import { insightsView } from "./views/insights.js";
import { articleView, kbView } from "./views/kb.js";
import { newTicketView } from "./views/new-ticket.js";
import { ticketView } from "./views/ticket.js";
import { ticketsView } from "./views/tickets.js";

// Order matters: "/tickets/new" must match before "/tickets/:id".
const ROUTES = [
  { pattern: /^\/tickets\/new$/, view: newTicketView, nav: "new", title: "New ticket" },
  { pattern: /^\/tickets\/(?<id>\d+)$/, view: ticketView, nav: "tickets", title: "Ticket" },
  { pattern: /^\/tickets$/, view: ticketsView, nav: "tickets", title: "Tickets" },
  { pattern: /^\/kb\/(?<id>\d+)$/, view: articleView, nav: "kb", title: "Article" },
  { pattern: /^\/kb$/, view: kbView, nav: "kb", title: "Knowledge base" },
  { pattern: /^\/insights$/, view: insightsView, nav: "insights", title: "Insights" },
];

const viewEl = document.getElementById("view");
let renderId = 0;

async function route() {
  const raw = location.hash.slice(1) || "/tickets";
  const [path, search = ""] = raw.split("?");
  const match = ROUTES.map((r) => ({ r, m: path.match(r.pattern) })).find((x) => x.m);
  if (!match) {
    location.replace("#/tickets");
    return;
  }

  const { r, m } = match;
  document.querySelectorAll("[data-nav]").forEach((a) => {
    if (a.dataset.nav === r.nav) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  document.title = `${r.title} · TriageDesk`;

  // A slow view finishing after the user navigated away must not overwrite the new page.
  const id = ++renderId;
  const container = h("div");
  viewEl.replaceChildren(container);
  try {
    await r.view(container, { params: m.groups || {}, query: new URLSearchParams(search) });
  } catch (err) {
    if (id === renderId) container.replaceChildren(errorState(err));
    console.error(err);
  }
  if (id === renderId) viewEl.focus({ preventScroll: true });
}

async function refreshHealth() {
  const el = document.getElementById("health");
  try {
    const health = await api.health();
    const dbOk = health.db === "ok";
    el.replaceChildren(
      h("div", { class: "row" }, h("span", { class: `badge ${dbOk ? "good" : "crit"}` }, dbOk ? "Database OK" : "Database down")),
      h("div", {}, h("strong", {}, health.provider), ` · ${health.chat_model}`),
      h("div", { class: "faint" }, `Embeddings: ${health.embedding_model}`));
  } catch {
    el.replaceChildren(h("span", { class: "badge crit" }, "API unreachable"));
  }
}

hydrateIcons();
window.addEventListener("hashchange", () => { window.scrollTo(0, 0); route(); });
route();
refreshHealth();
setInterval(refreshHealth, 30_000);
