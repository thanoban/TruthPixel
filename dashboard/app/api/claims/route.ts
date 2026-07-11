import { proxyJson } from "../../../lib/backend_proxy";

export async function GET(request: Request): Promise<Response> {
  const url = new URL(request.url);
  const suffix = url.search ? `?${url.searchParams.toString()}` : "";
  return proxyJson(`/v1/claims${suffix}`);
}
