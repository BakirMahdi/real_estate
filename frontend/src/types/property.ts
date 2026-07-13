export interface Property {
  id: number;
  source: string;
  ad_id: string;
  property_type: string;
  listing_type: string;
  title: string;
  description: string | null;
  price: number | null;
  area: number | null;
  city: string | null;
  address: string | null;
  governorate?: string | null;
  url: string;
  bedrooms?: number | null;
  garage?: boolean | null;
  furnished?: boolean | null;
  terrace?: boolean | null;
  pool?: boolean | null;
  subcategory?: string | null;
  images?: string[] | null;
  archived?: boolean;
}

export interface AgentMessage {
  role: "user" | "model";
  content: string;
  /** ISO 8601 timestamp; absent on messages saved before timestamps were added. */
  created_at?: string;
}

export interface PropertyEstimate {
  estimated_price: number;
  /** 0-100 deal quality vs. the model estimate; null for rentals and undisclosed prices. */
  investment_score: number | null;
  model_trained_at: string;
  model_metrics: Record<string, number>;
}

export interface PropertyListResponse {
  count: number;
  items: Property[];
}

export interface ScrapePhaseStats {
  status: string;
  count: number;
  inserted: number;
  skipped: number;
  errors: number;
}

export interface ScrapeResult {
  source: string;
  count?: number;
  inserted?: number;
  skipped?: number;
  errors?: number;
  archived?: number;
  error?: string;
  message?: string | null;
  phases?: Record<string, ScrapePhaseStats>;
  cancelled?: boolean;
}

export interface ScrapeSourceProgress {
  status: string;
  phase: string | null;
  step: string | null;
  pages_processed: number;
  total_pages: number;
  items_found: number;
  phases: Record<string, ScrapePhaseStats>;
}

export interface ScrapeProgress {
  total_sources: number;
  completed_sources: number;
  sources: Record<string, ScrapeSourceProgress>;
}

export interface SearchFilters {
  city?: string;
  property_type?: string;
  listing_type?: string;
  min_price?: number;
  max_price?: number;
  min_area?: number;
  max_area?: number;
  bedrooms?: number;
  limit?: number;
  offset?: number;
  query?: string;
  subcategory?: string;
}

export interface HealthStatus {
  status: string;
  database?: string;
}

export interface ArchiveSearchParams {
  search?: string;
  archivedOnly?: boolean;
  offset?: number;
  limit?: number;
  sortBy?: string;
  sortDir?: "asc" | "desc";
  city?: string;
  subcategory?: string;
  listingType?: string;
  minPrice?: number;
  maxPrice?: number;
  minArea?: number;
  maxArea?: number;
  bedrooms?: number;
}
