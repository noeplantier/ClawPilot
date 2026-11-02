import Footer from "@/components/Footer";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import { ArrowRight, CircleNotch, LockSimple, ShieldCheck } from "@phosphor-icons/react";
import Logo from "@/components/Logo";

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
    <div className="min-h-[100dvh] w-full flex flex-col justify-between items-center relative overflow-x-hidden overflow-y-auto px-4 py-8 sm:py-12 grid-bg grain">
      {/* Background ambient gradient inspired by noeplantier.com */}
      <div
        aria-hidden="true"
        className="pointer-events-none fixed inset-0 z-0 opacity-40"
        style={{
          background:
            "radial-gradient(650px circle at 50% 25%, rgba(124, 58, 237, 0.18), transparent 70%), radial-gradient(400px circle at 80% 80%, rgba(74, 222, 128, 0.05), transparent 60%)",
        }}
      />

      {/* Top brand anchor */}
      <header className="relative z-10 w-full max-w-md flex items-center justify-between pt-2 pb-4">
        <Link to="/" className="inline-flex focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-violet rounded-lg" data-testid="brand-logo" aria-label="Plantiers - OutreachOS">
          <Logo />
        </Link>
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-mono tracking-wider text-brand-lilac bg-brand-violet/10 border border-brand-violet/25">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" aria-hidden="true" />
          ONLINE
        </span>
      </header>

      {/* Truly centered login card */}
      <main className="relative z-10 w-full max-w-md my-auto">
        <motion.div
          initial={{ opacity: 0, y: 12, scale: 0.99 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.35, ease: "easeOut" }}
          className="w-full bg-[#0C0A14]/90 backdrop-blur-xl border border-white/10 rounded-2xl p-6 sm:p-9 shadow-[0_20px_50px_rgba(0,0,0,0.5),0_0_30px_rgba(124,58,237,0.12)] relative"
        >
          <div className="flex items-center justify-between mb-4">
            <span className="mono-accent text-[11px] text-brand-lilac flex items-center gap-1.5">
              <LockSimple size={13} weight="bold" /> // SECURE · AUTHENTICATION
            </span>
            <span className="text-[10px] font-mono text-white/40 tracking-wider">v2.4</span>
          </div>

          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-white leading-tight">
            Qualify. Review.<br />
            Then <span className="gradient-word">send.</span>
          </h1>

          <p className="mt-2.5 text-xs sm:text-sm text-soft leading-relaxed">
            Connect to OutreachOS command center: discover candidates, verify channels, qualify strictly, then prepare outreach.
          </p>

          {errorMsg && (
            <div
              role="alert"
              className="mt-4 p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-300 text-xs flex items-start gap-2 animate-in fade-in"
            >
              <span className="font-mono font-bold text-red-400">ERR:</span>
              <span className="flex-1">{errorMsg}</span>
            </div>
          )}

          <form onSubmit={submit} className="mt-6 space-y-4" data-testid="login-form">
            <div>
              <label className="mono-accent block mb-1.5 text-xs text-soft flex items-center justify-between" htmlFor="email-input">
                <span>email</span>
                <span className="text-[10px] text-white/30 lowercase font-mono">operator id</span>
              </label>
              <input
                id="email-input"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="neo-input font-mono w-full px-3.5 py-2.5 rounded-xl bg-white/[0.04] border border-white/10 text-white placeholder-white/20 text-sm focus:outline-none focus:ring-2 focus:ring-brand-violet focus:border-brand-violet transition-all"
                placeholder="operator@plantiers.com"
                data-testid="login-email-input"
                autoComplete="username"
                autoFocus
              />
            </div>

            <div>
              <label className="mono-accent block mb-1.5 text-xs text-soft flex items-center justify-between" htmlFor="password-input">
                <span>password</span>
                <span className="text-[10px] text-white/30 lowercase font-mono">secure key</span>
              </label>
              <input
                id="password-input"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="neo-input font-mono w-full px-3.5 py-2.5 rounded-xl bg-white/[0.04] border border-white/10 text-white placeholder-white/20 text-sm focus:outline-none focus:ring-2 focus:ring-brand-violet focus:border-brand-violet transition-all"
                placeholder="••••••••••••"
                data-testid="login-password-input"
                autoComplete="current-password"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full justify-center mt-6 py-3 rounded-xl text-sm font-semibold tracking-wide shadow-lg shadow-brand-violet/20 hover:shadow-brand-violet/35 transition-all active:scale-[0.99] disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
              data-testid="login-submit-button"
            >
              {loading ? (
                <>
                  <CircleNotch size={16} weight="bold" className="animate-spin" />
                  AUTHENTICATING...
                </>
              ) : (
                <>
                  ENTER COMMAND CENTER <ArrowRight size={16} weight="bold" />
                </>
              )}
            </button>
          </form>

          <div className="mt-6 pt-5 border-t border-white/5 flex items-center justify-between text-xs text-soft">
            <span>No credentials yet?</span>
            <Link
              to="/register"
              className="text-brand-lilac font-medium hover:underline inline-flex items-center gap-1 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-brand-violet rounded"
              data-testid="goto-register-link"
            >
              Request access →
            </Link>
          </div>

          <div className="mt-4 flex items-center justify-center gap-1.5 text-[11px] font-mono text-white/35">
            <ShieldCheck size={13} weight="bold" className="text-brand-lilac/70" />
            <span>Dry-run verified · Human review before send</span>
          </div>
        </motion.div>
      </main>

      {/* Bottom centered footer */}
      <Footer className="relative z-10 w-full max-w-md !border-0 !bg-transparent !px-0 !py-4 text-center" />
    </div>
  );
}