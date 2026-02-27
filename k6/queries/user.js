import { gqlRequest } from '../lib/graphql.js';

const USER_DETAILS = `
query {
  userDetails {
    details
  }
}
`;

const GET_USER_DETAILS_FOR_SESSION = `
query GetUserDetailsForSession {
  userDetails {
    details
    features {
      gitlabToolsEnabled
      customAgents
      secretsManagementEnabled
      devoAssistantEnabled
      devoToolsEnabled
      knowledgebasesViewOnly
      knowledgebasesEdit
      mcpManagement
      workflowsManage
      webhooksEnabled
      workflowBuilderEnabled
      rbacEnabled
      __typename
    }
    roles
    __typename
  }
}
`;

export function userDetails(url, token) {
  return gqlRequest(url, token, USER_DETAILS, {}, 'userDetails');
}

export function getUserDetailsForSession(url, token) {
  return gqlRequest(url, token, GET_USER_DETAILS_FOR_SESSION, {}, 'GetUserDetailsForSession');
}
