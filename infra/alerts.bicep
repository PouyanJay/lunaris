// Azure Monitor alerting for one Lunaris environment — deployed by CD after app.bicep (the metric
// alerts scope to the API Container App, which must already exist). Without these rules a prod
// 500-storm, a crash-looping revision, or memory pressure against the 2Gi Consumption cap is only
// discovered when a user reports it; with them, the action-group email fires within minutes.
//
// Deploy:  az deployment group create -g rg-lunaris-<env> -f infra/alerts.bicep \
//            -p env=<env> alertEmail=<operator email>

targetScope = 'resourceGroup'

@description('Environment name — drives resource names + the API app name.')
@allowed(['dev', 'prod'])
param env string

@description('Operator email the action group notifies.')
param alertEmail string

@description('Name of the API Container App the alerts watch (created by app.bicep).')
param apiAppName string = 'lunaris-${env}-api'

@description('Memory threshold in bytes — 85% of the 2Gi Consumption cap by default.')
param memoryThresholdBytes int = 1825361100

var tags = { app: 'lunaris', env: env, managedBy: 'bicep' }

resource api 'Microsoft.App/containerApps@2024-03-01' existing = {
  name: apiAppName
}

resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: 'lunaris-${env}-alerts'
  location: 'Global'
  tags: tags
  properties: {
    groupShortName: take('lunaris${env}', 12)
    enabled: true
    emailReceivers: [
      {
        name: 'operator'
        emailAddress: alertEmail
        useCommonAlertSchema: true
      }
    ]
  }
}

// A burst of server errors — the strongest "users are seeing failures right now" signal.
resource http5xxAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'lunaris-${env}-api-5xx'
  location: 'global'
  tags: tags
  properties: {
    description: 'API returned more than 10 HTTP 5xx responses in 5 minutes.'
    severity: 1
    enabled: true
    scopes: [api.id]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT5M'
    autoMitigate: true
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          criterionType: 'StaticThresholdCriterion'
          name: 'http5xx'
          metricNamespace: 'microsoft.app/containerapps'
          metricName: 'Requests'
          dimensions: [
            {
              name: 'statusCodeCategory'
              operator: 'Include'
              values: ['5xx']
            }
          ]
          operator: 'GreaterThan'
          threshold: 10
          timeAggregation: 'Total'
        }
      ]
    }
    actions: [
      { actionGroupId: actionGroup.id }
    ]
  }
}

// Replica restarts — a crash-looping revision (OOM, bad image, failed boot) restarts repeatedly.
resource restartAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'lunaris-${env}-api-restarts'
  location: 'global'
  tags: tags
  properties: {
    description: 'An API replica restarted more than 3 times within 15 minutes (crash loop / OOM).'
    severity: 2
    enabled: true
    scopes: [api.id]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    autoMitigate: true
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          criterionType: 'StaticThresholdCriterion'
          name: 'restarts'
          metricNamespace: 'microsoft.app/containerapps'
          metricName: 'RestartCount'
          operator: 'GreaterThan'
          threshold: 3
          timeAggregation: 'Maximum'
        }
      ]
    }
    actions: [
      { actionGroupId: actionGroup.id }
    ]
  }
}

// Memory pressure — the API runs at the Consumption tier's 2Gi ceiling with zero headroom, so
// sustained working-set above 85% is the early warning before the OOM kill (which the restart
// alert then catches too late).
resource memoryAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'lunaris-${env}-api-memory'
  location: 'global'
  tags: tags
  properties: {
    description: 'API working set averaged above 85% of the 2Gi memory cap for 15 minutes.'
    severity: 2
    enabled: true
    scopes: [api.id]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    autoMitigate: true
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          criterionType: 'StaticThresholdCriterion'
          name: 'memory'
          metricNamespace: 'microsoft.app/containerapps'
          metricName: 'WorkingSetBytes'
          operator: 'GreaterThan'
          threshold: memoryThresholdBytes
          timeAggregation: 'Average'
        }
      ]
    }
    actions: [
      { actionGroupId: actionGroup.id }
    ]
  }
}
