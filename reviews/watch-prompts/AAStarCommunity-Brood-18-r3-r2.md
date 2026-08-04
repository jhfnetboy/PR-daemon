R2_INDEPENDENT:
- [Med] china-kms-tunnel-setup.md Step 5 — claims "frps.toml 没有 vhostHTTPSCertFile/vhostHTTPSKeyFile 这类字段" + "只有 frpc 端 https2http/https2https 插件这一条路". Both FALSE — frps supports vhostHTTPSCertFile/vhostHTTPSKeyFile (server-side TLS term). Mechanism (frpc https2http plugin) is valid; justification is a wrong absolute.
- [Med] china-node-architecture.md:63/116 vs china-kms-tunnel-setup.md:106 — setup: frps owns :443 (vhostHTTPSPort=443); architecture: nginx owns :443 (nginx :443 /* → frp). Mutually exclusive TLS terminator; never reconciled.
- [sec] All 3 docs — POST /CreateKey + POST /Sign over public tunnels, zero mention of real KMS KMS_API_KEY/x-api-key auth. = unauthenticated signing oracle.

R2_CONFIRM: 1, 2, 3 (from R1 merged)
R2_REJECT: none
R2_ADD: none
R2_STRATEGIC:
- Pick ONE :443 topology in both docs. Since KMS is root-path, nginx path-routing is pointless — topology A (drop nginx, frps owns 443 via https2http-on-frpc) is simpler.
- Auth gap is 3 rounds old, operationally blocking: api-key generate + x-api-key must be a mandatory Step.
- Fixing finding #1 is one line (delete the absolute, note frps-side vhostHTTPSCertFile/KeyFile as server-termination alternative).
R2_TRIAGE_CONFIRM: 4-round
