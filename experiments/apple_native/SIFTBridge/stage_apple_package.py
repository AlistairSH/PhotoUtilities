"""Stage sources and a built local XCFramework into a new package outside Git.
SwiftPM binary target paths must stay within their package. No dependency binary
is placed in the versioned source checkout.
"""
from __future__ import annotations
import argparse
import plistlib
import shutil
from pathlib import Path


def stage(framework, output):
    framework=framework.resolve();output=output.resolve()
    source=Path(__file__).resolve().parent.parent
    if output==source or source in output.parents or output in source.parents:
        raise ValueError('Stage outside the source tree')
    if any((parent/'.git').exists() for parent in [output]+list(output.parents)):
        raise ValueError('Staging output must stay outside Git checkouts')
    if output.exists(): raise ValueError('Output exists; refusing overwrite')
    if framework==output or framework in output.parents:
        raise ValueError('Staging output must not be inside the source XCFramework')
    if not framework.is_dir() or framework.suffix!='.xcframework':
        raise ValueError('Expected a built .xcframework directory')
    info=plistlib.loads((framework/'Info.plist').read_bytes())
    libraries=info.get('AvailableLibraries',[])
    slices={(row.get('SupportedPlatform'),row.get('SupportedPlatformVariant','')) for row in libraries}
    if not {('ios',''),('ios','simulator'),('macos','')}.issubset(slices):
        raise ValueError('Need iOS device, iOS Simulator and macOS slices')
    for row in libraries:
        identifier=row['LibraryIdentifier'];library=row['LibraryPath']
        path=(framework/identifier/library).resolve()
        if framework not in path.parents or not path.exists():
            raise ValueError('Missing or invalid library path in XCFramework')
    # Copy the analysis package too: the optional CLI depends on its Grouping API.
    shutil.copytree(source,output,ignore=shutil.ignore_patterns('.build','.swiftpm','__pycache__','Artifacts'))
    artifacts=output/'SIFTBridge/Artifacts';artifacts.mkdir()
    shutil.copytree(framework,artifacts/'opencv2.xcframework')
    return output/'SIFTBridge'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('framework',type=Path)
    parser.add_argument('output',type=Path,help='New external staging root, outside the source tree')
    args=parser.parse_args()
    try:
        package=stage(args.framework,args.output)
    except (ValueError,OSError) as error:
        parser.error(str(error))
    print('Add this local package to the app: '+str(package))
    print('Use its NativeSIFT library product; XCFramework selection is automatic.')


if __name__=='__main__':main()
