import * as cdk from 'aws-cdk-lib';
import * as apigwv2 from 'aws-cdk-lib/aws-apigatewayv2';
import * as apigwv2Integrations from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as s3 from 'aws-cdk-lib/aws-s3';
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
  }
}
