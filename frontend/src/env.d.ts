/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the FastAPI backend. Defaults to http://localhost:8000. */
  readonly VITE_API_BASE_URL?: string
  /** CloudWatch RUM app monitor ID. Unset locally — RUM init is skipped. */
  readonly VITE_RUM_APPLICATION_ID?: string
  /** Cognito identity pool ID backing the RUM app monitor's guest role. */
  readonly VITE_RUM_IDENTITY_POOL_ID?: string
  /** AWS region the RUM app monitor lives in, e.g. "ca-central-1". */
  readonly VITE_RUM_REGION?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
