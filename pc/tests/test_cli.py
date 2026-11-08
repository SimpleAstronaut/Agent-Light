import contextlib
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from agent_light.cli import main
from agent_light.config import save_atomic
from test_runtime import configuration


class CLIErrorChecks(unittest.TestCase):
    def test_http_error_classification_and_quiet_event(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg = configuration(root)
            path = root / 'config.json'
            save_atomic(path, cfg)
            for command, status, code, expected_exit, expected_output in (
                ('test', 409, 'DEVICE_NOT_READY', 3, 'DEVICE_NOT_READY'),
                ('test', 409, 'DISPLAY_TEST_RUNNING', 3, 'DISPLAY_TEST_RUNNING'),
                ('health', 401, 'ignored', 4, 'AUTH_FAILED'),
                ('health', 500, 'private-canary', 1, 'HTTP_ERROR'),
                ('event', 503, 'private-canary', None, ''),
            ):
                body = io.BytesIO(json.dumps({'error': {'code': code}}).encode())
                error = urllib.error.HTTPError(cfg['endpoint'], status, 'ignored', {}, body)
                stderr = io.StringIO()
                stdin = io.TextIOWrapper(io.BytesIO(b'{}'))
                with self.subTest(command=command, status=status, code=code), \
                     patch('sys.argv', ['agent-light', '--config', str(path), command]), \
                     patch('sys.stdin', stdin), contextlib.redirect_stderr(stderr), \
                     patch('urllib.request.OpenerDirector.open', side_effect=error):
                    if expected_exit is None:
                        main()
                    else:
                        with self.assertRaises(SystemExit) as stopped:
                            main()
                        self.assertEqual(stopped.exception.code, expected_exit)
                    self.assertEqual(stderr.getvalue().strip(), expected_output)
