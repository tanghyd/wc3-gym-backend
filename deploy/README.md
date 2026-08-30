# Staging on Azure

One `Standard_B2ats_v2` VM in `northcentralus` runs the backend, the admin dashboard, PostgreSQL 17
and nginx as four Docker containers: a plain Docker host, the shape a self-hosted deployment takes.
This repo owns the box and everything on it except the frontend image, which the frontend repo
pins with its own `just deploy <tag>` against the same host.

Terraform owns the box. It does NOT own the app version: the image tags live in `/opt/gnl/.env` on
the box, because `custom_data` is ForceNew and carrying a tag through it would replace the VM and
delete the Postgres volume on every deploy. `vm.tf` therefore ignores changes to `custom_data`, and
the recipes carry later edits up instead.

| What changes | Command | From |
| --- | --- | --- |
| The box, the network, the NSG | `just terraform plan` then `just terraform apply` | this repo |
| The backend image | `just azure deploy [tag]` | this repo |
| The frontend image | `just deploy [tag]` | the frontend repo |
| `box/compose.yaml`, `box/nginx.conf`, the DB credentials | `just azure sync` | this repo |
| The data | `just azure seed` (the private seed repo) | this repo |

The files in `box/` are the stack itself. cloud-init writes them on first boot and `just azure sync`
replaces them afterwards, so there is one copy of each, not two.

State is a local file in this directory holding every generated password. It is gitignored and
never committed: a lost state is a fresh `apply` plus `just azure seed`, not a lost deployment.

## What it costs

| Item | USD per month |
| --- | --- |
| VM, `Standard_B2ats_v2`, 2 vCPU / 1 GiB | 6.86 |
| OS disk, 32 GB Standard SSD (E4 tier) | 2.40 |
| Public IPv4, Standard static | 3.65 |
| **Total** | **12.91** |

The v2 B-series carries 0 vCPUs of quota on a new subscription; `northcentralus` granted 4 on
2026-08-19. `Standard_B1s` (1 vCPU / 1 GiB, total 13.64) is the fallback if quota is withdrawn.
The box holds 1 GiB: `cloud-init.yaml` adds 2 GB of swap, and the backend sits near 200 MiB at a
20-season load. The frontend image serves static files with `http-server`; never run the Vite dev
server here.

## Steps

1. Log in and read your subscription id: `az login && az account show --query id -o tsv`.
2. `cp terraform.tfvars.example terraform.tfvars` and fill it in; `curl -s ifconfig.me` gives
   your address for `allowed_ssh_cidr`.
3. The URLs follow from `name_prefix` and `location`, because the public address carries an Azure
   DNS label: `http://<name_prefix>.<location>.cloudapp.azure.com` and `:5002` for the API.
4. Check both images exist. Each repo's "Staging image" workflow pushes its GHCR image on every
   push to main; both packages are public, so the box pulls them with no credentials.
   `just azure check-image-exists` here, `just check-image-exists` in the frontend repo.
   No build argument is needed: the frontend commits `VITE_BACKEND_URL=/api`, and nginx proxies
   `/api/` to the backend, stripping the prefix.
5. `just terraform plan && just terraform apply`. cloud-init writes the box files, pulls the images
   and starts the stack. A failed pull logs and leaves the box running.
6. `just terraform output ssh_command` and `just terraform output admin_token`.
7. `just azure seed` loads the private seed repo. `just azure status` shows the URLs, `/health`
   and what each container runs.
8. Deploy whenever a main moves: `just azure deploy [tag]` here, `just deploy [tag]` in the frontend
   repo. The frontend repo reads the host from `AZURE_STAGING_HOST` in its `.env.local`;
   `just terraform output fqdn` prints it.

SSH is open to one address. When a deploy times out on port 22 while the site still answers, run
`just terraform allow-my-ip`, then plan and apply. `apply` refuses a plan saved before a later
edit to a `.tf` or `.tfvars` file.

## What this does not give you

- **No HTTPS.** Port 80 and port 5002 serve plain HTTP. Add Caddy or certbot before anything real uses it.
- **No remote state.** Move it to an Azure storage backend before a second person runs it.
- **No production image.** Both repos build a staging image on every push to main; nothing builds or deploys a production image.

## Handover

Every name comes from `terraform.tfvars`. Handing the deployment to the Gym is a fresh apply in
their subscription with their copy of that file, then `just azure seed`.
