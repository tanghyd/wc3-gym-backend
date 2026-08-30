terraform {
  required_version = ">= 1.9"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "azurerm" {
  subscription_id = var.subscription_id
  features {}
}

resource "azurerm_resource_group" "gnl" {
  name     = "${var.name_prefix}-rg"
  location = var.location
  tags     = var.tags
}

# special = false keeps the value safe inside the DB_URL connection string.
resource "random_password" "db" {
  length  = 32
  special = false
}

# The value predates the Postgres switch; keep it so the box is not replaced for a rename.
moved {
  from = random_password.mysql_user
  to   = random_password.db
}

resource "random_password" "jwt_secret" {
  length  = 64
  special = false
}

resource "random_password" "admin_token" {
  length  = 32
  special = false
}

resource "random_password" "bot_client_token" {
  length  = 32
  special = false
}
