# TLS certificates (Cloudflare Origin)

`nginx.prod.conf` terminates TLS using a **Cloudflare Origin certificate**.
Two files are expected in this directory (they are bind-mounted into the nginx
container):

| File                        | Mounted to                     | Perms |
|-----------------------------|--------------------------------|-------|
| `origin.crt`                | `/etc/ssl/certs/origin.crt`    | 644   |
| `origin.key`                | `/etc/ssl/private/origin.key`  | 600   |

## How to generate

1. Cloudflare dashboard → **SSL/TLS → Origin Server → Create Certificate**.
2. Under hostnames, include **every** domain served by this stack:
   ```
   maxpayads.com, *.maxpayads.com
   browsmac.org, *.browsmac.org
   clickspot.icu, *.clickspot.icu
   clickfilesetup.info, *.clickfilesetup.info
   rydestudio.info, *.rydestudio.info
   ```
3. Save the **Origin Certificate** PEM as `origin.crt` here.
4. Save the **Private Key** PEM as `origin.key` here.
5. Set each domain's **SSL/TLS mode to "Full (strict)"** in Cloudflare.
6. Run `bash deployment/3-setup-ssl.sh` to validate + install.

## Security

These are secrets. `origin.key` must never be committed or shared. The
`.gitignore` in this folder excludes both files.
