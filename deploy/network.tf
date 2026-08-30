resource "azurerm_virtual_network" "gnl" {
  name                = "${var.name_prefix}-vnet"
  address_space       = ["10.20.0.0/16"]
  location            = azurerm_resource_group.gnl.location
  resource_group_name = azurerm_resource_group.gnl.name
  tags                = var.tags
}

resource "azurerm_subnet" "gnl" {
  name                 = "${var.name_prefix}-subnet"
  resource_group_name  = azurerm_resource_group.gnl.name
  virtual_network_name = azurerm_virtual_network.gnl.name
  address_prefixes     = ["10.20.1.0/24"]
}

# The DNS label makes the URL known before apply, so the frontend image can be
# built against it. Azure retired the Basic SKU, so Standard static is the only
# choice, at USD 3.65 per month.
resource "azurerm_public_ip" "gnl" {
  name                = "${var.name_prefix}-ip"
  location            = azurerm_resource_group.gnl.location
  resource_group_name = azurerm_resource_group.gnl.name
  allocation_method   = "Static"
  sku                 = "Standard"
  domain_name_label   = var.name_prefix
  tags                = var.tags
}

resource "azurerm_network_security_group" "gnl" {
  name                = "${var.name_prefix}-nsg"
  location            = azurerm_resource_group.gnl.location
  resource_group_name = azurerm_resource_group.gnl.name
  tags                = var.tags

  security_rule {
    name                       = "ssh"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = var.allowed_ssh_cidr
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "admin-frontend"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "80"
    source_address_prefix      = var.allowed_app_cidr
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "backend-api"
    priority                   = 120
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "5002"
    source_address_prefix      = var.allowed_app_cidr
    destination_address_prefix = "*"
  }
}

resource "azurerm_network_interface" "gnl" {
  name                = "${var.name_prefix}-nic"
  location            = azurerm_resource_group.gnl.location
  resource_group_name = azurerm_resource_group.gnl.name
  tags                = var.tags

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.gnl.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.gnl.id
  }
}

resource "azurerm_network_interface_security_group_association" "gnl" {
  network_interface_id      = azurerm_network_interface.gnl.id
  network_security_group_id = azurerm_network_security_group.gnl.id
}
