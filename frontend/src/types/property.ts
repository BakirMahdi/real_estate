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

export interface PropertyListResponse {
  count: number;
  items: Property[];
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
