import { Route, Routes } from "react-router-dom";
import { Header } from "./components/Header";
import { DashboardPage } from "./pages/DashboardPage";
import { HomePage } from "./pages/HomePage";
import { PropertyPage } from "./pages/PropertyPage";

export default function App() {
  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/property/:id" element={<PropertyPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
        </Routes>
      </main>
      <footer className="border-t border-white/5 py-6 text-center text-xs text-slate-600">
        Rews — Agrégateur immobilier Tunisie
      </footer>
    </div>
  );
}
