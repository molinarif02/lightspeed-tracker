# Operations

## Install

```bash
git clone https://github.com/molinarif02/lightspeed-tracker.git
cd lightspeed-tracker
docker compose pull
docker compose up -d
docker compose logs -f
```

To build locally instead of pulling, use `docker compose up -d --build`.

A successful test logs a line like this:

```
2026-10-28 22:00:41,512 INFO down 912.4 Mbps, up 241.7 Mbps, ping 9.8 ms
```

## Update

With the prebuilt image:

```bash
docker compose pull
docker compose up -d
```

With a local build:

```bash
git pull
docker compose up -d --build
```

The database lives on the `lightspeed-data` volume, so it survives rebuilds.

## Releases and CI

`.github/workflows/image.yml` builds `linux/amd64` (x86_64) and `linux/arm64` with Buildx (arm64
is emulated with QEMU) and pushes the image to `ghcr.io/molinarif02/lightspeed-tracker`:

- **Push to `main`**: tags `latest` and `sha-<short>`
- **Tag `vX.Y.Z`**: tags `X.Y.Z` and `X.Y`
- **Pull request**: builds only, no push
- **Changes only to docs, Markdown or LICENSE**: skipped

To cut a release:

```bash
git tag v1.0.0 && git push origin v1.0.0
```

The workflow can also be started by hand from the Actions tab (`workflow_dispatch`).

The image is linked to this repository through the `org.opencontainers.image.source` label
in the `Dockerfile`, so the package inherits the repository's visibility. The repository is
public, so anyone can pull the image without logging in. For a fork kept private, change the
visibility under *Packages* → *lightspeed-tracker* → *Package settings* → *Danger Zone*.

## Run a test now

```bash
docker exec lightspeed-tracker speedtest --accept-license --accept-gdpr
```

This only prints the result and does not store it. To store an extra result, restart the
container more than 55 minutes after the last test, or just wait for the next hour.

## Backup and restore

The whole state is one SQLite file.

```bash
# backup
docker run --rm -v lightspeed-data:/data -v "$PWD":/backup alpine \
  cp /data/lightspeed.db /backup/lightspeed-$(date +%F).db

# restore (stop the app first)
docker compose stop
docker run --rm -v lightspeed-data:/data -v "$PWD":/backup alpine \
  sh -c 'cp /backup/lightspeed-YYYY-MM-DD.db /data/lightspeed.db && chown 1000:1000 /data/lightspeed.db'
docker compose start
```

`compose.yaml` gives the volume a fixed name, `lightspeed-data`, so these commands work
whatever the Compose project is called.

## Query the data

```bash
curl -s http://<host>:8080/api | jq '.days'     # per-day values for the last 7 days
```

Or open the database directly:

```bash
docker run --rm -v lightspeed-data:/data keinos/sqlite3 \
  sqlite3 /data/lightspeed.db 'SELECT * FROM daily ORDER BY day DESC LIMIT 7;'
```

## Reverse proxy

The app serves plain HTTP and uses no absolute URLs, so it works behind any proxy at the root
path. For Cloudflare Tunnel, see [cloudflare-tunnel.md](cloudflare-tunnel.md). A minimal Caddy example:

```
speed.lan {
    reverse_proxy lightspeed-tracker:8080
}
```

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `speedtest failed: ... Cannot read from socket` | No connectivity, or the server is unavailable. Pin another server with `SPEEDTEST_SERVER_ID`. |
| `sqlite3.OperationalError: unable to open database file` | `/data` isn't writable by uid 1000. See the storage section in [configuration](configuration.md#storage). |
| The chart is empty but the tables show data | The browser can't reach `cdn.jsdelivr.net`. The tables still work. |
| Image build fails at the `curl` step | The Ookla download URL or version changed. Check the [Ookla CLI page](https://www.speedtest.net/apps/cli) and set `OOKLA_VERSION`. |
| `unsupported arch` during the build | Only `aarch64`, `x86_64` and `armv7l` are mapped in the `Dockerfile`. |
| Results cap around 940 Mbps | That's the real throughput limit of a gigabit NIC, such as the Raspberry Pi 5's. |
| Times look off by one hour | Check `DISPLAY_TZ`. The container clock is UTC, which is expected. |

## Uninstall

```bash
docker compose down -v   # -v also removes the data volume
```
