# Staging: one VM with Docker, the shape of prod.
# GCP mapping: resource group ~ a project's resource container,
# azurerm_linux_virtual_machine ~ google_compute_instance,
# network_security_group ~ google_compute_firewall, custom_data ~ startup-script.

terraform {
  required_version = ">= 1.10"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}

resource "azurerm_resource_group" "staging" {
  name     = "gnl-staging"
  location = var.location
}

resource "azurerm_virtual_network" "staging" {
  name                = "gnl-staging-vnet"
  address_space       = ["10.20.0.0/24"]
  location            = azurerm_resource_group.staging.location
  resource_group_name = azurerm_resource_group.staging.name
}

resource "azurerm_subnet" "staging" {
  name                 = "gnl-staging-subnet"
  resource_group_name  = azurerm_resource_group.staging.name
  virtual_network_name = azurerm_virtual_network.staging.name
  address_prefixes     = ["10.20.0.0/28"]
}

resource "azurerm_network_security_group" "staging" {
  name                = "gnl-staging-nsg"
  location            = azurerm_resource_group.staging.location
  resource_group_name = azurerm_resource_group.staging.name

  security_rule {
    name                       = "ssh"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = var.admin_cidr
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "backend"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "5002"
    source_address_prefix      = var.admin_cidr
    destination_address_prefix = "*"
  }
}

resource "azurerm_public_ip" "staging" {
  name                = "gnl-staging-ip"
  location            = azurerm_resource_group.staging.location
  resource_group_name = azurerm_resource_group.staging.name
  allocation_method   = "Static"
  sku                 = "Basic"
}

resource "azurerm_network_interface" "staging" {
  name                = "gnl-staging-nic"
  location            = azurerm_resource_group.staging.location
  resource_group_name = azurerm_resource_group.staging.name

  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.staging.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.staging.id
  }
}

resource "azurerm_network_interface_security_group_association" "staging" {
  network_interface_id      = azurerm_network_interface.staging.id
  network_security_group_id = azurerm_network_security_group.staging.id
}

resource "azurerm_linux_virtual_machine" "staging" {
  name                = "gnl-staging-vm"
  location            = azurerm_resource_group.staging.location
  resource_group_name = azurerm_resource_group.staging.name
  # B1ms: 1 vCPU / 2 GB, the memory shape of prod. See PLAN.md for prices.
  size                  = var.vm_size
  admin_username        = var.admin_username
  network_interface_ids = [azurerm_network_interface.staging.id]

  admin_ssh_key {
    username   = var.admin_username
    public_key = file(var.ssh_public_key_path)
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
    disk_size_gb         = 30
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }

  custom_data = base64encode(file("${path.module}/cloud-init.yaml"))
}
