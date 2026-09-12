import * as cdk from 'aws-cdk-lib';
import * as apigwv2 from 'aws-cdk-lib/aws-apigatewayv2';
import * as apigwv2Integrations from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import * as acm from 'aws-cdk-lib/aws-certificatemanager';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as cognito from 'aws-cdk-lib/aws-cognito';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as route53 from 'aws-cdk-lib/aws-route53';
import * as route53Targets from 'aws-cdk-lib/aws-route53-targets';
import * as rum from 'aws-cdk-lib/aws-rum';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as s3deploy from 'aws-cdk-lib/aws-s3-deployment';
import { Construct } from 'constructs';
import * as path from 'path';

export interface AstrologyStackProps extends cdk.StackProps {
  /**
   * Custom domain to serve the site on, e.g. "conjunctionfinder.ca".
   * Optional — omit (along with hostedZoneId/certificateArn) to keep the
   * default behavior: CloudFront issues its own *.cloudfront.net name with
   * a free default certificate. All three of domainName/hostedZoneId/
   * certificateArn must be set together to enable the custom domain; this
   * keeps the stack deployable as-is in a fresh account with no Route 53
   * zone or ACM cert of its own yet.
   */
  readonly domainName?: string;
  /** Route 53 hosted zone ID that owns domainName. */
  readonly hostedZoneId?: string;
  /**
   * ACM certificate ARN covering domainName. CloudFront requires this
   * certificate to live in us-east-1 specifically, regardless of which
   * region the stack itself deploys to — this is a plain ARN reference,
   * not a resource CDK creates, so the cross-region mismatch is fine.
   */
  readonly certificateArn?: string;
}

export class AstrologyStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: AstrologyStackProps) {
    super(scope, id, props);

    const { domainName, hostedZoneId, certificateArn } = props ?? {};
    const useCustomDomain = Boolean(domainName && hostedZoneId && certificateArn);
    if (Boolean(domainName || hostedZoneId || certificateArn) && !useCustomDomain) {
      throw new Error(
        'domainName, hostedZoneId and certificateArn must all be set together (or all omitted).',
      );
    }

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
      // Omitting domainNames/certificate (the useCustomDomain === false case)
      // is exactly what makes CloudFront issue its own *.cloudfront.net name
      // with a free default certificate — the zero-custom-domain path this
      // stack still supports for a fresh account with no Route 53 zone or
      // ACM cert of its own yet.
      domainNames: useCustomDomain ? [domainName!, `www.${domainName!}`] : undefined,
      certificate: useCustomDomain
        ? acm.Certificate.fromCertificateArn(this, 'SiteCertificate', certificateArn!)
        : undefined,
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
      // Custom-domain path also gets the CloudFront default *.cloudfront.net
      // domain — CloudFront never turns that off, so the auto-generated
      // name keeps working as a fallback URL alongside the custom domain.
      enableLogging: true,
      logBucket: accessLogsBucket,
      logFilePrefix: 'cloudfront-access-logs/',
    });

    if (useCustomDomain) {
      const hostedZone = route53.HostedZone.fromHostedZoneAttributes(this, 'SiteHostedZone', {
        hostedZoneId: hostedZoneId!,
        zoneName: domainName!,
      });
      const target = route53.RecordTarget.fromAlias(
        new route53Targets.CloudFrontTarget(distribution),
      );
      new route53.ARecord(this, 'SiteAliasA', { zone: hostedZone, target });
      new route53.AaaaRecord(this, 'SiteAliasAAAA', { zone: hostedZone, target });
      new route53.ARecord(this, 'SiteAliasWwwA', {
        zone: hostedZone,
        recordName: `www.${domainName}`,
        target,
      });
      new route53.AaaaRecord(this, 'SiteAliasWwwAAAA', {
        zone: hostedZone,
        recordName: `www.${domainName}`,
        target,
      });
    }

    new s3deploy.BucketDeployment(this, 'FrontendDeployment', {
      sources: [s3deploy.Source.asset(path.join(__dirname, '..', '..', 'frontend', 'dist'))],
      destinationBucket: siteBucket,
      distribution,
      distributionPaths: ['/*'],
    });

    // Canonical public URL: the custom domain once configured, otherwise
    // CloudFront's own generated name. Backend CORS and the RUM app monitor
    // both key off this — kept in one place so the two behaviors (custom
    // domain vs. auto-generated) can't drift apart.
    const siteUrl = useCustomDomain
      ? `https://${domainName}`
      : `https://${distribution.distributionDomainName}`;

    // Accept both the canonical URL and the CloudFront default domain
    // (which CloudFront always keeps serving alongside any custom domain)
    // so the API/Lambda keep functioning for either — a stale bookmark, a
    // link shared before DNS propagated, or the *.cloudfront.net URL from
    // before this domain was added should never suddenly start seeing CORS
    // failures.
    const allowedOrigins = useCustomDomain
      ? [
          `https://${domainName}`,
          `https://www.${domainName}`,
          `https://${distribution.distributionDomainName}`,
        ]
      : [`https://${distribution.distributionDomainName}`];
    backendFn.addEnvironment('ALLOWED_ORIGINS', allowedOrigins.join(','));

    // ── Real User Monitoring (CloudWatch RUM) ──────────────────────────
    //
    // RUM matches events against the page's actual origin domain, so this
    // needs every domain visitors can actually load the site from: the
    // custom domain(s) once configured, and always the CloudFront default
    // name too (it keeps serving traffic regardless — see allowedOrigins
    // above). RUM's `domainList` (not the older singular `domain`) is what
    // supports more than one domain on a single app monitor. Every value
    // here is a CloudFormation token or a plain string derived from one, so
    // this remains correct with no manual post-deploy step whether or not
    // a custom domain is configured, and if the distribution is ever torn
    // down and recreated, the new random name flows through automatically.
    //
    // Anonymous (unauthenticated) ingestion only: a Cognito identity pool
    // with unauthenticated identities enabled hands out short-lived,
    // scoped-down credentials to every browser that loads the page, purely
    // so the RUM web client can call PutRumEvents. No sign-in, no PII, no
    // persistent per-visitor identity beyond what RUM itself tracks.
    const rumIdentityPool = new cognito.CfnIdentityPool(this, 'RumIdentityPool', {
      allowUnauthenticatedIdentities: true,
    });

    const rumUnauthenticatedRole = new iam.Role(this, 'RumUnauthenticatedRole', {
      assumedBy: new iam.FederatedPrincipal(
        'cognito-identity.amazonaws.com',
        {
          StringEquals: {
            'cognito-identity.amazonaws.com:aud': rumIdentityPool.ref,
          },
          'ForAnyValue:StringLike': {
            'cognito-identity.amazonaws.com:amr': 'unauthenticated',
          },
        },
        'sts:AssumeRoleWithWebIdentity',
      ),
    });

    new cognito.CfnIdentityPoolRoleAttachment(this, 'RumIdentityPoolRoleAttachment', {
      identityPoolId: rumIdentityPool.ref,
      roles: { unauthenticated: rumUnauthenticatedRole.roleArn },
    });

    const rumDomainList = useCustomDomain
      ? [domainName!, `www.${domainName!}`, distribution.distributionDomainName]
      : undefined;

    const rumAppMonitor = new rum.CfnAppMonitor(this, 'RumAppMonitor', {
      name: 'AstrologyConjunctionFinder',
      // domain (singular) and domainList are mutually exclusive; only one
      // is ever set depending on useCustomDomain.
      domain: useCustomDomain ? undefined : distribution.distributionDomainName,
      domainList: rumDomainList,
      cwLogEnabled: true, // also mirrors RUM events into CloudWatch Logs
      appMonitorConfiguration: {
        allowCookies: true,
        enableXRay: false,
        sessionSampleRate: 1, // low-traffic personal project — sample everything
        telemetries: ['errors', 'performance', 'http'],
        identityPoolId: rumIdentityPool.ref,
        guestRoleArn: rumUnauthenticatedRole.roleArn,
      },
    });

    // Scope the guest role down to exactly this app monitor, not every
    // app monitor in the account/region.
    rumUnauthenticatedRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ['rum:PutRumEvents'],
        resources: [
          `arn:aws:rum:${this.region}:${this.account}:appmonitor/${rumAppMonitor.name}`,
        ],
      }),
    );

    new cdk.CfnOutput(this, 'SiteUrl', {
      value: siteUrl,
      description: 'Public HTTPS URL for the whole site (frontend + /api/*)',
    });
    new cdk.CfnOutput(this, 'ApiBaseUrl', {
      value: siteUrl,
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
    new cdk.CfnOutput(this, 'RumAppMonitorId', {
      value: rumAppMonitor.attrId,
      description: 'Value to bake into VITE_RUM_APPLICATION_ID for the frontend build',
    });
    new cdk.CfnOutput(this, 'RumIdentityPoolId', {
      value: rumIdentityPool.ref,
      description: 'Value to bake into VITE_RUM_IDENTITY_POOL_ID for the frontend build',
    });
    new cdk.CfnOutput(this, 'RumRegion', {
      value: this.region,
      description: 'Value to bake into VITE_RUM_REGION for the frontend build',
    });
  }
}
