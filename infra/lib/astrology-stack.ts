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

    const siteBucket = new s3.Bucket(this, 'FrontendBucket', {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.DESTROY, // demo project — no retention need
      autoDeleteObjects: true,
      enforceSSL: true,
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
    });

    const httpApi = new apigwv2.HttpApi(this, 'BackendApi', {
      defaultIntegration: new apigwv2Integrations.HttpLambdaIntegration(
        'BackendIntegration',
        backendFn,
      ),
    });

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
          originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER,
        },
      },
      // No `domainNames`/`certificate` props — this is exactly what makes
      // CloudFront issue its own *.cloudfront.net name with a free default
      // certificate. That satisfies "TLS, no custom domain" with zero extra
      // resources.
    });

    new s3deploy.BucketDeployment(this, 'FrontendDeployment', {
      sources: [s3deploy.Source.asset(path.join(__dirname, '..', '..', 'frontend', 'dist'))],
      destinationBucket: siteBucket,
      distribution,
      distributionPaths: ['/*'],
    });
  }
}
