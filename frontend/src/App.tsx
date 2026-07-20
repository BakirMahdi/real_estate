import type { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AgentChatWidget } from "./components/AgentChatWidget";
import { Header } from "./components/Header";
import { LandingBackground } from "./components/LandingBackground";
import { isAdmin, isAuthenticated } from "./api/client";
import { useLang } from "./lib/i18n";
import { DashboardPage } from "./pages/DashboardPage";
import { FavoritesPage } from "./pages/FavoritesPage";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { PropertyPage } from "./pages/PropertyPage";
import { WelcomePage } from "./pages/WelcomePage";

// The dashboard is admin-only. A logged-out visitor or a regular user hitting
// /dashboard directly is sent to the listings page rather than shown the page.
function RequireAdmin({ children }: { children: ReactNode }) {
  if (!isAuthenticated() || !isAdmin()) {
    return <Navigate to="/annonces" replace />;
  }
  return <>{children}</>;
}

// Any logged-in user (not just admins) - a logged-out visitor hitting
// /favorites directly is sent to log in and back, same ?next= pattern the
// dashboard's session-expiry redirect uses.
function RequireAuth({ children }: { children: ReactNode }) {
  if (!isAuthenticated()) {
    return <Navigate to="/login?next=/favorites" replace />;
  }
  return <>{children}</>;
}

export default function App() {
  const location = useLocation();
  const { t } = useLang();
  // The welcome and login pages are designed to fit the viewport, so the whole
  // layout switches to a fixed-height, non-scrolling mode (and drops the
  // footer) on those routes. Every other page keeps normal document scrolling.
  const fitsViewport = location.pathname === "/" || location.pathname === "/login";

  return (
    <div className={`flex flex-col ${fitsViewport ? "h-screen overflow-hidden" : "min-h-screen"}`}>
      <LandingBackground />
      <Header />
      <main className={fitsViewport ? "flex flex-1 overflow-hidden" : "flex-1"}>
        <Routes>
          <Route path="/" element={<WelcomePage />} />
          <Route path="/annonces" element={<HomePage />} />
          <Route path="/property/:id" element={<PropertyPage />} />
          <Route
            path="/favorites"
            element={
              <RequireAuth>
                <FavoritesPage />
              </RequireAuth>
            }
          />
          <Route
            path="/dashboard"
            element={
              <RequireAdmin>
                <DashboardPage />
              </RequireAdmin>
            }
          />
          <Route path="/login" element={<LoginPage />} />
        </Routes>
      </main>
      {!fitsViewport && (
        <footer className="border-t border-slate-100 py-6 text-center text-xs text-slate-400">
          {t("footer.tagline")}
        </footer>
      )}
      <AgentChatWidget />
    </div>
  );
}
