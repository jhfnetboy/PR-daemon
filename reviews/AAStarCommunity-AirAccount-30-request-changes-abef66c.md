Requesting changes on the latest head `abef66c`.

The previous long-form Cargo feature cases are now covered, but check #1 still misses Cargo's short feature alias:

```bash
cargo build -F export-secrets
cargo build -F=export-secrets
```

`cargo build --help` documents `-F, --features <FEATURES>`, so this is equivalent to enabling the same feature. The current gate only matches:

```bash
(--features[[:space:]+=].*export-secrets|--all-features)
```

I tested the current regex against the adversarial cases. It matches these:

```bash
--features export-secrets
--features=export-secrets
--features "export-secrets"
--features foo,export-secrets
--all-features
```

but it does not match:

```bash
-F export-secrets
-F=export-secrets
```

That means a future production deploy/CI script could still enable the secret-export path with valid Cargo syntax while `scripts/security-check.sh` passes. Since this PR's purpose is to prevent `ExportPrivateKey` / `export_key` from reaching production builds, the gate should also reject `-F` forms before merge.

Suggested fix:

- Extend check #1 to catch `-F export-secrets` and `-F=export-secrets`.
- Add explicit adversarial test cases for every accepted Cargo feature form: `--features ...`, `--features=...`, quoted lists, comma lists, `-F ...`, `-F=...`, and `--all-features`.
- Keep the existing `cargo geiger --all-features` whitelist for static analysis only.
