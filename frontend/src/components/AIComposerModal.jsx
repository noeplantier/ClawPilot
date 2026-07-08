import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Sparkle, X, Copy, Translate, ArrowClockwise, Stack, Check } from "@phosphor-icons/react";

const LANGUAGES = [
  { v: "en", l: "English" }, { v: "es", l: "Español" }, { v: "fr", l: "Français" },
  { v: "de", l: "Deutsch" }, { v: "ja", l: "日本語" }, { v: "pt", l: "Português" },
  { v: "it", l: "Italiano" }, { v: "zh", l: "中文" }, { v: "ar", l: "العربية" },
  { v: "hi", l: "हिंदी" },
];
const TONES = ["professional", "friendly", "casual", "urgent", "concise"];

export default function AIComposerModal({ open, onClose, defaults }) {
  const [form, setForm] = useState({
    recipient_name: defaults?.recipient_name || "",
    company: defaults?.company || "",
    product: defaults?.product || "ClawPilot agent-powered outreach platform",
    language: defaults?.language || "en",
    tone: "professional",
    channel: "email",
    goal: "book a 15-min discovery call",
  });
  const [result, setResult] = useState(null);
  const [variants, setVariants] = useState(null);
  const [loading, setLoading] = useState(false);
  const [variantsLoading, setVariantsLoading] = useState(false);

  useEffect(() => {
    if (open && defaults) {
      setForm((f) => ({ ...f, ...defaults }));
    }
    if (!open) { setResult(null); setVariants(null); }
  }, [open, defaults]);

  const update = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const generate = async () => {
    if (!form.recipient_name || !form.product) {
      toast.error("Recipient and product are required");
      return;
    }
    setLoading(true);
    setVariants(null);
    try {
      const { data } = await api.post("/ai/generate", form);
      setResult(data);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Generation failed");
    } finally {
      setLoading(false);
    }
  };

  const genVariants = async () => {
    if (!form.recipient_name || !form.product) {
      toast.error("Recipient and product are required");
      return;
    }
    setVariantsLoading(true);
    setResult(null);
    try {
      const { data } = await api.post("/ai/generate/variants", form);
      setVariants(data.variants);
    } catch (err) {
      toast.error("Variants generation failed");
    } finally {
      setVariantsLoading(false);
    }
  };

  const pickVariant = (v) => {
    setResult(v);
    setVariants(null);
    toast.success("Variant selected");
  };

  const copy = () => {
    const text = (result?.subject ? `Subject: ${result.subject}\n\n` : "") + (result?.body || "");
    navigator.clipboard.writeText(text);
    toast.success("Copied to clipboard");
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 bg-[#0F172A]/60 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={onClose}
        >
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10 }}
            onClick={(e) => e.stopPropagation()}
            className={`relative w-full max-w-4xl surface p-6 md:p-8 ${loading ? "glow-purple" : ""}`}
            data-testid="ai-composer-modal"
          >
            <button onClick={onClose} className="absolute top-4 right-4 text-[#6B6B66] hover:text-[#DC2626]" data-testid="close-ai-composer">
              <X size={20} />
            </button>

            <div className="flex items-center gap-2 mb-2">
              <Sparkle size={18} weight="fill" className="text-[#0F172A]" />
              <span className="mono-accent text-[#0F172A]">/// gemini-3-flash</span>
            </div>
            <h2 className="text-2xl font-black tracking-tighter">AI Message Composer</h2>
            <p className="text-[#6B6B66] text-sm mt-1">Multi-language, tone-aware outreach copy generated in seconds.</p>

            <div className="grid md:grid-cols-2 gap-6 mt-6">
              <div className="space-y-3">
                <div>
                  <label className="mono-accent block mb-1.5">recipient.name</label>
                  <input className="neo-input" value={form.recipient_name} onChange={update("recipient_name")} placeholder="Priya Shah" data-testid="ai-recipient-input" />
                </div>
                <div>
                  <label className="mono-accent block mb-1.5">company</label>
                  <input className="neo-input" value={form.company} onChange={update("company")} placeholder="Acme Labs" data-testid="ai-company-input" />
                </div>
                <div>
                  <label className="mono-accent block mb-1.5">product / offer</label>
                  <textarea rows={2} className="neo-input" value={form.product} onChange={update("product")} data-testid="ai-product-input" />
                </div>
                <div>
                  <label className="mono-accent block mb-1.5">goal</label>
                  <input className="neo-input" value={form.goal} onChange={update("goal")} data-testid="ai-goal-input" />
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <label className="mono-accent block mb-1.5">channel</label>
                    <select className="neo-input" value={form.channel} onChange={update("channel")} data-testid="ai-channel-select">
                      <option value="email">email</option>
                      <option value="whatsapp">whatsapp</option>
                    </select>
                  </div>
                  <div>
                    <label className="mono-accent block mb-1.5">tone</label>
                    <select className="neo-input" value={form.tone} onChange={update("tone")} data-testid="ai-tone-select">
                      {TONES.map((t) => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="mono-accent block mb-1.5">lang</label>
                    <select className="neo-input" value={form.language} onChange={update("language")} data-testid="ai-language-select">
                      {LANGUAGES.map((l) => <option key={l.v} value={l.v}>{l.l}</option>)}
                    </select>
                  </div>
                </div>

                <button onClick={generate} disabled={loading || variantsLoading} className="btn-primary w-full justify-center mt-2" data-testid="ai-generate-button">
                  {loading ? <><ArrowClockwise size={16} className="spin-slow" /> GENERATING…</> : <><Sparkle size={16} weight="fill" /> GENERATE MESSAGE</>}
                </button>
                <button onClick={genVariants} disabled={loading || variantsLoading} className="btn-ink w-full justify-center" data-testid="ai-variants-button">
                  {variantsLoading ? <><ArrowClockwise size={16} className="spin-slow" /> GENERATING 3…</> : <><Stack size={16} weight="fill" /> GENERATE 3 VARIANTS</>}
                </button>
              </div>

              {/* Result */}
              <div className="surface bg-[#FAFAF7] p-5 min-h-[380px] relative">
                <div className="flex items-center justify-between mb-3">
                  <span className="mono-accent">output</span>
                  {result && (
                    <button onClick={copy} className="chip chip-cyan hover:border-[#DC2626]" data-testid="ai-copy-button">
                      <Copy size={12} /> COPY
                    </button>
                  )}
                </div>
                {!result && !loading && !variants && !variantsLoading && (
                  <div className="h-full flex flex-col items-center justify-center text-center text-[#999995] py-16">
                    <Translate size={48} weight="duotone" className="text-[#D4D4C8] mb-3" />
                    <div className="mono-accent">awaiting.prompt</div>
                    <p className="text-xs mt-2 max-w-[220px]">Fill the form and hit generate — or request 3 tone variants.</p>
                  </div>
                )}
                {(loading || variantsLoading) && (
                  <div className="h-full flex items-center justify-center text-[#DC2626]">
                    <ArrowClockwise size={32} className="spin-slow" />
                  </div>
                )}

                {variants && (
                  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-3">
                    {["professional", "friendly", "urgent"].map((tone, i) => {
                      const v = variants[i];
                      if (!v) return null;
                      return (
                        <div key={tone} className="surface p-3 hover:border-[#DC2626]/40 transition cursor-pointer" onClick={() => pickVariant(v)} data-testid={`variant-${tone}`}>
                          <div className="flex items-center justify-between mb-2">
                            <span className="chip chip-red">{tone}</span>
                            <button className="btn-primary !py-1 !px-2 text-xs"><Check size={10} /> USE</button>
                          </div>
                          {v.subject && <div className="text-sm font-semibold text-[#0A0A0A] mb-1">{v.subject}</div>}
                          <div className="text-xs text-[#595955] font-mono whitespace-pre-wrap line-clamp-4">{v.body}</div>
                        </div>
                      );
                    })}
                  </motion.div>
                )}

                {result && (
                  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-3 font-mono text-sm">
                    {result.subject && (
                      <div>
                        <div className="mono-accent text-[#595955] mb-1">subject</div>
                        <div className="text-[#0A0A0A] font-display font-bold">{result.subject}</div>
                      </div>
                    )}
                    <div>
                      <div className="mono-accent text-[#595955] mb-1">body</div>
                      <div className="text-[#1a1a1a] whitespace-pre-wrap leading-relaxed" data-testid="ai-result-body">{result.body}</div>
                    </div>
                    <div className="pt-3 border-t border-[#D6D3C8] flex items-center justify-between">
                      <span className="chip chip-purple">{result.language}</span>
                      <span className="mono-accent text-[#999995]">gemini-3-flash · {(result.body || "").length} chars</span>
                    </div>
                  </motion.div>
                )}
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
