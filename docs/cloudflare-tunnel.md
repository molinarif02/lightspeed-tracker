# Publishing with Cloudflare Tunnel

A Cloudflare Tunnel makes the page reachable at a public hostname, such as
`speed.example.com`, without opening any port on your router. `cloudflared` makes an
outbound connection to Cloudflare, and Cloudflare forwards requests through it to the app.

```
browser ──► Cloudflare (TLS, Access) ──► tunnel ──► cloudflared ──► lightspeed:8080
```

## 1. Create the tunnel

1. In the Cloudflare dashboard, go to **Zero Trust → Networks → Tunnels → Create a tunnel**.
2. Choose **Cloudflared** as the connector type and give the tunnel a name, for example `lightspeed`.
3. On the **Install connector** step, copy the token. It's the long string after `--token`
   in the `docker run` example.
4. Under **Public hostnames**, add:

   | Field | Value |
   |---|---|
   | Subdomain / Domain | for example `speed` . `example.com` |
   | Path | *(empty)* |
   | Service type | `HTTP` |
   | URL | `lightspeed:8080` |

   `lightspeed` is the Compose service name, which resolves on the Compose network that
   `cloudflared` shares with the app.

## 2. Run cloudflared next to the app

```bash
cp .env.example .env
# edit .env: paste the token into TUNNEL_TOKEN; keep COMPOSE_PROFILES=tunnel
docker compose up -d
docker compose logs -f cloudflared
```

Look for `Registered tunnel connection` in the logs. The page is then live at
`https://speed.example.com/`, and also at `/index.html`.

Keep the token secret. `.env` is already in `.gitignore`.

### Already running cloudflared on the host?

Skip the sidecar: leave `COMPOSE_PROFILES` unset and point the public hostname at
`http://localhost:8080` instead. The `ports:` mapping in `compose.yaml` publishes the app
on the host.

### Tunnel only, no LAN port

To reach the app only through the tunnel, remove the `ports:` section from the
`lightspeed` service. `cloudflared` still reaches it over the Compose network.

## 3. Protect it with Cloudflare Access (recommended)

The app has no login, and `/api` returns all stored data. To restrict who can open it:

1. Go to **Zero Trust → Access → Applications → Add an application → Self-hosted**.
2. Set the application domain to the same hostname, for example `speed.example.com`.
3. Add a policy, for example **Allow**, with the rule **Emails**: your address. Or use a
   one-time PIN, or your identity provider.

Visitors then have to authenticate with Cloudflare before any request reaches the Pi.

## Notes

- **Caching**: the app sends `Cache-Control: no-store`, so Cloudflare always serves fresh data.
  The page reloads itself every 5 minutes.
- **Chart.js** is loaded by the visitor's browser from `cdn.jsdelivr.net`, not through the tunnel.
- **Health check**: `/healthz` returns `ok`. It's what the container's `HEALTHCHECK` uses, and
  it works for external uptime monitors too. If you use Access, add a bypass policy for that
  path so the monitor isn't asked to log in.
