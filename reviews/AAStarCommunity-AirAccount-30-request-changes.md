Requesting changes for the security gate itself. The latest commit fixed the function-scope check and docker scan scope, but the production `export-secrets` feature detection is still too narrow.

`scripts/security-check.sh` currently detects only:

```bash
--features export-secrets
```

but Cargo also accepts equivalent forms such as:

```bash
--features=export-secrets
--features "export-secrets"
--features foo,export-secrets
--all-features
```

I verified the current regex misses those forms. That means a future production deploy/CI script could enable the secret-export code path with valid Cargo syntax while this custom security check still passes. Since this PR's purpose is to prevent `ExportPrivateKey`/`export_key` from reaching production, the gate should cover these forms before merge.

Suggested fix:

- Broaden check #1 to match `--features=...`, quoted feature lists, comma-separated feature lists, and whitespace-separated feature lists containing `export-secrets`.
- Treat `--all-features` as forbidden in production build/deploy paths.
- Keep an explicit whitelist for the intentional `cargo geiger --all-features` static-analysis step in `.github/workflows/security-audit.yml`.
