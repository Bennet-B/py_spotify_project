import createClient from 'openapi-fetch'
import type { paths } from './types.gen'

/** Typed fetch client over the generated OpenAPI types; paths already carry the /api prefix. */
export const api = createClient<paths>({ baseUrl: '/' })

/** Shape of the backend's uniform error envelope (not part of the OpenAPI success schemas). */
export interface ApiErrorEnvelope {
  error: {
    code: string
    message: string
    detail: unknown
  }
}

/** Narrow an openapi-fetch error payload to the backend envelope. */
export function isApiError(err: unknown): err is ApiErrorEnvelope {
  return typeof err === 'object' && err !== null && 'error' in err && typeof (err as ApiErrorEnvelope).error?.code === 'string'
}

/** True when the error is the 409 "dataset_not_loaded" signal that a refresh job must run first. */
export function isDatasetNotLoaded(err: unknown): boolean {
  return isApiError(err) && err.error.code === 'dataset_not_loaded'
}
