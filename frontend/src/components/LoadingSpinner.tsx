import { useLang } from "../lib/i18n";

export function LoadingSpinner({ label }: { label?: string }) {
  const { t } = useLang();
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-20">
      <div className="h-10 w-10 animate-spin rounded-full border-2 border-brand-500/30 border-t-brand-400" />
      <p className="text-sm text-slate-500">{label ?? t("common.loading")}</p>
    </div>
  );
}
