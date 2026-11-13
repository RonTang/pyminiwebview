# Third-party notices

## webview

`vendor/webview/webview.h` and `vendor/webview.h` come directly from
https://github.com/webview/webview.

- Tag: `0.12.0`
- Commit: `3ab4b5d722438fc8a13e6ca830c5e2372d19a01d`
- License: MIT; see `licenses/webview-LICENSE.txt`.
- Original copyright headers for Serge Zaitsev and Steffen André Langnes are retained.

Only `vendor/webview/webview.h` contains local changes. Every changed region is
marked with `pyminiwebview patch begin/end`, and the complete diff is stored in
`patches/0001-pyminiwebview-engine-extensions.patch`. See `vendor/README.md` for
the three-API patch cap and synchronization procedure.

## Microsoft WebView2 SDK

`vendor/WebView2.h` and `vendor/WebView2EnvironmentOptions.h` are the official
headers from NuGet package `Microsoft.Web.WebView2 1.0.2420.47`. The project
upgraded from upstream webview 0.12.0's `1.0.1150.38` baseline to use the stable
`ICoreWebView2Settings9` non-client region setting.

License: BSD 3-Clause; see `licenses/Microsoft-WebView2-LICENSE.txt`.
Original Microsoft copyright and license headers are retained.

## python-webview2

https://github.com/59de44955ebd/python-webview2 was the functional reference for
the original rewrite. The Python binding layer in pyminiwebview is independent;
the current vendored engine is based directly on the upstream tag listed above,
not on python-webview2's modified copy.
