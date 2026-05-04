import { useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { X, UploadSimple, CheckCircle, Warning, Info, ClipboardText, FileCsv } from "@phosphor-icons/react";

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
  const [tab, setTab] = useState("paste");
  const [text, setText] = useState(
    "Priya Shah, priya@example.com, Acme Labs, VP Growth, IN\nLucas Moreau, lucas@vivelab.fr, ViveLab, CEO, FR\nHana Kobayashi, hana@kaze.jp, Kaze, Head of Sales, JP"
  );
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const fileRef = useRef(null);

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

  const submitCsv = async () => {
    if (!file) {
      toast.error("Choose a CSV file first");
      return;
    }
    setLoading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/leads/upload-csv", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResult(data);
      toast.success(`CSV imported · ${data.created} created (${data.skipped} duplicates)`);
      onDone?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "CSV upload failed");
    } finally {
      setLoading(false);
    }
  };

  const closeReset = () => {
    setResult(null);
    setFile(null);
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

            <div className="mt-5 flex gap-1 border-b border-[#D6D3C8]">
              <button onClick={() => setTab("paste")} className={`px-4 py-2 text-sm font-display font-semibold tracking-wide border-b-2 -mb-px transition ${tab === "paste" ? "border-[#DC2626] text-[#DC2626]" : "border-transparent text-[#595955] hover:text-[#0A0A0A]"}`} data-testid="tab-paste">
                <ClipboardText size={14} className="inline mr-1.5" /> PASTE TEXT
              </button>
              <button onClick={() => setTab("csv")} className={`px-4 py-2 text-sm font-display font-semibold tracking-wide border-b-2 -mb-px transition ${tab === "csv" ? "border-[#DC2626] text-[#DC2626]" : "border-transparent text-[#595955] hover:text-[#0A0A0A]"}`} data-testid="tab-csv">
                <FileCsv size={14} className="inline mr-1.5" /> CSV FILE
              </button>
            </div>

            {tab === "paste" && (
              <div className="mt-4">
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
                    <div className="p-4 text-[#999995] text-sm italic">No valid rows yet.</div>
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
                  <div className="mono-accent text-[#999995] mt-2">+ {parsed.length - 50} more…</div>
                )}
              </div>
            </div>
              </div>
            )}

            {tab === "csv" && (
              <div className="mt-4">
                <p className="text-[#595955] text-sm mb-3">
                  Upload a <span className="font-mono text-[#0F172A]">.csv</span> with header row. Recognized columns:
                  <span className="font-mono text-[#0F172A]"> full_name (or name), email, phone, company, title, country, language, tags, source, notes</span>
                </p>
                <div
                  onClick={() => fileRef.current?.click()}
                  onDrop={(e) => { e.preventDefault(); if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]); }}
                  onDragOver={(e) => e.preventDefault()}
                  className="surface bg-[#FAFAF7] border-2 border-dashed border-[#D6D3C8] hover:border-[#DC2626] cursor-pointer p-12 text-center transition-colors"
                  data-testid="csv-drop-zone"
                >
                  <FileCsv size={48} weight="duotone" className="text-[#DC2626] mx-auto mb-3" />
                  {file ? (
                    <div>
                      <div className="font-display font-bold text-[#0A0A0A]">{file.name}</div>
                      <div className="text-xs font-mono text-[#595955] mt-1">{(file.size / 1024).toFixed(1)} KB · click to change</div>
                    </div>
                  ) : (
                    <div>
                      <div className="font-display font-semibold">Drop CSV here or click to browse</div>
                      <div className="text-xs font-mono text-[#595955] mt-1">Header row required</div>
                    </div>
                  )}
                  <input
                    ref={fileRef}
                    type="file"
                    accept=".csv"
                    className="hidden"
                    onChange={(e) => e.target.files[0] && setFile(e.target.files[0])}
                    data-testid="csv-file-input"
                  />
                </div>
              </div>
            )}

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
              {tab === "paste" ? (
                <button onClick={submit} disabled={loading || parsed.length === 0} className="btn-primary" data-testid="bulk-import-submit">
                  {loading ? "IMPORTING..." : <><UploadSimple size={14} weight="bold" /> IMPORT {parsed.length} LEADS</>}
                </button>
              ) : (
                <button onClick={submitCsv} disabled={loading || !file} className="btn-primary" data-testid="csv-upload-submit">
                  {loading ? "UPLOADING..." : <><UploadSimple size={14} weight="bold" /> UPLOAD CSV</>}
                </button>
              )}
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
