// Only server-generated identifiers cross this event seam; no exception or input text.
export const SUPPORT_FAULT = "opencareer:support-fault";
export const SUPPORT_OPEN = "opencareer:support-open";
export const SUPPORT_RESET = "opencareer:support-reset";
export const safeDiagnosticId = (id: unknown): string | undefined =>
  typeof id === "string" && /^[0-9a-f]{32}$/.test(id) ? id : undefined;
export function publishFault(id: unknown): void {
  const requestId = safeDiagnosticId(id);
  if (requestId) window.dispatchEvent(new CustomEvent(SUPPORT_FAULT, { detail: { requestId } }));
}
export function openSupport(id?: string): void {
  window.dispatchEvent(new CustomEvent(SUPPORT_OPEN, { detail: { requestId: safeDiagnosticId(id) } }));
}
