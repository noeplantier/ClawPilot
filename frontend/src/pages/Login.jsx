import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import { Lightning, ArrowRight } from "@phosphor-icons/react";

const HERO_BG = "https://images.unsplash.com/photo-1754738381772-897447d10eb6?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1OTV8MHwxfHNlYXJjaHwzfHxhYnN0cmFjdCUyMGRhcmslMjB0ZWNobm9sb2d5fGVufDB8fHx8MTc3NjM3MTc2Nnww&ixlib=rb-4.1.0&q=85";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("demo@openclaw.io");
  const [password, setPassword] = useState("Demo12345!");
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
    <div className="min-h-screen grid lg:grid-cols-5 bg-[#050505]">
      {/* Left form */}
      <div className="lg:col-span-2 flex flex-col px-8 md:px-16 py-10 relative">
        <Link to="/" className="flex items-center gap-2" data-testid="brand-logo">
          <Lightning size={22} weight="fill" className="text-[#00E5FF]" />
          <span className="font-display font-black tracking-tight text-xl">OPENCLAW</span>
        </Link>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="flex-1 flex flex-col justify-center max-w-sm w-full"
        >
          <div className="mono-accent mb-4">// SECURE · AUTH</div>
          <h1 className="text-4xl sm:text-5xl font-black tracking-tighter text-white">
            Command your<br /> outreach fleet.
          </h1>
          <p className="mt-4 text-[#8B949E] leading-relaxed">
            Sign in to orchestrate OpenClaw agents across email, WhatsApp, and global markets.
          </p>

          <form onSubmit={submit} className="mt-10 space-y-4" data-testid="login-form">
            <div>
              <label className="mono-accent block mb-2">email</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="neo-input font-mono"
                placeholder="operator@openclaw.io"
                data-testid="login-email-input"
              />
            </div>
            <div>
              <label className="mono-accent block mb-2">password</label>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="neo-input font-mono"
                placeholder="••••••••"
                data-testid="login-password-input"
              />
            </div>

            <button type="submit" disabled={loading} className="btn-primary w-full justify-center mt-6" data-testid="login-submit-button">
              {loading ? "Authenticating..." : "ENTER COMMAND CENTER"} <ArrowRight size={16} weight="bold" />
            </button>
          </form>

          <p className="mt-8 text-sm text-[#8B949E]">
            No account?{" "}
            <Link to="/register" className="text-[#00E5FF] hover:underline" data-testid="goto-register-link">
              Request access →
            </Link>
          </p>
        </motion.div>

        <div className="mono-accent text-[#4B5563] mt-6">v1.0.0 · command-protocol</div>
      </div>

      {/* Right visual */}
      <div className="hidden lg:block lg:col-span-3 relative overflow-hidden border-l border-[#262626]">
        <img src={HERO_BG} alt="" className="absolute inset-0 w-full h-full object-cover" />
        <div className="absolute inset-0 bg-black/50" />
        <div className="absolute inset-0 grid-bg opacity-40" />
        <div className="absolute inset-0 scanline" />

        <div className="relative z-10 h-full flex flex-col justify-between p-14">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 bg-[#00E5FF] rounded-full pulse-dot" />
            <span className="mono-accent">// 4 AGENTS ONLINE · 482 TASKS IN-FLIGHT</span>
          </div>

          <div className="max-w-xl">
            <div className="mono-accent mb-3 text-[#BF55EC]">/// orchestrator</div>
            <h2 className="text-4xl md:text-5xl font-black tracking-tighter leading-[0.95] text-white">
              Deploy autonomous agents.<br />
              <span className="text-[#00E5FF]">Close globally.</span>
            </h2>
            <p className="mt-5 text-[#c9d1d9] max-w-md">
              Multi-language AI messaging, enrichment, and CRM in one dense command console.
            </p>
            <div className="mt-6 flex gap-2 flex-wrap">
              {["email", "whatsapp", "multi-lang", "enrichment", "crm"].map((t) => (
                <span key={t} className="chip chip-cyan">{t}</span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
