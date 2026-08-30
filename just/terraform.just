# Terraform for the staging box on Azure. Read deploy/README.md before the first apply.

# Recipes run from the repository root, one level up from this file.
set working-directory := '..'

dir := "./deploy"

default:
    @just --list terraform

# Download the providers. Run once, and again after a version change.
init:
    terraform -chdir={{ dir }} init

# Upgrade the provider versions within the constraints in main.tf.
upgrade:
    terraform -chdir={{ dir }} init -upgrade

# Check the syntax and formatting without contacting Azure.
validate:
    terraform -chdir={{ dir }} init -backend=false
    terraform -chdir={{ dir }} validate
    terraform -chdir={{ dir }} fmt -check

# Format the Terraform files in place.
fmt:
    terraform -chdir={{ dir }} fmt

# Show what apply would change.
plan *targets: init
    terraform -chdir={{ dir }} plan \
        -out=tfplan \
        $(for target in {{ targets }}; do echo -target="$target"; done)

# Create or update the box from the saved plan. Run plan first.
apply: init
    #!/usr/bin/env bash
    set -euo pipefail
    plan={{ dir }}/tfplan
    [ -f "$plan" ] || { echo "no saved plan; run: just terraform plan" >&2; exit 1; }
    # A plan saved before an edit applies the OLD values without saying so. allowed_ssh_cidr
    # is the one that bites: the address rotates, and a stale plan reinstates the dead one.
    stale=$(find {{ dir }} -maxdepth 1 \( -name '*.tf' -o -name '*.tfvars' \) -newer "$plan")
    [ -z "$stale" ] || { echo "these changed after the plan was saved:" >&2; echo "$stale" >&2; echo "re-run: just terraform plan" >&2; exit 1; }
    terraform -chdir={{ dir }} apply tfplan

# Read one output. Names: fqdn, public_ip, backend_url, frontend_url, ssh_command,
# admin_token, db_password.
output name:
    @terraform -chdir={{ dir }} output -raw {{ name }}

# Print the URLs and the login command.
urls:
    @terraform -chdir={{ dir }} output frontend_url
    @terraform -chdir={{ dir }} output backend_url
    @terraform -chdir={{ dir }} output ssh_command

# Point the SSH rule at the address you are calling from today. This address rotates, so a
# deploy that times out on port 22 while the site still answers usually just needs this.
# Widen the prefix (24 covers the neighbours your ISP hands out) to do it less often.
allow-my-ip prefix="32":
    #!/usr/bin/env bash
    set -euo pipefail
    ip=$(curl -fsS https://ifconfig.me)
    if [ "{{ prefix }}" = "32" ]; then
        cidr="$ip/32"
    else
        cidr=$(uv run python -c "import ipaddress, sys; print(ipaddress.ip_network(f'{sys.argv[1]}/{sys.argv[2]}', strict=False))" "$ip" "{{ prefix }}")
    fi
    file={{ dir }}/terraform.tfvars
    current=$(grep '^allowed_ssh_cidr' "$file" | cut -d'"' -f2)
    if [ "$current" = "$cidr" ]; then
        echo "allowed_ssh_cidr is already $current"
        exit 0
    fi
    sed -i "s|^allowed_ssh_cidr = \".*\"|allowed_ssh_cidr = \"$cidr\"|" "$file"
    echo "allowed_ssh_cidr $current -> $cidr. Run: just terraform plan && just terraform apply"

# Delete every resource. Billing stops, and the database volume goes with it.
[confirm("This destroys the box AND its Postgres volume. Type yes to continue.")]
destroy: init
    terraform -chdir={{ dir }} destroy

# Import a resource that already exists into the state.
import resource name: init
    terraform -chdir={{ dir }} import '{{ resource }}' '{{ name }}'

# Stop tracking a resource without deleting it.
rm resource: init
    terraform -chdir={{ dir }} state rm '{{ resource }}'
