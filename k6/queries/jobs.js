import { gqlRequest } from '../lib/graphql.js';

const LIST_JOB_CONFIGS = `
query ListJobConfigs($agentId: ID, $limit: Int) {
  listJobConfigs(agentId: $agentId, limit: $limit) {
    id
    name
    description
    enabled
    cronExpr
    toolsApproved
    agent {
      id
      name
      __typename
    }
    __typename
  }
}
`;

const LIST_ALL_JOB_INSTANCES = `
query ListAllJobInstances($agentId: ID, $jobConfigId: ID, $limit: Int, $status: String) {
  listAllJobInstances(
    agentId: $agentId
    jobConfigId: $jobConfigId
    limit: $limit
    status: $status
  ) {
    id
    startedAt
    updatedAt
    status
    errorMessage
    isRead
    agent {
      id
      name
      __typename
    }
    conversation {
      id
      __typename
    }
    jobConfig {
      id
      name
      description
      __typename
    }
    __typename
  }
}
`;

export function listJobConfigs(url, token, agentId, limit = 1000) {
  return gqlRequest(url, token, LIST_JOB_CONFIGS, { agentId, limit }, 'ListJobConfigs');
}

export function listAllJobInstances(url, token, agentId, limit = 1000) {
  return gqlRequest(url, token, LIST_ALL_JOB_INSTANCES, { agentId, limit }, 'ListAllJobInstances');
}
