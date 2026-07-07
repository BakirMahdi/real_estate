import type {
  HealthStatus,
  Property,
  PropertyListResponse,
  ScrapeResult,
  SearchFilters,
} from "../types/property";

const API_BASE = import.meta.env.VITE_API_URL ?? "/api";

let adminToken: string | null = null;

export function setAdminToken(token: string | null) {
  adminToken = token;
}

export function hasAdminToken() {
  return adminToken !== null && adminToken !== "";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  
  if (adminToken) {
    headers.set("x-api-key", adminToken);
  }

  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });

  if (response.status === 401) {
    throw new Error("UNAUTHORIZED");
  }

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed (${response.status})`);
  }

  return response.json() as Promise<T>;
}

function buildQuery(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();

  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  }

  const query = search.toString();
  return query ? `?${query}` : "";
}

export const api = {
  health: () => request<HealthStatus>("/health"),
  healthDb: () => request<HealthStatus>("/health/db"),
  scrape: () => request<{ status: string }>("/scrape", { method: "POST" }),
  getScrapeStatus: () => request<{ is_scraping: boolean; results: ScrapeResult[] | null; error: string | null; next_scrape_time: number | null }>("/scrape/status"),
  getAllProperties: () => request<PropertyListResponse>("/properties/all"),
  searchProperties: (filters: SearchFilters) =>
    request<PropertyListResponse>(
      `/properties/search${buildQuery(filters as Record<string, string | number | undefined>)}`,
    ),
  getProperty: (id: number) => request<Property>(`/properties/${id}`),
};
