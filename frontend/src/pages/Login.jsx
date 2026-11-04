import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import { ArrowRight, CircleNotch, LockSimple, ShieldCheck } from "@phosphor-icons/react";
import AuthShell from "@/components/AuthShell";

// A keyboard that pops up on its own hides half of a phone: the field is focused automatically only with a fine pointer (a mouse).
const finePointer = () => typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(pointer: fine)").matches;

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setErrorMsg("");
    try {
      await login(email, password);
      toast.success("Welcome back, operator.");
      navigate("/app/dashboard");
    } catch (err) {
      const msg = err?.response?.data?.detail || "Login failed. Check your credentials.";
      setErrorMsg(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell testId="login-page">
      <div className="mb-4 flex items-center gap-1.5">
        <span className="mono-accent flex items-center gap-1.5 text-[11px] text-brand-lilac">
          <LockSimple size={13} weight="bold" aria-hidden="true" /> // SECURE · AUTHENTICATION
        </span>
      </div>

      <h1 className="text-2xl font-extrabold leading-tight tracking-tight text-white sm:text-3xl">
        Qualify. Review.<br />
        Then <span className="gradient-word">send.</span>
      </h1>
      <p className="mt-2.5 text-xs leading-relaxed text-soft sm:text-sm">
        Sign in to the OutreachOS command center: discover candidates, qualify them on what is known, then prepare outreach for a person to approve.
      </p>

      {errorMsg && (
        <div role="alert" className="mt-4 flex items-start gap-2 rounded-xl border border-red-500/20 bg-red-500/10 p-3 text-xs text-red-300">
          <span className="font-mono font-bold text-red-400">ERR:</span>
          <span className="flex-1">{errorMsg}</span>
        </div>
      )}

      <form onSubmit={submit} className="mt-6 space-y-4" data-testid="login-form">
        <div>
          <label className="mono-accent mb-1.5 block text-xs text-soft" htmlFor="email-input">email</label>
          <input
            id="email-input"
            name="username"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="neo-input w-full font-mono"
            placeholder="you@company.com"
            data-testid="login-email-input"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            autoFocus={finePointer()}
          />
        </div>
        <div>
          <label className="mono-accent mb-1.5 block text-xs text-soft" htmlFor="password-input">password</label>
          <input
            id="password-input"
            name="password"
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="neo-input w-full font-mono"
            placeholder="••••••••••••"
            data-testid="login-password-input"
            autoComplete="current-password"
          />
        </div>

        <button type="submit" disabled={loading} className="btn-primary mt-6 w-full justify-center" data-testid="login-submit-button">
          {loading ? (
            <>
              <CircleNotch size={16} weight="bold" className="animate-spin" /> AUTHENTICATING...
            </>
          ) : (
            <>
              ENTER COMMAND CENTER <ArrowRight size={16} weight="bold" />
            </>
          )}
        </button>
      </form>

      <div className="mt-6 flex items-center justify-between border-t border-white/5 pt-5 text-xs text-soft">
        <span>No credentials yet?</span>
        <Link to="/register" className="inline-flex items-center gap-1 rounded font-medium text-brand-lilac hover:underline" data-testid="goto-register-link">
          Request access →
        </Link>
      </div>

      <div className="mt-4 flex items-center justify-center gap-1.5 font-mono text-[11px] text-faint">
        <ShieldCheck size={13} weight="bold" className="text-brand-lilac/70" aria-hidden="true" />
        <span>Nothing is sent without a person&apos;s approval</span>
      </div>
    </AuthShell>
  );
}
