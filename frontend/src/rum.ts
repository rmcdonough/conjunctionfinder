/**
 * CloudWatch RUM (Real User Monitoring) client initialization.
 *
 * Purely additive telemetry — page load performance, unhandled JS errors,
 * HTTP request outcomes — sent to an anonymous, unauthenticated Cognito
 * identity. No sign-in, no PII collected beyond what the RUM client itself
 * captures (browser/OS/device class, page URLs, error stacks).
 *
 * The three VITE_RUM_* values are outputs from the CDK stack
 * (infra/lib/astrology-stack.ts) — RumAppMonitorId, RumIdentityPoolId,
 * RumRegion — baked in at build time the same way VITE_API_BASE_URL is.
 * Unset in local dev (no .env entry for them), so `initRum()` is a no-op
 * outside the deployed site.
 */
export function initRum(): void {
  const applicationId = import.meta.env.VITE_RUM_APPLICATION_ID
  const identityPoolId = import.meta.env.VITE_RUM_IDENTITY_POOL_ID
  const region = import.meta.env.VITE_RUM_REGION

  if (!applicationId || !identityPoolId || !region) return

  // Dynamic import: keeps the ~50KB (gzipped) RUM client out of the bundle
  // entirely in local dev, where it would otherwise load and then no-op.
  import('aws-rum-web')
    .then(({ AwsRum }) => {
      new AwsRum(applicationId, '1.0.0', region, {
        sessionSampleRate: 1,
        identityPoolId,
        endpoint: `https://dataplane.rum.${region}.amazonaws.com`,
        telemetries: ['errors', 'performance', 'http'],
        allowCookies: true,
        enableXRay: false,
      })
    })
    .catch(() => {
      // Per AWS's own guidance: RUM client init failures should never break
      // the app. A dropped telemetry session is not worth a broken page.
    })
}
