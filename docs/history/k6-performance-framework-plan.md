# Plan: k6 Performance Test Framework for Matrix/Strike48

## Context

Build a k6-based performance testing framework for the Matrix/Strike48 APIs. The Postman collection uses a single GraphQL endpoint (`/api/v1alpha`) for all calls. There are no actual HTTP GET requests — read operations are **GraphQL queries** (vs mutations for writes). The framework targets these read/query operations, with configurable URL, dynamic auth via Keycloak login, configurable load profiles, and test data provisioned in the k6 `setup()` phase.

## GraphQL Queries to Test (14 total)

| Operation | GraphQL Query | Folder |
|---|---|---|
| List all agents/personas | `ListAllAgents` | Persona |
| Get all tools | `GetTools` | Persona |
| List job configs for a persona | `ListJobConfigs` | Jobs |
| List job instances for a persona | `ListAllJobInstances` | Jobs |
| Get all knowledge bases | `GetKnowledgeBases` | Knowledge |
| Search knowledge bases | `GetKnowledgeBases` (with filter) | Knowledge |
| Query inside a knowledge base | `QueryKnowledgeBase` | Knowledge |
| Fetch knowledge base graph | `GetKnowledgeGraph` | Knowledge |
| List conversations | `GetConversations` | Conversations |
| Get conversation by ID | `GetConversation` | Conversations |
| Get user details | `userDetails` | Auth/User |
| Get user session details | `GetUserDetailsForSession` | Auth/User |
| List documents | `ListDocuments` | Documents |
| Get document by ID | `GetDocument` | Documents |

## Directory Structure

```
performance-framework/
├── k6/
│   ├── config/
│   │   └── options.js           # Load profile definitions (smoke, ramp)
│   ├── lib/
│   │   ├── auth.js              # Keycloak login helper → returns Bearer token
│   │   ├── graphql.js           # GraphQL POST helper with checks
│   │   └── checks.js            # Shared check functions (status 200, no errors)
│   ├── queries/
│   │   ├── agents.js            # ListAllAgents, GetTools
│   │   ├── jobs.js              # ListJobConfigs, ListAllJobInstances
│   │   ├── knowledge.js         # GetKnowledgeBases, QueryKnowledgeBase, GetKnowledgeGraph
│   │   ├── conversations.js     # GetConversations, GetConversation
│   │   ├── documents.js         # ListDocuments, GetDocument
│   │   └── user.js              # userDetails, GetUserDetailsForSession
│   ├── scenarios/
│   │   └── read-operations.js   # Combines all query scenarios
│   └── main.js                  # Entry point: setup(), default(), teardown()
├── .env.example                 # Template showing all env var names
└── README.md                    # How to install k6 and run tests
```

## Configuration (Environment Variables)

```bash
# Required
BASE_URL=https://ai-beta-us-east-2.devo.cloud   # target host
AUTH_HOST=https://...                            # Keycloak host
AUTH_REALM=master                               # Keycloak realm
AUTH_CLIENT_ID=...
AUTH_USERNAME=...
AUTH_PASSWORD=...

# Load profile
LOAD_PROFILE=smoke          # "smoke" or "ramp" (default: smoke)
VUS=10                      # max virtual users (default: 10)
DURATION=30s                # hold duration (default: 30s)
RAMP_DURATION=30s           # ramp up/down duration for "ramp" profile
```

## Load Profiles (`k6/config/options.js`)

**Smoke** (`LOAD_PROFILE=smoke`):
- 2 VUs, 30s duration, no ramping — quick sanity check

**Ramp** (`LOAD_PROFILE=ramp`):
- Ramp 0 → N VUs over `RAMP_DURATION`, hold for `DURATION`, ramp back to 0

Both profiles include thresholds:
- `http_req_failed < 1%`
- `http_req_duration p(95) < 5000ms`

## Auth Flow (`k6/lib/auth.js`)

`setup()` in `main.js` calls `login()`:
1. POST to `${AUTH_HOST}/realms/${AUTH_REALM}/protocol/openid-connect/token`
2. Form-urlencoded with `grant_type=password`, client_id, username, password
3. Returns `access_token` → passed to all VU iterations as `data.token`

## Test Data Setup (`main.js` `setup()`)

After auth, `setup()` provisions test fixtures using mutation calls:
1. Create an Agent → store `agentId`
2. Create a Conversation (linked to agent) → store `conversationId`
3. Create a Knowledge Base → store `knowledgeBaseId`
4. Upload a small test document → store `documentId`

All IDs stored in the `data` object returned from `setup()`, consumed by VU iterations. `teardown()` deletes created resources.

## GraphQL Helper (`k6/lib/graphql.js`)

```js
export function gqlQuery(url, token, query, variables = {}) {
  const res = http.post(url, JSON.stringify({ query, variables }), {
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
  });
  check(res, {
    'status 200': r => r.status === 200,
    'no graphql errors': r => !JSON.parse(r.body).errors,
  });
  return res;
}
```

## Scenario Structure (`k6/scenarios/read-operations.js`)

Each query function is imported and called in a `group()` block:

```js
group('agents', () => { listAllAgents(...); getTools(...); });
group('jobs', () => { listJobConfigs(...); listJobInstances(...); });
group('knowledge', () => { ... });
group('conversations', () => { ... });
group('documents', () => { ... });
group('user', () => { ... });
```

Groups enable per-group metrics in k6 output.

## Critical Files to Create

1. `k6/main.js` — entry point with setup/default/teardown
2. `k6/config/options.js` — smoke/ramp load profile factory
3. `k6/lib/auth.js` — Keycloak token fetch
4. `k6/lib/graphql.js` — reusable GQL POST helper
5. `k6/lib/checks.js` — shared check predicates
6. `k6/queries/agents.js` — ListAllAgents, GetTools
7. `k6/queries/jobs.js` — ListJobConfigs, ListAllJobInstances
8. `k6/queries/knowledge.js` — GetKnowledgeBases, QueryKnowledgeBase, GetKnowledgeGraph
9. `k6/queries/conversations.js` — GetConversations, GetConversation
10. `k6/queries/documents.js` — ListDocuments, GetDocument
11. `k6/queries/user.js` — userDetails, GetUserDetailsForSession
12. `k6/scenarios/read-operations.js` — combines all queries
13. `.env.example` — env var template
14. `README.md` — usage instructions

## Verification

```bash
# Install k6
brew install k6

# Smoke test (no real load)
k6 run --env BASE_URL=https://... --env AUTH_HOST=... \
        --env AUTH_USERNAME=... --env AUTH_PASSWORD=... \
        --env LOAD_PROFILE=smoke k6/main.js

# Ramp test
k6 run --env LOAD_PROFILE=ramp --env VUS=20 --env DURATION=60s \
        ... k6/main.js

# Expected: all checks pass, thresholds met, groups appear in summary
```
