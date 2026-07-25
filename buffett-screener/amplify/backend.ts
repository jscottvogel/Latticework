import { defineBackend } from '@aws-amplify/backend';
import { auth } from './auth/resource';
import { data } from './data/resource';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import { Stack, RemovalPolicy, Duration } from 'aws-cdk-lib';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const backend = defineBackend({
  auth,
  data,
});

const stack = Stack.of(backend.data);

// ---------------------------------------------------------
// STEP 2: DYNAMODB TABLES
// ---------------------------------------------------------

const weeklyRunsTable = backend.data.resources.tables['WeeklyRun'];
const stockScoresTable = backend.data.resources.tables['StockScore'];
const rollingScoresTable = backend.data.resources.tables['RollingScore'];
const themeRegistryTable = backend.data.resources.tables['ThemeRegistry'];
const themeBasketTable = backend.data.resources.tables['ThemeBasket'];

const rawFinancialsTable = new dynamodb.Table(stack, 'RawFinancials', {
  partitionKey: { name: 'ticker', type: dynamodb.AttributeType.STRING },
  sortKey: { name: 'runId', type: dynamodb.AttributeType.STRING },
  billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
  pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true },
  removalPolicy: RemovalPolicy.RETAIN,
});

const scoreOutcomesTable = new dynamodb.Table(stack, 'ScoreOutcome', {
  partitionKey: { name: 'runId', type: dynamodb.AttributeType.STRING },
  sortKey: { name: 'tickerHorizon', type: dynamodb.AttributeType.STRING },
  billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
  pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true },
  removalPolicy: RemovalPolicy.RETAIN,
});

// ---------------------------------------------------------
// STEP 5: S3 BUCKET
// ---------------------------------------------------------

const dataBucket = new s3.Bucket(stack, 'BuffettScreenerData', {
  versioned: true,
  blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
  objectOwnership: s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
  cors: [
    {
      allowedMethods: [s3.HttpMethods.GET, s3.HttpMethods.HEAD],
      allowedOrigins: ['*'],
      allowedHeaders: ['*'],
    },
  ],
  removalPolicy: RemovalPolicy.RETAIN,
});

const distribution = new cloudfront.Distribution(stack, 'BuffettScreenerDistribution', {
  defaultBehavior: {
    origin: origins.S3BucketOrigin.withOriginAccessControl(dataBucket),
    viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
    allowedMethods: cloudfront.AllowedMethods.ALLOW_GET_HEAD_OPTIONS,
    cachedMethods: cloudfront.CachedMethods.CACHE_GET_HEAD,
    originRequestPolicy: cloudfront.OriginRequestPolicy.CORS_S3_ORIGIN,
    responseHeadersPolicy: cloudfront.ResponseHeadersPolicy.CORS_ALLOW_ALL_ORIGINS,
  },
});

// ---------------------------------------------------------
// STEP 4: IAM ROLE FOR LAMBDA FUNCTIONS
// ---------------------------------------------------------

const lambdaPolicy = new iam.PolicyStatement({
  actions: [
    'dynamodb:GetItem',
    'dynamodb:PutItem',
    'dynamodb:UpdateItem',
    'dynamodb:Query',
    'dynamodb:Scan',
    'dynamodb:BatchWriteItem',
    'dynamodb:BatchGetItem'
  ],
  resources: [
    weeklyRunsTable.tableArn,
    stockScoresTable.tableArn,
    rollingScoresTable.tableArn,
    rawFinancialsTable.tableArn,
    scoreOutcomesTable.tableArn,
    themeRegistryTable.tableArn,
    themeRegistryTable.tableArn + '/index/*',
    themeBasketTable.tableArn,
    themeBasketTable.tableArn + '/index/*',
  ]
});

const s3Policy = new iam.PolicyStatement({
  actions: ['s3:GetObject', 's3:PutObject', 's3:ListBucket'],
  resources: [
    dataBucket.bucketArn,
    dataBucket.arnForObjects('*')
  ],
});

const secretsPolicy = new iam.PolicyStatement({
  actions: ['secretsmanager:GetSecretValue'],
  resources: [`arn:aws:secretsmanager:${stack.region}:${stack.account}:secret:/buffett-screener/*`],
});

const snsPolicy = new iam.PolicyStatement({
  actions: ['sns:Publish'],
  resources: [`arn:aws:sns:${stack.region}:${stack.account}:buffett-screener-alerts`],
});

// ---------------------------------------------------------
// LAMBDA FUNCTIONS
// ---------------------------------------------------------

const orchestratorLambda = new lambda.Function(stack, 'ScreenerOrchestrator', {
  runtime: lambda.Runtime.PYTHON_3_11,
  handler: 'orchestrator.handler',
  code: lambda.Code.fromAsset(path.join(__dirname, 'functions')),
  architecture: lambda.Architecture.ARM_64,
  timeout: Duration.seconds(900),
  memorySize: 512,
});

const dataFetchLambda = new lambda.Function(stack, 'DataFetch', {
  runtime: lambda.Runtime.PYTHON_3_11,
  handler: 'dataFetch.handler',
  code: lambda.Code.fromAsset(path.join(__dirname, 'functions')),
  architecture: lambda.Architecture.ARM_64,
  timeout: Duration.seconds(900), 
});

const quantFilterLambda = new lambda.Function(stack, 'QuantFilter', {
  runtime: lambda.Runtime.PYTHON_3_11,
  handler: 'quantFilter.handler',
  code: lambda.Code.fromAsset(path.join(__dirname, 'functions')),
  architecture: lambda.Architecture.ARM_64,
  timeout: Duration.seconds(300), 
});

const newsFetchLambda = new lambda.Function(stack, 'NewsFetch', {
  runtime: lambda.Runtime.PYTHON_3_11,
  handler: 'newsFetch.handler',
  code: lambda.Code.fromAsset(path.join(__dirname, 'functions')),
  architecture: lambda.Architecture.ARM_64,
  timeout: Duration.seconds(900), 
});

const aiScorerLambda = new lambda.Function(stack, 'AiScorer', {
  runtime: lambda.Runtime.PYTHON_3_11,
  handler: 'aiScorer.handler',
  code: lambda.Code.fromAsset(path.join(__dirname, 'functions')),
  architecture: lambda.Architecture.ARM_64,
  timeout: Duration.seconds(900),
  memorySize: 512,
});

const monteCarloLambda = new lambda.Function(stack, 'MonteCarlo', {
  runtime: lambda.Runtime.PYTHON_3_11,
  handler: 'monteCarlo.handler',
  code: lambda.Code.fromAsset(path.join(__dirname, 'functions')),
  architecture: lambda.Architecture.ARM_64,
  timeout: Duration.seconds(120),
  memorySize: 256,
});

const backtestValidatorLambda = new lambda.Function(stack, 'BacktestValidator', {
  runtime: lambda.Runtime.PYTHON_3_11,
  handler: 'backtestValidator.handler',
  code: lambda.Code.fromAsset(path.join(__dirname, 'functions')),
  architecture: lambda.Architecture.ARM_64,
  timeout: Duration.seconds(900),
  memorySize: 512,
});

const themeBasketWorkerLambda = new lambda.Function(stack, 'ThemeBasketWorker', {
  runtime: lambda.Runtime.PYTHON_3_11,
  handler: 'themeBasketWorker.handler',
  code: lambda.Code.fromAsset(path.join(__dirname, 'functions')),
  architecture: lambda.Architecture.ARM_64,
  timeout: Duration.seconds(300),
  memorySize: 512,
});

const memoGeneratorLambda = new lambda.Function(stack, 'MemoGenerator', {
  runtime: lambda.Runtime.PYTHON_3_11,
  handler: 'memoGenerator.handler',
  code: lambda.Code.fromAsset(path.join(__dirname, 'functions')),
  architecture: lambda.Architecture.ARM_64,
  timeout: Duration.seconds(300),
  memorySize: 512,
});

// Grant permissions
const allLambdas = [
  orchestratorLambda, 
  dataFetchLambda, 
  quantFilterLambda, 
  newsFetchLambda, 
  aiScorerLambda, 
  monteCarloLambda, 
  backtestValidatorLambda,
  themeBasketWorkerLambda,
  memoGeneratorLambda
];

allLambdas.forEach(fn => {
  fn.addToRolePolicy(lambdaPolicy);
  fn.addToRolePolicy(s3Policy);
  fn.addToRolePolicy(secretsPolicy);
  fn.addToRolePolicy(snsPolicy);
});

// Grant Invokes
dataFetchLambda.grantInvoke(orchestratorLambda);
quantFilterLambda.grantInvoke(orchestratorLambda);
newsFetchLambda.grantInvoke(orchestratorLambda);
aiScorerLambda.grantInvoke(orchestratorLambda);
monteCarloLambda.grantInvoke(orchestratorLambda);
memoGeneratorLambda.grantInvoke(orchestratorLambda);
backtestValidatorLambda.grantInvoke(orchestratorLambda);
themeBasketWorkerLambda.grantInvoke(orchestratorLambda);

// Set environment variables
orchestratorLambda.addEnvironment('DATA_FETCH_FUNCTION_NAME', dataFetchLambda.functionName);
orchestratorLambda.addEnvironment('QUANT_FILTER_FUNCTION_NAME', quantFilterLambda.functionName);
orchestratorLambda.addEnvironment('NEWS_FETCH_FUNCTION_NAME', newsFetchLambda.functionName);
orchestratorLambda.addEnvironment('AI_SCORER_FUNCTION_NAME', aiScorerLambda.functionName);
orchestratorLambda.addEnvironment('MONTE_CARLO_FUNCTION_NAME', monteCarloLambda.functionName);
orchestratorLambda.addEnvironment('MEMO_GENERATOR_FUNCTION_NAME', memoGeneratorLambda.functionName);
orchestratorLambda.addEnvironment('BACKTEST_VALIDATOR_FUNCTION_NAME', backtestValidatorLambda.functionName);
orchestratorLambda.addEnvironment('THEME_BASKET_WORKER_FUNCTION_NAME', themeBasketWorkerLambda.functionName);

// Set environment variables
dataFetchLambda.addEnvironment('QUANT_FILTER_FUNCTION_NAME', quantFilterLambda.functionName);
dataFetchLambda.addEnvironment('S3_BUCKET', dataBucket.bucketName);
dataFetchLambda.addEnvironment('DYNAMODB_TABLE_RAW_FINANCIALS', rawFinancialsTable.tableName);
dataFetchLambda.addEnvironment('ALPHA_VANTAGE_TIER', 'premium'); // Premium API

quantFilterLambda.addEnvironment('NEWS_FETCH_FUNCTION_NAME', newsFetchLambda.functionName);
quantFilterLambda.addEnvironment('S3_BUCKET', dataBucket.bucketName);
quantFilterLambda.addEnvironment('DYNAMODB_TABLE_STOCK_SCORES', stockScoresTable.tableName);

newsFetchLambda.addEnvironment('AI_SCORER_FUNCTION_NAME', aiScorerLambda.functionName);

aiScorerLambda.addEnvironment('DYNAMODB_TABLE_STOCK_SCORES', stockScoresTable.tableName);
monteCarloLambda.addEnvironment('DYNAMODB_TABLE_STOCK_SCORES', stockScoresTable.tableName);

orchestratorLambda.addEnvironment('DYNAMODB_TABLE_WEEKLY_RUNS', weeklyRunsTable.tableName);
orchestratorLambda.addEnvironment('DYNAMODB_TABLE_STOCK_SCORES', stockScoresTable.tableName);
orchestratorLambda.addEnvironment('DYNAMODB_TABLE_ROLLING_SCORES', rollingScoresTable.tableName);
orchestratorLambda.addEnvironment('DYNAMODB_TABLE_RAW_FINANCIALS', rawFinancialsTable.tableName);
orchestratorLambda.addEnvironment('S3_BUCKET', dataBucket.bucketName);
orchestratorLambda.addEnvironment('SNS_ALERT_ARN', `arn:aws:sns:${stack.region}:${stack.account}:buffett-screener-alerts`);

backtestValidatorLambda.addEnvironment('DYNAMODB_TABLE_SCORE_OUTCOMES', scoreOutcomesTable.tableName);
backtestValidatorLambda.addEnvironment('DYNAMODB_TABLE_STOCK_SCORES', stockScoresTable.tableName);
backtestValidatorLambda.addEnvironment('S3_BUCKET', dataBucket.bucketName);
backtestValidatorLambda.addEnvironment('ALPHA_VANTAGE_TIER', 'premium');

themeBasketWorkerLambda.addEnvironment('DYNAMODB_TABLE_THEME_REGISTRY', themeRegistryTable.tableName);
themeBasketWorkerLambda.addEnvironment('DYNAMODB_TABLE_THEME_BASKET', themeBasketTable.tableName);
themeBasketWorkerLambda.addEnvironment('DYNAMODB_TABLE_ROLLING_SCORES', rollingScoresTable.tableName);
themeBasketWorkerLambda.addEnvironment('S3_BUCKET', dataBucket.bucketName);

memoGeneratorLambda.addEnvironment('DYNAMODB_TABLE_STOCK_SCORES', stockScoresTable.tableName);
memoGeneratorLambda.addEnvironment('DYNAMODB_TABLE_RAW_FINANCIALS', rawFinancialsTable.tableName);
memoGeneratorLambda.addEnvironment('S3_BUCKET', dataBucket.bucketName);

// EventBridge Scheduler (Mon-Fri at 8 AM CST / 2 PM UTC)
const dailyRule = new events.Rule(stack, 'DailyRunRule', {
  schedule: events.Schedule.cron({ minute: '0', hour: '14', weekDay: 'MON-FRI' }),
});
dailyRule.addTarget(new targets.LambdaFunction(orchestratorLambda));

// EventBridge Scheduler for weekly backtest validation (Sunday at 4 PM UTC / 10 AM CST)
const weeklyValidationRule = new events.Rule(stack, 'WeeklyValidationRule', {
  schedule: events.Schedule.cron({ minute: '0', hour: '16', weekDay: 'SUN' }),
});
weeklyValidationRule.addTarget(new targets.LambdaFunction(backtestValidatorLambda));
weeklyValidationRule.addTarget(new targets.LambdaFunction(themeBasketWorkerLambda));

// Add Function URL for manual trigger
const orchestratorUrl = orchestratorLambda.addFunctionUrl({
  authType: lambda.FunctionUrlAuthType.NONE,
  cors: {
    allowedOrigins: ['*'],
    allowedMethods: [lambda.HttpMethod.ALL],
    allowedHeaders: ['*'],
  },
});

backend.addOutput({
  custom: {
    orchestratorUrl: orchestratorUrl.url,
    dataBucketName: dataBucket.bucketName,
    awsRegion: stack.region,
    distributionDomainName: distribution.distributionDomainName,
  },
});
