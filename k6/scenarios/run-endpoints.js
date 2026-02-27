/**
 * Generic endpoint runner — iterates all endpoints from endpoints.json,
 * grouped by their "group" field, with optional sleep between groups.
 *
 * Imported by main.js default export.
 */

import { group, sleep } from 'k6';
import { endpointConfig } from '../lib/metrics.js';
import { executeEndpoint } from '../lib/request.js';
import { refreshOnUnauthorized } from '../lib/auth.js';

// Group endpoints by their "group" field, preserving insertion order
const _byGroup = (() => {
  const map = new Map();
  for (const ep of (endpointConfig.endpoints || [])) {
    const g = ep.group || 'default';
    if (!map.has(g)) map.set(g, []);
    map.get(g).push(ep);
  }
  return map;
})();

// Inter-group sleep in seconds (configurable via env var, default 0.5s)
const GROUP_SLEEP = Math.max(0, parseFloat(__ENV.GROUP_SLEEP) || 0.5);

/**
 * Run all endpoint groups for one VU iteration.
 *
 * @param {string} baseUrl     - BASE_URL
 * @param {Object} authHeaders - auth headers from getAuthHeaders()
 * @param {Object} data        - setup() data (fixture IDs etc.)
 */
export function runAllEndpoints(baseUrl, authHeaders, data) {
  let first = true;
  for (const [groupName, endpoints] of _byGroup) {
    if (!first && GROUP_SLEEP > 0) sleep(GROUP_SLEEP);
    first = false;

    group(groupName, () => {
      for (const ep of endpoints) {
        _maybeRunWeighted(ep, baseUrl, authHeaders, data);
      }
    });
  }
}

/**
 * Weighted execution: an endpoint with weight N has N times the call
 * frequency of one with weight 1. Fractional weights are randomised.
 */
function _maybeRunWeighted(ep, baseUrl, authHeaders, data) {
  const weight = ep.weight ?? 1;

  // Integer weights: call N times per iteration
  const full = Math.floor(weight);
  for (let i = 0; i < full; i++) {
    executeEndpoint(ep, baseUrl, authHeaders, data, refreshOnUnauthorized);
  }

  // Fractional part: call with that probability
  const frac = weight - full;
  if (frac > 0 && Math.random() < frac) {
    executeEndpoint(ep, baseUrl, authHeaders, data, refreshOnUnauthorized);
  }
}
