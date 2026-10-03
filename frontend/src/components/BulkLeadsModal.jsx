import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { X, UploadSimple, CheckCircle, Warning, Info } from "@phosphor-icons/react";

// Parses lines like "Name, email@x.com, Company, Title, Country"
// Flexible: fields in order, comma-separated. First field (name) is required.
const FIELDS = ["full_name", "email", "company", "title", "country"];

function parseRows(text) {
  const rows = [];
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  for (const line of lines) {
    const parts = line.split(",").map((s) => s.trim());
    if (!parts[0]) continue;
    const row = {};
    FIELDS.forEach((f, i) => {
      if (parts[i] && parts[i].length > 0) row[f] = parts[i];
    });
    rows.push(row);
  }
  return rows;
}

export default function BulkLeadsModal({ open, onClose, onDone }) {
  const [text, setText] = useState(
    "Priya Shah, priya@example.com, Acme Labs, VP Growth, IN\nLucas Moreau, lucas@vivelab.fr, ViveLab, CEO, FR\nHana Kobayashi, hana@kaze.jp, Kaze, Head of Sales, JP"
  );
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const parsed = parseRows(text);

  const submit = async () => {
    if (!parsed.length) {
      toast.error("Add at least one lead");
      return;
    }
    setLoading(true);
    try {
      const { data } = await api.post("/leads/bulk", { leads: parsed });
      setResult(data);
      toast.success(`Imported ${data.created} leads (${data.skipped} duplicates skipped)`);
      onDone?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Import failed");
    } finally {
      setLoading(false);
    }
  };

  const closeReset = () => {
    setResult(null);
    onClose();
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 bg-[#0F172A]/60 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={closeReset}
        >
          <motion.div
            initial={{ y: 10 }}
            animate={{ y: 0 }}
            className="surface w-full max-w-3xl p-8 relative max-h-[92vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
            data-testid="bulk-leads-modal"
          >
            <button onClick={closeReset} className="absolute top-4 right-4 text-[#595955] hover:text-[#DC2626]" data-testid="close-bulk-leads">
              <X size={20} />
            </button>
            <div className="mono-accent">/// leads.bulk.import</div>
            <h2 className="text-2xl font-black tracking-tighter mt-1 flex items-center gap-2">
              <UploadSimple size={22} weight="duotone" className="text-[#DC2626]" />
              Bulk Import Leads
            </h2>
            <p className="text-[#595955] mt-1 text-sm">
              One lead per line · comma-separated: <span className="font-mono text-[#0F172A]">name, email, company, title, country</span>
            </p>

            <div className="mt-6 grid md:grid-cols-2 gap-4">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="mono-accent">paste.data</span>
                  <span className="chip chip-red font-mono">{parsed.length} detected</span>
                </div>
                <textarea
                  rows={14}
                  className="neo-input font-mono text-sm"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  data-testid="bulk-leads-textarea"
                />
              </div>
              <div>
                <span className="mono-accent block mb-2">preview</span>
                <div className="surface bg-[#FAFAF7] max-h-[300px] overflow-y-auto divide-y divide-[#D6D3C8]">
                  {parsed.length === 0 && (
                    <div className="p-4 text-[#6B6B66] text-sm italic">No valid rows yet.</div>
                  )}
                  {parsed.slice(0, 50).map((r, i) => (
                    <div key={i} className="p-2.5 text-xs font-mono">
                      <div className="text-[#0A0A0A] font-semibold">{r.full_name}</div>
                      <div className="text-[#595955] truncate">
                        {r.email && <span>{r.email} · </span>}
                        {r.company || ""}
                      </div>
                    </div>
                  ))}
                </div>
                {parsed.length > 50 && (
                  <div className="mono-accent text-[#6B6B66] mt-2">+ {parsed.length - 50} more…</div>
                )}
              </div>
            </div>

            {result && (
              <div className="surface bg-[#F4FDF9] border-[#10B981]/40 p-4 mt-4 flex gap-3" data-testid="bulk-result">
                <CheckCircle size={22} weight="fill" className="text-[#10B981] flex-shrink-0 mt-0.5" />
                <div className="text-sm">
                  <div className="font-display font-bold">Import complete</div>
                  <div className="text-[#595955] mt-1 font-mono">
                    {result.created} created · {result.skipped} skipped (duplicate emails)
                    {result.errors?.length > 0 && ` · ${result.errors.length} errors`}
                  </div>
                  {result.errors?.length > 0 && (
                    <ul className="mt-2 text-xs text-[#991B1B] list-disc pl-4">
                      {result.errors.slice(0, 3).map((e, i) => <li key={i}>{e}</li>)}
                    </ul>
                  )}
                </div>
              </div>
            )}

            <div className="flex gap-3 mt-6 items-center">
              <button onClick={submit} disabled={loading || parsed.length === 0} className="btn-primary" data-testid="bulk-import-submit">
                {loading ? "IMPORTING..." : <><UploadSimple size={14} weight="bold" /> IMPORT {parsed.length} LEADS</>}
              </button>
              <button onClick={closeReset} className="btn-ghost">CLOSE</button>
              <div className="ml-auto flex items-center gap-1.5 text-xs font-mono text-[#595955]">
                <Info size={12} /> duplicates are auto-skipped by email
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
