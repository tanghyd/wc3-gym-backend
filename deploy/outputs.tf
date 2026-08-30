output "public_ip" {
  description = "The static address of the VM."
  value       = azurerm_public_ip.gnl.ip_address
}

output "fqdn" {
  description = "The Azure DNS name. It is known before apply, from name_prefix and location."
  value       = azurerm_public_ip.gnl.fqdn
}

output "backend_url" {
  description = "Build the frontend image with VITE_BACKEND_URL set to this."
  value       = local.backend_url
}

output "frontend_url" {
  description = "The admin dashboard."
  value       = local.frontend_url
}

output "ssh_command" {
  description = "Log in to the box."
  value       = "ssh ${var.admin_username}@${azurerm_public_ip.gnl.fqdn}"
}

output "admin_token" {
  description = "Admin API token the backend expects."
  value       = random_password.admin_token.result
  sensitive   = true
}

# `just azure sync` renders /opt/gnl/postgres.env from this output.
output "db_password" {
  description = "Password for the gym_user database account."
  value       = random_password.db.result
  sensitive   = true
}
