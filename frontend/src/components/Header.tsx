import { Link, useLocation } from "react-router-dom";
import { Building2, LayoutDashboard, Search, LogIn, LogOut } from "lucide-react";
import { isAuthenticated, logout } from "../api/client";

const nav = [
  { to: "/", label: "Annonces", icon: Search },
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
];

export function Header() {
  const location = useLocation();
  const authenticated = isAuthenticated();

  const handleLogout = () => {
    logout();
    window.location.href = "/";
  };

  return (
    <header className="sticky top-0 z-50 border-b border-white/5 bg-slate-950/80 backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6">
        <Link to="/" className="group flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-600 shadow-glow transition group-hover:bg-brand-500">
            <Building2 className="h-5 w-5 text-white" />
          </div>
          <div>
            <p className="font-display text-lg font-semibold tracking-tight text-white">
              Rews
            </p>
            <p className="text-xs text-slate-400">Immobilier Tunisie</p>
          </div>
        </Link>

        <nav className="flex items-center gap-1">
          {nav.map(({ to, label, icon: Icon }) => {
            const active = location.pathname === to;
            return (
              <Link
                key={to}
                to={to}
                className={`flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition ${
                  active
                    ? "bg-brand-600/20 text-brand-300"
                    : "text-slate-400 hover:bg-white/5 hover:text-white"
                }`}
              >
                <Icon className="h-4 w-4" />
                <span className="hidden sm:inline">{label}</span>
              </Link>
            );
          })}
          {authenticated ? (
            <button
              onClick={handleLogout}
              className="flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium text-slate-400 transition hover:bg-white/5 hover:text-white"
            >
              <LogOut className="h-4 w-4" />
              <span className="hidden sm:inline">Déconnexion</span>
            </button>
          ) : (
            <Link
              to="/login"
              className="flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium text-slate-400 transition hover:bg-white/5 hover:text-white"
            >
              <LogIn className="h-4 w-4" />
              <span className="hidden sm:inline">Connexion</span>
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}
