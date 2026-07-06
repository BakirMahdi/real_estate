export function formatPrice(price: number | null | undefined): string {
  if (price == null || price === 0) return "Prix sur demande";
  return new Intl.NumberFormat("fr-TN", {
    style: "currency",
    currency: "TND",
    maximumFractionDigits: 0,
  }).format(price);
}

export function formatArea(area: number | null | undefined): string {
  if (area == null) return "—";
  return `${area} m²`;
}

export function sourceLabel(source: string): string {
  const labels: Record<string, string> = {
    tayara: "Tayara",
    mubawab: "Mubawab",
  };
  return labels[source] ?? source;
}

export function typeLabel(type: string): string {
  const labels: Record<string, string> = {
    house: "Maison / Appartement",
    land: "Terrain",
  };
  return labels[type] ?? type;
}

export function listingTypeLabel(listingType: string): string {
  const labels: Record<string, string> = {
    sale: "À vendre",
    rent: "À louer",
  };
  return labels[listingType] ?? listingType;
}

export function truncate(text: string | null | undefined, max = 120): string {
  if (!text) return "";
  if (text.length <= max) return text;
  return `${text.slice(0, max).trim()}…`;
}

export function propertyGradient(id: number): string {
  const palettes = [
    "from-teal-500/20 via-emerald-400/10 to-cyan-500/20",
    "from-violet-500/20 via-purple-400/10 to-fuchsia-500/20",
    "from-amber-500/20 via-orange-400/10 to-rose-500/20",
    "from-sky-500/20 via-blue-400/10 to-indigo-500/20",
  ];
  return palettes[id % palettes.length];
}

export function subcategoryLabel(subcategory: string | null | undefined, fallbackType: string): string {
  if (!subcategory) {
    const labels: Record<string, string> = {
      house: "Maison / Villa",
      land: "Terrain",
    };
    return labels[fallbackType] ?? fallbackType;
  }
  const labels: Record<string, string> = {
    apartment: "Appartement",
    house: "Maison / Villa",
    office: "Bureau / Commerce",
    studio: "Studio / Chambre",
    land: "Terrain",
  };
  return labels[subcategory] ?? subcategory;
}
