// New ticket: submit a customer message and wait for synchronous triage (FR-7).

import { api } from "../api.js";
import { field, h, icon, pageHead, toast } from "../dom.js";

// Demo tickets that exercise the three main outcomes (acceptance criteria 3–5).
const SAMPLES = [
  {
    label: "Duplicate charge",
    customer_email: "sam@example.com",
    subject: "Charged twice this month",
    body: "Hi, my card was charged twice for the Pro plan on Sept 3. Please refund one.",
  },
  {
    label: "Outage",
    customer_email: "ops@acme.example",
    subject: "URGENT: production is down",
    body: "URGENT: production is down for all users, nobody on our team can log in.",
  },
  {
    label: "Not in the KB",
    customer_email: "lia@example.com",
    subject: "Gift cards",
    body: "Do you sell gift cards in Brazil?",
  },
];

export function newTicketView(root) {
  const email = h("input", { type: "email", required: true, autocomplete: "off", placeholder: "customer@example.com" });
  const subject = h("input", { type: "text", required: true, maxlength: 200, placeholder: "Short summary" });
  const body = h("textarea", { required: true, maxlength: 10000, rows: 8, placeholder: "What the customer wrote…" });
  const submit = h("button", { class: "btn btn-primary", type: "submit" }, icon("check"), "Create & triage");
  const progress = h("div");

  const fill = (sample) => {
    email.value = sample.customer_email;
    subject.value = sample.subject;
    body.value = sample.body;
  };

  const form = h("form", { class: "card-body form-grid" },
    field({ label: "Customer email", name: "customer_email", control: email }),
    field({ label: "Subject", name: "subject", control: subject }),
    field({ label: "Message", name: "body", control: body, hint: "Up to 10,000 characters." }),
    h("div", { class: "row spread" },
      h("div", { class: "row" }, h("span", { class: "faint" }, "Try a sample:"),
        SAMPLES.map((s) => h("button", { type: "button", class: "btn btn-sm btn-ghost", onClick: () => fill(s) }, s.label))),
      submit));

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const controls = form.querySelectorAll("input, textarea, button");
    controls.forEach((c) => { c.disabled = true; });
    const started = Date.now();
    const elapsed = h("span", { class: "faint" }, "0 s");
    const timer = setInterval(() => { elapsed.textContent = `${Math.round((Date.now() - started) / 1000)} s`; }, 1000);
    progress.replaceChildren(h("div", { class: "card", style: "margin-top:16px" },
      h("div", { class: "progress-panel" }, h("span", { class: "spinner" }),
        h("div", {},
          h("strong", {}, "Triaging the ticket… "), elapsed,
          h("p", { class: "muted", style: "margin-top:4px" },
            "The ticket is already saved. Local models can take up to a minute."),
          h("div", { class: "steps" }, ["Classify", "Retrieve", "Draft", "Guardrails"].map((s) => h("span", { class: "chip" }, s)))))));

    try {
      const ticket = await api.createTicket({
        customer_email: email.value.trim(),
        subject: subject.value.trim(),
        body: body.value.trim(),
      });
      toast(`Ticket #${ticket.id} triaged.`);
      location.hash = `#/tickets/${ticket.id}`;
    } catch (err) {
      toast(err.message, { error: true });
      progress.replaceChildren();
      controls.forEach((c) => { c.disabled = false; });
    } finally {
      clearInterval(timer);
    }
  });

  root.replaceChildren(
    pageHead("New ticket", "Triage runs immediately: classify, search the knowledge base, draft a cited reply, apply guardrails."),
    h("div", { style: "max-width:760px" }, h("div", { class: "card" }, form), progress),
  );
  email.focus();
}
