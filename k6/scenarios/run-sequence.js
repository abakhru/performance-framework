/**
 * Ordered scenario executor — runs endpoints as defined user journeys
 * rather than random weighted selection.
 *
 * Reads "scenarios" array from endpoints.json. Each scenario has:
 *   - name: identifier
 *   - weight: relative selection probability
 *   - think_time: default pause between steps (e.g. "0.5s")
 *   - steps: array of { ref: "EndpointName", think_time?: "1s" }
 *
 * The executor picks a scenario by weighted random selection, then
 * runs each step in order with configurable think-time pauses.
 *
 * Example endpoints.json scenario definition:
 *   "scenarios": [
 *     {
 *       "name": "browse_knowledge",
 *       "weight": 2,
 *       "think_time": "0.5s",
 *       "steps": [
 *         { "ref": "GetKnowledgeBases" },
 *         { "ref": "QueryKnowledgeBase", "think_time": "1s" },
 *         { "ref": "GetKnowledgeGraph" }
 *       ]
 *     }
 *   ]
 */

import { sleep } from 'k6';
import { getAuthHeaders, refreshOnUnauthorized } from '../lib/auth.js';
import { executeEndpoint } from '../lib/request.js';
import { endpointConfig } from '../lib/metrics.js';

// Build a lookup map: endpoint name → endpoint object
const _epMap = {};
for (const ep of (endpointConfig.endpoints || [])) {
  if (ep.name) _epMap[ep.name] = ep;
}

// Build weighted scenario list
const _scenarios = endpointConfig.scenarios || [];
const _totalWeight = _scenarios.reduce((s, sc) => s + (sc.weight || 1), 0);

/**
 * Pick a scenario by weighted random selection.
 */
function _pickScenario() {
  if (_scenarios.length === 0) return null;
  let r = Math.random() * _totalWeight;
  for (const sc of _scenarios) {
    r -= (sc.weight || 1);
    if (r <= 0) return sc;
  }
  return _scenarios[_scenarios.length - 1];
}

/**
 * Parse a duration string like "0.5s" or "2s" to a number of seconds.
 */
function _parseSleep(str) {
  if (!str) return 0;
  const n = parseFloat(str);
  return isNaN(n) ? 0 : n;
}

/**
 * Run one iteration of the scenario executor.
 * Call this from main.js default() function when scenarios are defined.
 *
 * @param {string} baseUrl    - BASE_URL env var
 * @param {Object} data       - setup() result data
 */
export function runScenario(baseUrl, data) {
  const scenario = _pickScenario();
  if (!scenario) return;

  const defaultThinkTime = _parseSleep(scenario.think_time);
  const authHeaders = getAuthHeaders();

  for (let i = 0; i < scenario.steps.length; i++) {
    const step = scenario.steps[i];
    const ep   = _epMap[step.ref];
    if (!ep) {
      console.warn(`[scenario] unknown endpoint ref: ${step.ref}`);
      continue;
    }

    // executeEndpoint handles 401 retry internally via the refreshOnUnauthorized callback
    executeEndpoint(ep, baseUrl, authHeaders, data, refreshOnUnauthorized);

    // Think time between steps (not after the last step)
    if (i < scenario.steps.length - 1) {
      const stepThinkTime = step.think_time !== undefined
        ? _parseSleep(step.think_time)
        : defaultThinkTime;
      if (stepThinkTime > 0) sleep(stepThinkTime);
    }
  }
}

/** Whether any scenarios are configured. */
export const hasScenarios = _scenarios.length > 0;
