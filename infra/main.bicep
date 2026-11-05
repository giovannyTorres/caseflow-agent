@description('Existing Azure Container Apps managed environment resource ID')
param environmentId string
param location string = resourceGroup().location
param name string = 'caseflow-agent'
@description('Web image built with API_INTERNAL_URL=http://localhost:8102')
param webImage string
param apiImage string
@secure()
param databaseUrl string
@secure()
param providerApiKey string = ''
@allowed(['DEMO', 'LIVE'])
param mode string = 'DEMO'
@allowed(['openai', 'gemini'])
param provider string = 'openai'
param model string = 'gpt-4.1-mini'
param appOrigin string
param registryServer string = ''
@description('Existing user assigned identity with AcrPull when using a private registry')
param registryIdentityId string = ''

var backendEnv = [
  { name: 'DATABASE_URL', secretRef: 'database-url' }
  { name: 'APP_MODE', value: mode }
  { name: 'APP_ORIGIN', value: appOrigin }
  { name: 'COOKIE_SECURE', value: 'true' }
  { name: 'MODEL_PROVIDER', value: provider }
  { name: 'MODEL_NAME', value: model }
  { name: provider == 'openai' ? 'OPENAI_API_KEY' : 'GEMINI_API_KEY', secretRef: 'provider-key' }
]
resource app 'Microsoft.App/containerApps@2025-01-01' = {
  name: name
  location: location
  identity: empty(registryIdentityId) ? { type: 'SystemAssigned' } : {
    type: 'UserAssigned'
    userAssignedIdentities: { '${registryIdentityId}': {} }
  }
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: { external: true, targetPort: 3102, transport: 'http', allowInsecure: false }
      secrets: [
        { name: 'database-url', value: databaseUrl }
        { name: 'provider-key', value: providerApiKey }
      ]
      registries: empty(registryServer) ? [] : [{ server: registryServer, identity: registryIdentityId }]
    }
    template: {
      scale: { minReplicas: 1, maxReplicas: 1 }
      containers: [
        {
          name: 'web'
          image: webImage
          env: [{ name: 'PORT', value: '3102' }, { name: 'HOSTNAME', value: '0.0.0.0' }]
          resources: { cpu: json('0.5'), memory: '1Gi' }
          probes: [{ type: 'Readiness', httpGet: { path: '/', port: 3102 }, initialDelaySeconds: 10, periodSeconds: 10 }]
        }
        {
          name: 'api'
          image: apiImage
          env: backendEnv
          resources: { cpu: json('0.5'), memory: '1Gi' }
          probes: [{ type: 'Readiness', httpGet: { path: '/api/health', port: 8102 }, initialDelaySeconds: 10, periodSeconds: 10 }]
        }
        {
          name: 'worker'
          image: apiImage
          command: ['/app/.venv/bin/python', '-m', 'caseflow.worker']
          env: backendEnv
          resources: { cpu: json('0.5'), memory: '1Gi' }
        }
      ]
    }
  }
}
output url string = 'https://${app.properties.configuration.ingress.fqdn}'
