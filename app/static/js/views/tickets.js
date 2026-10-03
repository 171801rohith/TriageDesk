// Ticket list: the review queue, filtered by status (tabs) and category.

import { api } from "../api.js";
import {
  CATEGORIES, STATUS, capitalize, confidenceMeter, errorState, h, icon, loading, pageHead,
  priorityBadge, statusBadge, timeAgo,
} from "../dom.js";

const PAGE_SIZE = 20;
const TABS = [
  ["needs_review", "Needs review"],
  ["auto_ready", "Auto-ready"],
  ["pending", "Pending"],
  ["approved", "Approved"],
  ["rejected", "Rejected"],
  ["", "All"],
];

/** Hash URL for a list state, e.g. #/tickets?status=needs_review&page=2. */
function listUrl({ status, category, page }) {
  const q = new URLSearchParams();
  q.set("status", status ?? "");
  if (category) q.set("category", category);
  if (page > 1) q.set("page", String(page));
  return `#/tickets?${q}`;
}

export async function ticketsView(root, { query }) {
  const status = query.has("status") ? query.get("status") : "needs_review";
  const category = query.get("category") || "";
  const page = Math.max(1, Number(query.get("page")) || 1);

  root.replaceChildren(
    pageHead("Tickets", "Every ticket is triaged on arrival. Nothing is sent without a human.",
      h("a", { class: "btn btn-primary", href: "#/tickets/new" }, icon("plus"), "New ticket")),
    loading(),
  );

  let tickets, stats;
  try {
    [tickets, stats] = await Promise.all([
      api.listTickets({ status, category, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE }),
      api.stats(),
    ]);
  } catch (err) {
    root.lastChild.replaceWith(errorState(err, () => ticketsView(root, { query })));
    return;
  }

  const total = Object.values(stats.by_status).reduce((a, b) => a + b, 0);
  const tabs = h("nav", { class: "tabs", "aria-label": "Filter by status" },
    TABS.map(([value, label]) =>
      h("a", { href: listUrl({ status: value, category }), "aria-current": String(value === status) },
        label, h("span", { class: "count" }, String(value ? stats.by_status[value] || 0 : total)))));

  const categorySelect = h("select", {
    "aria-label": "Filter by category",
    onChange: (e) => { location.hash = listUrl({ status, category: e.target.value }); },
  },
  h("option", { value: "" }, "All categories"),
  CATEGORIES.map((c) => h("option", { value: c, selected: c === category }, capitalize(c))));

  const toolbar = h("div", { class: "toolbar" }, tabs, categorySelect);

  if (!tickets.length) {
    root.lastChild.replaceWith(toolbar, h("div", { class: "card" }, emptyState(status, page)));
    return;
  }

  const rows = tickets.map((t) => {
    const href = `#/tickets/${t.id}`;
    return h("tr", { class: "clickable", onClick: (e) => { if (!e.target.closest("a")) location.hash = href; } },
      h("td", { class: "faint num" }, `#${t.id}`),
      h("td", {},
        h("a", { class: "cell-title", href }, t.subject),
        t.classification?.summary ? h("div", { class: "cell-sub" }, t.classification.summary) : null),
      h("td", { class: "hide-sm muted" }, t.customer_email),
      h("td", {}, t.classification ? capitalize(t.classification.category) : h("span", { class: "faint" }, "—")),
      h("td", {}, priorityBadge(t.classification?.priority)),
      h("td", {}, statusBadge(t.status)),
      h("td", { class: "hide-sm" }, confidenceMeter(t.confidence)),
      h("td", { class: "faint", style: "white-space:nowrap" }, timeAgo(t.created_at)));
  });

  const hasNext = tickets.length === PAGE_SIZE;
  const pager = h("div", { class: "pager" },
    h("span", {}, `Page ${page}`),
    h("div", { class: "row" },
      h("a", { class: "btn btn-sm", href: listUrl({ status, category, page: page - 1 }),
        "aria-disabled": String(page === 1), style: page === 1 ? "pointer-events:none;opacity:.5" : null }, "Previous"),
      h("a", { class: "btn btn-sm", href: listUrl({ status, category, page: page + 1 }),
        "aria-disabled": String(!hasNext), style: hasNext ? null : "pointer-events:none;opacity:.5" }, "Next")));

  root.lastChild.replaceWith(toolbar,
    h("div", { class: "card" },
      h("div", { class: "table-wrap" },
        h("table", {},
          h("thead", {}, h("tr", {},
            h("th", { class: "num" }, "ID"), h("th", {}, "Ticket"), h("th", { class: "hide-sm" }, "Customer"),
            h("th", {}, "Category"), h("th", {}, "Priority"), h("th", {}, "Status"),
            h("th", { class: "hide-sm" }, "Confidence"), h("th", {}, "Received"))),
          h("tbody", {}, rows))),
      pager));
}

function emptyState(status, page) {
  const label = STATUS[status]?.label.toLowerCase();
  return h("div", { class: "empty" },
    h("h2", {}, page > 1 ? "No more tickets" : status === "needs_review" ? "Review queue is clear" : "No tickets"),
    h("p", {}, page > 1 ? "You've reached the end of this list."
      : label ? `There are no ${label} tickets right now.` : "Create a ticket to see triage in action."),
    h("div", { class: "row", style: "justify-content:center;margin-top:14px" },
      h("a", { class: "btn", href: "#/tickets/new" }, icon("plus"), "New ticket")));
}
