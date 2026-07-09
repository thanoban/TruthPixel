import { NextResponse } from "next/server";

const DEFAULT_API_URL = "http://localhost:8000";
const API_URL = process.env.TRUTHPIXEL_API_URL || process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_URL;
const API_KEY = process.env.TRUTHPIXEL_DASHBOARD_API_KEY || "";
const REVIEWER_ID_DEFAULT = process.env.TRUTHPIXEL_DASHBOARD_REVIEWER_ID || "reviewer-1";
const DASHBOARD_LABEL = process.env.TRUTHPIXEL_DASHBOARD_LABEL || "TruthPixel reviewer dashboard";
const TENANT_LABEL = process.env.TRUTHPIXEL_DASHBOARD_TENANT_LABEL || "";

function joinUrl(path: string): string {
  return `${API_URL.replace(/\/$/, "")}${path.startsWith("/") ? path : `/${path}`}`;
}

export function artifactProxyPath(claimId: string, artifactId: number): string {
  return `/api/claims/${claimId}/artifacts/${artifactId}`;
}

export function dashboardAuthError(): NextResponse {
  return NextResponse.json(
    {
      detail:
        "dashboard API key not configured; set TRUTHPIXEL_DASHBOARD_API_KEY for reviewer access",
    },
    { status: 503 },
  );
}

export function dashboardAuthMode(): "tenant_api_key" | "local_passthrough" {
  return API_KEY ? "tenant_api_key" : "local_passthrough";
}

export function getReviewerContext() {
  const authMode = dashboardAuthMode();
  const tenantLabel = TENANT_LABEL.trim() || null;
  return {
    apiUrl: API_URL,
    authMode,
    reviewerIdDefault: REVIEWER_ID_DEFAULT,
    dashboardLabel: DASHBOARD_LABEL,
    tenantLabel,
    authHint:
      authMode === "tenant_api_key"
        ? "Requests are proxied with the configured tenant API key."
        : "No dashboard API key is configured; requests are passed through for local development only.",
  };
}

export async function proxyJson(path: string, init?: RequestInit): Promise<NextResponse> {
  const headers = new Headers(init?.headers);
  if (API_KEY) {
    headers.set("X-API-Key", API_KEY);
  }
  const hasBody = init?.body !== undefined && init?.body !== null;
  if (hasBody && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(joinUrl(path), {
    ...init,
    headers,
    cache: "no-store",
  });

  const text = await response.text();
  const forwardedHeaders = new Headers();
  forwardedHeaders.set(
    "content-type",
    response.headers.get("content-type") || "application/json; charset=utf-8",
  );
  const rateLimitLimit = response.headers.get("x-ratelimit-limit");
  const rateLimitRemaining = response.headers.get("x-ratelimit-remaining");
  const retryAfter = response.headers.get("retry-after");
  if (rateLimitLimit) {
    forwardedHeaders.set("x-ratelimit-limit", rateLimitLimit);
  }
  if (rateLimitRemaining) {
    forwardedHeaders.set("x-ratelimit-remaining", rateLimitRemaining);
  }
  if (retryAfter) {
    forwardedHeaders.set("retry-after", retryAfter);
  }
  forwardedHeaders.set("x-truthpixel-dashboard-auth-mode", dashboardAuthMode());
  return new NextResponse(text, {
    status: response.status,
    headers: forwardedHeaders,
  });
}

export async function proxyBinary(path: string): Promise<NextResponse> {
  const headers = new Headers();
  if (API_KEY) {
    headers.set("X-API-Key", API_KEY);
  }
  const response = await fetch(joinUrl(path), {
    headers,
    cache: "no-store",
  });

  const bytes = await response.arrayBuffer();
  const forwardedHeaders = new Headers();
  const mediaType = response.headers.get("content-type");
  const contentDisposition = response.headers.get("content-disposition");
  if (mediaType) {
    forwardedHeaders.set("content-type", mediaType);
  }
  if (contentDisposition) {
    forwardedHeaders.set("content-disposition", contentDisposition);
  }
  forwardedHeaders.set("x-truthpixel-dashboard-auth-mode", dashboardAuthMode());
  return new NextResponse(bytes, {
    status: response.status,
    headers: forwardedHeaders,
  });
}
