import { proxyJson } from "../../../../../lib/backend_proxy";

export async function GET(
  _request: Request,
  { params }: { params: { claimId: string } },
): Promise<Response> {
  return proxyJson(`/v1/claims/${params.claimId}/audit`);
}
