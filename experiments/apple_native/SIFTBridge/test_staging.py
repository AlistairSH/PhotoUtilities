"""Test packaging layout/refusal with synthetic manifests, not binary validity."""
import plistlib
import tempfile
from pathlib import Path
from stage_apple_package import stage


def main():
    with tempfile.TemporaryDirectory(prefix='sift-staging-') as folder:
        root=Path(folder);framework=root/'test.xcframework';framework.mkdir()
        libraries=[]
        for identifier,platform,variant in [('ios-arm64','ios',''),('ios-arm64-simulator','ios','simulator'),('macos-arm64','macos','')]:
            library=framework/identifier/'opencv2.framework';library.mkdir(parents=True)
            libraries.append({'LibraryIdentifier':identifier,'LibraryPath':'opencv2.framework','SupportedPlatform':platform,'SupportedPlatformVariant':variant})
        (framework/'Info.plist').write_bytes(plistlib.dumps({'AvailableLibraries':libraries}))
        try: stage(framework,framework/'recursive')
        except ValueError: pass
        else: raise AssertionError('Recursive artifact copy allowed')
        package=stage(framework,root/'staged')
        assert (package/'Sources/NativeSIFT/SIFT.swift').exists()
        assert (package/'Artifacts/opencv2.xcframework/Info.plist').exists()
        assert (package.parent/'Sources/NativePhotoCore/Grouping.swift').exists()
        try: stage(framework,root/'staged')
        except ValueError: pass
        else: raise AssertionError('Overwrite allowed')
        libraries.pop()
        (framework/'Info.plist').write_bytes(plistlib.dumps({'AvailableLibraries':libraries}))
        try: stage(framework,root/'bad')
        except ValueError: pass
        else: raise AssertionError('Incomplete platform set accepted')
        assert not (root/'bad').exists()
    print('Passed external package layout, collision, recursive-copy and missing-slice checks (synthetic manifests only)')


if __name__=='__main__': main()
