Requesting changes for two quickstart commands that will fail for a user following the guide.

1. `docs/dk2-quickstart.md` copies the TA Dev Kit into a root-owned `/opt` directory without making it writable.

```bash
sudo mkdir -p /opt/dk2-ta-dev-kit
scp -r root@192.168.7.2:/usr/include/optee/export-ta_arm32 /opt/dk2-ta-dev-kit/
```

The first command creates `/opt/dk2-ta-dev-kit` as root; the second command runs `scp` as the normal macOS user and can fail with `Permission denied`. Please either use a user-writable path, or add an explicit ownership step before `scp`, for example:

```bash
sudo mkdir -p /opt/dk2-ta-dev-kit
sudo chown "$(whoami)" /opt/dk2-ta-dev-kit
scp -r root@192.168.7.2:/usr/include/optee/export-ta_arm32 /opt/dk2-ta-dev-kit/
```

2. The CreateKey verification endpoint is wrong.

The guide currently says:

```bash
curl -X POST http://192.168.7.2:3000/kms/CreateKey \
  -H "Content-Type: application/json" \
  -d '{"keyType":"secp256k1"}'
```

But the current KMS server route is `POST /CreateKey`, not `/kms/CreateKey`, and it requires the exact `x-amz-target: TrentService.CreateKey` header. Existing API docs and tests use:

```bash
curl -X POST http://192.168.7.2:3000/CreateKey \
  -H "Content-Type: application/json" \
  -H "x-amz-target: TrentService.CreateKey" \
  -d '{ ... AWS KMS CreateKey body ... }'
```

Please update the quickstart to use the real endpoint and a valid request body, or point users to `kms/test/run-api-tests.sh` for the full WebAuthn/passkey-backed CreateKey flow.

Non-blocking cleanup: the sample deploy output says `{"status":"ok","version":"0.19.3"}`, while `/health` currently returns `status: "healthy"` and `KMS_VERSION` is `0.19.0`. It would be less confusing if the quickstart sample matched the actual health response.
