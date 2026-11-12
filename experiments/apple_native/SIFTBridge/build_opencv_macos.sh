#!/bin/sh
# Source is external: pinned OpenCV 4.11.0, never downloaded at application runtime.
set -eu
[ "$#" -eq 2 ] || { echo 'usage: build_opencv_macos.sh OPENCV_SOURCE NEW_BUILD_ROOT' >&2; exit 2; }
source_dir=$(CDPATH= cd -- "$1" && pwd)
build_root=$2
version_header="$source_dir/modules/core/include/opencv2/core/version.hpp"
python3 - "$version_header" <<'PYVERSION'
import re, sys
from pathlib import Path
text=Path(sys.argv[1]).read_text()
version=[int(re.search(r'#define\s+CV_VERSION_'+p+r'\s+(\d+)',text).group(1)) for p in ('MAJOR','MINOR','REVISION')]
if version != [4,11,0]: raise SystemExit('Expected pinned OpenCV 4.11.0 source')
PYVERSION
cmake_bin=${CMAKE_BIN:-cmake}
ninja_bin=${NINJA_BIN:-ninja}
[ ! -e "$build_root" ] || { echo 'Build root already exists; refusing overwrite' >&2; exit 2; }
mkdir -p "$build_root"
"$cmake_bin" -S "$source_dir" -B "$build_root/build" -G Ninja \
 -DCMAKE_MAKE_PROGRAM="$ninja_bin" -DCMAKE_BUILD_TYPE=Release \
 -DCMAKE_INSTALL_PREFIX="$build_root/install" -DCMAKE_OSX_DEPLOYMENT_TARGET=14.0 \
 -DBUILD_LIST=core,imgproc,features2d,calib3d -DBUILD_SHARED_LIBS=OFF \
 -DBUILD_TESTS=OFF -DBUILD_PERF_TESTS=OFF -DBUILD_EXAMPLES=OFF \
 -DBUILD_opencv_apps=OFF -DBUILD_opencv_python2=OFF -DBUILD_opencv_python3=OFF \
 -DBUILD_JAVA=OFF -DBUILD_opencv_objc=OFF -DWITH_OPENCL=OFF -DWITH_IPP=OFF \
 -DWITH_ITT=OFF -DWITH_PROTOBUF=OFF -DWITH_LAPACK=OFF -DWITH_ADE=OFF \
 -DWITH_EIGEN=OFF -DWITH_TBB=OFF -DWITH_OPENEXR=OFF -DWITH_JPEG=OFF \
 -DWITH_PNG=OFF -DWITH_TIFF=OFF -DWITH_WEBP=OFF -DWITH_OPENJPEG=OFF \
 -DWITH_FFMPEG=OFF -DWITH_AVFOUNDATION=OFF -DWITH_CAP_IOS=OFF \
 -DWITH_1394=OFF -DWITH_QUIRC=OFF -DWITH_FLATBUFFERS=OFF \
 -DBUILD_ZLIB=ON -DOPENCV_ENABLE_NONFREE=OFF
"$cmake_bin" --build "$build_root/build" --parallel "${BUILD_JOBS:-6}"
"$cmake_bin" --install "$build_root/build"
