import { Link } from "react-router-dom";
import { ArrowRight, Building2, Calculator, Layers, MessageCircle, Sparkles } from "lucide-react";
import { isAuthenticated } from "../api/client";
import { useLang } from "../lib/i18n";

const features = [
  { icon: Layers, titleKey: "welcome.f1.title", textKey: "welcome.f1.text" },
  { icon: Sparkles, titleKey: "welcome.f2.title", textKey: "welcome.f2.text" },
  { icon: MessageCircle, titleKey: "welcome.f3.title", textKey: "welcome.f3.text" },
  { icon: Calculator, titleKey: "welcome.f4.title", textKey: "welcome.f4.text" },
];

export function WelcomePage() {
  const authenticated = isAuthenticated();
  const { t } = useLang();

  return (
    <div className="relative flex h-full w-full items-center overflow-hidden">
      {/* The decorative gradient blobs live in <LandingBackground>, mounted
          fixed at the App level so they show behind every page. */}

      <section className="mx-auto w-full max-w-5xl px-4 py-8 text-center sm:px-6">
        <div
          className="mb-6 inline-flex animate-slide-up items-center gap-2 rounded-full border border-brand-200 bg-white/70 px-4 py-1.5 text-xs font-medium text-brand-600 opacity-0"
          style={{ animationDelay: "0.05s" }}
        >
          <Building2 className="h-3.5 w-3.5" />
          {t("welcome.badge")}
        </div>

        <h1
          className="animate-slide-up font-display text-4xl font-extrabold leading-tight tracking-tight text-slate-900 opacity-0 sm:text-6xl"
          style={{ animationDelay: "0.15s" }}
        >
          {t("welcome.titlePrefix")}{" "}
          <span className="bg-gradient-to-r from-brand-400 to-brand-700 bg-clip-text text-transparent">
            Rews
          </span>
        </h1>

        <p
          className="mx-auto mt-6 max-w-2xl animate-slide-up text-base leading-relaxed text-slate-500 opacity-0 sm:text-lg"
          style={{ animationDelay: "0.25s" }}
        >
          {t("welcome.subtitle")}
        </p>

        <div
          className="mt-9 flex animate-slide-up flex-wrap items-center justify-center gap-3 opacity-0"
          style={{ animationDelay: "0.35s" }}
        >
          <Link to="/annonces" className="btn-primary px-6 py-3 text-base">
            {t("welcome.explore")}
            <ArrowRight className="h-4 w-4" />
          </Link>
          {!authenticated && (
            <Link to="/login" className="btn-secondary px-6 py-3 text-base">
              {t("welcome.login")}
            </Link>
          )}
        </div>

        <div className="mt-12 grid gap-4 text-left sm:grid-cols-2 lg:grid-cols-4">
          {features.map(({ icon: Icon, titleKey, textKey }, idx) => (
            <div
              key={titleKey}
              className="glass animate-slide-up p-5 opacity-0 shadow-card transition hover:-translate-y-1 hover:border-brand-300"
              style={{ animationDelay: `${0.45 + idx * 0.1}s` }}
            >
              <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-brand-600/15">
                <Icon className="h-5 w-5 text-brand-500" />
              </div>
              <h3 className="font-display text-sm font-semibold text-slate-900">{t(titleKey)}</h3>
              <p className="mt-1.5 text-xs leading-relaxed text-slate-500">{t(textKey)}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
