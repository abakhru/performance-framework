import { gqlRequest } from '../lib/graphql.js';

const LIST_DOCUMENTS = `
query ListDocuments($first: Int, $after: String, $last: Int, $before: String, $filter: ListDocumentsFilter) {
  listDocuments(
    first: $first
    after: $after
    last: $last
    before: $before
    filter: $filter
  ) {
    edges {
      cursor
      node {
        id
        title
        type
        conversationId
        timestamp
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

const GET_DOCUMENT = `
query GetDocument($conversationId: ID!, $documentId: ID!) {
  document(conversationId: $conversationId, documentId: $documentId) {
    id
    title
    type
    content
    timestamp
    __typename
  }
}
`;

export function listDocuments(url, token, first = 1000, filter = {}) {
  return gqlRequest(url, token, LIST_DOCUMENTS, { first, filter }, 'ListDocuments');
}

export function listDocumentsByAgent(url, token, agentId, first = 1000) {
  return gqlRequest(
    url,
    token,
    LIST_DOCUMENTS,
    { first, filter: { agentId } },
    'ListDocumentsByAgent'
  );
}

export function getDocument(url, token, conversationId, documentId) {
  return gqlRequest(url, token, GET_DOCUMENT, { conversationId, documentId }, 'GetDocument');
}
