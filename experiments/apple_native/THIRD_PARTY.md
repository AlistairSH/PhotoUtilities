# Algorithm references and attribution

The base native package has no linked or downloaded third-party dependencies.
The separate opt-in [SIFTBridge](SIFTBridge/README.md) statically links OpenCV
4.11.0 and its minimal dependencies; retained notices are in `SIFTBridge/Licenses`.
`SeededSampling.swift` independently expresses PCG64 arithmetic and the pinned
NumPy 2.0.2 unweighted, no-replacement choice algorithm in Swift, solely to preserve
`default_rng(0)` edge selection. It is not a general NumPy random replacement.
The initial state/increment and regression vectors were exported from the installed
pinned baseline. Floyd selection, partial Fisher–Yates shuffle and Lemire bounded
sampling follow these primary references:

- [NumPy 2.0.2 choice and shuffle](https://github.com/numpy/numpy/blob/v2.0.2/numpy/random/_generator.pyx)
- [NumPy 2.0.2 bounded sampling](https://github.com/numpy/numpy/blob/v2.0.2/numpy/random/src/distributions/distributions.c)
- [PCG64 arithmetic and license](https://github.com/numpy/numpy/blob/v2.0.2/numpy/random/src/pcg64/pcg64.h)

Compatibility is explicitly pinned and verified by full-vector hashes, including
both sides of NumPy's choice strategy switch. No source photograph or metadata
was sent with these public source lookups. Notices are retained below.

## NumPy license

Copyright (c) 2005-2024, NumPy Developers.
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are
met:

    * Redistributions of source code must retain the above copyright
       notice, this list of conditions and the following disclaimer.

    * Redistributions in binary form must reproduce the above
       copyright notice, this list of conditions and the following
       disclaimer in the documentation and/or other materials provided
       with the distribution.

    * Neither the name of the NumPy Developers nor the names of any
       contributors may be used to endorse or promote products derived
       from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
"AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

## PCG MIT notice

Copyright 2014 Melissa O'Neill
Copyright 2015 Robert Kern

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Filtering references

The edge-boundary investigation additionally consulted the pinned
[OpenCV 4.11 separable filters](https://github.com/opencv/opencv/blob/4.11.0/modules/imgproc/src/filter.simd.hpp)
and [magnitude arithmetic](https://github.com/opencv/opencv/blob/4.11.0/modules/core/src/mathfuncs_core.simd.hpp)
to identify accumulation order. The native implementation uses Swift floating-point
operations, not linked OpenCV code. Accelerate calls are compiled against the local
Apple SDK; no external package is introduced.
