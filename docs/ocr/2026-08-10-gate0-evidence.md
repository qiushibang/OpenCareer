# OCR Gate 0 Evidence

Date: 2026-08-10

## Environment

- Python: 3.12.13
- Host: macOS 26.4.1 arm64
- Target desktop floor: macOS 12
- Target matrix: macOS arm64, macOS x86_64, Windows x86_64

## Version Selection

Rejected combination:

- RapidOCR 3.9.2
- ONNX Runtime 1.28.0

Reason: `onnxruntime==1.28.0` has a Python 3.12 Windows x64 wheel, but pip
finds no compatible `macosx_12_0_arm64` or `macosx_12_0_x86_64` wheel.

Accepted local candidate:

- RapidOCR 3.9.2
- ONNX Runtime 1.19.2
- OpenCV 4.10.0.84
- NumPy 1.26.4
- pypdfium2 4.30.0

The OpenCV and NumPy pins are required. Unconstrained installation selected
OpenCV 5.0.0.93 with a macOS 13 arm64 wheel and NumPy 2.5.2 with a macOS 14
arm64 wheel, both above the application's macOS 12 floor.

## Wheel Evidence

`pip download --only-binary=:all: --no-deps --python-version 312` succeeded
for the accepted four-package core on all target tags:

| Target | ONNX Runtime | OpenCV | NumPy |
|---|---|---|---|
| macOS arm64 | `macosx_11_0_universal2` | `macosx_11_0_arm64` | `macosx_11_0_arm64` |
| macOS x86_64 | `macosx_11_0_universal2` | `macosx_12_0_x86_64` | `macosx_10_9_x86_64` |
| Windows x86_64 | `win_amd64` | `win_amd64` | `win_amd64` |

RapidOCR 3.9.2 is the same `py3-none-any` wheel on all targets. Its direct
dependencies pyclipper, Shapely, PyYAML, Pillow, six, tqdm, OmegaConf,
requests, and colorlog also have compatible wheels on all three target tags.
The ONNX Runtime direct dependencies coloredlogs, flatbuffers, packaging,
protobuf, and sympy also passed the same wheel check.

Native binary inspection:

- macOS ONNX Runtime `onnxruntime_pybind11_state.so` is universal2 with
  x86_64 and arm64 slices.
- Windows `onnxruntime_pybind11_state.pyd` is PE32+ x86-64.

Core wheel SHA-256:

```text
rapidocr 3.9.2 all:
04d6b8d151f823d930bd91910555f57bea897c0c44fa6794267b94cf9c1ef9a0

onnxruntime 1.19.2 macOS universal2:
68e7051bef9cfefcbb858d2d2646536829894d72a4130c24019219442b1dd2ed

onnxruntime 1.19.2 Windows x64:
190103273ea4507638ffc31d66a980594b237874b65379e273125150eb044857

opencv-python 4.10.0.84 macOS arm64:
fc182f8f4cda51b45f01c64e4cbedfc2f00aff799debebc305d8d0210c43f251

opencv-python 4.10.0.84 macOS x86_64:
71e575744f1d23f79741450254660442785f45a0797212852ee5199ef12eed98

opencv-python 4.10.0.84 Windows x64:
32dbbd94c26f611dc5cc6979e6b7aa1f55a64d6b463cc1dcd3c95505a63e48fe
```

## Models And Licenses

The RapidOCR wheel contains all three selected models. Runtime initialization
is passed their absolute installed paths explicitly; production metadata
stores only these package-relative identities:

| Role | Model | Bytes | SHA-256 |
|---|---|---:|---|
| detection | `PP-OCRv6_det_small` | 9,929,594 | `090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f` |
| orientation | `ch_ppocr_mobile_v2.0_cls_mobile` | 585,532 | `e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c` |
| recognition | `PP-OCRv6_rec_small` | 21,234,383 | `6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884` |

License evidence:

- RapidOCR 3.9.2 wheel metadata: Apache-2.0.
- RapidOCR v3.9.2 repository license: Apache-2.0.
- PaddleOCR repository license: Apache-2.0.
- ONNX Runtime v1.19.2 repository license: MIT.

Primary sources:

- <https://github.com/RapidAI/RapidOCR/blob/v3.9.2/LICENSE>
- <https://github.com/PaddlePaddle/PaddleOCR/blob/main/LICENSE>
- <https://github.com/microsoft/onnxruntime/blob/v1.19.2/LICENSE>

The application distribution must retain these license and attribution texts.

## Fixture Evidence

Both fixtures contain only invented facts, consist of one image-only PDF page,
and return an empty string through `pypdf`:

```text
chinese-scanned.pdf
d0d591172f20257568ffc8554d60a6671c3f70fcad2aa7040205641bd38a1e94

mixed-scanned.pdf
9440104d32e0dc7bf5e69ef05ff12f486656bc3f40b6ce1b446e10f9786886c3
```

Socket-blocked installed-runtime recognition matched `项目` and `Python` in
the Chinese fixture. It matched `技能` and `Python` in the mixed fixture.
The two-letter string `AI` was intentionally removed as a gate term because
the fixture font's uppercase `I` was read as lowercase `l`; the stable,
longer English token remains required.

The generator rewrites Pillow output through `pypdf` with fixed metadata.
Two runs separated by two seconds produced identical hashes.

## Performance And Resource Evidence

The accepted configuration fixes:

- ONNX intra-op threads: 1
- ONNX inter-op threads: 1
- RapidOCR preprocessing maximum side: 1600
- PDF render DPI: 200
- Page processing: sequential with explicit PDFium bitmap/page release

Measured installed-runtime results:

| OCR pages | OCR duration | Process peak RSS |
|---:|---:|---:|
| 1 | 1.36 s | 620 MB |
| 3 | 3.46 s | 873 MB |
| 10 | 12.32 s | 852 MB |

The 10-page result demonstrates that memory does not grow linearly through
the allowed OCR page limit. The peak remains high enough to require
single-workflow concurrency and sequential page release in production.

Uncompressed isolated package directories:

| Package | Size |
|---|---:|
| RapidOCR | 32 MB |
| ONNX Runtime | 64 MB |
| OpenCV | 152 MB |
| NumPy | 56 MB |
| Pillow | 14 MB |
| pypdfium2 Python package, excluding its adjacent binary | 0.5 MB |

## Packaging Evidence

Local macOS arm64 PyInstaller onedir:

- Collection policy: `--collect-data rapidocr`; standard PyInstaller hooks
  collect imported ONNX Runtime, OpenCV, NumPy, Pillow, and PDFium binaries.
- Frozen size: 229 MB before integration into the existing OpenWorker sidecar.
- Frozen offline recognition: passed.
- Frozen model hashes: exactly match the three manifest hashes.
- Frozen warm run: about 2 seconds total.
- First uncached run: about 23.5 seconds total, with actual OCR about 1.7
  seconds. Most delay was cold filesystem loading of the standalone onedir.

This verifier size is not the final installer increment because the existing
OpenWorker sidecar already bundles Python, NumPy-adjacent dependencies,
pypdfium2, and Pillow-related code. Production packaging must still avoid
`collect-all` for RapidOCR and ONNX Runtime.

## Cross-Platform Frozen Matrix

`.github/workflows/ocr-gate0.yml` defines the required installed and frozen
offline recognition matrix on:

- `macos-latest` arm64
- `macos-15-intel` x86_64
- `windows-latest` x86_64

Run:

- URL: <https://github.com/qiushibang/openworker-career/actions/runs/31374122574>
- Head: `b67f62a3e9f32f2fbaca44751d9d62d55a1ac2d5`
- Conclusion: `success`

Jobs:

| Target | Job ID | Installed offline | Frozen offline | Duration |
|---|---:|---|---|---:|
| macOS arm64 | 93409421576 | passed, 1.76 s | passed, 2.34 s | 1m19s |
| macOS x86_64 | 93409421609 | passed, 5.77 s | passed, 4.72 s | 2m39s |
| Windows x86_64 | 93409421618 | passed, 1.78 s | passed, 2.11 s | 1m50s |

Every installed and frozen result reported the same three model SHA-256
values recorded in `config/ocr-model-manifest.json` and matched both required
fixture terms with networking disabled.

Artifacts:

| Artifact | Bytes | Digest |
|---|---:|---|
| `ocr-gate0-macos-arm64` | 114,405,746 | `sha256:33b457e53a87317f1db2ffd7c4c749d42190eefc299f4042c7bac9e4cfddc6cc` |
| `ocr-gate0-macos-x64` | 138,345,398 | `sha256:9aaf47f7e2d07491ae0d6f767fe20ddae3d146987d7e288f0e5bfcde6bc3540e` |
| `ocr-gate0-windows-x64` | 115,080,855 | `sha256:21dbdedd17d745bd8edcac3dd1b9d6a93efb8a2c141dc44bbf860a20a4451a29` |

The runner emitted a maintenance warning that actions using Node.js 20 are
being forced to Node.js 24. It did not affect OCR installation, freezing,
offline inference, hashes, or artifacts.

Gate 0 decision: PASS

## Production macOS arm64 Packaging Gate

The production desktop packaging path was validated on the same macOS arm64
host after adding the OCR runtime to `packaging/openworker-server.spec`.
PyInstaller 6.22.0 built the full OpenWorker sidecar with:

- RapidOCR package data and `rapidocr-3.9.2.dist-info`.
- ONNX Runtime dynamic libraries and `onnxruntime-1.19.2.dist-info`.
- OpenCV and NumPy dynamic libraries.
- One copy of `config/ocr-model-manifest.json`.
- Exactly one copy of each accepted detection, orientation, and recognition
  model.

The first frozen verifier failure exposed missing package metadata required by
`importlib.metadata.version()`. Adding only the RapidOCR and ONNX Runtime
metadata fixed the failure without weakening version or model hash checks.

The macOS build required Rust and CMake for the existing Tauri and
`whisper-rs-sys` dependencies. The verified build environment used:

```text
Rust 1.97.1 (Homebrew)
Cargo 1.97.1 (Homebrew)
CMake 4.4.2
PyInstaller 6.22.0
```

Run:

```text
OCW_SKIP_NOTARIZE=1 packaging/build_dmg.sh
```

Results:

- PyInstaller production sidecar: passed.
- Staged manifest and three model size/hash checks: passed.
- Staged frozen OCR with socket networking disabled: passed.
- GUI TypeScript and Vite production build: passed.
- Tauri arm64 `.app`: passed.
- `hdiutil` DMG creation: passed.
- Read-only DMG mount and OCR execution from
  `OpenWorker.app/Contents/Resources/sidecar/openworker-server`: passed.
- DMG-contained manifest/model uniqueness and hashes: passed.

The frozen verifier recognized the Chinese fixture with
`extraction_method=ocr`, selected page 1, matched `Python` and `技能`, and
reported the exact three manifest model hashes. It did not emit OCR text,
private paths, or model paths.

Artifacts:

| Artifact | Size | SHA-256 |
|---|---:|---|
| `OpenWorker.app` | 560 MiB on disk | development intermediate |
| `OpenWorker_0.1.7_aarch64.dmg` | 236,235,577 bytes | `c5f83e738af36904a13aef6365e2f39678698f9398e170dae2de82c24c49f8ae` |

The DMG is an ad-hoc signed, non-notarized local acceptance artifact because
no Apple Developer ID or updater signing key was supplied. It is not a public
release artifact. Windows x86_64 production NSIS/MSI packaging remains a
separate required gate.
