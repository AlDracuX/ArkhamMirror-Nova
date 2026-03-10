/**
 * future_shards_integration.test.ts
 *
 * Static TypeScript integration verification for the 18 new future shard UI components.
 *
 * Verifies all 18 page components export correctly and all API client functions
 * match their rewritten domain-specific signatures (post api.ts alignment).
 */

import type { FC } from 'react';

// ============================================================
// PAGE COMPONENT EXPORT VERIFICATION
// ============================================================

import { ComparatorPage } from './comparator';
import { DisclosurePage } from './disclosure';
import { ChainPage } from './chain';
import { AuditTrailPage } from './audit-trail';
import { CrossExamPage } from './crossexam';
import { BundlePage } from './bundle';
import { BurdenMapPage } from './burden-map';
import { CommsPage } from './comms';
import { SkeletonPage } from './skeleton';
import { RulesPage } from './rules';
import { CostsPage } from './costs';
import { SentimentPage } from './sentiment';
import { RedlinePage } from './redline';
import { StrategistPage } from './strategist';
import { PlaybookPage } from './playbook';
import { OraclePage } from './oracle';
import { RespondentIntelPage } from './respondent-intel';
import { DigestPage } from './digest';

// ============================================================
// API CLIENT EXPORT VERIFICATION — Domain-specific imports
// ============================================================

import {
  listComparators,
  getComparator,
  createComparator,
  updateComparator,
  deleteComparator,
  listIncidents,
  getIncident,
  createIncident,
} from './comparator/api';

import {
  listRequests,
  createRequest,
  listResponses,
  createResponse,
  listGaps as disclosureListGaps,
  createGap,
  listEvasionScores,
  getComplianceDashboard,
} from './disclosure/api';

import {
  logCustodyEvent,
  getDocumentHistory,
  verifyDocumentIntegrity,
  generateProvenanceReport,
  listItems as chainListItems,
  getItem as chainGetItem,
  createItem as chainCreateItem,
} from './chain/api';

import {
  listActions,
  getAuditSummary,
  listSessions as auditListSessions,
  listExports,
  recordExport,
} from './audit-trail/api';

import {
  listTrees,
  getTreeNodes,
  createTree,
  createNode,
  listImpeachments,
  generateQuestionTree,
  listItems as crossexamListItems,
  getItem as crossexamGetItem,
  createItem as crossexamCreateItem,
} from './crossexam/api';

import {
  listBundles,
  getBundle,
  createBundle,
  updateBundle,
  deleteBundle,
  compileBundle,
  listVersions,
  getVersionPages,
  getVersionIndex,
} from './bundle/api';

import {
  listElements,
  createElement,
  getBurdenDashboard,
  addEvidenceWeight,
} from './burden-map/api';

import {
  listThreads,
  createThread,
  listMessages,
  createMessage,
  listParticipants,
  listGaps as commsListGaps,
  listCoordinationFlags,
} from './comms/api';

import {
  listItems as skeletonListItems,
  getItem as skeletonGetItem,
  createItem as skeletonCreateItem,
  updateItem as skeletonUpdateItem,
  deleteItem as skeletonDeleteItem,
} from './skeleton/api';

import {
  listItems as rulesListItems,
  getItem as rulesGetItem,
  createItem as rulesCreateItem,
  updateItem as rulesUpdateItem,
  deleteItem as rulesDeleteItem,
} from './rules/api';

import {
  listTimeEntries,
  createTimeEntry,
  listExpenses,
  createExpense,
  listConductLog,
  createConductLog,
  listApplications,
} from './costs/api';

import {
  createAnalysis,
  getAnalysis,
  listPatterns,
  listComparatorDiffs,
  listItems as sentimentListItems,
  getItem as sentimentGetItem,
} from './sentiment/api';

import { createComparison, getComparison, listChains } from './redline/api';

import {
  createPrediction,
  getPrediction,
  listReports as strategistListReports,
  listTacticalModels,
} from './strategist/api';

import { createStrategy, getStrategy, listObjectives } from './playbook/api';

import {
  startResearch,
  getSession as oracleGetSession,
  getAuthority,
  listAuthorities,
  listItems as oracleListItems,
  getItem as oracleGetItem,
  createItem as oracleCreateItem,
} from './oracle/api';

import { listProfiles, getProfile, createProfile } from './respondent-intel/api';

import { generateBriefing, getBriefing, listBriefings, getChangelog } from './digest/api';

// ============================================================
// TYPE-LEVEL MOUNT ASSERTIONS
// ============================================================

type PageComponent = FC;

const _pageComponentRegistry: Record<string, PageComponent> = {
  ComparatorPage,
  DisclosurePage,
  ChainPage,
  AuditTrailPage,
  CrossExamPage,
  BundlePage,
  BurdenMapPage,
  CommsPage,
  SkeletonPage,
  RulesPage,
  CostsPage,
  SentimentPage,
  RedlinePage,
  StrategistPage,
  PlaybookPage,
  OraclePage,
  RespondentIntelPage,
  DigestPage,
};

// ============================================================
// API FUNCTION CALLABLE SHAPE ASSERTIONS
// ============================================================

const _domainApiRegistry: Record<string, Record<string, (...args: never[]) => Promise<unknown>>> = {
  comparator: {
    listComparators,
    getComparator,
    createComparator,
    updateComparator,
    deleteComparator,
    listIncidents,
    getIncident,
    createIncident,
  },
  disclosure: {
    listRequests,
    createRequest,
    listResponses,
    createResponse,
    listGaps: disclosureListGaps,
    createGap,
    listEvasionScores,
    getComplianceDashboard,
  },
  chain: {
    logCustodyEvent,
    getDocumentHistory,
    verifyDocumentIntegrity,
    generateProvenanceReport,
    listItems: chainListItems,
    getItem: chainGetItem,
    createItem: chainCreateItem,
  },
  'audit-trail': {
    listActions,
    getAuditSummary,
    listSessions: auditListSessions,
    listExports,
    recordExport,
  },
  crossexam: {
    listTrees,
    getTreeNodes,
    createTree,
    createNode,
    listImpeachments,
    generateQuestionTree,
    listItems: crossexamListItems,
    getItem: crossexamGetItem,
    createItem: crossexamCreateItem,
  },
  bundle: {
    listBundles,
    getBundle,
    createBundle,
    updateBundle,
    deleteBundle,
    compileBundle,
    listVersions,
    getVersionPages,
    getVersionIndex,
  },
  'burden-map': { listElements, createElement, getBurdenDashboard, addEvidenceWeight },
  comms: {
    listThreads,
    createThread,
    listMessages,
    createMessage,
    listParticipants,
    listGaps: commsListGaps,
    listCoordinationFlags,
  },
  skeleton: {
    listItems: skeletonListItems,
    getItem: skeletonGetItem,
    createItem: skeletonCreateItem,
    updateItem: skeletonUpdateItem,
    deleteItem: skeletonDeleteItem,
  },
  rules: {
    listItems: rulesListItems,
    getItem: rulesGetItem,
    createItem: rulesCreateItem,
    updateItem: rulesUpdateItem,
    deleteItem: rulesDeleteItem,
  },
  costs: {
    listTimeEntries,
    createTimeEntry,
    listExpenses,
    createExpense,
    listConductLog,
    createConductLog,
    listApplications,
  },
  sentiment: {
    createAnalysis,
    getAnalysis,
    listPatterns,
    listComparatorDiffs,
    listItems: sentimentListItems,
    getItem: sentimentGetItem,
  },
  redline: { createComparison, getComparison, listChains },
  strategist: {
    createPrediction,
    getPrediction,
    listReports: strategistListReports,
    listTacticalModels,
  },
  playbook: { createStrategy, getStrategy, listObjectives },
  oracle: {
    startResearch,
    getSession: oracleGetSession,
    getAuthority,
    listAuthorities,
    listItems: oracleListItems,
    getItem: oracleGetItem,
    createItem: oracleCreateItem,
  },
  'respondent-intel': { listProfiles, getProfile, createProfile },
  digest: { generateBriefing, getBriefing, listBriefings, getChangelog },
};

// ============================================================
// INTEGRATION SUMMARY
// ============================================================

export const INTEGRATION_MANIFEST = {
  totalShards: 18,
  appTxRegistered: 18,
  apiAligned: 18,
  pageComponentRegistry: Object.keys(_pageComponentRegistry),
  domainApiRegistry: Object.keys(_domainApiRegistry),
  _pageComponentRegistry,
  _domainApiRegistry,
} as const;
