/**
 * Shared check predicates for use with k6's check().
 */

export const statusIs200 = (r) => r.status === 200;

export const noGqlErrors = (r) => {
  try {
    const body = JSON.parse(r.body);
    return !body.errors || body.errors.length === 0;
  } catch (_) {
    return false;
  }
};

export const hasData = (r) => {
  try {
    const body = JSON.parse(r.body);
    return body.data !== null && body.data !== undefined;
  } catch (_) {
    return false;
  }
};

/**
 * Returns a checks object keyed by operation name.
 * Suitable for passing directly to k6's check().
 */
export function checksFor(opName) {
  return {
    [`${opName}: status 200`]: statusIs200,
    [`${opName}: no graphql errors`]: noGqlErrors,
    [`${opName}: has data`]: hasData,
  };
}
