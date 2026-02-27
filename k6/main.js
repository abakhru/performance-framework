/**
 * Generic k6 Performance Test — config-driven via k6/config/endpoints.json
 *
 * Supports any HTTP service: REST, GraphQL, or mixed.
 * Auth, load profiles, and thresholds are all configurable via env vars.
 *
 * Quick start:
 *   # Smoke test (2 VUs, 30s)
 *   k6 run --env BASE_URL=https://api.example.com \
 *           --env AUTH_TOKEN=<token> \
 *           --env LOAD_PROFILE=smoke \
 *           k6/main.js
 *
 *   # Ramp test
 *   k6 run --env BASE_URL=https://api.example.com \
 *           --env AUTH_TOKEN=<token> \
 *           --env LOAD_PROFILE=ramp --env VUS=20 --env DURATION=60s \
 *           k6/main.js
 *
 * See .env.example for all supported env vars.
 * See k6/config/endpoints.json to configure which endpoints to test.
 */

import { getOptions } from './config/options.js';
import { getAuthHeaders, refreshOnUnauthorized } from './lib/auth.js';
import { executeEndpoint, extractFromResponse } from './lib/request.js';
import { endpointConfig } from './lib/metrics.js';
import { runAllEndpoints } from './scenarios/run-endpoints.js';
import { runScenario, hasScenarios } from './scenarios/run-sequence.js';

// ---------------------------------------------------------------------------
// k6 options — resolved from LOAD_PROFILE env var
// ---------------------------------------------------------------------------
export const options = getOptions();

const BASE_URL = __ENV.BASE_URL || 'https://ai-beta-us-east-2.devo.cloud';

// ---------------------------------------------------------------------------
// setup() — runs once before VU iterations; returns data shared with all VUs
// ---------------------------------------------------------------------------
export function setup() {
  const authHeaders = getAuthHeaders();
  const data = {};

  // Run setup endpoints defined in endpoints.json
  for (const ep of (endpointConfig.setup || [])) {
    // Check required data keys (support chained setup: e.g. agentId needed by next step)
    if (ep.requires) {
      const missing = ep.requires.filter(k => !data[k]);
      if (missing.length > 0) {
        console.warn(`[setup] skipping ${ep.name} — missing data keys: ${missing.join(', ')}`);
        continue;
      }
    }

    const res = executeEndpoint(ep, BASE_URL, authHeaders, data, refreshOnUnauthorized);
    if (!res) continue;

    // Extract result value and store in data under result_key
    if (ep.result_key && ep.result_path) {
      const value = extractFromResponse(res, ep.result_path);
      data[ep.result_key] = value;
      console.log(`[setup] ${ep.name} → ${ep.result_key}=${value}`);
    }
  }

  return { authHeaders, ...data };
}

// ---------------------------------------------------------------------------
// default() — runs per VU iteration
// ---------------------------------------------------------------------------
export default function (setupData) {
  const { authHeaders, ...data } = setupData;

  if (hasScenarios) {
    // Scenario mode: ordered user journeys with weighted selection
    runScenario(BASE_URL, data);
  } else {
    // Default mode: random weighted endpoint execution grouped by group
    runAllEndpoints(BASE_URL, authHeaders, data);
  }
}

// ---------------------------------------------------------------------------
// teardown() — runs once after all VU iterations; cleans up test fixtures
// ---------------------------------------------------------------------------
export function teardown(setupData) {
  const { authHeaders, ...data } = setupData;

  for (const ep of (endpointConfig.teardown || [])) {
    if (ep.requires) {
      const missing = ep.requires.filter(k => !data[k]);
      if (missing.length > 0) {
        console.warn(`[teardown] skipping ${ep.name} — missing data keys: ${missing.join(', ')}`);
        continue;
      }
    }

    const res = executeEndpoint(ep, BASE_URL, authHeaders, data, refreshOnUnauthorized);
    if (res) {
      console.log(`[teardown] ${ep.name} → status=${res.status}`);
    }
  }
}
