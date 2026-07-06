export function LoadingSpinner({ label = "Chargement..." }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-20">
      <div className="h-10 w-10 animate-spin rounded-full border-2 border-brand-500/30 border-t-brand-400" />
      <p className="text-sm text-slate-400">{label}</p>
    </div>
  );
}
