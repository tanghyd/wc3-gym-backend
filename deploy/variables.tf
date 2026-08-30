variable "subscription_id" {
  description = "Azure subscription id. Read it with: az account show --query id -o tsv"
  type        = string
}

variable "name_prefix" {
  description = "Prefix for every resource name, and the DNS label on the public address."
  type        = string
  default     = "gnl-staging"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,30}[a-z0-9]$", var.name_prefix))
    error_message = "Azure DNS labels take lowercase letters, digits and dashes only."
  }
}

variable "location" {
  description = "Azure region. eastus is the cheapest region for this size."
  type        = string
  default     = "eastus"
}

# B1s is 0.73 dearer than B2ats_v2 but deployable today. This subscription has
# 0 vCPUs of quota in every v2 B-series family (Basv2, Bsv2, Bpsv2) and 10 in the
# original BS family. Raising the Basv2 quota is a free support request; until it
# is granted, B2ats_v2 fails at apply.
variable "vm_size" {
  description = "VM size. Standard_B1s is 1 vCPU and 1 GiB, at USD 7.59 per month."
  type        = string
  default     = "Standard_B1s"
}

variable "os_disk_size_gb" {
  description = "OS disk size. 32 buys the E4 tier at USD 2.40 per month."
  type        = number
  default     = 32
}

variable "swap_size" {
  description = "Swap file size. B1s holds 1 GB of memory, so swap is the safety net."
  type        = string
  default     = "2G"
}

variable "admin_username" {
  description = "Login name for SSH."
  type        = string
  default     = "azureuser"
}

variable "ssh_public_key_path" {
  description = "Path to the public key that may log in."
  type        = string
  default     = "~/.ssh/id_rsa.pub"
}

variable "allowed_ssh_cidr" {
  description = "Address range allowed to reach SSH. Find yours with: curl -s ifconfig.me"
  type        = string

  validation {
    condition     = var.allowed_ssh_cidr != "0.0.0.0/0"
    error_message = "Set your own address range. SSH open to the internet is not acceptable."
  }
}

variable "allowed_app_cidr" {
  description = "Address range allowed to reach the app ports 80 and 5002."
  type        = string
  default     = "0.0.0.0/0"
}

variable "backend_image" {
  description = "Backend image reference, for example ghcr.io/tanghyd/gnl-backend:staging."
  type        = string
}

variable "frontend_image" {
  description = "Admin frontend image. Build it with VITE_BACKEND_URL set to the backend_url output."
  type        = string
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
  default = {
    project = "gnl"
    env     = "staging"
    owner   = "tanghyd"
  }
}
