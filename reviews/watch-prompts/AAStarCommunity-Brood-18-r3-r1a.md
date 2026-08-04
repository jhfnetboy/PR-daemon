FILES:
- research/global-network/china-kms-tunnel-setup.md — frp TLS termination moved to frpc https2http plugin; DNS-01 certbot; test API body
- research/global-network/china-node-architecture.md — KMS root-path service, /Sign API, no separate UI; paths updated
- research/global-network/cloudflare-tunnel-global-availability.md — frp auth.token in [auth] section; webServer bound to localhost with password

FINDINGS:
1. [Medium] research/global-network/china-kms-tunnel-setup.md:224 — `https2http` plugin config uses `[proxies.plugin]` but frp syntax requires `[proxies.plugin]` under `[[proxies]]`; verify TOML nesting | Confirm frp plugin TOML structure
2. [Low] research/global-network/china-kms-tunnel-setup.md:270 — `openssl rand -hex 64` generates 64 bytes, but P-256/secp256k1 public key is 33 bytes (compressed) or 65 bytes (uncompressed); 04+64 bytes = 65 bytes uncompressed, correct | No issue, correct format

TRIAGE: significant — Core network architecture and security config changes

SKELETON:
The diff correctly moves TLS termination to the frpc side using the https2http plugin, which is the only supported path for vhost HTTPS in frp. The webServer hardening (localhost bind, strong password) is a good security improvement. The test API body now uses a realistic PasskeyPublicKey format. One point to verify: the TOML structure for the plugin config — ensure `[proxies.plugin]` is correctly nested under the `[[proxies]]` array element, as frp's TOML parsing can be strict about this.