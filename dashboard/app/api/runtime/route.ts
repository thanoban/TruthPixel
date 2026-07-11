import { getBackendApiKey, getBackendUrl, getDefaultReviewerId, getTenantLabel } from "../../../lib/backend_proxy";

export async function GET(): Promise<Response> {
  return Response.json({
    backend_url: getBackendUrl(),
    tenant_label: getTenantLabel(),
    reviewer_auth_mode: getBackendApiKey() ? "tenant_api_key_proxy" : "local_dev_bypass",
    api_key_configured: Boolean(getBackendApiKey()),
    default_reviewer_id: getDefaultReviewerId(),
  });
}
