import { NextRequest } from "next/server";

import { proxyJson } from "../_lib/backend";

export async function GET(request: NextRequest): Promise<Response> {
  const search = request.nextUrl.search;
  return proxyJson(`/v1/claims${search}`);
}
