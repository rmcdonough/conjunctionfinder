#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { AstrologyStack } from '../lib/astrology-stack';

const app = new cdk.App();
new AstrologyStack(app, 'AstrologyConjunctionFinder', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION ?? 'ca-central-1',
  },
});
