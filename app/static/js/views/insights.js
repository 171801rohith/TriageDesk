// Insights: headline numbers as stat tiles, then two single-series bar charts.
// Single series → one hue, no legend, values labeled directly; hover/focus a bar
// for its exact count and share.

import { api } from "../api.js";
import { STATUS, capitalize, errorState, h, loading, pageHead, seconds } from "../dom.js";

const STATUS_ORDER = ["needs_review", "auto_ready", "pending", "approved", "rejected"];

export async function insightsView(root) {
  root.replaceChildren(pageHead("Insights", "Where tickets end up, and how fast each provider triages."), loading());

  let stats;
  try {
    stats = await api.stats();
  } catch (err) {
    root.lastChild.replaceWith(errorState(err, () => insightsView(root)));
    return;
  }

  const byStatus = stats.by_status;
  const total = Object.values(byStatus).reduce((a, b) => a + b, 0);
  const triaged = total - (byStatus.pending || 0);
  const pct = (n, d) => (d ? `${Math.round((n / d) * 100)}%` : "—");

  const tiles = h("div", { class: "tiles" },
    tile("Tickets", String(total), `${triaged} triaged`),
    tile("Needs review", String(byStatus.needs_review || 0), `${pct(byStatus.needs_review || 0, total)} of all tickets`),
    tile("Auto-ready now", String(byStatus.auto_ready || 0), "Passed every guardrail, awaiting one-click approval"),
    tile("Reviewed", String((byStatus.approved || 0) + (byStatus.rejected || 0)),
      `${byStatus.approved || 0} approved · ${byStatus.rejected || 0} rejected`),
    Object.entries(stats.by_provider).map(([provider, p]) =>
      tile(`Avg triage time · ${provider}`, seconds(p.avg_latency_ms),
        `Average over successful runs · ${p.runs} run${p.runs === 1 ? "" : "s"} total`)));

  const statusRows = STATUS_ORDER.map((s) => [STATUS[s].label, byStatus[s] || 0]);
  const categoryRows = Object.entries(stats.by_category).sort((a, b) => b[1] - a[1]).map(([c, n]) => [capitalize(c), n]);

  root.lastChild.replaceWith(
    tiles,
    h("div", { class: "grid-kb" },
      chartCard("Tickets by status", statusRows, total),
      chartCard("Tickets by category", categoryRows, Object.values(stats.by_category).reduce((a, b) => a + b, 0),
        "Only classified tickets have a category.")));
}

function tile(label, value, note) {
  return h("div", { class: "card tile" },
    h("div", { class: "label" }, label), h("div", { class: "value" }, value), h("div", { class: "note" }, note));
}

/** Horizontal bars from a zero baseline; the longest bar spans the track. */
function chartCard(title, rows, total, footnote) {
  const max = Math.max(1, ...rows.map(([, n]) => n));
  const body = rows.length && total
    ? h("div", { class: "bars", role: "list" }, rows.map(([name, n]) => {
      const share = total ? Math.round((n / total) * 100) : 0;
      return h("div", { class: "bar-row", role: "listitem", tabindex: 0, "aria-label": `${name}: ${n} tickets, ${share}%` },
        h("span", { class: "name" }, name),
        h("span", { class: "track" }, h("span", { class: "bar", style: `display:block;width:${(n / max) * 100}%` })),
        h("span", { class: "value" }, String(n)),
        h("span", { class: "tip", "aria-hidden": "true" }, `${name}: ${n} ticket${n === 1 ? "" : "s"} · ${share}% of ${total}`));
    }))
    : h("p", { class: "muted" }, "No data yet.");

  return h("section", { class: "card" },
    h("div", { class: "card-head" }, h("h2", {}, title), h("span", { class: "faint" }, `${total} total`)),
    h("div", { class: "card-body" }, body, footnote ? h("p", { class: "faint", style: "margin-top:10px" }, footnote) : null));
}
