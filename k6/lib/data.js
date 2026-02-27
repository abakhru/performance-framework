/**
 * Data-driven load injection — loads CSV files from the data/ directory
 * into k6 SharedArrays for memory-efficient cross-VU data sharing.
 *
 * Usage in endpoints.json:
 *   "data_file": "users",
 *   "variables_from_data_file": { "userId": "id", "q": "searchTerm" }
 *
 * The CSV file must be at data/<name>.csv relative to the repo root.
 * k6 open() reads it at init time; it is parsed into an array of objects.
 */

import { SharedArray } from 'k6/data';

// Cache of loaded SharedArrays, keyed by filename stem
const _cache = {};

/**
 * Load a CSV data file and return a SharedArray of row objects.
 * Calls must happen at init time (module level or in a top-level block).
 *
 * @param {string} name - File stem (without .csv), e.g. "users"
 * @returns {SharedArray} Array of objects with column-name keys
 */
export function loadDataFile(name) {
  if (_cache[name]) return _cache[name];
  const arr = new SharedArray(name, function () {
    const raw = open(`../../data/${name}.csv`);
    return _parseCsv(raw);
  });
  _cache[name] = arr;
  return arr;
}

/**
 * Pick a row from a data array for the current VU iteration.
 * Uses modular arithmetic for even distribution across VUs.
 *
 * @param {SharedArray} arr - Data array from loadDataFile()
 * @param {number} vuId     - __VU identifier
 * @param {number} iter     - __ITER identifier
 * @returns {Object} One row as a plain object
 */
export function pickRow(arr, vuId, iter) {
  if (!arr || arr.length === 0) return {};
  const idx = (vuId * 1000 + iter) % arr.length;
  return arr[idx];
}

// ── Internal CSV parser ───────────────────────────────────────────────────────

function _parseCsv(text) {
  const lines = text.split('\n').map(l => l.trim()).filter(l => l.length > 0);
  if (lines.length < 2) return [];
  const headers = _splitCsvRow(lines[0]);
  const rows = [];
  for (let i = 1; i < lines.length; i++) {
    const values = _splitCsvRow(lines[i]);
    const obj = {};
    for (let j = 0; j < headers.length; j++) {
      obj[headers[j]] = values[j] !== undefined ? values[j] : '';
    }
    rows.push(obj);
  }
  return rows;
}

function _splitCsvRow(line) {
  // RFC 4180 CSV split — handles quoted fields and "" escape sequences
  const result = [];
  let current = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') {
        // Escaped double-quote inside a quoted field: "" → "
        current += '"';
        i++;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (ch === ',' && !inQuotes) {
      result.push(current.trim());
      current = '';
    } else {
      current += ch;
    }
  }
  result.push(current.trim());
  return result;
}
