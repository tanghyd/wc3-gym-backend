variable "subscription_id" {
  type        = string
  description = "The Azure subscription that owns the staging resources."
}

variable "location" {
  type        = string
  default     = "westeurope"
  description = "Azure region. GCP mapping: region, e.g. europe-west."
}

variable "vm_size" {
  type        = string
  default     = "Standard_B1ms"
  description = "B1ms is 1 vCPU / 2 GB, the memory shape of prod. GCP mapping: e2-small."
}

variable "admin_username" {
  type        = string
  default     = "gnl"
  description = "The SSH login on the VM."
}

variable "ssh_public_key_path" {
  type        = string
  description = "Path to the SSH public key that unlocks the VM."
}

variable "admin_cidr" {
  type        = string
  description = "The only CIDR the NSG lets in for SSH and the backend port."
}
