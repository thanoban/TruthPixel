import { proxyJson } from "../../../../../lib/backend_proxy";

export async function POST(
  request: Request,
  { params }: { params: { claimId: string } },
): Promise<Response> {
  return proxyJson(`/v1/claims/${params.claimId}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: await request.text(),
  });
}
