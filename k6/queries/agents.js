import { gqlRequest } from '../lib/graphql.js';

const LIST_ALL_AGENTS = `
query ListAllAgents {
  templateAgents: listAgents(first: 1000, filter: {isTemplate: true}) {
    edges {
      cursor
      node {
        id
        name
        description
        isPublic
        isTemplate
        isEnabled
        systemMessage
        tools
        knowledgeBaseIds
        knowledgeBases {
          id
          name
          description
          status
          documentCount
          __typename
        }
        __typename
      }
      __typename
    }
    pageInfo {
      hasNextPage
      hasPreviousPage
      startCursor
      endCursor
      __typename
    }
    __typename
  }
  customAgents: listAgents(first: 1000) {
    edges {
      cursor
      node {
        id
        name
        description
        isPublic
        isTemplate
        isEnabled
        systemMessage
        tools
        knowledgeBaseIds
        knowledgeBases {
          id
          name
          description
          status
          documentCount
          __typename
        }
        __typename
      }
      __typename
    }
    pageInfo {
      hasNextPage
      hasPreviousPage
      startCursor
      endCursor
      __typename
    }
    __typename
  }
}
`;

const GET_TOOLS = `
query GetTools {
  tools {
    name
    description
    enabled
    category
    __typename
  }
}
`;

const CREATE_AGENT = `
mutation CreateAgent($input: AgentInput!) {
  createAgent(input: $input) {
    id
    model
    systemMessage
    context
    __typename
  }
}
`;

const DELETE_AGENT = `
mutation DeleteAgent($id: ID!) {
  deleteAgent(id: $id) {
    id
    __typename
  }
}
`;

export function listAllAgents(url, token) {
  return gqlRequest(url, token, LIST_ALL_AGENTS, {}, 'ListAllAgents');
}

export function getTools(url, token) {
  return gqlRequest(url, token, GET_TOOLS, {}, 'GetTools');
}

export function createAgent(url, token, input) {
  return gqlRequest(url, token, CREATE_AGENT, { input }, 'CreateAgent');
}

export function deleteAgent(url, token, id) {
  return gqlRequest(url, token, DELETE_AGENT, { id }, 'DeleteAgent');
}
