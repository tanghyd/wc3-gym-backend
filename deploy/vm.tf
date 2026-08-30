locals {
  backend_url  = "http://${azurerm_public_ip.gnl.fqdn}:5002"
  frontend_url = "http://${azurerm_public_ip.gnl.fqdn}"

  # The box files live in box/ so one copy serves both first boot and `just azure sync`.
  cloud_init = templatefile("${path.module}/cloud-init.yaml", {
    admin_username   = var.admin_username
    swap_size        = var.swap_size
    backend_image    = var.backend_image
    frontend_image   = var.frontend_image
    compose_yaml     = indent(6, file("${path.module}/box/compose.yaml"))
    nginx_conf       = indent(6, file("${path.module}/box/nginx.conf"))
    db_password      = random_password.db.result
    jwt_secret_key   = random_password.jwt_secret.result
    admin_token      = random_password.admin_token.result
    bot_client_token = random_password.bot_client_token.result
    frontend_url     = local.frontend_url
  })
}

resource "azurerm_linux_virtual_machine" "gnl" {
  name                            = "${var.name_prefix}-vm"
  resource_group_name             = azurerm_resource_group.gnl.name
  location                        = azurerm_resource_group.gnl.location
  size                            = var.vm_size
  admin_username                  = var.admin_username
  network_interface_ids           = [azurerm_network_interface.gnl.id]
  disable_password_authentication = true
  custom_data                     = base64encode(local.cloud_init)
  tags                            = var.tags

  admin_ssh_key {
    username   = var.admin_username
    public_key = file(pathexpand(var.ssh_public_key_path))
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "StandardSSD_LRS"
    disk_size_gb         = var.os_disk_size_gb
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }

  # Managed boot diagnostics needs no storage account of our own.
  boot_diagnostics {}

  # custom_data is ForceNew: editing the box files or the image tags would otherwise
  # replace the VM and delete the Postgres volume with it. A fresh box still boots from the
  # current files; `just azure sync` and `just azure deploy` carry later changes up.
  lifecycle {
    ignore_changes = [custom_data]
  }
}
