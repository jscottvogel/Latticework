import { defineBackend } from '@aws-amplify/backend';
import { data } from './data/resource';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as s3 from 'aws-cdk-lib/aws-s3';
import { Stack, RemovalPolicy, Duration } from 'aws-cdk-lib';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const backend = defineBackend({
  data,
});

const stack = Stack.of(backend.data);

// ---------------------------------------------------------
// STEP 2: DYNAMODB TABLES
// ---------------------------------------------------------

const weeklyRunsTable = backend.data.resources.tables['WeeklyRun'];
const stockScoresTable = backend.data.resources.tables['StockScore'];
const rollingScoresTable = backend.data.resources.tables['RollingScore'];

const rawFinancialsTable = new dynamodb.Table(stack, 'RawFinancials', {
  partitionKey: { name: 'ticker', type: dynamodb.AttributeType.STRING },
  sortKey: { name: 'runId', type: dynamodb.AttributeType.STRING },
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
  removalPolicy: RemovalPolicy.RETAIN,
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
  ]
});

const s3Policy = new iam.PolicyStatement({
  actions: ['s3:GetObject', 's3:PutObject'],
  resources: [dataBucket.arnForObjects('*')],
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

// Grant permissions
const allLambdas = [orchestratorLambda, dataFetchLambda, quantFilterLambda, newsFetchLambda, aiScorerLambda, monteCarloLambda];

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

// Set environment variables
orchestratorLambda.addEnvironment('DATA_FETCH_FUNCTION_NAME', dataFetchLambda.functionName);
orchestratorLambda.addEnvironment('QUANT_FILTER_FUNCTION_NAME', quantFilterLambda.functionName);
orchestratorLambda.addEnvironment('NEWS_FETCH_FUNCTION_NAME', newsFetchLambda.functionName);
orchestratorLambda.addEnvironment('AI_SCORER_FUNCTION_NAME', aiScorerLambda.functionName);
orchestratorLambda.addEnvironment('MONTE_CARLO_FUNCTION_NAME', monteCarloLambda.functionName);

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

orchestratorLambda.addEnvironment('DATA_FETCH_FUNCTION_NAME', dataFetchLambda.functionName);
orchestratorLambda.addEnvironment('DYNAMODB_TABLE_WEEKLY_RUNS', weeklyRunsTable.tableName);
orchestratorLambda.addEnvironment('DYNAMODB_TABLE_STOCK_SCORES', stockScoresTable.tableName);
orchestratorLambda.addEnvironment('DYNAMODB_TABLE_ROLLING_SCORES', rollingScoresTable.tableName);
orchestratorLambda.addEnvironment('DYNAMODB_TABLE_RAW_FINANCIALS', rawFinancialsTable.tableName);
orchestratorLambda.addEnvironment('S3_BUCKET', dataBucket.bucketName);
orchestratorLambda.addEnvironment('SNS_ALERT_ARN', `arn:aws:sns:${stack.region}:${stack.account}:buffett-screener-alerts`);

// EventBridge Scheduler (Daily at 5 PM UTC)
const dailyRule = new events.Rule(stack, 'DailyRunRule', {
  schedule: events.Schedule.cron({ minute: '0', hour: '17' }),
});
dailyRule.addTarget(new targets.LambdaFunction(orchestratorLambda));

// Add Function URL for manual trigger
const orchestratorUrl = orchestratorLambda.addFunctionUrl({
  authType: lambda.FunctionUrlAuthType.NONE,
  cors: {
    allowedOrigins: ['*'],
    allowedMethods: [lambda.HttpMethod.POST],
  },
});

backend.addOutput({
  custom: {
    orchestratorUrl: orchestratorUrl.url,
  },
});
