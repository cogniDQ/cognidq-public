/**
 * Lightweight client-side JWT utility.
 *
 * Only the payload is decoded — no signature verification.
 * The signature is always verified by the backend on every API call; this
 * utility is only used for reading non-sensitive public claims (actor_role)
 * to drive client-side UI decisions.
 */

function decodePayload(token: string): Record<string, unknown> | null {
  const parts = token.split('.');
  if (parts.length !== 3) return null;
  try {
    // RFC 4648 §5 base64url → base64
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const json = atob(base64);
    return JSON.parse(json) as Record<string, unknown>;
  } catch {
    return null;
  }
}

/**
 * Extract the `actor_role` claim from a JWT string.
 *
 * Historically this used to apply a dev-mode role override (when a
 * platform_admin had picked an impersonated role in localStorage). That
 * mechanism has been removed: the role returned here is always the
 * authenticated user's real role from the JWT.
 */
export function getRealActorRole(token: string | null): string | null {
  if (!token) return null;
  const payload = decodePayload(token);
  const role = payload?.actor_role;
  return typeof role === 'string' ? role : null;
}

/**
 * Effective role used for UI gating. Equivalent to {@link getRealActorRole}
 * since the dev impersonation override has been removed.
 */
export function getActorRole(token: string | null): string | null {
  return getRealActorRole(token);
}

/**
 * Extract the `actor_id` claim from a JWT string.
 * Returns `null` if the token is missing, malformed, or has no such claim.
 */
export function getActorId(token: string | null): string | null {
  if (!token) return null;
  const payload = decodePayload(token);
  const id = payload?.actor_id;
  return typeof id === 'string' ? id : null;
}

/**
 * Extract the `tenant_id` claim from a JWT string.
 * Returns `null` if the token is missing, malformed, or has no such claim.
 */
export function getTenantId(token: string | null): string | null {
  if (!token) return null;
  const payload = decodePayload(token);
  const tid = payload?.tenant_id;
  return typeof tid === 'string' ? tid : null;
}
