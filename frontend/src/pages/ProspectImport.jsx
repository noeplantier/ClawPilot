import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, UploadSimple, ShieldCheck } from "@phosphor-icons/react";
import { useAuth } from "@/contexts/AuthContext";
import { canDecide, importsApi, prospectsApi, useAsync } from "@/lib/outreach";
import { describeApiError, formatDateTime } from "@/lib/outreachFormat";
import { LEGAL_BASES, MAX_ROWS, describeImport, fileProblem, formatFromFilename, validateImportForm } from "@/lib/importForm";
import { EmptyBlock, ErrorBlock, LoadingBlock } from "@/components/outreach/States";

const EMPTY = {
  content: "", format: "", filename: "", origin: "", legal_basis: "", legal_basis_note: "", country: "FR", language: "fr",
  vertical: "",
};

function Field({ label, error, children, testId }) {
  return (
    <label className="block">
      <span className="mono-accent block mb-1">{label}</span>
      {children}
      {error && <span role="alert" className="text-xs text-[#991B1B] mt-1 block" data-testid={`${testId}-error`}>{error}</span>}
    </label>
  );
}

function ImportForm({ onImported }) {
  const [values, setValues] = useState(EMPTY);
  const [errors, setErrors] = useState({});
  const [attest, setAttest] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [apiError, setApiError] = useState(null);
  const set = (key) => (e) => { setValues((v) => ({ ...v, [key]: e.target.value })); setResult(null); };

  const pick = async (e) => {
    const file = e.target.files && e.target.files[0];
    setResult(null);
    if (!file) return;
    const problem = fileProblem(file);
    if (problem) { setErrors({ content: problem }); setValues((v) => ({ ...v, content: "", format: "", filename: "" })); return; }
    const text = await file.text();
    setErrors({});
    setValues((v) => ({ ...v, content: text, format: formatFromFilename(file.name), filename: file.name }));
  };

  const run = async (preview) => {
    const check = validateImportForm(values);
    if (!check.ok) { setErrors(check.errors); return; }
    setErrors({});
    setApiError(null);
    setBusy(true);
    try {
      const body = { ...check.data, country: check.data.country.toUpperCase(), language: check.data.language.toLowerCase(), filename: values.filename || null, legal_basis_note: check.data.legal_basis_note || null, preview, attestation: !preview && attest };
      const data = await importsApi.submit(body);
      setResult(data);
      if (!preview) {
        toast.success(`Imported: ${data.created} new prospect${data.created === 1 ? "" : "s"}, all pending your review`);
        setAttest(false);
        onImported();
      }
    } catch (err) {
      setApiError(describeApiError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="surface p-6 space-y-5" data-testid="import-form">
      <div className="flex items-start gap-2 text-sm text-[#475569]">
        <ShieldCheck size={18} className="shrink-0 mt-0.5" />
        <p>
          Only import a list you have the right to use. Nothing is sent and nothing is fetched from the web: every imported prospect is
          <strong> pending</strong> until a human approves it. Up to {MAX_ROWS} rows. Columns: name (required), email, phone, website,
          address, postcode, city, category, description, hours, last_updated (YYYY-MM-DD). An empty cell is stored as unknown, never as a finding.
        </p>
      </div>

      <Field label="file (.csv or .json)" error={errors.content || errors.format} testId="file">
        <input type="file" accept=".csv,.json,text/csv,application/json" onChange={pick} className="neo-input" data-testid="import-file" />
        {values.filename && <span className="text-xs text-[#5F5F5A] mt-1 block" data-testid="import-filename">{values.filename} · {values.format}</span>}
      </Field>

      <div className="grid md:grid-cols-2 gap-4">
        <Field label="where does this list come from?" error={errors.origin} testId="origin">
          <input className="neo-input" value={values.origin} onChange={set("origin")} placeholder="e.g. export of my own customer CRM, March 2026" data-testid="import-origin" />
        </Field>
        <Field label="activity of these companies" error={errors.vertical} testId="vertical">
          <input className="neo-input" value={values.vertical} onChange={set("vertical")} placeholder="e.g. restaurants, craftsmen" data-testid="import-vertical" />
        </Field>
        <Field label="legal basis" error={errors.legal_basis} testId="basis">
          <select className="neo-input" value={values.legal_basis} onChange={set("legal_basis")} data-testid="import-basis">
            <option value="">Choose…</option>
            {LEGAL_BASES.map((b) => <option key={b.value} value={b.value}>{b.label}</option>)}
          </select>
        </Field>
        <Field label="legal basis note (required for “other”)" error={errors.legal_basis_note} testId="note">
          <input className="neo-input" value={values.legal_basis_note} onChange={set("legal_basis_note")} data-testid="import-note" />
        </Field>
        <Field label="country" error={errors.country} testId="country">
          <input className="neo-input font-mono" value={values.country} onChange={set("country")} maxLength={2} data-testid="import-country" />
        </Field>
        <Field label="message language" error={errors.language} testId="language">
          <input className="neo-input font-mono" value={values.language} onChange={set("language")} maxLength={2} data-testid="import-language" />
        </Field>
      </div>

      {apiError && <div role="alert" className="text-sm text-[#991B1B]" data-testid="import-api-error">{apiError}</div>}

      <div className="flex gap-2 flex-wrap items-center">
        <button className="btn-ghost" disabled={busy} onClick={() => run(true)} data-testid="import-preview"><UploadSimple size={14} /> PREVIEW (WRITES NOTHING)</button>
      </div>

      {result && (
        <div className="border border-[#D6D3C8] rounded-md p-4 bg-white space-y-3" data-testid="import-result" role="status">
          <p className="text-sm" data-testid="import-summary">{describeImport(result)}</p>
          {result.already_imported && <p className="text-sm text-[#92400E]" data-testid="import-already">A file with exactly this content was imported before.</p>}
          {result.ignored_columns.length > 0 && <p className="text-xs text-[#5F5F5A]">Ignored columns: {result.ignored_columns.join(", ")}</p>}
          {result.errors.length > 0 && (
            <ul className="text-xs text-[#991B1B] list-disc pl-5" data-testid="import-errors">
              {result.errors.map((e) => <li key={e.row}>row {e.row}: {e.message}</li>)}
              {result.errors_count > result.errors.length && <li>…and {result.errors_count - result.errors.length} more</li>}
            </ul>
          )}
          {result.preview && (
            <div className="space-y-2 border-t border-[#D6D3C8] pt-3">
              <label className="flex items-start gap-2 text-sm">
                <input type="checkbox" checked={attest} onChange={(e) => setAttest(e.target.checked)} className="mt-1" data-testid="import-attest" />
                <span>I confirm that I have the right to use this list for B2B prospecting on the legal basis stated above, and that the origin I gave is accurate.</span>
              </label>
              <button className="btn-ink" disabled={busy || !attest || result.rows_valid === 0} onClick={() => run(false)} data-testid="import-commit">
                IMPORT {result.created + result.updated} PROSPECT{result.created + result.updated === 1 ? "" : "S"}
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

export default function ProspectImport() {
  const { user } = useAuth();
  const page = useAsync(async () => {
    const [settings, batches] = await Promise.all([prospectsApi.settings(), importsApi.list()]);
    return { settings, batches };
  }, []);
  const enabled = page.data && page.data.settings.flags.prospect_import;

  return (
    <div className="p-6 md:p-10 space-y-6 max-w-4xl" data-testid="import-page">
      <div>
        <Link to="/app/prospects" className="text-sm text-[#5F5F5A] inline-flex items-center gap-1"><ArrowLeft size={14} /> Prospects</Link>
        <div className="mono-accent mt-2">// prospects.import</div>
        <h1 className="text-4xl font-black tracking-tighter">Import a list</h1>
      </div>

      {page.loading && !page.data && <LoadingBlock label="Reading the server configuration…" />}
      {page.error && <ErrorBlock message={page.error} onRetry={page.reload} />}

      {page.data && !enabled && (
        <EmptyBlock title="Import is switched off on this server" testId="import-disabled">
          <p>Set <code>FEATURE_PROSPECT_IMPORT=true</code> on the server and redeploy to allow importing a list. It stays off by default.</p>
        </EmptyBlock>
      )}
      {page.data && enabled && !canDecide(user) && (
        <EmptyBlock title="Only an owner or admin can import a list" testId="import-forbidden"><p>Ask an owner or admin of your organisation.</p></EmptyBlock>
      )}
      {page.data && enabled && canDecide(user) && <ImportForm onImported={page.reload} />}

      {page.data && (
        <section className="space-y-3" data-testid="import-history">
          <h2 className="font-display text-xl font-bold">Previous imports</h2>
          {page.data.batches.length === 0 ? (
            <EmptyBlock title="No list has been imported yet" testId="import-history-empty"><p>Each import is recorded here with its origin and legal basis.</p></EmptyBlock>
          ) : (
            <div className="surface overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-[#FAFAF7] border-b border-[#D6D3C8]"><tr className="text-left mono-accent"><th className="p-3">when</th><th className="p-3">file</th><th className="p-3">origin</th><th className="p-3">basis</th><th className="p-3">rows</th><th className="p-3">created</th></tr></thead>
                <tbody>
                  {page.data.batches.map((b) => (
                    <tr key={b.id} className="border-b border-[#EEE]" data-testid="import-batch">
                      <td className="p-3">{formatDateTime(b.created_at)}</td>
                      <td className="p-3">{b.filename || "—"}</td>
                      <td className="p-3">{b.origin}</td>
                      <td className="p-3 font-mono text-xs">{b.legal_basis}</td>
                      <td className="p-3">{b.rows_total}</td>
                      <td className="p-3">{b.summary.prospects_created ?? 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
