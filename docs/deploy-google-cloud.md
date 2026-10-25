# Host Contxt on Google Cloud

This guide puts your Contxt (Gnomon) on a server of your own in Google Cloud, always on, with
HTTPS on your own domain. It uses the private-server profile from [Operations](operations.md):
Docker Compose with the app, PostgreSQL and Caddy, on one Compute Engine VM.

Everything here runs in your own Google Cloud project, billed to you. Nothing in this guide
is done for you: run each command yourself, in order.

## What you get

```
internet --443--> Caddy (HTTPS, your domain) --> app :8787 (web app, API, /mcp)
                                                  |  heartbeat, knowledge agent, Claude Code
                                                  |  Gnomon's own n8n on 127.0.0.1:5678
                                                  +-> PostgreSQL :5432
```

- Only Caddy is reachable from the internet, on ports 80 and 443. The app, its MCP endpoint
  and PostgreSQL listen only inside the Compose network; n8n listens on the app container's
  own 127.0.0.1, so not even the other containers reach it.
- Every request needs the owner token (the web app's sign-in) or a model's own token (`/mcp`).
- The n8n inbox and error routes refuse anything that did not come straight from n8n inside
  the app container: Caddy answers them with 403, and the app refuses any post that carries a
  proxy's forwarding header.
- The sign-in link and tokens never appear in the logs: `docker compose logs` says to run
  `contxt token` instead, and the access log hides a token in an address.

## Why a VM, not Cloud Run

Cloud Run runs a container only while it answers requests, and may stop or replace it at any
time. Contxt needs the opposite:

- **Background work.** The heartbeat, the worker's clock, the knowledge agent's runs and
  Gnomon's own n8n run all the time, not just while a request is open.
- **A signed-in CLI.** The heartbeat and the knowledge agent run Claude Code, which keeps its
  login in a home folder. That login has to survive restarts, on a disk that stays.
- **Local state.** The Brain is a git repository of Markdown files, n8n keeps its own
  database, and the app keeps uploaded files and its sign-in key in its data folder. They
  belong on a persistent disk, not in a container that can vanish.

A small VM that is always on, with a persistent disk, fits all three, and costs about the
same.

## Machine size

| Machine | vCPU, memory | Good for | Rough cost (us-central1, on demand) |
|---|---|---|---|
| e2-medium | 2 shared, 4 GB | the app, PostgreSQL and Claude Code runs; n8n fits but is tight | about $25 a month |
| **e2-standard-2** (recommended) | 2, 8 GB | all of it, n8n and the speech model included | about $50 a month |
| e2-micro (free tier) | 2 shared, 1 GB | not enough: n8n alone wants about 0.5 GB | |

Disks: a 20 GB boot disk and a separate 30 GB data disk (pd-balanced), about $5 a month
together. The data disk holds Docker's data (the volumes), the Brain and the backups, and is
kept when the VM is deleted.

## Costs, roughly

| Item | Per month |
|---|---|
| VM (e2-standard-2, always on) | $45 to $55 (a 1-year commitment takes off about a third) |
| Disks (50 GB pd-balanced) | about $5 |
| Static external IPv4 address | about $3 to $4 |
| Disk snapshots (daily, 14 days) | $1 to $3 |
| Cloud Storage backups (Standard, a few GB) | under $1 |
| Network out | under $1 for one person's use |
| **Total** | **about $55 to $70** (about $35 on e2-medium) |

Your Claude plan (for Claude Code) and your domain are separate. Prices change: check the
[Google Cloud pricing calculator](https://cloud.google.com/products/calculator) for your
region.

## Before you start

- A Google Cloud project with billing, and the `gcloud` CLI signed in on your own computer
  (`gcloud auth login`, then `gcloud config set project YOUR_PROJECT`).
- A domain whose DNS you can change, for example `contxt.example.com`.
- Your Claude account, to sign Claude Code in on the server.

The commands below use these names; change them to yours:

```bash
REGION=us-central1
ZONE=us-central1-a
VM=contxt
DOMAIN=contxt.example.com
BUCKET=YOUR_PROJECT-contxt-backups   # bucket names are global: make it unique
```

## 1. Network: a static address and the firewall

```bash
gcloud services enable compute.googleapis.com storage.googleapis.com
gcloud compute addresses create contxt-ip --region "$REGION"
gcloud compute addresses describe contxt-ip --region "$REGION" --format='value(address)'
```

Only HTTPS (and HTTP, which Caddy uses to get its certificate and to send you to HTTPS) is open
to the internet. SSH is open only to Google's Identity-Aware Proxy, so you connect with
`gcloud compute ssh --tunnel-through-iap` and port 22 is closed to everyone else:

```bash
gcloud compute firewall-rules create contxt-web \
  --network default --direction INGRESS --target-tags contxt \
  --allow tcp:80,tcp:443,udp:443 --source-ranges 0.0.0.0/0
gcloud compute firewall-rules create contxt-ssh-iap \
  --network default --direction INGRESS --target-tags contxt \
  --allow tcp:22 --source-ranges 35.235.240.0/20
```

The default network also has a rule that opens SSH (and RDP) to the whole internet. If nothing
else in the project needs them, delete them:

```bash
gcloud compute firewall-rules delete default-allow-ssh default-allow-rdp
```

Never open 8787 (the app), 5678 (n8n) or 5432 (PostgreSQL): nothing needs them from outside.

## 2. DNS

At your DNS provider, add an **A record** for `$DOMAIN` pointing at the address the
`describe` command printed. Wait until it resolves before you start Caddy (step 6), or
Let's Encrypt cannot check the name:

```bash
dig +short "$DOMAIN"     # prints the static address when it is ready
```

## 3. The backup bucket and the VM's identity

The VM gets a service account of its own that may only add objects to the backup bucket:

```bash
gcloud iam service-accounts create contxt-vm --display-name "Contxt VM"
SA="contxt-vm@$(gcloud config get-value project).iam.gserviceaccount.com"
gcloud storage buckets create "gs://$BUCKET" --location "$REGION" \
  --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member "serviceAccount:$SA" --role roles/storage.objectCreator
```

Keep 30 days of backups, then delete them on their own:

```bash
cat > lifecycle.json <<'EOF'
{"rule": [{"action": {"type": "Delete"}, "condition": {"age": 30}}]}
EOF
gcloud storage buckets update "gs://$BUCKET" --lifecycle-file lifecycle.json
```

## 4. The VM and its data disk

```bash
gcloud compute instances create "$VM" \
  --zone "$ZONE" --machine-type e2-standard-2 \
  --image-family debian-12 --image-project debian-cloud \
  --boot-disk-size 20GB --boot-disk-type pd-balanced \
  --create-disk name=contxt-data,size=30GB,type=pd-balanced,device-name=contxt-data,auto-delete=no \
  --address contxt-ip --tags contxt \
  --service-account "$SA" --scopes cloud-platform \
  --shielded-secure-boot --shielded-vtpm --shielded-integrity-monitoring
```

Daily snapshots of the data disk, kept 14 days:

```bash
gcloud compute resource-policies create snapshot-schedule contxt-daily \
  --region "$REGION" --daily-schedule --start-time 04:00 --max-retention-days 14
gcloud compute disks add-resource-policies contxt-data \
  --zone "$ZONE" --resource-policies contxt-daily
```

A snapshot holds everything on the disk, including your owner token and Claude Code's login.
Keep the project's access to yourself.

## 5. On the VM: the disk, Docker and Contxt

Connect:

```bash
gcloud compute ssh "$VM" --zone "$ZONE" --tunnel-through-iap
```

Format and mount the data disk (once), and keep it mounted across restarts:

```bash
sudo mkfs.ext4 -m 0 -E lazy_itable_init=0,lazy_journal_init=0,discard /dev/disk/by-id/google-contxt-data
sudo mkdir -p /srv/contxt
echo "UUID=$(sudo blkid -s UUID -o value /dev/disk/by-id/google-contxt-data) /srv/contxt ext4 discard,defaults,nofail 0 2" | sudo tee -a /etc/fstab
sudo mount /srv/contxt
sudo chown "$(id -u):$(id -g)" /srv/contxt
```

Install Docker from Docker's own repository, with its data on the data disk:

```bash
sudo apt-get update && sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list
sudo mkdir -p /etc/docker /srv/contxt/docker
echo '{"data-root": "/srv/contxt/docker", "log-driver": "local"}' | sudo tee /etc/docker/daemon.json
sudo apt-get update && sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker "$USER"
exit
```

Connect again (so the `docker` group applies), then get Contxt and build its image (a few
minutes; the image carries Node.js 22, npm and Claude Code):

```bash
gcloud compute ssh "$VM" --zone "$ZONE" --tunnel-through-iap
git clone https://github.com/rami-guzlan/Contxt.git /srv/contxt/app
cd /srv/contxt/app
docker compose build app
```

## 6. Your Brain and settings

Make the Brain on the data disk, outside the repository. `empty` starts your own; or copy a
Brain you already have (the folder that holds `vault/`) to `/srv/contxt/home/brain` with git
or `scp` instead. Setup also fetches the small model that matches requests by meaning (about
70 MB, once, into the Brain):

```bash
mkdir -p /srv/contxt/home
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v /srv/contxt/home:/home-dir contxt:latest \
  contxt --home /home-dir setup --brain empty
```

Then write the settings. The owner token and the database password are made here and go
straight into `.env`, which only you can read; they are never printed:

```bash
cd /srv/contxt/app
umask 077
cat > .env <<EOF
CONTXT_NAME=Contxt
CONTXT_TIMEZONE=America/Denver
CONTXT_DOMAIN=$DOMAIN
CONTXT_OWNER_TOKEN=$(docker run --rm contxt:latest contxt token --new)
POSTGRES_PASSWORD=$(openssl rand -hex 24)
CONTXT_UID=$(id -u)
CONTXT_GID=$(id -g)
BRAIN_HOST_DIR=/srv/contxt/home/brain
EXPORTS_HOST_DIR=/srv/contxt/home/outputs
COMPOSE_FILE=compose.yaml:docker/compose.server.yaml
EOF
```

(`$DOMAIN` is not set on the VM: write your domain there. Set `CONTXT_TIMEZONE` to yours, an
IANA name; it sets the app's schedules and the container's clock. `COMPOSE_FILE` makes every
`docker compose` command in this folder use the private-server profile.)

For Scout, put the folders it should read under one folder and add
`SCOUT_HOST_DIR=/srv/contxt/scout` to `.env`; they appear in the container at `/scout`,
read-only. In Scout's settings, add `/scout/<folder>`.

## 7. Start it

```bash
docker compose up -d
docker compose ps
curl -fsS "https://YOUR_DOMAIN/api/health"
```

`ps` shows `app` and `db` healthy and `proxy` up; Caddy gets the certificate on the first
request (`docker compose logs proxy` says so).

## 8. Sign in

```bash
docker compose exec app contxt token
```

prints your sign-in link, in your SSH session only. Open it in your own browser: it signs that
browser in with a cookie for 30 days. Or open `https://YOUR_DOMAIN`, choose to paste a key,
and paste only the part after `token=`. The link is your key: never paste it into a chat, an
email or a file.

## 9. Sign Claude Code in (by hand, once)

The heartbeat, the knowledge agent and *Run now* use Claude Code inside the app container.
Sign it in to your Claude account:

```bash
docker compose exec -it app claude auth login
```

It prints an address: open it in your own browser, sign in, and paste the code it shows back
into the terminal. The login is kept in the data volume (`/data/home/.claude`), so it survives
restarts, rebuilds and updates. Check it with `docker compose exec app claude auth status`,
then in the app: Settings, AI apps, **Check again**.

## 10. Gnomon's own n8n (optional)

In the app, the heartbeat's **Host n8n here** installs a pinned n8n into the data volume (a
few minutes and a few hundred MB, once) and runs it on the app container's 127.0.0.1:5678. It
starts with the app from then on.

To sign in to your apps in n8n, you need its page in your own browser. n8n listens only inside
the app container, so reach it through a short-lived forwarder that shares the container's
network, and an SSH tunnel to it. On the VM:

```bash
APP=$(docker compose ps -q app)
docker run -d --rm --name n8n-forward --network "container:$APP" alpine/socat \
  TCP-LISTEN:5679,fork,reuseaddr TCP:127.0.0.1:5678
docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' "$APP"
```

On your own computer, with the first address `inspect` printed:

```bash
gcloud compute ssh "$VM" --zone "$ZONE" --tunnel-through-iap -- -N -L 5678:APP_ADDRESS:5679
```

Open `http://127.0.0.1:5678` and sign in to your apps there (their sign-in pages return to
that same address). When you are done, stop the tunnel and the forwarder
(`docker stop n8n-forward`): while the forwarder runs, n8n is reachable inside the Compose
network, never from the internet.

## 11. Backups to Cloud Storage

A daily backup of the database, the files and the Brain, copied to the bucket. On the VM:

```bash
cat > /srv/contxt/backup.sh <<'EOF'
#!/bin/sh
set -eu
cd /srv/contxt/app
name="contxt-$(date -u +%Y%m%d-%H%M%S).zip"
docker compose exec -T app contxt --env-file "" backup "/data/backups/$name" --with-brain
docker compose cp "app:/data/backups/$name" "/srv/contxt/$name"
docker compose exec -T app rm "/data/backups/$name"
gcloud storage cp "/srv/contxt/$name" "gs://BUCKET/$name"
rm "/srv/contxt/$name"
EOF
sed -i "s|BUCKET|$BUCKET|" /srv/contxt/backup.sh   # or write your bucket's name in it
chmod 700 /srv/contxt/backup.sh
/srv/contxt/backup.sh
( crontab -l 2>/dev/null; echo "30 3 * * * /srv/contxt/backup.sh >> /srv/contxt/backup.log 2>&1" ) | crontab -
```

(`$BUCKET` is not set on the VM either: write your bucket's name.) The backup holds the
database rows, the uploaded files, and the Brain's vault with the original bytes of filed
documents. It does not hold the models (they download again), Claude Code's login, or n8n's
own data (sign in again after a restore). The disk snapshots from step 4 hold those.

To restore, on a fresh install with an empty data volume:

```bash
gcloud storage cp "gs://$BUCKET/contxt-YYYYMMDD-HHMMSS.zip" /srv/contxt/restore.zip
docker compose run --rm -T -v /srv/contxt/restore.zip:/restore.zip:ro app \
  contxt --env-file "" restore /restore.zip --brain-dir /data/restored-brain
```

## 12. Updates

```bash
cd /srv/contxt/app
/srv/contxt/backup.sh
git pull
docker compose up -d --build --remove-orphans
docker compose ps
```

Migrations run when the app starts. Claude Code updates with the image (its own updater is
off in the container); `docker compose build --pull --no-cache app` gets the newest base
images and Claude Code. Debian's own updates: `sudo apt-get update && sudo apt-get upgrade`,
and turn on `unattended-upgrades` for security fixes.

## What has to be done by hand

| What | When | How |
|---|---|---|
| Sign Claude Code in | once, and if its login expires | `docker compose exec -it app claude auth login` |
| Sign in to your apps in n8n | once per app | step 10 |
| Download the speech model (optional, about 480 MB) | once | `docker compose exec app contxt models --download` |
| Keep `.env` and the snapshots to yourself | always | they hold the owner token and the database password |

## Instead of a public domain: Tailscale

If only your own devices use Contxt, keep it off the internet altogether. Install
[Tailscale](https://tailscale.com/kb/1031/install-linux) on the VM and on your devices, and let
Tailscale give it HTTPS on your tailnet's name:

- Skip the `contxt-web` firewall rule and the DNS record (steps 1 and 2): no port is open to the
  internet but IAP's SSH.
- Use the local profile: `docker compose up -d`, which publishes the app on the VM's
  127.0.0.1:8787 only (SQLite in the data volume; no Caddy, no PostgreSQL).
- In `.env`, instead of `CONTXT_DOMAIN`: `CONTXT_PUBLIC_URL=https://contxt.YOUR-TAILNET.ts.net`,
  `CONTXT_ALLOWED_ORIGINS` set to the same address, and `CONTXT_TRUST_PROXY=1`.
- Then `sudo tailscale up --hostname contxt` and `sudo tailscale serve --bg 8787`: Tailscale
  serves `https://contxt.YOUR-TAILNET.ts.net` to your tailnet alone, with its own
  certificate.

Everything else (Claude Code's sign-in, n8n, backups, updates) is the same. The app refuses n8n
posts that Tailscale passes on, as it does for Caddy.
