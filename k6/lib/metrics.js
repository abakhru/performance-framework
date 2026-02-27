import { Trend, Counter, Rate } from 'k6/metrics';

/**
 * Dynamically register per-operation k6 metrics from endpoints.json.
 *
 * k6 requires all custom metrics to be instantiated at init time (not inside
 * VU functions). We achieve dynamic registration by reading the config file
 * with open() — which is only available at init time — and registering a
 * Trend + two Counters for every named endpoint (including setup/teardown ops).
 */

// Read endpoint names at init time via k6's open()
const _raw = open('../config/endpoints.json');
const _cfg = JSON.parse(_raw);

// Collect all op names across endpoints, setup, and teardown arrays
function _collectNames(cfg) {
  const names = new Set();
  for (const section of ['endpoints', 'setup', 'teardown']) {
    for (const ep of (cfg[section] || [])) {
      if (ep.name) names.add(ep.name);
    }
  }
  return [...names];
}

const ALL_OPS = _collectNames(_cfg);

// Register metrics at module level (init time) — required by k6
export const opMetrics = {};
for (const op of ALL_OPS) {
  opMetrics[op] = {
    duration: new Trend(`op_${op}_ms`, true),
    requests: new Counter(`op_${op}_reqs`),
    errors:   new Counter(`op_${op}_errs`),
  };
}

/**
 * Record a completed operation's timing and error state.
 * Called from request.js after each request.
 */
export function recordOp(opName, durationMs, hasError) {
  const m = opMetrics[opName];
  if (!m) return;
  m.duration.add(durationMs);
  m.requests.add(1);
  if (hasError) m.errors.add(1);
}

/** Expose the loaded config so main.js can import it without re-parsing. */
export const endpointConfig = _cfg;

// ── Aggregated request-level metrics ─────────────────────────────────────────

/** HTTP status class counters (2xx, 3xx, 4xx, 5xx). */
export const statusCounters = {
  s2xx: new Counter('http_status_2xx'),
  s3xx: new Counter('http_status_3xx'),
  s4xx: new Counter('http_status_4xx'),
  s5xx: new Counter('http_status_5xx'),
};

/**
 * Latency histogram bucket counters (upper edge in ms, exclusive).
 * Buckets: ≤50ms, ≤200ms, ≤500ms, ≤1s, ≤2s, ≤5s, >5s
 */
export const LAT_BUCKETS = [50, 200, 500, 1000, 2000, 5000];
export const latBucketCounters = {
  b50:   new Counter('lat_bucket_50'),
  b200:  new Counter('lat_bucket_200'),
  b500:  new Counter('lat_bucket_500'),
  b1000: new Counter('lat_bucket_1000'),
  b2000: new Counter('lat_bucket_2000'),
  b5000: new Counter('lat_bucket_5000'),
  binf:  new Counter('lat_bucket_inf'),
};

/**
 * Apdex counters.
 * T (satisfying threshold) is configurable via APDEX_T env var (default 500ms).
 *   Satisfied:  duration ≤ T
 *   Tolerating: T < duration ≤ 4T
 *   Frustrated: duration > 4T
 * Score = (satisfied + tolerating × 0.5) / total
 */
export const APDEX_T = parseInt(__ENV.APDEX_T || '500', 10) || 500;
export const apdexCounters = {
  satisfied:  new Counter('apdex_satisfied'),
  tolerating: new Counter('apdex_tolerating'),
  frustrated: new Counter('apdex_frustrated'),
};

/**
 * Connection reuse rate.
 * 1 = existing TCP connection was reused (connecting time = 0)
 * 0 = new TCP connection was established
 */
export const connReuseRate = new Rate('connection_reused');

/**
 * Record per-request aggregated metrics: status class, histogram bucket,
 * Apdex category, and connection reuse.
 *
 * @param {number} statusCode   - HTTP response status code
 * @param {number} durationMs   - Total request duration in ms
 * @param {number} connectingMs - TCP connecting time in ms; 0 = reused connection
 */
export function recordRequestExtras(statusCode, durationMs, connectingMs) {
  // Status class counters
  const sc = Math.floor((statusCode || 0) / 100);
  if      (sc === 2) statusCounters.s2xx.add(1);
  else if (sc === 3) statusCounters.s3xx.add(1);
  else if (sc === 4) statusCounters.s4xx.add(1);
  else if (sc === 5) statusCounters.s5xx.add(1);

  // Latency histogram bucket (exclusive upper edge)
  const ms = durationMs || 0;
  if      (ms <=   50) latBucketCounters.b50.add(1);
  else if (ms <=  200) latBucketCounters.b200.add(1);
  else if (ms <=  500) latBucketCounters.b500.add(1);
  else if (ms <= 1000) latBucketCounters.b1000.add(1);
  else if (ms <= 2000) latBucketCounters.b2000.add(1);
  else if (ms <= 5000) latBucketCounters.b5000.add(1);
  else                 latBucketCounters.binf.add(1);

  // Apdex category
  if      (ms <= APDEX_T)       apdexCounters.satisfied.add(1);
  else if (ms <= 4 * APDEX_T)  apdexCounters.tolerating.add(1);
  else                          apdexCounters.frustrated.add(1);

  // Connection reuse: connecting === 0 means an existing connection was reused
  connReuseRate.add(connectingMs === 0 ? 1 : 0);
}
