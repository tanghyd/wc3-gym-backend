output "public_ip" {
  value       = azurerm_public_ip.staging.ip_address
  description = "SSH and backend address of the staging VM."
}
