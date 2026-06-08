using './main.bicep'

// Prod compute sits in westus2: the subscription allows only one Container App Environment per
// region and dev holds the West US slot. westus2 is effectively co-located with Supabase us-west-1
// (a few ms more than westus — negligible for minutes-long builds). swaLocation is already westus2.
param env = 'prod'
param location = 'westus2'
param swaLocation = 'westus2'
