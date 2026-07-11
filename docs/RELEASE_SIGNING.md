# Releasing signed installers

The [`release`](../.github/workflows/release.yml) workflow builds one-click
installers for Windows, macOS and Linux and attaches them to a GitHub Release.

> **New to this?** [`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md) is the
> step-by-step readiness list — dry-run, on-device testing, then signing.

**To cut a release:** push a tag, e.g.
```bash
git tag v2.4.0 && git push origin v2.4.0
```
(or run the workflow manually from the Actions tab and enter a version).

The installers build **whether or not** code-signing is configured. Without
signing they still work — users click through the OS "unverified app" prompt
(documented in [`INSTALL.md`](INSTALL.md)). Configure the secrets below to
produce **signed** (and, on macOS, **notarized**) installers that install with no
scary prompts.

Set these under **Repo → Settings → Secrets and variables → Actions**.

## Windows (Authenticode)

You need a code-signing certificate (OV or EV) from a CA (e.g. DigiCert, Sectigo,
SSL.com). Export it as a password-protected `.pfx`, then:

```bash
base64 -w0 your-cert.pfx        # copy the output into the secret
```

| Secret | Value |
| --- | --- |
| `WINDOWS_CERT_BASE64` | base64 of the `.pfx` |
| `WINDOWS_CERT_PASSWORD` | the `.pfx` password |

When present, the workflow signs `TempSensor-Setup-*.exe` with `signtool`
(SHA-256, RFC-3161 timestamp).

## macOS (Developer ID + notarization)

Requires a paid **Apple Developer** account.

1. Create a **Developer ID Application** certificate in your Apple Developer
   account, export it from Keychain as a `.p12`, and base64-encode it:
   ```bash
   base64 -i DeveloperID.p12 -o -    # copy output
   ```
2. Create an **App Store Connect API key** (Users and Access → Integrations →
   Keys) with the *Developer* role for notarization, and base64-encode the `.p8`.

| Secret | Value |
| --- | --- |
| `APPLE_CERT_BASE64` | base64 of the Developer ID `.p12` |
| `APPLE_CERT_PASSWORD` | the `.p12` password |
| `APPLE_SIGN_IDENTITY` | e.g. `Developer ID Application: Your Name (TEAMID)` |
| `APPLE_API_KEY_BASE64` | base64 of the notary `.p8` key |
| `APPLE_API_KEY_ID` | the key's ID |
| `APPLE_API_ISSUER` | the issuer UUID |

When the certificate secrets are present the app is signed with the hardened
runtime and the entitlements in
[`packaging/macos/entitlements.plist`](../packaging/macos/entitlements.plist);
when the notary key is also present the `.dmg` is notarized and stapled.

## Linux

No signing needed — the Linux artifact is a plain tarball of the onedir bundle.

## Building installers locally (unsigned)

You can build each installer on its own OS without any secrets:

- **Windows:** `packaging\windows\build_installer.ps1` (needs Inno Setup on PATH).
- **macOS:** `packaging/macos/build_dmg.sh`.
- **Linux:** `packaging/build.sh`, then `tar -C dist -czf TempSensor-linux.tar.gz temperature-hub`.

Set `APPLE_SIGN_IDENTITY` / the `APPLE_API_*` vars before running the macOS
script to sign locally.
