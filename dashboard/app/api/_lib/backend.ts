import { NextResponse } from "next/server";

const DEFAULT_API_URL = "http://localhost:8000";
const API_URL = process.env.TRUTHPIXEL_API_URL || process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_URL;
const API_KEY = process.env.TRUTHPIXEL_DASHBOARD_API_KEY || "";

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

export async function proxyJson(path: string, init?: RequestInit): Promise<NextResponse> {
  if (!API_KEY) {
    return dashboardAuthError();
  }

  const headers = new Headers(init?.headers);
  headers.set("X-API-Key", API_KEY);
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
  return new NextResponse(text, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") || "application/json; charset=utf-8",
    },
  });
}

export async function proxyBinary(path: string): Promise<NextResponse> {
  if (!API_KEY) {
    return dashboardAuthError();
  }

  const response = await fetch(joinUrl(path), {
    headers: {
      "X-API-Key": API_KEY,
    },
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
  return new NextResponse(bytes, {
    status: response.status,
    headers: forwardedHeaders,
  });
}
