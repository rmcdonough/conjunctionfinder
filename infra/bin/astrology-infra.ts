#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { AstrologyStack } from '../lib/astrology-stack';

const app = new cdk.App();

// Custom domain is fully optional — set all three env vars together to
// enable it, or leave them unset to keep the default *.cloudfront.net
// behavior (see AstrologyStackProps in astrology-stack.ts for details).
const domainName = process.env.SITE_DOMAIN_NAME;
const hostedZoneId = process.env.SITE_HOSTED_ZONE_ID;
const certificateArn = process.env.SITE_CERTIFICATE_ARN;

new AstrologyStack(app, 'AstrologyConjunctionFinder', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION ?? 'ca-central-1',
  },
  domainName,
  hostedZoneId,
  certificateArn,
});
