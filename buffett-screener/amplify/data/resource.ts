import { type ClientSchema, a, defineData } from '@aws-amplify/backend';

const schema = a.schema({
  WeeklyRun: a
    .model({
      runId: a.id().required(),
      runDate: a.string().required(),
      weekNumber: a.integer(),
      stocksScreened: a.integer(),
      candidatesScored: a.integer(),
      status: a.string(),
      totalCostUsd: a.float(),
      stocksScreenedCumulative: a.integer(),
      universeCoveragePct: a.float(),
    })
    .identifier(['runId'])
    .authorization(allow => [allow.publicApiKey()]),

  StockScore: a
    .model({
      runId: a.id().required(),
      ticker: a.string().required(),
      companyName: a.string(),
      sector: a.string(),
      scoreMoat: a.float(),
      scoreFinancialHealth: a.float(),
      scoreManagement: a.float(),
      scoreSimplicity: a.float(),
      scoreMarginOfSafety: a.float(),
      compositeScore: a.float(),
      aiReportedComposite: a.float(),
      revenueExposure: a.string(),
      verdict: a.string(),
      confidence: a.string(),
      oneLineThesis: a.string(),
      keyRisks: a.string().array(),
      redFlags: a.string().array(),
      rankThisWeek: a.integer(),
      mcP10: a.float(),
      mcP90: a.float(),
      mcProbInvestigate: a.float(),
      mcConfidenceBand: a.string(),
    })
    .identifier(['runId', 'ticker'])
    .authorization(allow => [allow.publicApiKey()]),

  RollingScore: a
    .model({
      ticker: a.id().required(),
      companyName: a.string(),
      sector: a.string(),
      appearancesLast4Weeks: a.integer(),
      appearanceRate: a.float(),
      avgCompositeScore: a.float(),
      investigateCount: a.integer(),
      isInvestable: a.boolean(),
      latestThesis: a.string(),
      latestVerdict: a.string(),
      lastSeen: a.string(),
      updatedAt: a.string(),
    })
    .identifier(['ticker'])
    .authorization(allow => [allow.publicApiKey()]),
  ThemeRegistry: a
    .model({
      themeId: a.id().required(),
      name: a.string().required(),
      description: a.string(),
      keywords: a.string().array(),
    })
    .identifier(['themeId'])
    .authorization(allow => [allow.publicApiKey()]),

  ThemeBasket: a
    .model({
      themeId: a.string().required(),
      ticker: a.string().required(),
      companyName: a.string(),
      sector: a.string(),
      avgCompositeScore: a.float(),
      latestVerdict: a.string(),
      isInvestable: a.boolean(),
      matchedKeywords: a.string().array(),
    })
    .identifier(['themeId', 'ticker'])
    .authorization(allow => [allow.publicApiKey()]),
});

export type Schema = ClientSchema<typeof schema>;

export const data = defineData({
  schema,
  authorizationModes: {
    defaultAuthorizationMode: 'apiKey',
    apiKeyAuthorizationMode: { expiresInDays: 365 },
  },
});
