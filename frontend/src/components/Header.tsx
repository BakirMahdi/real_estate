import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Building2, ChevronDown, Heart, LayoutDashboard, Search, LogIn, LogOut, UserCircle } from "lucide-react";
import { isAuthenticated, logout, isAdmin, getUsername } from "../api/client";
import { useLang, type Lang } from "../lib/i18n";

const nav = [
  { to: "/annonces", labelKey: "nav.listings", icon: Search },
  { to: "/favorites", labelKey: "nav.favorites", icon: Heart, authOnly: true },
  { to: "/dashboard", labelKey: "nav.dashboard", icon: LayoutDashboard, adminOnly: true },
];

const LANGS: Lang[] = ["fr", "en"];

export function Header() {
  const location = useLocation();
  const authenticated = isAuthenticated();
  const userIsAdmin = isAdmin();
  const username = getUsername();
  const { lang, setLang, t } = useLang();

  // Account menu: the email acts as a trigger that reveals a popover holding
  // the logout button, keeping the header compact.
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const onPointerDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [menuOpen]);

  const handleLogout = () => {
    setMenuOpen(false);
    logout();
    window.location.href = "/";
  };

  return (
    <header className="sticky top-0 z-50 border-b border-slate-100 bg-white/80 backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6">
        <Link to="/" className="group flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-600 shadow-glow transition group-hover:bg-brand-700">
            <Building2 className="h-5 w-5 text-white" />
          </div>
          <div>
            <p className="font-display text-lg font-semibold tracking-tight text-slate-900">
              Rews
            </p>
            <p className="text-xs text-slate-500">Real Estate Web Scraper</p>
          </div>
        </Link>

        <nav className="flex items-center gap-1">
          {nav.map(({ to, labelKey, icon: Icon, adminOnly, authOnly }) => {
            if (adminOnly && !userIsAdmin) return null;
            if (authOnly && !authenticated) return null;
            const active = location.pathname === to;
            return (
              <Link
                key={to}
                to={to}
                className={`flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition ${
                  active
                    ? "bg-brand-600 text-white"
                    : "text-slate-500 hover:bg-slate-100 hover:text-slate-900"
                }`}
              >
                <Icon className="h-4 w-4" />
                <span className="hidden sm:inline">{t(labelKey)}</span>
              </Link>
            );
          })}
          {authenticated ? (
            <div className="relative" ref={menuRef}>
              <button
                type="button"
                onClick={() => setMenuOpen((open) => !open)}
                aria-haspopup="menu"
                aria-expanded={menuOpen}
                className={`flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium transition ${
                  menuOpen
                    ? "bg-slate-100 text-slate-900"
                    : "text-slate-700 hover:bg-slate-100"
                }`}
              >
                <UserCircle className="h-4 w-4 shrink-0 text-brand-500" />
                {username && <span className="break-all">{username}</span>}
                <ChevronDown
                  className={`h-3.5 w-3.5 shrink-0 text-slate-400 transition ${
                    menuOpen ? "rotate-180" : ""
                  }`}
                />
              </button>
              {menuOpen && (
                <div
                  role="menu"
                  className="absolute right-0 top-full z-50 mt-2 min-w-[10rem] rounded-xl border border-slate-100 bg-white p-1 shadow-lg"
                >
                  <button
                    role="menuitem"
                    onClick={handleLogout}
                    className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-900"
                  >
                    <LogOut className="h-4 w-4" />
                    {t("nav.logout")}
                  </button>
                </div>
              )}
            </div>
          ) : (
            <Link
              to="/login"
              className="flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium text-slate-500 transition hover:bg-slate-100 hover:text-slate-900"
            >
              <LogIn className="h-4 w-4" />
              <span className="hidden sm:inline">{t("nav.login")}</span>
            </Link>
          )}

          <div className="ml-2 flex items-center rounded-xl border border-slate-200 bg-white p-0.5">
            {LANGS.map((code) => (
              <button
                key={code}
                type="button"
                onClick={() => setLang(code)}
                aria-pressed={lang === code}
                className={`rounded-[10px] px-2.5 py-1.5 text-xs font-semibold uppercase transition ${
                  lang === code
                    ? "bg-brand-600 text-white"
                    : "text-slate-400 hover:text-slate-900"
                }`}
              >
                {code}
              </button>
            ))}
          </div>
        </nav>
      </div>
    </header>
  );
}
