import Footer from "@/components/Footer";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import { ArrowRight } from "@phosphor-icons/react";
import Logo, { LogoMark } from "@/components/Logo";


export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await login(email, password);
      toast.success("Welcome back, operator.");
      navigate("/app/dashboard");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Login failed");
    } finally {
      setLoading(false);
    }
  };


  return (
    <div className="min-h-screen grid lg:grid-cols-5 grid-bg">
      {/* Left form */}
      <div className="lg:col-span-2 flex flex-col px-8 md:px-16 py-10 relative bg-void-elevated/80 backdrop-blur-md border-r border-border">
        <Link to="/" className="inline-flex" data-testid="brand-logo" aria-label="Plantiers - OutreachOS">
          <Logo />
        </Link>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="flex-1 flex flex-col justify-center max-w-sm w-full"
        >
          <div className="mono-accent mb-4">// SECURE · AUTH</div>
          <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tighter text-foreground">
            Qualify. Review.<br /> Then <span className="gradient-word">send.</span>
          </h1>
          <p className="mt-4 text-soft leading-relaxed">
            Sign in to run compliant B2B outreach: detect, qualify, validate, then send.
          </p>

          <form onSubmit={submit} className="mt-10 space-y-4" data-testid="login-form">
            <div>
              <label className="mono-accent block mb-2" htmlFor="email-input">email</label>
              <input
                id="email-input"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="neo-input font-mono w-full"
                placeholder="you@example.com"
                data-testid="login-email-input"
                autoComplete="username"
              />
            </div>
            <div>
              <label className="mono-accent block mb-2" htmlFor="password-input">password</label>
              <input
                id="password-input"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="neo-input font-mono w-full"
                placeholder="••••••••"
                data-testid="login-password-input"
                autoComplete="current-password"
              />
            </div>

            <button type="submit" disabled={loading} className="btn-primary w-full justify-center mt-6" data-testid="login-submit-button">
              {loading ? "Authenticating..." : "ENTER COMMAND CENTER"} <ArrowRight size={16} weight="bold" />
            </button>
          </form>

          <p className="mt-8 text-sm text-soft">
            No account?{" "}
            <Link to="/register" className="text-brand-lilac underline" data-testid="goto-register-link">
              Request access →
            </Link>
          </p>
        </motion.div>

        <Footer className="mt-6 !border-0 !bg-transparent !px-0" />
      </div>

      {/* Right visual: the product as the prospecting side of plantiers.com */}
      <div className="hidden lg:block lg:col-span-3 relative overflow-hidden grain">
        <div aria-hidden="true" className="absolute inset-0" style={{ background: "radial-gradient(70% 55% at 22% 18%, rgba(124,58,237,0.42), transparent 62%), radial-gradient(55% 45% at 86% 78%, rgba(91,33,182,0.38), transparent 62%), radial-gradient(40% 35% at 60% 100%, rgba(34,197,94,0.10), transparent 62%)" }} />
        <div className="absolute inset-0" style={{ backgroundImage: "linear-gradient(rgba(255,255,255,0.035) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.035) 1px, transparent 1px)", backgroundSize: "56px 56px" }} />

        <div className="relative z-10 h-full flex flex-col justify-between p-14 text-white">
          <div className="flex items-center gap-2">
            <span className="pos-live-dot" aria-hidden="true" />
            <span className="mono-accent">// DRY-RUN BY DEFAULT · HUMAN REVIEW BEFORE SENDING</span>
          </div>

          <div className="max-w-xl">
            <LogoMark decorative className="h-28 mb-8 drop-shadow-[0_0_40px_rgba(124,58,237,0.45)]" />
            <div className="mono-accent mb-3">/// plantiers.outreachos</div>
            <h2 className="text-4xl md:text-5xl font-extrabold tracking-tighter leading-[0.98] text-white">
              Detect the need.<br />
              <span className="gradient-word">Reach out responsibly.</span>
            </h2>
            <p className="mt-5 text-soft max-w-md">
              Find companies that need digital solutions, explain every score, and send only what a human approved.
            </p>
            <div className="mt-6 flex gap-2 flex-wrap">
              {["signals", "explainable score", "human review", "consent", "audit"].map((t) => (
                <span key={t} className="chip">{t}</span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}