import * as cdk from 'aws-cdk-lib';
import * as apigwv2 from 'aws-cdk-lib/aws-apigatewayv2';
import * as apigwv2Integrations from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as s3deploy from 'aws-cdk-lib/aws-s3-deployment';
import { Construct } from 'constructs';
import * as path from 'path';

export class AstrologyStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Central bucket for every access log this stack produces (S3, its own
    // server access logs; CloudFront's standard logs) — one place to look,
    // one lifecycle policy, no per-service log bucket sprawl. Prefixed
    // per-source below so they can still be told apart / queried separately.
    const accessLogsBucket = new s3.Bucket(this, 'AccessLogsBucket', {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.DESTROY, // demo project — no retention need
      autoDeleteObjects: true,
      enforceSSL: true,
      // CloudFront's standard logging delivers via legacy ACL-based grants,
      // which require Object Ownership other than the (otherwise
      // recommended) bucket-owner-enforced default. S3-to-S3 server access
      // logging is unaffected either way — it uses a bucket-policy grant
      // that the CDK L2 (serverAccessLogsBucket below) sets up itself.
      objectOwnership: s3.ObjectOwnership.OBJECT_WRITER,
      lifecycleRules: [{ expiration: cdk.Duration.days(90) }],
    });

    const siteBucket = new s3.Bucket(this, 'FrontendBucket', {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.DESTROY, // demo project — no retention need
      autoDeleteObjects: true,
      enforceSSL: true,
      serverAccessLogsBucket: accessLogsBucket,
      serverAccessLogsPrefix: 's3-access-logs/frontend-bucket/',
    });

    const backendFn = new lambda.DockerImageFunction(this, 'BackendFunction', {
      code: lambda.DockerImageCode.fromImageAsset(
        path.join(__dirname, '..', '..', 'backend'),
      ),
      memorySize: 1024,
      timeout: cdk.Duration.seconds(30),
      architecture: lambda.Architecture.X86_64,
      environment: {
        // Placeholder; replaced with the real CloudFront domain once the
        // distribution exists (later task). Keeps local synth/diff runnable
        // before that resource is defined.
        ALLOWED_ORIGINS: 'http://localhost:5173,http://127.0.0.1:5173',
        GEOCODER_USER_AGENT: 'astrology-conjunction-finder/1.0',
      },
      logRetention: logs.RetentionDays.TWO_WEEKS,
      // Lambda's own Advanced Logging Controls: JSON wraps every line the
      // app writes via the stdlib `logging` module (see
      // backend/app/logging_config.py) into structured
      // {timestamp, level, message, requestId, ...} CloudWatch records —
      // no app-side JSON encoding needed. applicationLogLevelV2 governs
      // which of *our* log calls (INFO and up) get through; systemLogLevelV2
      // governs the separate platform START/END/REPORT lines (left at INFO,
      // their only useful level).
      loggingFormat: lambda.LoggingFormat.JSON,
      applicationLogLevelV2: lambda.ApplicationLogLevel.INFO,
      systemLogLevelV2: lambda.SystemLogLevel.INFO,
    });

    const httpApi = new apigwv2.HttpApi(this, 'BackendApi', {
      defaultIntegration: new apigwv2Integrations.HttpLambdaIntegration(
        'BackendIntegration',
        backendFn,
      ),
    });

    // Access logging isn't exposed on HttpApiProps/HttpStageOptions in a way
    // that reaches the auto-created $default stage, so set it via the L1
    // escape hatch on that existing stage rather than building a second
    // HttpStage with the same physical stage name (which CloudFormation
    // rejects as a duplicate — confirmed via a real failed deploy attempt).
    const apiAccessLogGroup = new logs.LogGroup(this, 'ApiAccessLogGroup', {
      retention: logs.RetentionDays.TWO_WEEKS,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
    const defaultStage = httpApi.defaultStage!.node.defaultChild as apigwv2.CfnStage;
    defaultStage.accessLogSettings = {
      destinationArn: apiAccessLogGroup.logGroupArn,
      // JSON (not the apigwv2 default CLF string) so it can be queried the
      // same way as the Lambda's own structured logs. $context fields per
      // https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-logging-variables.html
      format: JSON.stringify({
        requestId: '$context.requestId',
        requestTime: '$context.requestTime',
        httpMethod: '$context.httpMethod',
        path: '$context.path',
        routeKey: '$context.routeKey',
        status: '$context.status',
        responseLatencyMs: '$context.responseLatency',
        integrationLatencyMs: '$context.integrationLatency',
        integrationStatus: '$context.integrationStatus',
        sourceIp: '$context.identity.sourceIp',
        userAgent: '$context.identity.userAgent',
        errorMessage: '$context.error.message',
      }),
    };

    // HttpApi's generated domain, without the scheme — HttpOrigin wants a
    // bare hostname. apiEndpoint looks like "https://abc123.execute-api.
    // ca-central-1.amazonaws.com"; defaultStage exists automatically (HttpApi
    // creates one unless createDefaultStage: false is passed, which it wasn't).
    const apiDomain = cdk.Fn.select(2, cdk.Fn.split('/', httpApi.apiEndpoint));

    const distribution = new cloudfront.Distribution(this, 'SiteDistribution', {
      defaultRootObject: 'index.html',
      defaultBehavior: {
        origin: origins.S3BucketOrigin.withOriginAccessControl(siteBucket),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
      },
      additionalBehaviors: {
        '/api/*': {
          origin: new origins.HttpOrigin(apiDomain, {
            protocolPolicy: cloudfront.OriginProtocolPolicy.HTTPS_ONLY,
          }),
          viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
          cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
          // NOT ALL_VIEWER: that policy forwards the original Host header
          // (the CloudFront domain) straight through to API Gateway's
          // regional endpoint, which rejects it as a Host mismatch —
          // reproduced directly against the API (curl -H "Host: <cloudfront
          // domain>") and confirmed that's the exact cause of a live 403.
          // This AWS-managed policy is built for exactly this pairing: every
          // viewer header/cookie/query string except Host.
          originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
        },
      },
      // No `domainNames`/`certificate` props — this is exactly what makes
      // CloudFront issue its own *.cloudfront.net name with a free default
      // certificate. That satisfies "TLS, no custom domain" with zero extra
      // resources.
      enableLogging: true,
      logBucket: accessLogsBucket,
      logFilePrefix: 'cloudfront-access-logs/',
    });

    new s3deploy.BucketDeployment(this, 'FrontendDeployment', {
      sources: [s3deploy.Source.asset(path.join(__dirname, '..', '..', 'frontend', 'dist'))],
      destinationBucket: siteBucket,
      distribution,
      distributionPaths: ['/*'],
    });

    // Replace the localhost placeholder now that the real domain exists.
    backendFn.addEnvironment(
      'ALLOWED_ORIGINS',
      `https://${distribution.distributionDomainName}`,
    );

    new cdk.CfnOutput(this, 'SiteUrl', {
      value: `https://${distribution.distributionDomainName}`,
      description: 'Public HTTPS URL for the whole site (frontend + /api/*)',
    });
    new cdk.CfnOutput(this, 'ApiBaseUrl', {
      value: `https://${distribution.distributionDomainName}`,
      description:
        'Value to bake into VITE_API_BASE_URL for the frontend build (no /api suffix — frontend/src/api.ts appends /api/... itself, same convention as the http://localhost:8000 local default)',
    });
    new cdk.CfnOutput(this, 'DistributionId', {
      value: distribution.distributionId,
      description: 'CloudFront distribution ID (for manual invalidations)',
    });
    new cdk.CfnOutput(this, 'BucketName', {
      value: siteBucket.bucketName,
      description: 'Frontend S3 bucket name',
    });
  }
}
