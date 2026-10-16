"""PyInstaller entry point for the bundled desktop sidecar server.

Thin wrapper so PyInstaller has a concrete script to analyze (the console_script
`openworker-server` is generated metadata, not a file). Runs the same `main()`.
"""

import sys

from coworker.server.run import main

if __name__ == "__main__":
    if (
        len(sys.argv) > 1
        and sys.argv[1] == "--verify-ocr-installation"
    ):
        from extensions.career_mcp.ocr.installation_verifier import (
            main as verify_ocr_installation,
        )

        raise SystemExit(verify_ocr_installation(sys.argv[2:]))
    main()
