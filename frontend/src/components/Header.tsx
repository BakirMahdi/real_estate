import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  Building2,
  ChevronDown,
  LogIn,
  LogOut,
  Menu,
  Moon,
  Sun,
  UserCircle,
} from "lucide-react";
import { isAuthenticated, logout, getUsername } from "../api/client";
import { useLang, type Lang } from "../lib/i18n";
import { useTheme } from "../lib/theme";

const LANGS: Lang[] = ["fr", "en"];

// Page titles shown as the header's breadcrumb, keyed by route.
const ROUTE_TITLES: Record<string, string> = {
  "/": "nav.home",
  "/annonces": "nav.listings",
  "/favorites": "nav.favorites",
  "/dashboard": "nav.dashboard",
  "/login": "nav.login",
};

export function Header({ onOpenMenu }: { onOpenMenu: () => void }) {
  const location = useLocation();
  const authenticated = isAuthenticated();
  const username = getUsername();
  const { lang, setLang, t } = useLang();
  const { theme, toggleTheme } = useTheme();

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

  const titleKey = ROUTE_TITLES[location.pathname] ?? "nav.listings";

  return (
    <header className="sticky top-0 z-30 border-b border-gray-200 bg-lightPrimary/80 backdrop-blur-xl dark:border-white/10 dark:bg-navy-900/80">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-3 sm:px-6">
        {/* Left: the menu trigger. The drawer is the primary navigation at
            every breakpoint, so this button is never hidden. */}
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            onClick={onOpenMenu}
            aria-label={t("nav.openMenu")}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-navy-700 transition hover:bg-white dark:text-white dark:hover:bg-navy-700"
          >
            <Menu className="h-5 w-5" />
          </button>

          <Link to="/" className="flex min-w-0 items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-500 shadow-glow">
              <Building2 className="h-4 w-4 text-white" />
            </div>
            <div className="min-w-0">
              <p className="truncate font-display text-base font-bold leading-tight text-navy-700 dark:text-white">
                {t(titleKey)}
              </p>
              <p className="hidden truncate text-xs text-gray-700 dark:text-gray-600 sm:block">
                Rews · Real Estate Web Scraper
              </p>
            </div>
          </Link>
        </div>

        {/* Right: theme, language, and the account menu — the username stays
            here rather than moving into the drawer. */}
        <div className="flex shrink-0 items-center gap-2 rounded-full bg-white px-2 py-1.5 shadow-card shadow-shadow-500 dark:bg-navy-800 dark:shadow-none">
          <button
            type="button"
            onClick={toggleTheme}
            aria-label={t(theme === "dark" ? "nav.lightMode" : "nav.darkMode")}
            className="flex h-8 w-8 items-center justify-center rounded-full text-gray-700 transition hover:bg-lightPrimary hover:text-navy-700 dark:text-gray-600 dark:hover:bg-navy-700 dark:hover:text-white"
          >
            {theme === "dark" ? (
              <Sun className="h-4 w-4" />
            ) : (
              <Moon className="h-4 w-4" />
            )}
          </button>

          <div className="flex items-center rounded-full bg-lightPrimary p-0.5 dark:bg-navy-900">
            {LANGS.map((code) => (
              <button
                key={code}
                type="button"
                onClick={() => setLang(code)}
                aria-pressed={lang === code}
                className={`rounded-full px-2.5 py-1 text-xs font-bold uppercase transition ${
                  lang === code
                    ? "bg-brand-500 text-white"
                    : "text-gray-700 hover:text-navy-700 dark:text-gray-600 dark:hover:text-white"
                }`}
              >
                {code}
              </button>
            ))}
          </div>

          {authenticated ? (
            <div className="relative" ref={menuRef}>
              <button
                type="button"
                onClick={() => setMenuOpen((o) => !o)}
                aria-haspopup="menu"
                aria-expanded={menuOpen}
                className={`flex max-w-[180px] items-center gap-1.5 rounded-full px-2 py-1.5 text-sm font-medium transition ${
                  menuOpen
                    ? "bg-lightPrimary text-navy-700 dark:bg-navy-700 dark:text-white"
                    : "text-navy-700 hover:bg-lightPrimary dark:text-white dark:hover:bg-navy-700"
                }`}
              >
                <UserCircle className="h-4 w-4 shrink-0 text-brand-500 dark:text-brand-400" />
                {username && (
                  <span className="hidden truncate sm:inline">{username}</span>
                )}
                <ChevronDown
                  className={`h-3.5 w-3.5 shrink-0 text-gray-700 transition dark:text-gray-600 ${
                    menuOpen ? "rotate-180" : ""
                  }`}
                />
              </button>
              {menuOpen && (
                <div
                  role="menu"
                  className="absolute right-0 top-full z-50 mt-2 min-w-[12rem] rounded-2xl bg-white p-2 shadow-card dark:bg-navy-700"
                >
                  {username && (
                    <p className="truncate border-b border-gray-200 px-3 pb-2 text-xs text-gray-700 dark:border-white/10 dark:text-gray-600">
                      {username}
                    </p>
                  )}
                  <button
                    role="menuitem"
                    onClick={handleLogout}
                    className="mt-1 flex w-full items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium text-navy-700 transition hover:bg-lightPrimary dark:text-white dark:hover:bg-navy-600"
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
              className="flex items-center gap-2 rounded-full px-3 py-1.5 text-sm font-medium text-navy-700 transition hover:bg-lightPrimary dark:text-white dark:hover:bg-navy-700"
            >
              <LogIn className="h-4 w-4" />
              <span className="hidden sm:inline">{t("nav.login")}</span>
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
