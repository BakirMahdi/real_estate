import type {
  HealthStatus,
  Property,
  PropertyListResponse,
  ScrapeResult,
  SearchFilters,
} from "../types/property";

const API_BASE = import.meta.env.VITE_API_URL ?? "/api";

let authToken: string | null = null;

export function setAuthToken(token: string | null) {
  authToken = token;
  if (token) {
    localStorage.setItem("auth_token", token);
  } else {
    localStorage.removeItem("auth_token");
  }
}

export function getAuthToken() {
  if (!authToken) {
    authToken = localStorage.getItem("auth_token");
  }
  return authToken;
}

export function isAuthenticated() {
  return getAuthToken() !== null && getAuthToken() !== "";
}

export function logout() {
  setAuthToken(null);
  localStorage.removeItem("user_role");
}

export function isAdmin() {
  const role = localStorage.getItem("user_role");
  return role === "admin";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Content-Type", "application/json");
  
  const token = getAuthToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
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
  getAllProperties: (includeArchived: boolean = false) => 
    request<PropertyListResponse>(`/properties/all?include_archived=${includeArchived}`),
  searchProperties: (filters: SearchFilters, includeArchived: boolean = false, archivedOnly: boolean = false) => {
    const query = buildQuery({ 
      ...filters, 
      include_archived: includeArchived ? "true" : "false",
      archived_only: archivedOnly ? "true" : "false"
    } as Record<string, string | number | undefined>);
    return request<PropertyListResponse>(`/properties/search${query}`);
  },
  getProperty: (id: number) => request<Property>(`/properties/${id}`),
  register: (username: string, password: string) =>
    request<{ message: string }>("/register", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  login: (username: string, password: string) =>
    request<{ access_token: string; token_type: string; role: string }>("/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  adminSearch: (searchId: string, includeArchived: boolean = false) =>
    request<{ count: number; items: Property[] }>(`/admin/search?search_id=${searchId}&include_archived=${includeArchived}`),
  adminArchive: (propertyId: number) =>
    request<{ message: string }>(`/admin/${propertyId}/archive`, {
      method: "POST",
    }),
  adminUnarchive: (propertyId: number) =>
    request<{ message: string }>(`/admin/${propertyId}/unarchive`, {
      method: "POST",
    }),
  getKpis: () =>
    request<{
      properties_by_type: Record<string, number>;
      archived_count: number;
      user_count: number;
      ads_by_source: Record<string, number>;
    }>("/admin/kpis"),
};
