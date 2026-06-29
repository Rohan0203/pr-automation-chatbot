"""Console test for the intent classifier graph.

Usage:
    # Run all predefined test cases
    python -m backend_wlg.tests.test_intent

    # Interactive chat mode
    python -m backend_wlg.tests.test_intent --chat

DEPRECATED: This file redirects to backend_wlg.tests.test_intent.
"""

from backend_wlg.tests.test_intent import run_tests, interactive_chat, sys, asyncio

if __name__ == "__main__":
    if "--chat" in sys.argv:
        asyncio.run(interactive_chat())
    else:
        asyncio.run(run_tests())
