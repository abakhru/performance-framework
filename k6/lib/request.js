/**
 * Generic HTTP request helper — supports REST (GET/POST/PUT/DELETE/PATCH)
 * and GraphQL (POST with {query, variables} body).
 *
 * Called by the generic scenario runner (k6/scenarios/run-endpoints.js)
 * for each endpoint defined in k6/config/endpoints.json.
 */

import http from 'k6/http';
import { check } from 'k6';
import { recordOp, recordRequestExtras } from './metrics.js';

/**
 * Execute a single endpoint definition.
 *
 * @param {Object}   ep               - Endpoint config object from endpoints.json
 * @param {string}   baseUrl          - BASE_URL env var value
 * @param {Object}   authHeaders      - Headers produced by getAuthHeaders() in auth.js
 * @param {Object}   data             - Data returned from setup() (fixture IDs etc.)
 * @param {Function} [onUnauthorized] - Optional callback invoked on 401; should return
 *                                      fresh auth headers. When provided the request is
 *                                      automatically retried once with the new headers.
 * @returns {http.Response|null}  null if endpoint was skipped due to missing data
 */
export function executeEndpoint(ep, baseUrl, authHeaders, data, onUnauthorized) {
  // Check required data keys — skip if any are missing
  if (ep.requires) {
    for (const key of ep.requires) {
      if (!data[key]) {
        return null;
      }
    }
  }

  // Build merged variables: static + data-driven overrides
  const variables = _buildVariables(ep, data);

  // Build full URL
  const url = baseUrl + ep.path;

  // Build request headers
  const headers = Object.assign({}, authHeaders, ep.headers || {});

  let res;
  const type = (ep.type || 'rest').toLowerCase();

  if (type === 'graphql') {
    res = _graphqlRequest(url, headers, ep.query, variables);
  } else {
    res = _restRequest(url, headers, ep.method || 'GET', _buildBody(ep, data));
  }

  // Auto-retry on 401 with refreshed credentials
  if (res && res.status === 401 && typeof onUnauthorized === 'function') {
    const newHeaders = onUnauthorized();
    const type2 = (ep.type || 'rest').toLowerCase();
    if (type2 === 'graphql') {
      res = _graphqlRequest(url, Object.assign({}, newHeaders, ep.headers || {}), ep.query, variables);
    } else {
      res = _restRequest(url, Object.assign({}, newHeaders, ep.headers || {}), ep.method || 'GET', _buildBody(ep, data));
    }
  }

  // Run checks
  const hasError = _runChecks(res, ep);

  // Record per-operation metrics
  recordOp(ep.name, res.timings.duration, hasError);

  // Record aggregated request-level metrics (status class, histogram, Apdex, conn reuse)
  recordRequestExtras(res.status, res.timings.duration, res.timings.connecting || 0);

  return res;
}

// ── Internal helpers ──────────────────────────────────────────────────────────

function _buildVariables(ep, data) {
  const vars = Object.assign({}, ep.variables || {});

  // Merge data-driven variables: { varName: dataKey }
  if (ep.variables_from_data) {
    for (const [varKey, dataKey] of Object.entries(ep.variables_from_data)) {
      vars[varKey] = data[dataKey];
    }
  }

  // Template substitution in variables_template (e.g. "${timestamp}")
  if (ep.variables_template) {
    const rendered = JSON.parse(
      JSON.stringify(ep.variables_template).replace(/\$\{timestamp\}/g, Date.now())
    );
    Object.assign(vars, rendered);
  }

  return vars;
}

function _buildBody(ep, data) {
  if (!ep.body) return null;

  // Support ${data.key} template substitution in REST body strings
  const raw = JSON.stringify(ep.body);
  const rendered = raw.replace(/"\$\{data\.(\w+)\}"/g, (_m, key) => {
    const val = data[key];
    return val == null ? 'null' : JSON.stringify(val);
  });
  return rendered;
}

function _graphqlRequest(url, headers, query, variables) {
  return http.post(
    url,
    JSON.stringify({ query, variables }),
    { headers: Object.assign({ 'Content-Type': 'application/json' }, headers) }
  );
}

function _restRequest(url, headers, method, body) {
  const params = { headers: Object.assign({ 'Content-Type': 'application/json' }, headers) };
  const m = method.toUpperCase();

  if (m === 'GET' || m === 'DELETE' || m === 'HEAD') {
    return http[m.toLowerCase()](url, params);
  }
  return http.request(m, url, body, params);
}

function _runChecks(res, ep) {
  const cfg = ep.checks || {};
  const checks = {};
  let hasError = false;

  // Status code check
  const expectedStatus = cfg.status ?? 200;
  const statusPassed = res.status === expectedStatus;
  checks[`${ep.name}: status ${expectedStatus}`] = () => statusPassed;
  if (!statusPassed) hasError = true;

  // GraphQL-specific checks
  if ((ep.type || 'rest').toLowerCase() === 'graphql') {
    let body = null;
    try { body = JSON.parse(res.body); } catch (_) { /* ignore */ }

    if (cfg.no_graphql_errors !== false) {
      const noErrors = body ? !(body.errors && body.errors.length > 0) : false;
      checks[`${ep.name}: no graphql errors`] = () => noErrors;
      if (!noErrors) hasError = true;
    }

    if (cfg.has_data !== false) {
      const hasData = body ? body.data != null : false;
      checks[`${ep.name}: has data`] = () => hasData;
      if (!hasData) hasError = true;
    }
  }

  // Optional: check a JSON body path exists (for REST)
  if (cfg.body_path) {
    const pathOk = _checkBodyPath(res, cfg.body_path);
    checks[`${ep.name}: body path ${cfg.body_path}`] = () => pathOk;
    if (!pathOk) hasError = true;
  }

  check(res, checks);
  return hasError;
}

function _checkBodyPath(res, path) {
  try {
    let obj = JSON.parse(res.body);
    for (const key of path.split('.')) {
      if (obj == null) return false;
      obj = obj[key];
    }
    return obj != null;
  } catch (_) {
    return false;
  }
}

/**
 * Extract a value from a response body using a dot-separated path.
 * Used by setup() to capture IDs from mutation results.
 */
export function extractFromResponse(res, path) {
  try {
    let obj = JSON.parse(res.body);
    for (const key of path.split('.')) {
      if (obj == null) return null;
      obj = obj[key];
    }
    return obj ?? null;
  } catch (_) {
    return null;
  }
}
