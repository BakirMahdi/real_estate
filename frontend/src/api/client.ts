import type {
  AgentMessage,
  ArchiveSearchParams,
  HealthStatus,
  Property,
  PropertyEstimate,
  PropertyListResponse,
  ScrapeProgress,
  ScrapeResult,
  SearchFilters,
} from "../types/property";

export const API_BASE = import.meta.env.VITE_API_URL ?? "/api";

// The JWT itself lives ONLY in an HttpOnly cookie set by the backend, so it's
// unreadable from JavaScript and can't be stolen via XSS. What we keep in
// localStorage is non-sensitive UI state (are we logged in, display name,
// role) — a forged value here just yields a broken-looking UI, since the
// server re-verifies the signed cookie on every request.
export function setSession(role: string, username: string) {
  localStorage.setItem("logged_in", "1");
  localStorage.setItem("user_role", role);
  localStorage.setItem("username", username);
}

function clearSession() {
  localStorage.removeItem("logged_in");
  localStorage.removeItem("user_role");
  localStorage.removeItem("username");
}

export function isAuthenticated() {
  return localStorage.getItem("logged_in") === "1";
}

export function logout() {
  // Fire-and-forget: ask the server to clear the HttpOnly cookie, then drop
  // local UI state regardless of the network result.
  void fetch(`${API_BASE}/logout`, { method: "POST", credentials: "include" }).catch(() => {});
  clearSession();
}

export function isAdmin() {
  return localStorage.getItem("user_role") === "admin";
}

/** The logged-in user's display name (stored at login), or null. */
export function getUsername(): string | null {
  return localStorage.getItem("username");
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Content-Type", "application/json");

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers,
      // Send/receive the HttpOnly auth cookie on every request.
      credentials: "include",
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    if (response.status === 401) {
      // The cookie is missing/expired — drop stale local UI state so the app
      // shows the logged-out view instead of a half-authenticated one.
      clearSession();
      throw new Error("UNAUTHORIZED");
    }

    if (!response.ok) {
      const body = await response.text();
      // FastAPI wraps error messages as {"detail": "..."} — surface only the
      // message itself, never the raw JSON payload.
      let detail = body;
      try {
        const parsed = JSON.parse(body);
        if (parsed && typeof parsed.detail === "string") detail = parsed.detail;
      } catch {
        // Body wasn't JSON; keep it as-is.
      }
      throw new Error(detail || `Request failed (${response.status})`);
    }

    return response.json() as Promise<T>;
  } catch (error) {
    clearTimeout(timeoutId);
    if (error instanceof Error && error.name === 'AbortError') {
      throw new Error("Request timeout - server may be busy");
    }
    throw error;
  }
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
  cancelScrape: () => request<{ status: string }>("/scrape/cancel", { method: "POST" }),
  getScrapeStatus: () => request<{
    is_scraping: boolean;
    cancel_requested: boolean;
    cancelled: boolean;
    triggered_by: string | null;
    results: ScrapeResult[] | null;
    error: string | null;
    next_scrape_time: number | null;
    progress?: ScrapeProgress;
    training?: boolean;
    training_error?: string | null;
    model_metrics?: Record<string, number> | null;
  }>("/scrape/status"),
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
  getPropertyEstimate: (id: number) =>
    request<PropertyEstimate>(`/properties/${id}/estimate`),
  register: (email: string, password: string) =>
    request<{ message: string; email: string }>("/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  verifyEmail: (email: string, code: string) =>
    request<{ access_token: string; token_type: string; role: string; username: string }>(
      "/auth/verify-email",
      {
        method: "POST",
        body: JSON.stringify({ email, code }),
      },
    ),
  resendCode: (email: string) =>
    request<{ message: string }>("/auth/resend-code", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),
  login: (email: string, password: string) =>
    request<{ access_token: string; token_type: string; role: string; username: string }>("/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  getAuthConfig: () => request<{ google_client_id: string }>("/auth/config"),
  googleLogin: (credential: string) =>
    request<{ access_token: string; token_type: string; role: string; username: string }>("/auth/google", {
      method: "POST",
      body: JSON.stringify({ credential }),
    }),
  adminArchiveSearch: (params: ArchiveSearchParams) => {
    const query = buildQuery({
      search: params.search,
      archived_only: params.archivedOnly ? "true" : undefined,
      offset: params.offset,
      limit: params.limit,
      sort_by: params.sortBy,
      sort_dir: params.sortDir,
      city: params.city,
      subcategory: params.subcategory,
      listing_type: params.listingType,
      min_price: params.minPrice,
      max_price: params.maxPrice,
      min_area: params.minArea,
      max_area: params.maxArea,
      bedrooms: params.bedrooms,
    });
    return request<{ total: number; total_filtered: number; items: Property[] }>(
      `/admin/archive-search${query}`,
    );
  },
  adminArchive: (propertyId: number) =>
    request<{ message: string }>(`/admin/${propertyId}/archive`, {
      method: "POST",
    }),
  adminUnarchive: (propertyId: number) =>
    request<{ message: string }>(`/admin/${propertyId}/unarchive`, {
      method: "POST",
    }),
  getAgentHistory: () => request<{ messages: AgentMessage[] }>("/agent/history"),
  agentChat: (message: string, propertyId?: number) =>
    request<{ reply: string }>("/agent/chat", {
      method: "POST",
      body: JSON.stringify({ message, property_id: propertyId ?? null }),
    }),
  getKpis: () =>
    request<{
      properties_by_type: Record<string, number>;
      archived_count: number;
      user_count: number;
      ads_by_source: Record<string, number>;
    }>("/admin/kpis"),
};
