# Staging deployment

One Azure VM with Docker, the shape of prod. Terraform builds the VM. A script deploys the app.

## What runs where

| Piece | Where |
| --- | --- |
| VM, network, firewall | `deploy/terraform` (Terraform, resource group `gnl-staging`) |
| MySQL 5.7.41 + backend | Docker Compose on the VM (`deploy/compose.yaml`) |
| Image transport | `docker save` over SSH. No registry account is needed. |

## First deployment

1. Log in once: `az login`.
2. Copy `deploy/env.example` to `deploy/.env` and fill in the three secrets.
3. Create the VM:

```bash
cd deploy/terraform
terraform init
terraform apply \
  -var subscription_id=<sub-id> \
  -var ssh_public_key_path=~/.ssh/id_ed25519.pub \
  -var admin_cidr=<your-ip>/32
```

4. Deploy the app: `deploy/deploy.sh <public_ip>` (the IP is a Terraform output).

## Day-to-day

- Redeploy after a code change: run `deploy/deploy.sh <public_ip>` again.
- Read the logs: `ssh gnl@<ip> docker logs --tail 100 <container>`. Rotation is set in the compose file.
- Reach MySQL: `ssh -L 3306:localhost:3306 gnl@<ip>`, then connect to `localhost:3306`.
- Tear down everything: `terraform destroy` in `deploy/terraform`. The monthly cost of an idle stack is the VM plus a 30 GB disk; see PLAN.md for prices.

## Costs

`Standard_B1ms` (1 vCPU / 2 GB, the memory shape of prod) is about USD 15 per month. The ceiling Daniel set is USD 50. `just azure-price` at the gym root re-measures.
