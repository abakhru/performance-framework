import { gqlRequest } from '../lib/graphql.js';

const GET_KNOWLEDGE_BASES = `
query GetKnowledgeBases($filter: KnowledgeBaseFilterInput) {
  knowledgeBases(filter: $filter) {
    id
    name
    description
    status
    config
    metadata
    documentCount
    insertedAt
    updatedAt
    __typename
  }
}
`;

const QUERY_KNOWLEDGE_BASE = `
query QueryKnowledgeBase($id: ID!, $query: String!, $mode: QueryMode, $topK: Int) {
  queryKnowledgeBase(id: $id, query: $query, mode: $mode, topK: $topK) {
    content
    sourceDocuments
    metadata
    __typename
  }
}
`;

const GET_KNOWLEDGE_GRAPH = `
query GetKnowledgeGraph($knowledgeBaseId: ID!, $limit: Int, $maxDepth: Int, $label: String) {
  knowledgeGraph(
    knowledgeBaseId: $knowledgeBaseId
    limit: $limit
    maxDepth: $maxDepth
    label: $label
  ) {
    entities {
      id
      type
      name
      properties
      importanceScore
      __typename
    }
    relationships {
      id
      source
      target
      type
      properties
      weight
      __typename
    }
    stats {
      totalEntities
      totalRelationships
      totalDocuments
      totalChunks
      entityTypes
      relationshipTypes
      __typename
    }
    __typename
  }
}
`;

const CREATE_KNOWLEDGE_BASE = `
mutation CreateKnowledgeBase($input: CreateKnowledgeBaseInput!) {
  createKnowledgeBase(input: $input) {
    id
    name
    description
    status
    config
    metadata
    documentCount
    insertedAt
    updatedAt
    __typename
  }
}
`;

const DELETE_KNOWLEDGE_BASE = `
mutation DeleteKnowledgeBase($id: ID!) {
  deleteKnowledgeBase(id: $id) {
    id
    __typename
  }
}
`;

export function getKnowledgeBases(url, token, filter = {}) {
  return gqlRequest(url, token, GET_KNOWLEDGE_BASES, { filter }, 'GetKnowledgeBases');
}

export function searchKnowledgeBases(url, token, nameContains) {
  return gqlRequest(
    url,
    token,
    GET_KNOWLEDGE_BASES,
    { filter: { nameContains } },
    'SearchKnowledgeBases'
  );
}

export function queryKnowledgeBase(url, token, id, query, mode = 'HYBRID', topK = 10) {
  return gqlRequest(
    url,
    token,
    QUERY_KNOWLEDGE_BASE,
    { id, query, mode, topK },
    'QueryKnowledgeBase'
  );
}

export function getKnowledgeGraph(url, token, knowledgeBaseId, limit = 100, maxDepth = 3, label = '*') {
  return gqlRequest(
    url,
    token,
    GET_KNOWLEDGE_GRAPH,
    { knowledgeBaseId, limit, maxDepth, label },
    'GetKnowledgeGraph'
  );
}

export function createKnowledgeBase(url, token, input) {
  return gqlRequest(url, token, CREATE_KNOWLEDGE_BASE, { input }, 'CreateKnowledgeBase');
}

export function deleteKnowledgeBase(url, token, id) {
  return gqlRequest(url, token, DELETE_KNOWLEDGE_BASE, { id }, 'DeleteKnowledgeBase');
}
