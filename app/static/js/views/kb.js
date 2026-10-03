// Knowledge base: semantic search playground, article list, add / delete / reindex.

import { api } from "../api.js";
import {
  CATEGORIES, capitalize, dateTime, errorState, field, h, icon, loading, openDialog, pageHead,
  timeAgo, toast, withBusy,
} from "../dom.js";

const SNIPPET = 260;

export async function kbView(root) {
  const addButton = h("button", { class: "btn btn-primary" }, icon("plus"), "Add article");
  const reindexButton = h("button", { class: "btn" }, icon("refresh"), "Re-index");
  const listCard = h("section", { class: "card" }, loading("Loading articles…"));

  const refreshList = async () => {
    try {
      listCard.replaceChildren(articleTable(await api.listArticles(), refreshList));
    } catch (err) {
      listCard.replaceChildren(errorState(err, refreshList));
    }
  };

  addButton.addEventListener("click", async () => {
    const values = await openDialog({
      title: "Add article",
      description: "The article is split into chunks and embedded right away.",
      fields: [
        field({ label: "Title", name: "title", control: h("input", { type: "text", required: true, maxlength: 200 }) }),
        field({ label: "Category", name: "category",
          control: h("select", {}, CATEGORIES.map((c) => h("option", { value: c }, capitalize(c)))) }),
        field({ label: "Content", name: "content", hint: "Plain text or markdown.",
          control: h("textarea", { rows: 10, required: true }) }),
      ],
      confirmLabel: "Add article",
    });
    if (!values) return;
    try {
      const article = await api.createArticle(values);
      toast(`Added "${article.title}".`);
      refreshList();
    } catch (err) {
      toast(err.message, { error: true });
    }
  });

  reindexButton.addEventListener("click", async () => {
    const ok = await openDialog({
      title: "Re-index the knowledge base?",
      description: "Re-embeds every chunk with the current embedding model. Needed after switching embedding provider; can take a while.",
      confirmLabel: "Re-index",
    });
    if (!ok) return;
    await withBusy(reindexButton, "Re-indexing…", async () => {
      try {
        const result = await api.reindex();
        toast(`Re-embedded ${result.reindexed_chunks} chunks with ${result.embedding_model}.`);
      } catch (err) {
        toast(err.message, { error: true });
      }
    });
  });

  root.replaceChildren(
    pageHead("Knowledge base", "Help articles the drafts are grounded in. Search shows exactly what triage would retrieve.",
      reindexButton, addButton),
    h("div", { class: "grid-kb" }, searchCard(), listCard),
  );
  refreshList();
}

function searchCard() {
  const input = h("input", { type: "search", required: true, placeholder: "e.g. I was billed two times", "aria-label": "Search query" });
  const k = h("select", { "aria-label": "Number of results" }, [3, 4, 5, 8].map((n) => h("option", { value: n, selected: n === 4 }, `Top ${n}`)));
  const button = h("button", { class: "btn btn-primary", type: "submit" }, icon("search"), "Search");
  const results = h("div", {}, h("div", { class: "card-body faint" },
    "Results are ranked by cosine distance (0 = identical). Triage only uses passages under RETRIEVAL_MAX_DISTANCE (default 0.5)."));

  const form = h("form", { class: "card-body row", style: "flex-wrap:nowrap" }, input, k, button);
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    withBusy(button, "Searching…", async () => {
      try {
        const hits = await api.search(input.value.trim(), Number(k.value));
        results.replaceChildren(hits.length ? h("ol", { class: "results" }, hits.map(resultItem))
          : h("div", { class: "card-body muted" }, "No chunks embedded with the current model. Seed or re-index the KB."));
      } catch (err) {
        toast(err.message, { error: true });
      }
    });
  });

  return h("section", { class: "card" },
    h("div", { class: "card-head" }, h("h2", {}, "Search playground")), form, results);
}

function resultItem(hit, index) {
  const text = hit.text.length > SNIPPET ? `${hit.text.slice(0, SNIPPET)}…` : hit.text;
  // Bar shows closeness: distance 0 → full, 1 or more → empty.
  const closeness = Math.max(0, Math.min(1, 1 - hit.distance)) * 100;
  return h("li", {},
    h("div", { class: "row spread" },
      h("a", { class: "cell-title", href: `#/kb/${hit.article_id}` }, `${index + 1}. ${hit.title}`),
      h("span", { class: `badge ${hit.distance <= 0.5 ? "good" : ""}` }, hit.distance <= 0.5 ? "Relevant" : "Weak match")),
    h("p", { class: "muted", style: "margin-top:4px;font-size:13px" }, text),
    h("div", { class: "dist" },
      h("span", { class: "track" }, h("span", { class: "fill", style: `display:block;width:${closeness}%` })),
      `distance ${hit.distance.toFixed(3)}`));
}

function articleTable(articles, refresh) {
  const head = h("div", { class: "card-head" }, h("h2", {}, "Articles"), h("span", { class: "faint" }, `${articles.length} total`));
  if (!articles.length) {
    return h("div", {}, head, h("div", { class: "empty" }, h("h2", {}, "No articles yet"),
      h("p", {}, "Add one here, or run ", h("code", {}, "uv run python scripts/seed_kb.py"), ".")));
  }
  return h("div", {}, head,
    h("div", { class: "table-wrap" }, h("table", {},
      h("thead", {}, h("tr", {}, h("th", {}, "Title"), h("th", {}, "Category"), h("th", { class: "hide-sm" }, "Added"), h("th", {}, ""))),
      h("tbody", {}, articles.map((a) => h("tr", {},
        h("td", {}, h("a", { class: "cell-title", href: `#/kb/${a.id}` }, a.title), h("div", { class: "faint" }, `#${a.id}`)),
        h("td", {}, capitalize(a.category)),
        h("td", { class: "hide-sm faint" }, timeAgo(a.created_at)),
        h("td", { class: "num" }, deleteButton(a, refresh))))))));
}

function deleteButton(article, onDeleted) {
  return h("button", {
    class: "btn btn-sm btn-ghost btn-danger",
    "aria-label": `Delete ${article.title}`,
    onClick: async () => {
      const ok = await openDialog({
        title: `Delete "${article.title}"?`,
        description: "The article and all its embedded chunks are removed. Tickets that cited it keep the id.",
        confirmLabel: "Delete",
        danger: true,
      });
      if (!ok) return;
      try {
        await api.deleteArticle(article.id);
        toast(`Deleted "${article.title}".`);
        onDeleted();
      } catch (err) {
        toast(err.message, { error: true });
      }
    },
  }, icon("trash"));
}

export async function articleView(root, { params }) {
  const back = h("a", { class: "back", href: "#/kb" }, icon("back"), "Knowledge base");
  root.replaceChildren(back, loading("Loading article…"));
  try {
    const a = await api.getArticle(Number(params.id));
    root.replaceChildren(back,
      pageHead(a.title, `#${a.id} · ${capitalize(a.category)} · added ${dateTime(a.created_at)}`,
        deleteButton(a, () => { location.hash = "#/kb"; })),
      h("article", { class: "card", style: "max-width:820px" }, h("div", { class: "card-body prewrap" }, a.content)));
  } catch (err) {
    root.replaceChildren(back, errorState(err));
  }
}
