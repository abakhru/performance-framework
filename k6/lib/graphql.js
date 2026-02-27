import http from 'k6/http';
import { check } from 'k6';
import { recordOp } from './metrics.js';

/**
 * Sends a GraphQL request (query or mutation) and asserts basic checks.
 *
 * @param {string} url       - Full GraphQL endpoint URL
 * @param {string} token     - Bearer token
 * @param {string} query     - GraphQL query/mutation string
 * @param {Object} variables - GraphQL variables (optional)
 * @param {string} opName    - Operation name used for check labels and metrics
 * @returns {http.Response}
 */
export function gqlRequest(url, token, query, variables = {}, opName = '') {
  const label = opName ? `${opName}: ` : '';

  const res = http.post(
    url,
    JSON.stringify({ query, variables }),
    {
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
    }
  );

  const hasGqlErrors = (() => {
    try {
      const body = JSON.parse(res.body);
      return !!(body.errors && body.errors.length > 0);
    } catch (_) {
      return true;
    }
  })();

  check(res, {
    [`${label}status 200`]: (r) => r.status === 200,
    [`${label}no graphql errors`]: () => !hasGqlErrors,
    [`${label}has data`]: (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.data !== null && body.data !== undefined;
      } catch (_) {
        return false;
      }
    },
  });

  if (opName) {
    recordOp(opName, res.timings.duration, hasGqlErrors);
  }

  return res;
}

/**
 * Parse JSON response body, returning null on parse failure.
 */
export function parseBody(res) {
  try {
    return JSON.parse(res.body);
  } catch (_) {
    return null;
  }
}
