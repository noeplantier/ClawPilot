import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, ArrowsClockwise, Check, Envelope, Globe, MapPin, Phone, Trash, X } from "@phosphor-icons/react";
import { useAuth } from "@/contexts/AuthContext";
import { canDecide, outboundApi, prospectsApi, useAsync } from "@/lib/outreach";
import { REVIEW_META, describeApiError, domainOf, mergeTimeline } from "@/lib/outreachFormat";
import ScoreBadge from "@/components/outreach/ScoreBadge";
import ScoreBreakdown from "@/components/outreach/ScoreBreakdown";
import SignalList from "@/components/outreach/SignalList";
import SourceList from "@/components/outreach/SourceList";
import HistoryTimeline from "@/components/outreach/HistoryTimeline";
import DraftPanel from "@/components/outreach/DraftPanel";
import { ErrorBlock, LoadingBlock } from "@/components/outreach/States";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

function Section({ title, hint, actions, children, testId }) {
  return (
    <section className="surface p-5 space-y-3" data-testid={testId}>
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h2 className="font-display text-xl font-bold">{title}</h2>
          {hint && <p className="text-sm text-[#5F5F5A]">{hint}</p>}
        </div>
        {actions}
      </div>
      {children}
    </section>
  );
}

export default function ProspectDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);

  // Everything on this page is one coherent read: the prospect, its audit trail, its messages (with events) and the
  // sending status. A failure of the secondary reads degrades to an empty section instead of hiding the prospect.
  const page = useAsync(async () => {
    const prospect = await prospectsApi.get(id);
    const [events, messages, status] = await Promise.all([
      prospectsApi.events(id).catch(() => []),
      outboundApi.list({ limit: 200 }).catch(() => []),
      outboundApi.status().catch(() => null),
    ]);
    const mine = messages.filter((m) => m.lead_id === id);
    const withEvents = await Promise.all(mine.map((m) => outboundApi.get(m.id).catch(() => ({ ...m, events: [] }))));
    return { prospect, events, messages: withEvents, status };
  }, [id]);

  const run = async (key, fn, success) => {
    setBusy(key);
    setError(null);
    try {
      await fn();
      if (success) toast.success(success);
      await page.reload();
    } catch (e) {
      setError(describeApiError(e));
    } finally {
      setBusy(null);
    }
  };

  const erase = async () => {
    setBusy("erase");
    try {
      await prospectsApi.erase(id);
      toast.success("Prospect erased and suppressed");
      navigate("/app/prospects");
    } catch (e) {
      setError(describeApiError(e));
      setBusy(null);
    }
  };

  if (page.loading && !page.data) return <div className="p-6 md:p-10"><LoadingBlock label="Loading prospect…" /></div>;
  if (page.error)
    return (
      <div className="p-6 md:p-10 space-y-4">
        <Link to="/app/prospects" className="underline inline-flex items-center gap-1 text-sm"><ArrowLeft size={12} /> back to prospects</Link>
        <ErrorBlock message={page.error} onRetry={page.reload} />
      </div>
    );

  const { prospect: p, events, messages, status } = page.data;
  const decide = canDecide(user);
  const timeline = mergeTimeline(events, messages, user && user.id);

  return (
    <div className="p-6 md:p-10 space-y-6 max-w-5xl" data-testid="prospect-detail">
      <Link to="/app/prospects" className="underline inline-flex items-center gap-1 text-sm"><ArrowLeft size={12} /> back to prospects</Link>

      <header className="flex items-start justify-between flex-wrap gap-4">
        <div className="space-y-2">
          <div className="mono-accent">// prospect · {p.vertical || "unclassified"}</div>
          <h1 className="text-4xl font-black tracking-tighter" data-testid="detail-name">{p.name}</h1>
          <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-[#475569]">
            <span className="inline-flex items-center gap-1"><MapPin size={14} />{p.city || "city unknown"}</span>
            <span className="inline-flex items-center gap-1"><Globe size={14} />{domainOf(p.website) || "no own website listed"}</span>
            <span className="inline-flex items-center gap-1"><Envelope size={14} />{p.contact_email || "no public e-mail"}</span>
            <span className="inline-flex items-center gap-1"><Phone size={14} />{p.contact_phone || "no public phone"}</span>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <ScoreBadge score={p.score} coverage={p.coverage} showCoverage />
          <span className={`chip ${REVIEW_META[p.review_status].chip}`} data-testid="detail-status">{REVIEW_META[p.review_status].label}</span>
        </div>
      </header>

      {error && (
        <div role="alert" className="text-sm text-[#991B1B] bg-[#FEF2F2] border border-[#FCA5A5] rounded-md p-3" data-testid="detail-error">{error}</div>
      )}

      <Section title="Review" hint="A person decides. Approving makes the prospect eligible for a draft; it never sends anything." testId="section-review">
        <textarea className="neo-input" rows={2} maxLength={1000} placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} data-testid="detail-note" />
        <div className="flex flex-wrap gap-2 items-center">
          <button className="btn-primary" disabled={!decide || busy === "approve" || p.review_status === "approved"}
            onClick={() => run("approve", () => prospectsApi.review(id, "approve", note), "Prospect approved")} data-testid="detail-approve">
            <Check size={14} weight="bold" /> APPROVE
          </button>
          <button className="btn-ghost" disabled={!decide || busy === "reject" || p.review_status === "rejected"}
            onClick={() => run("reject", () => prospectsApi.review(id, "reject", note), "Prospect rejected")} data-testid="detail-reject">
            <X size={14} /> REJECT
          </button>
          {!decide && <span className="mono-accent text-[#999995]">deciding requires owner or admin</span>}
          {p.reviewed_at && <span className="mono-accent text-[#5F5F5A]">last decision {new Date(p.reviewed_at).toLocaleString()}</span>}
        </div>
      </Section>

      <Section
        title="Score justification"
        testId="section-score"
        actions={
          <button className="btn-ghost" disabled={!decide || busy === "rescore"}
            onClick={() => run("rescore", () => prospectsApi.rescore(id), "Score recomputed from the stored signals")} data-testid="rescore"
            title="Recomputes with the active configuration; no new observation is made">
            <ArrowsClockwise size={14} /> RECOMPUTE
          </button>
        }
      >
        <ScoreBreakdown detail={p.score_detail} />
      </Section>

      <Section title="Signals" hint="What was observed, with the evidence and when." testId="section-signals">
        <SignalList signals={p.signals} />
      </Section>

      <Section title="Drafts" hint="Messages prepared for a human to approve." testId="section-drafts">
        <DraftPanel prospect={p} drafts={p.drafts} messages={messages} canDecide={decide} dryRun={status ? status.dry_run : null} onChanged={page.reload} />
      </Section>

      <Section title="Provenance" hint="Every source this prospect was built from." testId="section-sources">
        <SourceList sources={p.sources} />
      </Section>

      <Section title="History" hint="Decisions, drafts and message events, newest first." testId="section-history">
        <HistoryTimeline items={timeline} />
      </Section>

      <Section title="Erase" hint="Right to erasure: blanks the personal data everywhere it was copied and adds the identity to your suppression list." testId="section-erase">
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <button className="btn-ghost !text-[#991B1B] !border-[#FCA5A5]" disabled={!decide || busy === "erase"} data-testid="erase-open">
              <Trash size={14} /> ERASE THIS PROSPECT
            </button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Erase {p.name}?</AlertDialogTitle>
              <AlertDialogDescription>
                This cannot be undone. The contact data, source copies, evidence, score detail and drafts are blanked, and the e-mail, phone and
                domain are suppressed so this organisation will not rediscover them.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={erase} data-testid="erase-confirm">Erase permanently</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </Section>
    </div>
  );
}
