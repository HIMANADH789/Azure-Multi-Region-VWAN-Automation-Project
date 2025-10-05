import os
import subprocess
from azure.identity import DefaultAzureCredential
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.compute import ComputeManagementClient

subscription_id = os.environ["AZURE_SUBSCRIPTION_ID"]
credential = DefaultAzureCredential()
resource_client = ResourceManagementClient(credential, subscription_id)
network_client = NetworkManagementClient(credential, subscription_id)
compute_client = ComputeManagementClient(credential, subscription_id)

rg_name = "RG-VWAN-Demo"
location1 = "centralindia"
location2 = "eastasia"
vwan_name = "GlobalVWAN"
hub_name = "CentralHub"
vnet1_name = "VNet-Primary"
vnet2_name = "VNet-Secondary"
workspace_name = "LogAnalyticsWorkspace"
storage_name = "flowlogstorageacct"
nsg_frontend_name = "NSG-Frontend"
nsg_backend_name = "NSG-Backend"

def run_cli(command):
    subprocess.run(command, shell=True, check=True)

resource_client.resource_groups.create_or_update(rg_name, {"location": location1})

def create_vnet(name, location, address_prefix, subnet_configs):
    vnet_params = {
        "location": location,
        "address_space": {"address_prefixes": [address_prefix]},
        "subnets": subnet_configs
    }
    return network_client.virtual_networks.begin_create_or_update(rg_name, name, vnet_params).result()

vnet1 = create_vnet(vnet1_name, location1, "10.0.0.0/16", [
    {"name": "FrontendSubnet", "address_prefix": "10.0.1.0/24"},
    {"name": "BackendSubnet", "address_prefix": "10.0.2.0/24"}
])
vnet2 = create_vnet(vnet2_name, location2, "10.1.0.0/16", [
    {"name": "AppSubnet", "address_prefix": "10.1.1.0/24"}
])

def create_nsg(name, location):
    return network_client.network_security_groups.begin_create_or_update(
        rg_name, name, {"location": location}
    ).result()

nsg_frontend = create_nsg(nsg_frontend_name, location1)
nsg_backend = create_nsg(nsg_backend_name, location1)

def create_vm(name, location, subnet_id):
    nic_params = {
        "location": location,
        "ip_configurations": [{
            "name": f"{name}-ipconfig",
            "subnet": {"id": subnet_id},
            "public_ip_address": None
        }]
    }
    nic = network_client.network_interfaces.begin_create_or_update(rg_name, f"{name}-nic", nic_params).result()

    vm_params = {
        "location": location,
        "storage_profile": {
            "image_reference": {
                "publisher": "Canonical",
                "offer": "UbuntuServer",
                "sku": "18.04-LTS",
                "version": "latest"
            }
        },
        "hardware_profile": {"vm_size": "Standard_B1s"},
        "os_profile": {
            "computer_name": name,
            "admin_username": "azureuser",
            "admin_password": "YourPassword123!"
        },
        "network_profile": {"network_interfaces": [{"id": nic.id}]}
    }
    return compute_client.virtual_machines.begin_create_or_update(rg_name, name, vm_params).result()

subnet_frontend = network_client.subnets.get(rg_name, vnet1_name, "FrontendSubnet")
subnet_backend = network_client.subnets.get(rg_name, vnet1_name, "BackendSubnet")
subnet_app = network_client.subnets.get(rg_name, vnet2_name, "AppSubnet")

vm_frontend = create_vm("FrontendVM", location1, subnet_frontend.id)
vm_backend = create_vm("BackendVM", location1, subnet_backend.id)
vm_app = create_vm("AppVM", location2, subnet_app.id)

run_cli(f"az network vwan create --name {vwan_name} --resource-group {rg_name} --location {location1}")
run_cli(f"az network vhub create --name {hub_name} --resource-group {rg_name} --vwan {vwan_name} --address-prefix 10.2.0.0/16 --location {location1}")
run_cli(f"az network vhub connection create --name VNet1Connection --resource-group {rg_name} --vhub-name {hub_name} --remote-vnet {vnet1.id} --internet-security false")
run_cli(f"az network vhub connection create --name VNet2Connection --resource-group {rg_name} --vhub-name {hub_name} --remote-vnet {vnet2.id} --internet-security false")
run_cli(f"az network vpn-gateway create --name VPNGateway --resource-group {rg_name} --vhub {hub_name} --location {location1}")
run_cli(f"az network watcher configure --locations {location1} {location2} --enabled true")
run_cli(f"az network watcher flow-log create --location {location1} --resource-group {rg_name} --nsg {nsg_frontend_name} "
        f"--storage-account {storage_name} --enabled true --workspace {workspace_name} --traffic-analytics true")
