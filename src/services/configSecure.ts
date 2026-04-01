import { api } from './api'

export type GoogleSetupConfig = {
  configured: boolean
  workspace_email: string
  drive_folder_name: string
  default_sheet_title: string
  service_account_key_path: string
  oauth_client_id: string
  oauth_client_secret_masked: string
  oauth_redirect_uri: string
  oauth_token_path: string
  oauth_connected: boolean
  current_sheet_id: string
  current_sheet_url: string
}

export async function fetchGoogleSetupConfig() {
  const { data } = await api.get<GoogleSetupConfig>('/config/google-setup')
  return data
}

export async function updateGoogleSetupConfig(payload: {
  workspace_email: string
  drive_folder_name: string
  default_sheet_title: string
  service_account_key_path: string
  oauth_client_id: string
  oauth_client_secret: string
  oauth_redirect_uri: string
  oauth_token_path: string
  create_new_sheet: boolean
  migrate_existing_data: boolean
}) {
  const { data } = await api.put<GoogleSetupConfig>('/config/google-setup', payload)
  return data
}

export async function startGoogleOAuthLogin(returnTo?: string) {
  const { data } = await api.post<{ auth_url: string }>('/config/google-oauth/start', null, {
    params: returnTo ? { return_to: returnTo } : undefined,
  })
  return data
}
