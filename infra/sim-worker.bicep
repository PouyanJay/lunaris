// Dedicated trusted supervisor host; no API traffic or generated code runs on the host.
// Generated programs execute solely in the restricted, networkless verifier containers.
targetScope = 'resourceGroup'
param location string = resourceGroup().location
param managedIdentityResourceId string
@description('Stable operator public key. NSG denies all ingress, including SSH.')
param sshPublicKey string
param adminUsername string = 'lunaris'
param vmSize string = 'Standard_D2als_v7'
param availabilityZone string = '1'
var name = 'lunaris-prod-sim-worker'
resource nsg 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: '${name}-nsg'
  location: location
  properties: {
    securityRules: [{
      name: 'DenyAllInbound'
      properties: {
        priority: 100
        direction: 'Inbound'
        access: 'Deny'
        protocol: '*'
        sourcePortRange: '*'
        destinationPortRange: '*'
        sourceAddressPrefix: '*'
        destinationAddressPrefix: '*'
      }
    }]
  }
}
resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: '${name}-vnet'
  location: location
  properties: {
    addressSpace: { addressPrefixes: ['10.83.0.0/24'] }
    subnets: [{
      name: 'supervisor'
      properties: {
        addressPrefix: '10.83.0.0/27'
        networkSecurityGroup: { id: nsg.id }
        defaultOutboundAccess: false
      }
    }]
  }
}
// Explicit egress address; no inbound rule admits traffic to this address.
resource ip 'Microsoft.Network/publicIPAddresses@2024-05-01' = {
  name: '${name}-egress'
  location: location
  sku: { name: 'Standard' }
  properties: { publicIPAllocationMethod: 'Static' }
}
resource nic 'Microsoft.Network/networkInterfaces@2024-05-01' = {
  name: '${name}-nic'
  location: location
  properties: {
    networkSecurityGroup: { id: nsg.id }
    ipConfigurations: [{
      name: 'primary'
      properties: {
        privateIPAllocationMethod: 'Dynamic'
        subnet: { id: '${vnet.id}/subnets/supervisor' }
        publicIPAddress: { id: ip.id }
      }
    }]
  }
}
resource vm 'Microsoft.Compute/virtualMachines@2024-03-01' = {
  name: name
  location: location
  zones: [availabilityZone]
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${managedIdentityResourceId}': {} }
  }
  properties: {
    hardwareProfile: { vmSize: vmSize }
    storageProfile: {
      imageReference: {
        publisher: 'Canonical'
        offer: 'ubuntu-24_04-lts'
        sku: 'server'
        version: 'latest'
      }
      osDisk: {
        createOption: 'FromImage'
        diskSizeGB: 64
        managedDisk: { storageAccountType: 'StandardSSD_LRS' }
        deleteOption: 'Delete'
      }
    }
    osProfile: {
      computerName: name
      adminUsername: adminUsername
      customData: base64(loadTextContent('sim-worker/cloud-init.yaml'))
      linuxConfiguration: {
        disablePasswordAuthentication: true
        provisionVMAgent: true
        ssh: { publicKeys: [{ path: '/home/${adminUsername}/.ssh/authorized_keys', keyData: sshPublicKey }] }
        patchSettings: { patchMode: 'AutomaticByPlatform', assessmentMode: 'AutomaticByPlatform' }
      }
    }
    networkProfile: { networkInterfaces: [{ id: nic.id }] }
    securityProfile: {
      securityType: 'TrustedLaunch'
      uefiSettings: { secureBootEnabled: true, vTpmEnabled: true }
    }
  }
}
output vmName string = vm.name
