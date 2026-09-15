# SmooDL Shortcut

`SmooDL` receives a URL from the Apple share sheet and calls the SmooDL service. Video jobs download automatically. Image and mixed-media posts show a multi-select preview before downloading.

The HTTPS service URL is embedded at release build time. Importing the Shortcut shows one setup field for the API Key; enter only the key, without a `Bearer` prefix. The shared template contains no credential. Subsequent runs reuse the entered key.

## Build

On an Apple Silicon Mac with Python 3 and the Shortcuts app signed into iCloud:

```sh
shortcuts/build.sh https://download.example.com
```

The build script downloads the pinned Cherri compiler, verifies its SHA-256 checksum, compiles the source, validates control-flow groups and emitted materialization JSON, and asks Apple's `shortcuts` command to sign the result for anyone. Transient signing failures are retried up to five times. The signed artifact is written to `shortcuts/dist/SmooDL.shortcut`.

Compile and validate without contacting a signing service:

```sh
shortcuts/build.sh https://smoodl.violetcho.tech --unsigned
```

If Apple's signing endpoint is temporarily unavailable, a maintainer may explicitly use Cherri's RoutineHub HubSign fallback:

```sh
shortcuts/build.sh https://download.example.com --hubsign
```

HubSign receives the generated workflow plist in order to sign it. Use this fallback only while the Shortcut contains public configuration and no API key, cookie, credential, or other secret. Rebuild with Apple's signer before the final public release when possible.

Do not add Cherri's `--derive-uuids` flag here. Version 2.3.0 assigns the same grouping identifier to nested control-flow blocks in this workflow; random UUID generation is required for a valid Shortcut.

For a local macOS smoke test, HTTP is allowed only for loopback addresses:

```sh
shortcuts/build.sh http://127.0.0.1:8000
```

## Release behavior

- Share-sheet input: text, URL, or Safari webpage
- No input: asks only for the media URL
- Multiple links: asks which URL to download
- Quality: `best_available`
- Watermark policy: `prefer_clean`
- Gallery: preview and select multiple items; all are selected initially
- Compatible images and videos: saved to Photos
- Other original-quality containers: saved under `iCloud Drive/Shortcuts/SmooDL/<job ID>/`, without overwriting existing files
- Server errors: displays the API error; a missing API key gets a dedicated explanation
- Polling: up to 300 refreshes, with one-second waits; requests and selection time are additional
- Completion reads the latest materialization result, including immediately completed jobs

Cancelling the native picker stops the Shortcut; it does not send a cancellation request to the server. Network errors and denied Photos/Files permissions may stop execution with Apple's own error dialog. The macOS import form and public authentication endpoints have been verified. A complete media download and save on iPhone has not yet been verified.

## Installation URL

Install from [smoodl.violetcho.tech/install](https://smoodl.violetcho.tech/install). This entry redirects (302, no-store) to [the iCloud release](https://www.icloud.com/shortcuts/f560167cd07b415295e4f190941ed76c). Choose **Add Shortcut**, fill the **SmooDL API Key** setup field, and confirm. The service URL is already set.

The production service keeps authentication enabled. `SMOODL_SHORTCUT_API_KEY` is an optional separate credential accepted alongside `SMOODL_API_KEY`, with the same API access; it is not a separate user account or job namespace. Rotate or clear the Shortcut key in the server `.env` and recreate the service to revoke it while leaving the original key valid. Keep at least the main key configured on the public deployment.

For updates, rebuild and import the signed file, choose **Share → Copy iCloud Link**, and replace the redirect target in `deploy/nginx-smoodl.conf`. Verify the published iCloud template still has an empty key field. The explicit introductory Comment action is required with Cherri 2.3.0: it prevents the compiler from omitting `ActionIndex=0`, which would cause Apple to discard the import question.
