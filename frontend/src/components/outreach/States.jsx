import { Warning, CircleNotch, Tray } from "@phosphor-icons/react";

export function LoadingBlock({ label = "Loading…" }) {
  return (
    <div className="surface p-8 flex items-center gap-3 text-[#5F5F5A]" role="status" data-testid="loading-block">
      <CircleNotch size={18} className="animate-spin" /> <span className="font-mono text-sm">{label}</span>
    </div>
  );
}

export function ErrorBlock({ message, onRetry }) {
  return (
    <div className="surface p-6 border-[#FCA5A5] bg-[#FEF2F2] flex items-start gap-3" role="alert" data-testid="error-block">
      <Warning size={20} className="text-[#DC2626] shrink-0 mt-0.5" weight="fill" />
      <div className="flex-1">
        <div className="font-display font-bold text-[#991B1B]">Something went wrong</div>
        <p className="text-sm text-[#7F1D1D] mt-1">{message}</p>
      </div>
      {onRetry && (
        <button onClick={onRetry} className="btn-ghost" data-testid="error-retry">
          RETRY
        </button>
      )}
    </div>
  );
}

// An explicit empty state: says what is missing and what to do, never a blank area or placeholder numbers.
export function EmptyBlock({ title, children, testId = "empty-block" }) {
  return (
    <div className="surface p-10 text-center" data-testid={testId}>
      <Tray size={28} className="mx-auto text-[#6B6B66]" />
      <div className="font-display font-bold text-lg mt-3">{title}</div>
      <div className="text-sm text-[#5F5F5A] mt-2 max-w-xl mx-auto space-y-3">{children}</div>
    </div>
  );
}
