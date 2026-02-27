/**
 * k6 load profile factory.
 *
 * Select a profile via LOAD_PROFILE env var (default: smoke).
 * All numeric parameters are configurable via env vars.
 *
 * Profiles:
 *   smoke  — 2 VUs, 30 s — quick sanity / CI gate
 *   ramp   — 0 → VUS, hold, ramp back — standard load ramp
 *   soak   — sustained load for SOAK_DURATION — endurance test
 *   stress — escalating stages to STRESS_VUS — find breaking point
 *   spike  — instant spike to SPIKE_VUS for SPIKE_DURATION — resilience check
 *
 * Thresholds (all configurable via env vars):
 *   THRESHOLD_ERROR_RATE   max error rate  (default: 0.01 = 1%)
 *   THRESHOLD_P95_MS       p95 latency ms  (default: 5000)
 *   THRESHOLD_P99_MS       p99 latency ms  (optional, disabled by default)
 *   THRESHOLD_ABORT        abort on threshold breach (default: false)
 */

const LOAD_PROFILE  = __ENV.LOAD_PROFILE   || 'smoke';
const VUS           = parseInt(__ENV.VUS          || '10', 10);
const DURATION      = __ENV.DURATION              || '60s';
const RAMP_DURATION = __ENV.RAMP_DURATION         || '30s';
const SOAK_DURATION = __ENV.SOAK_DURATION         || '10m';
const STRESS_VUS    = parseInt(__ENV.STRESS_VUS   || '50', 10);
const SPIKE_VUS     = parseInt(__ENV.SPIKE_VUS    || '100', 10);
const SPIKE_DURATION= __ENV.SPIKE_DURATION        || '30s';

// Threshold configuration — use || fallback to guard against NaN from invalid env vars
const ERR_RATE = parseFloat(__ENV.THRESHOLD_ERROR_RATE) || 0.01;
const P95_MS   = parseInt(__ENV.THRESHOLD_P95_MS, 10)   || 5000;
const P99_MS   = __ENV.THRESHOLD_P99_MS ? (parseInt(__ENV.THRESHOLD_P99_MS, 10) || null) : null;
const ABORT    = __ENV.THRESHOLD_ABORT === 'true';

function buildThresholds() {
  const t = {
    http_req_failed:  [{ threshold: `rate<${ERR_RATE}`, abortOnFail: ABORT }],
    http_req_duration:[{ threshold: `p(95)<${P95_MS}`,  abortOnFail: ABORT }],
  };
  if (P99_MS) {
    t.http_req_duration.push({ threshold: `p(99)<${P99_MS}`, abortOnFail: ABORT });
  }
  return t;
}

const thresholds = buildThresholds();

const profiles = {
  // ── Smoke: 2 VUs, 30s — minimal sanity check ──────────────────────────────
  smoke: {
    vus: 2,
    duration: '30s',
    thresholds,
  },

  // ── Ramp: 0→N VUs, hold, ramp back ────────────────────────────────────────
  ramp: {
    stages: [
      { duration: RAMP_DURATION, target: VUS },
      { duration: DURATION,      target: VUS },
      { duration: RAMP_DURATION, target: 0   },
    ],
    thresholds,
  },

  // ── Soak: sustained load for extended period (endurance/memory leak test) ─
  soak: {
    stages: [
      { duration: RAMP_DURATION, target: VUS },
      { duration: SOAK_DURATION, target: VUS },
      { duration: RAMP_DURATION, target: 0   },
    ],
    thresholds,
  },

  // ── Stress: step up to find the breaking point ────────────────────────────
  stress: {
    stages: [
      { duration: RAMP_DURATION, target: Math.ceil(STRESS_VUS * 0.25) },
      { duration: DURATION,      target: Math.ceil(STRESS_VUS * 0.25) },
      { duration: RAMP_DURATION, target: Math.ceil(STRESS_VUS * 0.50) },
      { duration: DURATION,      target: Math.ceil(STRESS_VUS * 0.50) },
      { duration: RAMP_DURATION, target: Math.ceil(STRESS_VUS * 0.75) },
      { duration: DURATION,      target: Math.ceil(STRESS_VUS * 0.75) },
      { duration: RAMP_DURATION, target: STRESS_VUS },
      { duration: DURATION,      target: STRESS_VUS },
      { duration: RAMP_DURATION, target: 0 },
    ],
    thresholds,
  },

  // ── Spike: instant burst to simulate sudden traffic surge ─────────────────
  spike: {
    stages: [
      { duration: '10s',          target: VUS       },  // warm-up
      { duration: '10s',          target: SPIKE_VUS },  // spike up
      { duration: SPIKE_DURATION, target: SPIKE_VUS },  // hold spike
      { duration: '10s',          target: VUS       },  // recover
      { duration: DURATION,       target: VUS       },  // steady state
      { duration: RAMP_DURATION,  target: 0         },  // ramp down
    ],
    thresholds,
  },
};

export function getOptions() {
  const profile = profiles[LOAD_PROFILE];
  if (!profile) {
    throw new Error(
      `Unknown LOAD_PROFILE "${LOAD_PROFILE}". ` +
      `Valid profiles: ${Object.keys(profiles).join(', ')}.`
    );
  }
  return profile;
}
