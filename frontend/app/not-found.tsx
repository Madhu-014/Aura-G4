export default function NotFound() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[#050509] px-6 text-white">
      <section className="rounded-2xl border border-emerald-500/20 bg-slate-900/50 p-8 text-center backdrop-blur-xl">
        <h1 className="mb-2 text-2xl font-semibold uppercase tracking-[0.08em]">Route Not Found</h1>
        <p className="text-sm text-slate-300">The requested tactical console route does not exist.</p>
      </section>
    </main>
  );
}
