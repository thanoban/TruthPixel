import "server-only";

const DEFAULT_BACKEND_URL = "http://localhost:8000";
const JSON_CONTENT_TYPE = "application/json";

function trimTrailingSlash(value: string): string {
  return value.endsWith("/") ? value.slice(0, -1) : value;
}

export function getBackendUrl(): string {
  const configured =
    process.env.TRUTHPIXEL_API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    DEFAULT_BACKEND_URL;
  return trimTrailingSlash(configured);
}

export function getBackendApiKey(): string {
  return process.env.TRUTHPIXEL_API_KEY || process.env.NEXT_PUBLIC_API_KEY || "";
}

export function getTenantLabel(): string {
  return process.env.NEXT_PUBLIC_DASHBOARD_TENANT_LABEL || "Reviewer workspace";
}

export function getDefaultReviewerId(): string {
  return process.env.NEXT_PUBLIC_DEFAULT_REVIEWER_ID || "";
}

function withAuthHeaders(headers: Headers): Headers {
  const enriched = new Headers(headers);
  const apiKey = getBackendApiKey();
  if (apiKey) {
    enriched.set("X-API-Key", apiKey);
  }
  return enriched;
}

function buildErrorDetail(
  upstreamStatus: number,
  upstreamDetail: unknown,
  apiKeyConfigured: boolean,
): string {
  if (
    upstreamStatus === 401 &&
    !apiKeyConfigured &&
    typeof upstreamDetail === "string" &&
    upstreamDetail.toLowerCase().includes("api key")
  ) {
    return "Dashboard reviewer auth is not configured. Set TRUTHPIXEL_API_KEY in dashboard/.env.local or disable API_AUTH_ENABLED for local-only use.";
  }
  if (typeof upstreamDetail === "string" && upstreamDetail.trim()) {
    return upstreamDetail;
  }
  return `Backend request failed with ${upstreamStatus}.`;
}

export async function proxyJson(
  pathWithQuery: string,
  init?: RequestInit,
): Promise<Response> {
  const backendUrl = `${getBackendUrl()}${pathWithQuery}`;
  const baseHeaders = new Headers(init?.headers);
  if (!baseHeaders.has("Content-Type") && init?.body) {
    baseHeaders.set("Content-Type", JSON_CONTENT_TYPE);
  }

  let upstream: Response;
  try {
    upstream = await fetch(backendUrl, {
      ...init,
      headers: withAuthHeaders(baseHeaders),
      cache: "no-store",
    });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unknown backend connectivity failure";
    return Response.json(
      { detail: `Dashboard could not reach ${getBackendUrl()}: ${message}` },
      { status: 502 },
    );
  }

  const responseHeaders = new Headers();
  const rateHeaders = ["X-RateLimit-Limit", "X-RateLimit-Remaining", "Retry-After"];
  for (const headerName of rateHeaders) {
    const value = upstream.headers.get(headerName);
    if (value) {
      responseHeaders.set(headerName, value);
    }
  }

  const contentType = upstream.headers.get("content-type") || JSON_CONTENT_TYPE;
  if (!contentType.includes(JSON_CONTENT_TYPE)) {
    return new Response(await upstream.arrayBuffer(), {
      status: upstream.status,
      headers: responseHeaders,
    });
  }

  let payload: unknown = null;
  try {
    payload = await upstream.json();
  } catch {
    payload = null;
  }

  if (!upstream.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? (payload as { detail?: unknown }).detail
        : payload;
    return Response.json(
      { detail: buildErrorDetail(upstream.status, detail, Boolean(getBackendApiKey())) },
      {
        status: upstream.status,
        headers: responseHeaders,
      },
    );
  }

  responseHeaders.set("Content-Type", JSON_CONTENT_TYPE);
  return new Response(JSON.stringify(payload), {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export async function proxyBinary(pathWithQuery: string): Promise<Response> {
  const backendUrl = `${getBackendUrl()}${pathWithQuery}`;
  let upstream: Response;
  try {
    upstream = await fetch(backendUrl, {
      headers: withAuthHeaders(new Headers()),
      cache: "no-store",
    });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unknown backend connectivity failure";
    return Response.json(
      { detail: `Dashboard could not reach ${getBackendUrl()}: ${message}` },
      { status: 502 },
    );
  }

  if (!upstream.ok) {
    const detail =
      upstream.headers.get("content-type")?.includes(JSON_CONTENT_TYPE)
        ? ((await upstream.json()) as { detail?: unknown }).detail
        : null;
    return Response.json(
      { detail: buildErrorDetail(upstream.status, detail, Boolean(getBackendApiKey())) },
      { status: upstream.status },
    );
  }

  const headers = new Headers();
  for (const headerName of ["Content-Type", "Content-Disposition", "Cache-Control", "ETag"]) {
    const value = upstream.headers.get(headerName);
    if (value) {
      headers.set(headerName, value);
    }
  }
  return new Response(await upstream.arrayBuffer(), {
    status: upstream.status,
    headers,
  });
}
