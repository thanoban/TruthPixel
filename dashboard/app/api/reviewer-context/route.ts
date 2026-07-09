import { NextResponse } from "next/server";

import { getReviewerContext } from "../_lib/backend";

export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  return NextResponse.json(getReviewerContext());
}
