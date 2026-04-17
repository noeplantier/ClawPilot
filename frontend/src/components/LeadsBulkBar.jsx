import { motion, AnimatePresence } from "framer-motion";
import { useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Trash, Tag, Funnel, X, Check } from "@phosphor-icons/react";

const STAGES = ["new", "contacted", "engaged", "qualified", "won", "lost"];

export default function LeadsBulkBar({ selectedIds, onCleared, onDone }) {
  const [stageOpen, setStageOpen] = useState(false);
  const [tagOpen, setTagOpen] = useState(false);
  const [tagInput, setTagInput] = useState("");

  const count = selectedIds.length;
  if (count === 0) return null;

  const bulkDelete = async () => {
    if (!window.confirm(`Delete ${count} lead(s)? This cannot be undone.`)) return;
    try {
      const { data } = await api.post("/leads/bulk-delete", { lead_ids: selectedIds });
      toast.success(`Deleted ${data.deleted} leads`);
      onCleared();
      onDone();
    } catch (e) {
      toast.error("Bulk delete failed");
    }
  };

  const bulkStage = async (stage) => {
    try {
      await api.post("/leads/bulk-stage", { lead_ids: selectedIds, stage });
      toast.success(`${count} leads moved to ${stage}`);
      setStageOpen(false);
      onDone();
    } catch (e) {
      toast.error("Bulk stage failed");
    }
  };

  const bulkTag = async () => {
    const tags = tagInput.split(",").map((t) => t.trim()).filter(Boolean);
    if (!tags.length) {
      toast.error("Enter at least one tag");
      return;
    }
    try {
      await api.post("/leads/bulk-tag", { lead_ids: selectedIds, tags, mode: "add" });
      toast.success(`Added ${tags.length} tag(s) to ${count} leads`);
      setTagOpen(false);
      setTagInput("");
      onDone();
    } catch (e) {
      toast.error("Bulk tag failed");
    }
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ y: 20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        exit={{ y: 20, opacity: 0 }}
        className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 surface bg-[#0F172A] border-[#0F172A] px-4 py-3 flex items-center gap-3 text-white glow-red"
        data-testid="bulk-toolbar"
      >
        <span className="mono-accent !text-[#DC2626]">{count} selected</span>
        <div className="h-5 w-px bg-white/20" />
        <button onClick={() => setStageOpen(!stageOpen)} className="flex items-center gap-1.5 text-sm hover:text-[#DC2626] relative" data-testid="bulk-stage-button">
          <Funnel size={14} /> Stage
          {stageOpen && (
            <div className="absolute bottom-full left-0 mb-2 surface bg-white text-[#0A0A0A] py-1 min-w-[140px] flex flex-col">
              {STAGES.map((s) => (
                <button key={s} onClick={() => bulkStage(s)} className="px-3 py-1.5 hover:bg-[#FEF2F2] hover:text-[#DC2626] text-left text-xs font-mono uppercase" data-testid={`bulk-stage-${s}`}>
                  {s}
                </button>
              ))}
            </div>
          )}
        </button>
        <button onClick={() => setTagOpen(!tagOpen)} className="flex items-center gap-1.5 text-sm hover:text-[#DC2626] relative" data-testid="bulk-tag-button">
          <Tag size={14} /> Tags
          {tagOpen && (
            <div className="absolute bottom-full left-0 mb-2 surface bg-white text-[#0A0A0A] p-3 w-[260px]" onClick={(e) => e.stopPropagation()}>
              <label className="mono-accent block mb-1.5">add.tags (comma-separated)</label>
              <input
                autoFocus
                className="neo-input text-sm"
                value={tagInput}
                onChange={(e) => setTagInput(e.target.value)}
                placeholder="vip, q2, enterprise"
                onKeyDown={(e) => e.key === "Enter" && bulkTag()}
                data-testid="bulk-tag-input"
              />
              <button onClick={bulkTag} className="btn-primary !py-1.5 mt-2 w-full justify-center" data-testid="bulk-tag-apply">
                <Check size={12} weight="bold" /> APPLY
              </button>
            </div>
          )}
        </button>
        <button onClick={bulkDelete} className="flex items-center gap-1.5 text-sm hover:text-[#DC2626]" data-testid="bulk-delete-button">
          <Trash size={14} /> Delete
        </button>
        <div className="h-5 w-px bg-white/20" />
        <button onClick={onCleared} className="text-white/50 hover:text-white" data-testid="bulk-clear-button">
          <X size={14} />
        </button>
      </motion.div>
    </AnimatePresence>
  );
}
