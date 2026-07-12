import { proxyBinary } from "../../../../_lib/backend";

export async function GET(
  _request: Request,
  { params }: { params: { claimId: string; artifactId: string } },
): Promise<Response> {
  return proxyBinary(`/v1/claims/${params.claimId}/artifacts/${params.artifactId}`);
}
