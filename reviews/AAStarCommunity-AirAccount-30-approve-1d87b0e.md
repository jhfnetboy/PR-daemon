Approved on latest head `1d87b0e`.

The remaining blocker from my previous review is fixed. Check #1 now covers Cargo's short `-F` feature alias in addition to the long `--features` forms and `--all-features`:

```bash
--features export-secrets
--features=export-secrets
--features "export-secrets"
--features foo,export-secrets
--features foo export-secrets
-F export-secrets
-F=export-secrets
--all-features
```

I re-ran the local security check and it passes:

```text
=== Results: 4 passed, 0 failed ===
```

I also manually tested the current regex against the adversarial Cargo feature forms above. The production scan catches the `export-secrets` enabling forms, and the existing `cargo geiger --all-features` whitelist remains scoped to static analysis.

No remaining blocking issues from my side.
