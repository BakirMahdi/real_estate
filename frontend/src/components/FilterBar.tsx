import { Search, SlidersHorizontal, X } from "lucide-react";
import type { SearchFilters } from "../types/property";

interface FilterBarProps {
  filters: SearchFilters;
  cities: string[];
  onChange: (filters: SearchFilters) => void;
  onReset: () => void;
}

export function FilterBar({ filters, cities, onChange, onReset }: FilterBarProps) {
  const set = (key: keyof SearchFilters, value: any) => {
    onChange({
      ...filters,
      [key]: value === "" ? undefined : value,
      offset: 0,
    });
  };

  const hasFilters = Object.entries(filters).some(
    ([key, value]) => key !== "limit" && key !== "offset" && value !== undefined && value !== "",
  );

  return (
    <div className="glass animate-fade-in rounded-2xl p-5 shadow-card space-y-4">
      {/* Top Section: Search Input and Actions */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-white/5 pb-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            className="input-field pl-10 pr-4 py-2.5 w-full bg-slate-950/40 border-white/10 text-white placeholder-slate-500 rounded-xl focus:border-brand-500/50 focus:ring-1 focus:ring-brand-500/30"
            placeholder="Rechercher par mot-clé (ex: piscine, vue mer, villa, Lac 2...)"
            value={filters.query ?? ""}
            onChange={(e) => set("query", e.target.value)}
          />
        </div>
        <div className="flex items-center justify-between gap-4 shrink-0">
          <div className="flex items-center gap-2 text-sm font-medium text-slate-300">
            <SlidersHorizontal className="h-4 w-4 text-brand-400" />
            Filtres
          </div>
          {hasFilters && (
            <button
              type="button"
              onClick={onReset}
              className="flex items-center gap-1 text-xs text-slate-500 transition hover:text-slate-300 hover:bg-white/5 px-2.5 py-1.5 rounded-lg"
            >
              <X className="h-3.5 w-3.5" />
              Réinitialiser
            </button>
          )}
        </div>
      </div>

      {/* Filters Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
        <div>
          <label className="mb-1.5 block text-xs font-medium text-slate-400">Ville</label>
          <select
            className="input-field w-full"
            value={filters.city ?? ""}
            onChange={(e) => set("city", e.target.value)}
          >
            <option value="">Toutes</option>
            {cities.map((city) => (
              <option key={city} value={city}>
                {city}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="mb-1.5 block text-xs font-medium text-slate-400">Catégorie</label>
          <select
            className="input-field w-full"
            value={filters.subcategory ?? ""}
            onChange={(e) => set("subcategory", e.target.value)}
          >
            <option value="">Toutes</option>
            <option value="apartment">Appartement</option>
            <option value="house">Maison / Villa</option>
            <option value="office">Bureau / Commerce</option>
            <option value="studio">Studio / Chambre</option>
            <option value="land">Terrain</option>
          </select>
        </div>

        <div>
          <label className="mb-1.5 block text-xs font-medium text-slate-400">Transaction</label>
          <select
            className="input-field w-full"
            value={filters.listing_type ?? ""}
            onChange={(e) => set("listing_type", e.target.value)}
          >
            <option value="">Toutes</option>
            <option value="sale">À vendre</option>
            <option value="rent">À louer</option>
          </select>
        </div>

        <div>
          <label className="mb-1.5 block text-xs font-medium text-slate-400">Prix Min (DT)</label>
          <input
            type="number"
            className="input-field w-full"
            placeholder="0"
            min={0}
            value={filters.min_price ?? ""}
            onChange={(e) => set("min_price", e.target.value ? Number(e.target.value) : undefined)}
          />
        </div>

        <div>
          <label className="mb-1.5 block text-xs font-medium text-slate-400">Prix Max (DT)</label>
          <input
            type="number"
            className="input-field w-full"
            placeholder="∞"
            min={0}
            value={filters.max_price ?? ""}
            onChange={(e) => set("max_price", e.target.value ? Number(e.target.value) : undefined)}
          />
        </div>

        <div>
          <label className="mb-1.5 block text-xs font-medium text-slate-400">Surface Min (m²)</label>
          <input
            type="number"
            className="input-field w-full"
            placeholder="Min"
            min={0}
            value={filters.min_area ?? ""}
            onChange={(e) => set("min_area", e.target.value ? Number(e.target.value) : undefined)}
          />
        </div>

        <div>
          <label className="mb-1.5 block text-xs font-medium text-slate-400">Surface Max (m²)</label>
          <input
            type="number"
            className="input-field w-full"
            placeholder="Max"
            min={0}
            value={filters.max_area ?? ""}
            onChange={(e) => set("max_area", e.target.value ? Number(e.target.value) : undefined)}
          />
        </div>
      </div>
    </div>
  );
}
