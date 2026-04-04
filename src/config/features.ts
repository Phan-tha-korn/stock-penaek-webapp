export const featureFlags = {
  foundationPhaseReady: true,
  supplierModule: true,
  pricingModule: true,
  matchingModule: true,
  verificationWorkflow: true,
  searchV2: true,
  notificationsV2: true,
  historicalSnapshots: false,
} as const

export type FeatureFlagKey = keyof typeof featureFlags
