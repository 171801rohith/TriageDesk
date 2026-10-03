// Ticket detail: the customer message, what triage decided and why, the draft
// reply with its citations, the review actions, and the full run history.

import { api } from "../api.js";
import {
  REASONS, RETRIAGEABLE, REVIEWABLE, capitalize, confidenceMeter, dateTime, errorState, field, h,
  icon, loading, openDialog, priorityBadge, seconds, statusBadge, timeAgo, toast, withBusy,
} from "../dom.js";

const STEP_ORDER = ["classify", "retrieve", "draft", "guardrails"];

export async function ticketView(root, { params }) {
  const id = Number(params.id);
  root.replaceChildren(loading("Loading ticket…"));

  let ticket, runs;
  try {
    [ticket, runs] = await Promise.all([api.getTicket(id), api.listRuns(id)]);
  } catch (err) {
    root.replaceChildren(backLink(), errorState(err, () => ticketView(root, { params })));
    return;
  }
  const articles = await loadCitedArticles(ticket.cited_article_ids);
  const rerender = () => ticketView(root, { params });

  root.replaceChildren(
    backLink(),
    header(ticket),
    h("div", { class: "grid-detail" },
      h("div", { class: "stack" },
        messageCard(ticket),
        triageCard(ticket),
        replyCard(ticket, articles, rerender)),
      h("div", { class: "stack" },
        actionsCard(ticket, rerender),
        runsCard(runs))),
  );
}

const backLink = () => h("a", { class: "back", href: "#/tickets" }, icon("back"), "All tickets");

/** Titles for the cited article ids; a deleted article is shown as such, not an error. */
async function loadCitedArticles(ids) {
  const entries = await Promise.all(
    ids.map((id) => api.getArticle(id).then((a) => [id, a]).catch(() => [id, null])));
  return new Map(entries);
}

function header(t) {
  const run = t.latest_run;
  return h("div", { class: "page-head" },
    h("div", {},
      h("div", { class: "row", style: "margin-bottom:6px" },
        h("span", { class: "faint" }, `#${t.id}`), statusBadge(t.status), priorityBadge(t.classification?.priority)),
      h("h1", {}, t.subject),
      h("p", { class: "sub" },
        t.customer_email, " · received ", timeAgo(t.created_at),
        run ? ` · triaged by ${run.provider} / ${run.model}` : "")));
}

function messageCard(t) {
  return h("section", { class: "card" },
    h("div", { class: "card-head" }, h("h2", {}, "Customer message")),
    h("div", { class: "card-body prewrap" }, t.body));
}

function triageCard(t) {
  const c = t.classification;
  const body = h("div", { class: "card-body stack", style: "gap:14px" });

  if (c) {
    body.append(
      h("div", { class: "row" },
        h("span", { class: "chip" }, "Category ", h("strong", {}, capitalize(c.category))),
        h("span", { class: "chip" }, "Priority ", h("strong", {}, capitalize(c.priority))),
        h("span", { class: "chip" }, "Sentiment ", h("strong", {}, capitalize(c.sentiment))),
        h("span", { class: "chip" }, "Language ", h("strong", {}, c.language))),
      h("p", {}, c.summary));
  } else if (t.status !== "pending") {
    body.append(h("p", { class: "muted" }, "The ticket could not be classified."));
  }

  if (t.status === "pending") {
    body.append(h("div", { class: "callout info" }, icon("info"),
      h("div", {}, "Triage hasn't finished. If it was interrupted, re-run it from the actions panel.")));
  } else if (t.review_reasons.length) {
    body.append(h("div", { class: "callout warn" }, icon("alert"),
      h("div", {}, h("strong", {}, "Routed to human review"),
        h("ul", {}, t.review_reasons.map((r) => h("li", {}, REASONS[r] || r))))));
  } else if (t.status === "auto_ready") {
    body.append(h("div", { class: "callout good" }, icon("check"),
      h("div", {}, h("strong", {}, "Passed every guardrail. "),
        "The draft is ready to send with one click — a person still approves it.")));
  }

  return h("section", { class: "card" },
    h("div", { class: "card-head" }, h("h2", {}, "Triage"),
      t.confidence !== null ? h("span", { class: "row faint" }, "Draft confidence ", confidenceMeter(t.confidence)) : null),
    body);
}

function citations(ids, articles) {
  if (!ids.length) return null;
  return h("div", { class: "row" },
    h("span", { class: "faint" }, "Sources"),
    ids.map((id) => {
      const article = articles.get(id);
      return article
        ? h("a", { class: "chip", href: `#/kb/${id}` }, icon("book"), `#${id} ${article.title}`)
        : h("span", { class: "chip", title: "Not found in the knowledge base" }, `#${id} (deleted)`);
    }));
}

function replyCard(t, articles, rerender) {
  const head = h("div", { class: "card-head" }, h("h2", {}, "Reply"));

  // Finished tickets: show the outcome, read-only.
  if (t.status === "approved" || t.status === "rejected") {
    const approved = t.status === "approved";
    return h("section", { class: "card" }, head,
      h("div", { class: "card-body stack", style: "gap:12px" },
        h("div", { class: `callout ${approved ? "good" : "crit"}` }, icon(approved ? "check" : "x"),
          h("div", {}, h("strong", {}, approved ? "Approved" : "Rejected"), " ", dateTime(t.reviewed_at),
            t.review_note ? h("div", {}, `Note: ${t.review_note}`) : null)),
        approved ? h("div", { class: "prewrap" }, t.final_reply) : null,
        citations(t.cited_article_ids, articles)));
  }

  if (!REVIEWABLE.has(t.status)) {
    return h("section", { class: "card" }, head,
      h("div", { class: "card-body muted" }, "A reply can be reviewed once triage has finished."));
  }

  const draft = t.draft_reply || "";
  const editor = h("textarea", {
    rows: 10,
    "aria-label": "Reply to the customer",
    placeholder: "No draft was generated for this ticket. Write the reply yourself.",
    value: draft,
  });
  const approve = h("button", { class: "btn btn-primary" }, icon("check"), "Approve draft");
  const reject = h("button", { class: "btn btn-danger" }, icon("x"), "Reject…");
  const hint = h("span", { class: "faint" });

  // One primary button: "approve" if the draft is untouched, "edit" once it changes.
  const sync = () => {
    const text = editor.value.trim();
    const edited = editor.value !== draft;
    approve.disabled = !text;
    approve.lastChild.textContent = edited || !draft ? "Approve edited reply" : "Approve draft";
    hint.textContent = edited ? "Edited — your version will be sent." : draft ? "" : "Write a reply to approve.";
  };
  editor.addEventListener("input", sync);
  sync();

  approve.addEventListener("click", () =>
    withBusy(approve, "Saving…", async () => {
      const edited = editor.value !== draft || !draft;
      try {
        await api.review(t.id, edited ? { action: "edit", final_reply: editor.value } : { action: "approve" });
        toast("Reply approved.");
        rerender();
      } catch (err) {
        toast(err.message, { error: true });
      }
    }));

  reject.addEventListener("click", async () => {
    const values = await openDialog({
      title: "Reject this ticket?",
      description: "No reply will be approved. You can leave a note for the audit trail.",
      fields: [field({ label: "Note (optional)", name: "note", control: h("textarea", { rows: 3 }) })],
      confirmLabel: "Reject ticket",
      danger: true,
    });
    if (!values) return;
    try {
      await api.review(t.id, { action: "reject", note: values.note.trim() || null });
      toast("Ticket rejected.");
      rerender();
    } catch (err) {
      toast(err.message, { error: true });
    }
  });

  return h("section", { class: "card" }, head,
    h("div", { class: "card-body stack", style: "gap:12px" },
      editor,
      citations(t.cited_article_ids, articles),
      h("div", { class: "row spread" }, hint, h("div", { class: "row" }, reject, approve))));
}

function actionsCard(t, rerender) {
  const allowed = RETRIAGEABLE.has(t.status);
  const button = h("button", { class: "btn", disabled: !allowed }, icon("refresh"), "Re-run triage");
  button.addEventListener("click", () =>
    withBusy(button, "Running… (up to a minute)", async () => {
      try {
        const updated = await api.retriage(t.id);
        toast(`Re-triaged: ${updated.status.replace("_", " ")}.`);
        rerender();
      } catch (err) {
        toast(err.message, { error: true });
      }
    }));

  return h("section", { class: "card" },
    h("div", { class: "card-head" }, h("h2", {}, "Actions")),
    h("div", { class: "card-body stack", style: "gap:10px" },
      button,
      h("p", { class: "faint" }, allowed
        ? "Runs classify → retrieve → draft → guardrails again, e.g. after adding KB articles. Every run is kept below."
        : "Reviewed tickets are final and can't be re-triaged.")));
}

function runsCard(runs) {
  const items = [...runs].reverse().map((run, i) => {
    const failed = run.status === "failed";
    const timings = STEP_ORDER.filter((s) => s in run.step_timings)
      .map((s) => h("span", {}, `${s} ${seconds(run.step_timings[s])}`));
    return h("li", {},
      h("div", { class: "row spread" },
        h("span", { class: `badge ${failed ? "crit" : "good"}` }, failed ? "Failed" : "Succeeded"),
        h("span", { class: "faint" }, i === 0 ? "Latest · " : "", timeAgo(run.created_at))),
      h("div", { class: "muted", style: "font-size:13px" },
        `${run.provider} / ${run.chat_model} · prompt ${run.prompt_version} · ${seconds(run.latency_ms)}`),
      h("div", { class: "timings" }, timings),
      run.retrieved.length
        ? h("div", { class: "faint" }, "Retrieved: ",
          run.retrieved.map((c) => `#${c.article_id} (${c.distance.toFixed(2)})`).join(", "))
        : null,
      failed && run.error ? h("div", { class: "error-box" }, run.error) : null);
  });

  return h("section", { class: "card" },
    h("div", { class: "card-head" }, h("h2", {}, "Run history"), h("span", { class: "faint" }, `${runs.length} run${runs.length === 1 ? "" : "s"}`)),
    items.length ? h("ul", { class: "runs" }, items) : h("div", { class: "card-body muted" }, "No runs yet."));
}
