import { proxyJson } from "../../../_lib/backend";

export async function POST(
  request: Request,
  { params }: { params: { claimId: string } },
): Promise<Response> {
  return proxyJson(`/v1/claims/${params.claimId}/decision`, {
    method: "POST",
    body: await request.text(),
  });
}
