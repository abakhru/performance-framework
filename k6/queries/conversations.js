import { gqlRequest } from '../lib/graphql.js';

const GET_CONVERSATIONS = `
query GetConversations($filter: ConversationFilterInput) {
  conversations(filter: $filter) {
    id
    title
    summary
    metadata
    __typename
  }
}
`;

const GET_CONVERSATION = `
query GetConversation($id: ID!) {
  conversation(id: $id) {
    id
    title
    summary
    metadata
    messages {
      id
      parts {
        ... on TextPart {
          id
          text
          __typename
        }
        ... on ToolCallPart {
          id
          toolCall {
            id
            name
            arguments
            result
            error
            status
            __typename
          }
          __typename
        }
        __typename
      }
      profile {
        id
        type
        name
        avatarUrl
        __typename
      }
      timestamp
      conversationId
      parentId
      metadata
      __typename
    }
    __typename
  }
}
`;

const CREATE_CONVERSATION = `
mutation CreateConversation($input: CreateConversationInput!) {
  createConversation(input: $input) {
    id
    title
    summary
    metadata
    __typename
  }
}
`;

const DELETE_CONVERSATION = `
mutation DeleteConversation($id: ID!) {
  deleteConversation(id: $id) {
    id
    __typename
  }
}
`;

export function getConversations(url, token, filter = {}) {
  return gqlRequest(url, token, GET_CONVERSATIONS, { filter }, 'GetConversations');
}

export function getConversation(url, token, id) {
  return gqlRequest(url, token, GET_CONVERSATION, { id }, 'GetConversation');
}

export function createConversation(url, token, input) {
  return gqlRequest(url, token, CREATE_CONVERSATION, { input }, 'CreateConversation');
}

export function deleteConversation(url, token, id) {
  return gqlRequest(url, token, DELETE_CONVERSATION, { id }, 'DeleteConversation');
}
