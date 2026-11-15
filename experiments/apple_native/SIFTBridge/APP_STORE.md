# Framewise Mac App Store preparation

## Local sandbox test

Build with the macOS 27 SDK and the pinned OpenCV dependency described in [the build guide](README.md).

```sh
OPENCV_ROOT=/absolute/path/to/opencv/install \
  ./build_app.sh --store-candidate /absolute/path/to/Framewise-Store-Candidate.app
codesign --verify --strict /absolute/path/to/Framewise-Store-Candidate.app
codesign -d --entitlements :- /absolute/path/to/Framewise-Store-Candidate.app
```

The local candidate is ad-hoc signed. Its bundle ID is the development ID, which it shares with the regular test build. Quit that build before opening the candidate. The candidate adds App Sandbox and user-selected read/write access to the Photos-enabled configuration. It bundles the privacy text, privacy manifest and compiled dependency notices.

The Store candidate does not run Homebrew SANE. It accepts externally captured
sheets through **Add Saved Sheet…** and uses Image Capture for direct scans. The SANE setting is disabled in this build. Bundling a
SANE-based helper would require a dependency and license review, sandboxed USB
verification, and a signed distribution archive.

## Acceptance checks

Use disposable copies and a disposable System Photo Library. A successful build and signature check leave these workflows to test in the sandbox.

- Open individual JPEGs in Finder-selected folders, including an iCloud Drive folder and an external volume if you plan to support those. Add and remove a genre and Favorite, reopen the file, save a rotation, and move a test copy to Trash. Check existing embedded keywords and image data. Check that metadata failures leave the original intact and explain the limitation. Access to an adjacent legacy XMP file may be limited by the file selection grant.
- Choose from Photos with read/write access denied. Confirm review still works and unsaved genres report the limitation. Repeat with access granted. Verify native keyword write and search, Favorites, rotation, and the single system delete confirmation. Cancel deletion and check the asset remains.
- Include a RAW+JPEG pair in Photos and verify that a keyword applies to the selected library asset. Import a JPEG with existing and multiple scene keywords via Save to Photos. Check keyword search and that the import did not create duplicates.
- Open Help → Privacy Policy and verify the policy text and hosted link in the signed release.

## Sandbox test status

On November 14, 2026, the tester reported that the other sandbox checks passed. Removing an existing Photos genre was the exception. The refreshed candidate includes a fix for that case. Retest it by removing a previously saved genre and checking that Photos and Framewise agree.

## Release prerequisites

1. Install full Xcode with the macOS 27 SDK and sign in with the Apple Developer Program team that will publish the app. Confirm the final registered bundle identifier, marketing version and build number.
2. Review the [privacy policy text](Resources/PrivacyPolicy.txt), publish it at a public HTTPS address, and set that address both in App Store Connect and as `FramewisePrivacyPolicyURL` in the release Info.plist. The local bundle script accepts `FRAMEWISE_PRIVACY_POLICY_URL` for testing the link. Confirm the final App Privacy answers against the distributed binary and the policy.
3. Create the Xcode macOS app target and archive for Apple silicon with macOS 27 as the deployment minimum. Use the Framewise Swift sources and native Swift package products, and bundle the icon, dependency notices and privacy resources. Carry the sandbox, user-selected file and Photos capabilities and the two Photos usage descriptions into the target. The command-line candidate is for local validation.
4. Validate the distribution archive in Xcode and App Store Connect. Complete the product page, support URL, screenshots, age rating, export compliance and App Review contact and notes. Explain local analysis, automatic genre persistence, and how to exercise both pickers. Confirm the store listing and binary before submission.

[App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/) · [Mac App Sandbox](https://developer.apple.com/documentation/security/app-sandbox)
