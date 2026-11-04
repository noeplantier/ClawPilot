import { Link } from "react-router-dom";
import { motion, useReducedMotion } from "framer-motion";
import Logo from "@/components/Logo";
import Footer from "@/components/Footer";

// The frame of Login and Register: the card sits in the middle of the free height and, when the screen is short or a phone keyboard
// takes half of it, the page simply scrolls (100dvh follows the keyboard; nothing is clipped). It shares nothing with the sidebar
// layout, so signing in never shifts. No status is printed here: this page cannot know the state of the server.
export default function AuthShell({ children, testId }) {
  const reduce = useReducedMotion();
  return (
    <div className="grid-bg grain relative min-h-[100dvh] w-full overflow-x-hidden" data-testid={testId}>
      <div
        aria-hidden="true"
        className="pointer-events-none fixed inset-0 z-0 opacity-40"
        style={{ background: "radial-gradient(650px circle at 50% 25%, rgba(124,58,237,0.18), transparent 70%), radial-gradient(400px circle at 80% 80%, rgba(74,222,128,0.05), transparent 60%)" }}
      />
      <div className="relative z-10 mx-auto flex min-h-[100dvh] w-full max-w-md flex-col px-4 pb-4 pt-6 sm:pt-8">
        <header className="flex shrink-0 items-center pb-4">
          <Link to="/" className="inline-flex rounded-lg" data-testid="brand-logo" aria-label="Plantiers - OutreachOS">
            <Logo />
          </Link>
        </header>
        <main className="flex flex-1 items-center justify-center py-2" data-testid="auth-main">
          <motion.div
            initial={reduce ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: reduce ? 0 : 0.3, ease: "easeOut" }}
            className="relative w-full rounded-2xl border border-white/10 bg-void-elevated/90 p-6 shadow-[0_20px_50px_rgba(0,0,0,0.5)] backdrop-blur-xl sm:p-9"
          >
            {children}
          </motion.div>
        </main>
        <Footer className="mt-4 !border-0 !bg-transparent !px-0 !py-3 text-center" />
      </div>
    </div>
  );
}
