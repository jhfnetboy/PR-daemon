The two earlier blockers are mostly addressed: the `/opt/dk2-ta-dev-kit` copy now fixes ownership before `scp`, and the quickstart no longer shows the invalid `/kms/CreateKey` curl.

I still need to request one change because the replacement API-test instruction points users at the wrong script for this DK2 flow:

```bash
cd /path/to/AirAccount && bash scripts/test-kms-api-simple.sh
```

That script is explicitly a QEMU Guest VM helper and its requests post to the root path:

```bash
curl -s -X POST http://localhost:3000/ \
  -H 'X-Amz-Target: TrentService.CreateKey' \
  ...
```

The current KMS server routes are path-specific, for example `POST /CreateKey` with `x-amz-target: TrentService.CreateKey`; `POST /` is the stats dashboard root and will not exercise the DK2 API flow. The script also starts `./kms-api-server` from the current directory, which does not match the DK2 deployment path in this guide.

Please point the quickstart to the current DK2/full API test instead, for example:

```bash
DK2_KMS_URL=http://192.168.7.2:3000 ./kms/test/run-api-tests.sh
```

or update the instruction to match the existing `docs/dk2-deployment-guide.md` verification section. After that change, the quickstart should be consistent with the implemented KMS routes and the DK2 deployment flow.
