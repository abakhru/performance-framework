/**
 * Auth strategy selector — Bearer, Basic, API Key, Keycloak client_credentials.
 * Supports automatic token refresh for long-running tests.
 */

import http from 'k6/http';
import { check } from 'k6';

// ── Token state (module-scoped, per-VU) ──────────────────────────────────────
let _cachedToken    = __ENV.AUTH_TOKEN || '';
let _tokenFetchedAt = 0;  // epoch ms when token was last fetched (0 = never)
const _REFRESH_INTERVAL_MS = (parseInt(__ENV.AUTH_REFRESH_INTERVAL || '3300', 10) || 3300) * 1000;

/**
 * Return auth headers for the current VU based on configured auth mode.
 * Automatically refreshes expired Keycloak tokens.
 *
 * Auth mode is selected automatically from environment variables (checked in order):
 *
 *  1. Keycloak client_credentials — AUTH_HOST + AUTH_CLIENT_ID + AUTH_CLIENT_SECRET.
 *     Performs an OAuth2 client_credentials grant against Keycloak.
 *     Supports auto-refresh via AUTH_REFRESH_INTERVAL (seconds, default 3300).
 *     → { Authorization: "Bearer <access_token>" }
 *
 *  2. Bearer token  — AUTH_TOKEN is set directly.
 *     Supports refresh via AUTH_REFRESH_ENDPOINT if AUTH_REFRESH_INTERVAL elapses.
 *     → { Authorization: "Bearer <token>" }
 *
 *  3. Basic auth — AUTH_BASIC_USER (+ optional AUTH_BASIC_PASS).
 *     → { Authorization: "Basic <base64(user:pass)>" }
 *
 *  4. API key header — AUTH_API_KEY + AUTH_API_KEY_HEADER (default: "X-API-Key").
 *     → { <AUTH_API_KEY_HEADER>: "<AUTH_API_KEY>" }
 *
 *  5. No auth — AUTH_NONE=true.
 *     → {}
 *
 * If none of the above are configured, throws an error.
 */
export function getAuthHeaders() {
  // Keycloak client_credentials flow — supports auto-refresh
  if (__ENV.AUTH_HOST && __ENV.AUTH_CLIENT_ID && __ENV.AUTH_CLIENT_SECRET) {
    const now = Date.now();
    if (!_cachedToken || (now - _tokenFetchedAt) > _REFRESH_INTERVAL_MS) {
      _cachedToken    = _fetchKeycloakToken();
      _tokenFetchedAt = now;
    }
    return { Authorization: `Bearer ${_cachedToken}` };
  }

  // Bearer token — static or env-provided; refresh if AUTH_REFRESH_INTERVAL set
  if (__ENV.AUTH_TOKEN) {
    const now = Date.now();
    const shouldRefresh = __ENV.AUTH_REFRESH_ENDPOINT &&
      _tokenFetchedAt > 0 &&
      (now - _tokenFetchedAt) > _REFRESH_INTERVAL_MS;
    if (shouldRefresh) {
      const refreshed = _fetchRefreshEndpoint();
      if (refreshed) {
        _cachedToken    = refreshed;
        _tokenFetchedAt = now;
      }
    } else if (_tokenFetchedAt === 0) {
      _cachedToken    = __ENV.AUTH_TOKEN;
      _tokenFetchedAt = now;
    }
    return { Authorization: `Bearer ${_cachedToken}` };
  }

  // HTTP Basic auth
  if (__ENV.AUTH_BASIC_USER) {
    const creds   = `${__ENV.AUTH_BASIC_USER}:${__ENV.AUTH_BASIC_PASS || ''}`;
    const encoded = btoa(creds);
    return { Authorization: `Basic ${encoded}` };
  }

  // API key
  if (__ENV.AUTH_API_KEY) {
    const header = __ENV.AUTH_API_KEY_HEADER || 'X-API-Key';
    return { [header]: __ENV.AUTH_API_KEY };
  }

  // Explicit no-auth mode
  if (['true', '1', 'yes'].includes((__ENV.AUTH_NONE || '').toLowerCase())) {
    return {};
  }

  throw new Error(
    'No auth configured. Set one of:\n' +
    '  AUTH_HOST + AUTH_CLIENT_ID + AUTH_CLIENT_SECRET → Keycloak client credentials\n' +
    '  AUTH_TOKEN                                       → Bearer token\n' +
    '  AUTH_BASIC_USER [+ AUTH_BASIC_PASS]              → HTTP Basic auth\n' +
    '  AUTH_API_KEY [+ AUTH_API_KEY_HEADER]             → API key header\n' +
    '  AUTH_NONE=true                                   → No authentication'
  );
}

/**
 * Handle a 401 response — force-refresh the token and return new headers.
 * Call this from the request executor when a 401 is received.
 */
export function refreshOnUnauthorized() {
  if (__ENV.AUTH_HOST && __ENV.AUTH_CLIENT_ID && __ENV.AUTH_CLIENT_SECRET) {
    _cachedToken    = _fetchKeycloakToken();
    _tokenFetchedAt = Date.now();
    return { Authorization: `Bearer ${_cachedToken}` };
  }
  if (__ENV.AUTH_REFRESH_ENDPOINT) {
    const refreshed = _fetchRefreshEndpoint();
    if (refreshed) {
      _cachedToken    = refreshed;
      _tokenFetchedAt = Date.now();
      return { Authorization: `Bearer ${_cachedToken}` };
    }
  }
  return getAuthHeaders();
}

/**
 * Convenience: returns just the Bearer token string (backwards compat with
 * old code that called getToken() and passed the token directly to gqlRequest).
 */
export function getToken() {
  const headers   = getAuthHeaders();
  const authValue = headers['Authorization'] || headers['authorization'] || '';
  if (authValue.startsWith('Bearer ')) {
    return authValue.slice(7);
  }
  // For non-Bearer modes, return empty string (callers that need raw token
  // should migrate to getAuthHeaders()).
  return '';
}

// ── Internal helpers ──────────────────────────────────────────────────────────

function _fetchKeycloakToken() {
  const host    = __ENV.AUTH_HOST.replace(/\/$/, '');
  const realm   = __ENV.AUTH_REALM || 'master';
  const url     = `${host}/realms/${realm}/protocol/openid-connect/token`;
  const payload = {
    grant_type:    'client_credentials',
    client_id:     __ENV.AUTH_CLIENT_ID,
    client_secret: __ENV.AUTH_CLIENT_SECRET,
  };
  const res = http.post(url, payload, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });
  const ok = check(res, { 'keycloak token ok': (r) => r.status === 200 });
  if (!ok) {
    console.error(`[auth] Keycloak token fetch failed: ${res.status} ${res.body}`);
    return _cachedToken || '';
  }
  try {
    return JSON.parse(res.body).access_token || '';
  } catch (_) {
    return _cachedToken || '';
  }
}

function _fetchRefreshEndpoint() {
  const baseUrl = __ENV.BASE_URL || '';
  const path    = __ENV.AUTH_REFRESH_ENDPOINT || '';
  if (!baseUrl || !path) return null;
  const res = http.post(`${baseUrl}${path}`, null, {
    headers: { Authorization: `Bearer ${_cachedToken}` },
  });
  if (res.status !== 200) return null;
  try {
    const body = JSON.parse(res.body);
    return body.access_token || body.token || null;
  } catch (_) {
    return null;
  }
}
