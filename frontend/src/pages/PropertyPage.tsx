import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  ArrowUpRight,
  BedDouble,
  Building,
  Car,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  MapPin,
  Maximize2,
  Sofa,
  Sun,
  Tag,
  Waves,
} from "lucide-react";
import { api } from "../api/client";
import { LoadingSpinner } from "../components/LoadingSpinner";
import type { Property } from "../types/property";
import {
  formatArea,
  formatPrice,
  governorateOf,
  listingTypeLabel,
  propertyGradient,
  sourceLabel,
  subcategoryLabel,
} from "../lib/format";

function DetailItem({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ElementType;
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-slate-100 bg-white p-4">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-600/20">
        <Icon className="h-4 w-4 text-brand-400" />
      </div>
      <div>
        <p className="text-xs text-slate-400">{label}</p>
        <p className="mt-0.5 font-medium text-slate-900">{value}</p>
      </div>
    </div>
  );
}

export function PropertyPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [property, setProperty] = useState<Property | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeImageIndex, setActiveImageIndex] = useState(0);

  useEffect(() => {
    if (!id) return;

    setLoading(true);
    api
      .getProperty(Number(id))
      .then((data) => {
        setProperty(data);
        setActiveImageIndex(0);
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Annonce introuvable"),
      )
      .finally(() => setLoading(false));
  }, [id]);

  const goBack = () => {
    // Prefer real browser back navigation so the previous page (search
    // results, dashboard, etc.) is restored exactly as it was, instead of
    // always landing on the homepage. Falls back to "/" when this page was
    // opened directly (no in-app history to go back to).
    const historyIndex = (window.history.state as { idx?: number } | null)?.idx;
    if (typeof historyIndex === "number" && historyIndex > 0) {
      navigate(-1);
    } else {
      navigate("/");
    }
  };

  if (loading) return <LoadingSpinner label="Chargement de l'annonce..." />;

  if (error || !property) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-20 text-center">
        <p className="text-red-600">{error ?? "Annonce introuvable"}</p>
        <button type="button" onClick={goBack} className="btn-primary mt-6 inline-flex">
          <ArrowLeft className="h-4 w-4" />
          Retour
        </button>
      </div>
    );
  }

  const gradient = propertyGradient(property.id);
  const images = property.images && property.images.length > 0 ? property.images : [];
  const hasMultipleImages = images.length > 1;

  const nextImage = () => {
    if (images.length === 0) return;
    setActiveImageIndex((prev) => (prev + 1) % images.length);
  };

  const prevImage = () => {
    if (images.length === 0) return;
    setActiveImageIndex((prev) => (prev - 1 + images.length) % images.length);
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <button
        type="button"
        onClick={goBack}
        className="mb-6 inline-flex items-center gap-2 text-sm text-slate-500 transition hover:text-slate-900"
      >
        <ArrowLeft className="h-4 w-4" />
        Retour
      </button>

      <div className="animate-fade-in overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-card">
        {/* Gallery Section */}
        <div className="relative border-b border-slate-100 bg-slate-100">
          <div className="relative h-64 overflow-hidden sm:h-96 md:h-[450px]">
            {images.length > 0 ? (
              <img
                src={images[activeImageIndex]}
                alt={`${property.title} - Image ${activeImageIndex + 1}`}
                className="h-full w-full object-contain bg-slate-100 transition duration-300"
              />
            ) : (
              <div className={`absolute inset-0 bg-gradient-to-br ${gradient} flex items-center justify-center`}>
                <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDAiIGhlaWdodD0iNDAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PGRlZnM+PHBhdHRlcm4gaWQ9ImEiIHdpZHRoPSI0MCIgaGVpZ2h0PSI0MCIgcGF0dGVyblVuaXRzPSJ1c2VyU3BhY2VPblVzZSI+PHBhdGggZD0iTTAgMTBoMTBNMTAgMHYxMCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJyZ2JhKDI1NSwyNTUsMjU1LDAuMDUpIi8+PC9wYXR0ZXJuPjwvZGVmcz48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSJ1cmwoI2EpIi8+PC9zdmc+')] opacity-50" />
                <span className="text-sm font-medium text-slate-500">Aucune image disponible</span>
              </div>
            )}

            {/* Navigation Arrows */}
            {hasMultipleImages && (
              <>
                <button
                  type="button"
                  onClick={prevImage}
                  className="absolute left-4 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full bg-white/85 border border-slate-200 text-slate-900 backdrop-blur transition hover:bg-white"
                  aria-label="Image précédente"
                >
                  <ChevronLeft className="h-5 w-5" />
                </button>
                <button
                  type="button"
                  onClick={nextImage}
                  className="absolute right-4 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full bg-white/85 border border-slate-200 text-slate-900 backdrop-blur transition hover:bg-white"
                  aria-label="Image suivante"
                >
                  <ChevronRight className="h-5 w-5" />
                </button>
              </>
            )}

            {/* Image Counter Badge */}
            {images.length > 0 && (
              <div className="absolute bottom-4 right-4 rounded-lg bg-white/85 px-2.5 py-1 text-xs font-medium text-slate-700 backdrop-blur">
                {activeImageIndex + 1} / {images.length}
              </div>
            )}
          </div>

          {/* Thumbnails Row */}
          {hasMultipleImages && (
            <div className="flex gap-2 overflow-x-auto p-4 bg-slate-50 scrollbar-none">
              {images.map((img, idx) => (
                <button
                  key={`${idx}-${img}`}
                  type="button"
                  onClick={() => setActiveImageIndex(idx)}
                  className={`relative w-20 h-16 shrink-0 overflow-hidden rounded-lg border-2 transition ${
                    activeImageIndex === idx
                      ? "border-brand-500 scale-95"
                      : "border-transparent opacity-60 hover:opacity-100"
                  }`}
                >
                  <img
                    src={img}
                    alt={`${property.title} thumbnail ${idx + 1}`}
                    className="h-full w-full object-cover"
                  />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Content Section */}
        <div className="p-6 sm:p-8">
          {/* Title and Price */}
          <div className="mb-6 border-b border-slate-100 pb-6">
            <div className="mb-3 flex flex-wrap gap-2">
              <span className="rounded-lg bg-brand-500/15 px-3 py-1 text-xs font-semibold text-slate-900">
                {sourceLabel(property.source)}
              </span>
              <span className="rounded-lg bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">
                {subcategoryLabel(property.subcategory, property.property_type)}
              </span>
              <span className="rounded-lg bg-amber-500/15 px-3 py-1 text-xs font-semibold text-amber-700">
                {listingTypeLabel(property.listing_type)}
              </span>
            </div>
            <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
              <h1 className="font-display text-2xl font-bold leading-tight text-slate-900 sm:text-3xl">
                {property.title}
              </h1>
              <p className="shrink-0 font-display text-2xl font-extrabold text-brand-400 sm:text-3xl">
                {formatPrice(property.price)}
              </p>
            </div>
          </div>

          {/* Details Grid */}
          <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <DetailItem
              icon={MapPin}
              label="Localisation"
              value={governorateOf(property)}
            />
            <DetailItem icon={Maximize2} label="Surface" value={formatArea(property.area)} />
            <DetailItem icon={Tag} label="Source" value={sourceLabel(property.source)} />
            <DetailItem icon={Building} label="Type" value={subcategoryLabel(property.subcategory, property.property_type)} />
            <DetailItem
              icon={Tag}
              label="Transaction"
              value={listingTypeLabel(property.listing_type)}
            />
            {property.property_type === "house" && property.bedrooms != null && (
              <DetailItem icon={BedDouble} label="Chambres" value={property.bedrooms} />
            )}
            {property.property_type === "house" && property.garage != null && (
              <DetailItem
                icon={Car}
                label="Garage"
                value={property.garage ? "Oui" : "Non"}
              />
            )}
            {property.property_type === "house" && property.furnished != null && (
              <DetailItem
                icon={Sofa}
                label="Meublé"
                value={property.furnished ? "Oui" : "Non"}
              />
            )}
            {property.property_type === "house" && property.terrace != null && (
              <DetailItem
                icon={Sun}
                label="Terrasse / Balcon"
                value={property.terrace ? "Oui" : "Non"}
              />
            )}
            {property.property_type === "house" && property.pool != null && (
              <DetailItem
                icon={Waves}
                label="Piscine"
                value={property.pool ? "Oui" : "Non"}
              />
            )}
          </div>

          {/* Description */}
          {property.description && (
            <div className="mb-8 border-t border-slate-100 pt-6">
              <h2 className="mb-3 font-display text-xl font-semibold text-slate-900">
                Description
              </h2>
              <p className="whitespace-pre-wrap leading-relaxed text-slate-500">
                {property.description}
              </p>
            </div>
          )}

          {/* External Action */}
          <div className="flex flex-wrap gap-3 border-t border-slate-100 pt-6">
            <a
              href={property.url}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-primary"
            >
              <ExternalLink className="h-4 w-4" />
              Voir sur {sourceLabel(property.source)}
              <ArrowUpRight className="h-4 w-4" />
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
