export default function LoginPage() {
  return (
    <main className="relative flex min-h-screen items-center justify-center bg-slate-950 text-slate-100">
      <div className="starfield" />
      <div className="parallax-gradient" />
      <div className="glass relative z-10 w-full max-w-md rounded-2xl p-6 text-slate-200">
        <h1 className="text-2xl font-semibold text-white">Welcome</h1>
        <p className="mt-2 text-sm text-slate-300">
          Login is disabled. Head back to the dashboard home.
        </p>
        <a
          href="/"
          className="mt-4 inline-flex rounded-lg bg-gradient-to-r from-cyan-400 to-indigo-500 px-4 py-2 font-semibold text-slate-950 transition hover:brightness-105"
        >
          Go to Dashboard
        </a>
      </div>
    </main>
  );
}
