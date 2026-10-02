// Render tests for the OutreachOS screens, without a browser and without any network: the API module is mocked.
// What they pin down: explicit empty states, the explainable score, and that decisions are gated by role.
import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";

jest.mock("@/lib/api", () => ({ api: { get: jest.fn(), post: jest.fn(), put: jest.fn() } }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: global.__user }) }));

// babel-jest hoists the jest.mock calls above these imports.
import { api } from "@/lib/api";
import Prospects from "@/pages/Prospects";
import ProspectDetail from "@/pages/ProspectDetail";
import ReviewQueue from "@/pages/ReviewQueue";
import Sending from "@/pages/Sending";

global.IS_REACT_ACT_ENVIRONMENT = true;

const owner = { id: "u1", role: "owner", email: "o@x.example" };
const member = { id: "u2", role: "member", email: "m@x.example" };

let container;
let root;
beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  api.get.mockReset();
  api.post.mockReset();
  api.put.mockReset();
  global.__user = owner;
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

const answer = (table) =>
  api.get.mockImplementation((url) => {
    const hit = Object.entries(table).find(([k]) => url === k || (k.endsWith("*") && url.startsWith(k.slice(0, -1))));
    return hit ? Promise.resolve({ data: typeof hit[1] === "function" ? hit[1]() : hit[1] }) : Promise.reject(new Error(`unexpected GET ${url}`));
  });

async function show(ui, path = "/") {
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/" element={ui} />
          <Route path="/app/prospects/:id" element={ui} />
        </Routes>
      </MemoryRouter>
    );
  });
  await act(async () => {}); // let the data hooks settle
}
const text = () => container.textContent;
const byId = (id) => container.querySelector(`[data-testid="${id}"]`);

const SUMMARY = { id: "p1", name: "Le Petit Bouchon", city: "Lyon", vertical: "restaurant", website: null, review_status: "pending", score: 40, coverage: 0.43, created_at: "2026-06-01T10:00:00Z" };
const BREAKDOWN = [
  { signal: "no_website", label: "No own website listed", state: "detected", weight: 30, points: 30, explanation: "No website listed in annuaire" },
  { signal: "website_unreachable", label: "Website did not respond correctly", state: "unknown", weight: 25, points: 0, explanation: "Not applicable: no own website listed" },
  { signal: "public_contact_present", label: "Public contact details available", state: "detected", weight: 10, points: 10, explanation: "Public phone and email published" },
];
const DETAIL = {
  ...SUMMARY, contact_email: "resa@petit-bouchon.example", contact_phone: "+33478998877", reviewed_at: null,
  sources: [{ id: "s1", source_name: "fixture_directory", source_url: "fixture://x", external_id: "d-004", license_note: "Fictional data", fetched_at: "2026-06-01T10:00:00Z", fields: { name: "Le Petit Bouchon" } }],
  signals: [{ key: "no_website", label: "No own website listed", state: "detected", evidence: "No website listed in annuaire", observed_at: "2026-06-01T10:00:00Z" }],
  score_detail: { score: 40, coverage: 0.43, version: 1, config_label: "default", config_hash: "abc123", computed_at: "2026-06-01T10:00:00Z", breakdown: BREAKDOWN },
  drafts: [],
};
const STATUS = { dry_run: true, kill_switch: false, paused: false, limits: {}, sent_today: 0, sent_last_hour: 0, last_dispatched_at: null, next_allowed_at: null, blocked_by: null };

describe("Prospects list", () => {
  it("shows an explicit empty state, not placeholder numbers, when nothing was discovered", async () => {
    answer({ "/prospects": { items: [], total: 0 } });
    await show(<Prospects />);
    expect(byId("empty-no-prospects")).toBeTruthy();
    expect(text()).toContain("No prospect yet");
    expect(byId("prospects-table")).toBeNull();
    expect(byId("empty-run-discovery")).toBeTruthy();
  });

  it("lists real rows with score, review state and website", async () => {
    answer({ "/prospects": (() => ({ items: [SUMMARY, { ...SUMMARY, id: "p2", name: "Pizzeria Il Forno", score: null, coverage: null, website: "https://il-forno.example" }], total: 2 })) });
    await show(<Prospects />);
    expect(container.querySelectorAll('[data-testid="prospect-row"]').length).toBe(2);
    expect(text()).toContain("Le Petit Bouchon");
    expect(text()).toContain("none listed");
    expect(text()).toContain("il-forno.example");
    expect(text()).toContain("not scored"); // never scored is not "0"
    expect(byId("prospects-total").textContent).toBe("2 prospects");
  });

  it("surfaces a server failure with a retry instead of a blank page", async () => {
    api.get.mockRejectedValue({ response: { status: 500, data: { detail: "boom" } } });
    await show(<Prospects />);
    expect(byId("error-block").textContent).toContain("boom");
    expect(byId("error-retry")).toBeTruthy();
  });

  it("disables discovery for a member (the API would refuse anyway)", async () => {
    global.__user = member;
    answer({ "/prospects": { items: [], total: 0 } });
    await show(<Prospects />);
    expect(byId("run-discovery").disabled).toBe(true);
  });
});

describe("Prospect detail", () => {
  const load = (extra = {}) =>
    answer({ "/prospects/p1": { ...DETAIL, ...extra }, "/prospects/p1/events": [], "/outbound": [], "/outbound/status": STATUS });

  it("explains the score line by line and never counts unknown against the prospect", async () => {
    load();
    await show(<ProspectDetail />, "/app/prospects/p1");
    expect(byId("detail-name").textContent).toBe("Le Petit Bouchon");
    expect(byId("breakdown-no_website").textContent).toContain("30");
    expect(byId("breakdown-website_unreachable").textContent).toContain("Unknown");
    expect(byId("breakdown-website_unreachable").textContent).not.toContain("detected 25");
    expect(byId("score-total").textContent).toBe("40");
    expect(text()).toContain("2 of 3 weighted signals could be observed");
    expect(text()).toContain("never subtract");
    expect(byId("source-list").textContent).toContain("Licence note: Fictional data");
    expect(byId("history-empty")).toBeTruthy();
  });

  it("shows the empty drafts state and says why a draft cannot be prepared yet", async () => {
    load();
    await show(<ProspectDetail />, "/app/prospects/p1");
    expect(byId("drafts-empty")).toBeTruthy();
    expect(byId("create-draft").disabled).toBe(true);
    expect(byId("create-hint").textContent).toContain("Approve the prospect first");
    expect(byId("dry-run-note")).toBeTruthy();
  });

  it("offers a draft once approved and shows the facts it states", async () => {
    load({ review_status: "approved", drafts: [{ id: "d1", channel: "email", subject: "À propos de X", body: "Bonjour", facts: ["Aucun moyen de réserver."], template_version: "v1", status: "draft", dry_run: true, review_note: null, reviewed_at: null, created_at: "2026-06-01T10:00:00Z" }] });
    await show(<ProspectDetail />, "/app/prospects/p1");
    expect(byId("create-draft").disabled).toBe(false);
    expect(byId("draft-body").textContent).toBe("Bonjour");
    expect(text()).toContain("Aucun moyen de réserver.");
    expect(byId("approve-draft")).toBeTruthy();
    expect(byId("dispatch-draft")).toBeNull(); // only an approved draft can be dispatched
  });

  it("hides decisions from a member", async () => {
    global.__user = member;
    load();
    await show(<ProspectDetail />, "/app/prospects/p1");
    expect(byId("detail-approve").disabled).toBe(true);
    expect(byId("erase-open").disabled).toBe(true);
    expect(text()).toContain("requires owner or admin");
  });
});

describe("Review queue", () => {
  it("shows an explicit empty queue", async () => {
    answer({ "/prospects": { items: [], total: 0 } });
    await show(<ReviewQueue />);
    expect(byId("queue-empty").textContent).toContain("The review queue is empty");
  });

  it("presents the best pending prospect with its evidence and decision buttons", async () => {
    answer({ "/prospects": { items: [SUMMARY], total: 1 }, "/prospects/p1": DETAIL });
    await show(<ReviewQueue />);
    expect(byId("queue-name").textContent).toBe("Le Petit Bouchon");
    expect(byId("score-breakdown")).toBeTruthy();
    expect(byId("queue-approve").disabled).toBe(false);
    expect(byId("queue-position").textContent).toContain("1 of 1 pending prospect");
  });
});

describe("Sending", () => {
  const load = (messages = [], settings = { flags: {}, sender_configured: true, usage: {}, active_score_version: 1 }, status = STATUS) =>
    answer({
      "/outbound/status": status,
      "/outbound/limits": { max_per_day: 20, max_per_hour: 100, min_delay_seconds: 60, sending_paused: false },
      "/outbound": messages,
      "/prospects/settings": settings,
    });

  it("shows real status, the dry-run mode and an empty message history", async () => {
    load();
    await show(<Sending />);
    expect(byId("fact-mode").textContent).toContain("Dry-run");
    expect(byId("fact-kill").textContent).toBe("off");
    expect(byId("fact-today").textContent).toBe("0");
    expect(byId("fact-can-send").textContent).toBe("yes");
    expect(byId("messages-empty")).toBeTruthy();
    expect(byId("usage")).toBeNull(); // no usage recorded: nothing invented
  });

  it("says why sending is blocked and warns when the sender identity is missing", async () => {
    load([], { flags: {}, sender_configured: false, usage: {}, active_score_version: null }, { ...STATUS, kill_switch: true, blocked_by: "kill_switch" });
    await show(<Sending />);
    expect(byId("fact-kill").textContent).toContain("ON");
    expect(byId("fact-can-send").textContent).toContain("kill switch");
    expect(byId("fact-sender").textContent).toBe("not configured");
    expect(text()).toContain("no sender identity");
  });

  it("validates the limits form like the API and only enables saving for a valid change", async () => {
    load();
    await show(<Sending />);
    const day = byId("limit-max_per_day");
    const setValue = async (el, v) => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
      await act(async () => {
        setter.call(el, v);
        el.dispatchEvent(new Event("input", { bubbles: true }));
      });
    };
    expect(byId("save-limits").disabled).toBe(true); // nothing changed
    await setValue(day, "5");
    expect(byId("save-limits").disabled).toBe(false);
    await setValue(day, "-3");
    expect(byId("limit-error-max_per_day")).toBeTruthy();
    expect(byId("save-limits").disabled).toBe(true);
  });

  it("lists dispatched messages, marks dry-run, and shows erased addresses as such", async () => {
    load([
      { id: "m1", lead_id: "p1", draft_id: "d1", channel: "email", to_email: "a@b.example", subject: "S", status: "sent", dry_run: true, adapter: "dry_run_email", provider_message_id: "dryrun-1", error: null, dispatched_at: "2026-06-01T10:00:00Z", created: true },
      { id: "m2", lead_id: "p2", draft_id: "d2", channel: "email", to_email: null, subject: "[erased]", status: "replied", dry_run: true, adapter: "dry_run_email", provider_message_id: "dryrun-2", error: null, dispatched_at: "2026-06-01T11:00:00Z", created: true },
    ]);
    await show(<Sending />);
    expect(container.querySelectorAll('[data-testid="message-row"]').length).toBe(2);
    expect(text()).toContain("a@b.example");
    expect(text()).toContain("erased");
    expect(text()).toContain("dry-run");
  });
});
