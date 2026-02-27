import { group, sleep } from 'k6';

import { listAllAgents, getTools } from '../queries/agents.js';
import { listJobConfigs, listAllJobInstances } from '../queries/jobs.js';
import {
  getKnowledgeBases,
  searchKnowledgeBases,
  queryKnowledgeBase,
  getKnowledgeGraph,
} from '../queries/knowledge.js';
import { getConversations, getConversation } from '../queries/conversations.js';
import { listDocuments, getDocument } from '../queries/documents.js';
import { userDetails, getUserDetailsForSession } from '../queries/user.js';

/**
 * Executes all read/query operations grouped by domain.
 *
 * @param {string} url            - GraphQL endpoint URL
 * @param {string} token          - Bearer token
 * @param {Object} testData       - IDs provisioned in setup()
 * @param {string} testData.agentId
 * @param {string} testData.conversationId
 * @param {string} testData.knowledgeBaseId
 * @param {string} testData.documentConversationId
 * @param {string} testData.documentId
 */
export function runReadOperations(url, token, testData) {
  group('agents', () => {
    listAllAgents(url, token);
    getTools(url, token);
  });

  sleep(0.5);

  group('jobs', () => {
    listJobConfigs(url, token, testData.agentId);
    listAllJobInstances(url, token, testData.agentId);
  });

  sleep(0.5);

  group('knowledge', () => {
    getKnowledgeBases(url, token);
    searchKnowledgeBases(url, token, 'perf-test');
    if (testData.knowledgeBaseId) {
      queryKnowledgeBase(url, token, testData.knowledgeBaseId, 'test query');
      getKnowledgeGraph(url, token, testData.knowledgeBaseId);
    }
  });

  sleep(0.5);

  group('conversations', () => {
    getConversations(url, token);
    if (testData.conversationId) {
      getConversation(url, token, testData.conversationId);
    }
  });

  sleep(0.5);

  group('documents', () => {
    listDocuments(url, token);
    if (testData.documentConversationId && testData.documentId) {
      getDocument(url, token, testData.documentConversationId, testData.documentId);
    }
  });

  sleep(0.5);

  group('user', () => {
    userDetails(url, token);
    getUserDetailsForSession(url, token);
  });
}
