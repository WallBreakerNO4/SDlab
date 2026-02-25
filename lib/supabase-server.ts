import 'server-only'

import { createClient } from '@supabase/supabase-js'

type SupabaseServiceEnvSnapshot = {
  hasUrl: boolean
  urlLength: number
  hasServiceRoleKey: boolean
  serviceRoleKeyLength: number
}

export class SupabaseServiceConfigError extends Error {
  code: 'missing_env'
  context: SupabaseServiceEnvSnapshot

  constructor(code: 'missing_env', context: SupabaseServiceEnvSnapshot) {
    super('missing required Supabase configuration')
    this.name = 'SupabaseServiceConfigError'
    this.code = code
    this.context = context
  }
}

function _readSupabaseServiceEnv(): { url: string; serviceRoleKey: string } {
  const url = (process.env.SUPABASE_URL ?? '').trim()
  const serviceRoleKey = (process.env.SUPABASE_SERVICE_ROLE_KEY ?? '').trim()

  const snapshot: SupabaseServiceEnvSnapshot = {
    hasUrl: url.length > 0,
    urlLength: url.length,
    hasServiceRoleKey: serviceRoleKey.length > 0,
    serviceRoleKeyLength: serviceRoleKey.length,
  }

  if (!snapshot.hasUrl || !snapshot.hasServiceRoleKey) {
    throw new SupabaseServiceConfigError('missing_env', snapshot)
  }

  return { url, serviceRoleKey }
}

export function createSupabaseServiceClient() {
  const { url, serviceRoleKey } = _readSupabaseServiceEnv()

  return createClient(url, serviceRoleKey, {
    auth: {
      persistSession: false,
      autoRefreshToken: false,
      detectSessionInUrl: false,
    },
  })
}
