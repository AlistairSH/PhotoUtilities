"""Build a local OpenCV XCFramework for Swift, using pinned upstream tooling.
Needs full Xcode and iPhoneOS/iPhoneSimulator SDKs. Does not install/change Xcode.
"""
from __future__ import annotations
import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path,help='Verified OpenCV 4.11.0 source tree')
    parser.add_argument('output',type=Path,help='New directory outside Git')
    args=parser.parse_args()
    if not shutil.which('xcodebuild'):
        parser.error('Full Xcode is required; Command Line Tools alone cannot build iOS slices. Select an installed Xcode developer directory first.')
    if subprocess.run(['xcodebuild','-version'],capture_output=True).returncode:
        parser.error('Full Xcode is required; the selected developer directory only provides Command Line Tools.')
    for sdk in ('macosx','iphoneos','iphonesimulator'):
        result=subprocess.run(['xcrun','--sdk',sdk,'--show-sdk-path'],capture_output=True,text=True)
        if result.returncode: parser.error('Required Apple SDK unavailable: '+sdk)
        print(result.stdout.strip())
    if not shutil.which('cmake'):
        parser.error('CMake must be on PATH')
    if args.output.exists(): parser.error('Output exists; refusing overwrite')
    source=args.source.resolve()
    version=(source/'modules/core/include/opencv2/core/version.hpp').read_text()
    import re
    numbers=[int(re.search(r'#define\s+CV_VERSION_'+part+r'\s+(\d+)',version).group(1)) for part in ('MAJOR','MINOR','REVISION')]
    if numbers != [4,11,0]: parser.error('Expected pinned OpenCV 4.11.0 source')
    keep={'core','imgproc','features2d','flann','calib3d'}
    excluded=sorted(p.name for p in (source/'modules').iterdir() if p.is_dir() and (p/'CMakeLists.txt').exists() and p.name not in keep)
    command=[sys.executable,str(source/'platforms/apple/build_xcframework.py'),
             '--out',str(args.output.resolve()),'--build_only_specified_archs',
             '--iphoneos_archs','arm64','--iphonesimulator_archs','arm64,x86_64',
             '--macos_archs','arm64,x86_64','--without','objc','--disable-swift','--disable-bitcode']
    for module in excluded: command += ['--without',module]
    for feature in ('OPENCL','IPP','ITT','LAPACK','ADE','EIGEN','TBB','FFMPEG','AVFOUNDATION'):
        command += ['--disable',feature]
    print('Building device, simulator and macOS slices; this recipe still requires validation on a full Xcode host.',flush=True)
    subprocess.run(command,check=True,cwd=source)
    print('Stage the built artifact with stage_apple_package.py: '+str(args.output.resolve()/'opencv2.xcframework'))


if __name__=='__main__': main()
