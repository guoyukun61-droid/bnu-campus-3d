import unittest
from pathlib import Path
from package_release import permitted
from verify_release import check


class ReleaseAuditTests(unittest.TestCase):
    def test_zip_preserves_dependency_license_and_excludes_private_data(self):
        self.assertTrue(permitted(Path('vendor/three/LICENSE')))
        self.assertTrue(permitted(Path('app/explore/main.js')))
        self.assertFalse(permitted(Path('data/life/catalog.json')))
        self.assertFalse(permitted(Path('.env')))

    def test_generated_secret_is_blocked_without_returning_value(self):
        secret = b'sk-' + b'a' * 32
        result = check('app/example.js', b'\n' + secret)
        self.assertEqual(result, [('app/example.js', 'provider-key', 2)])
        self.assertNotIn(secret.decode(), repr(result))

    def test_private_paths_are_blocked(self):
        for name in ['data/life/accounts/store.json', '.env', 'run.log', 'secrets.key', 'releases/bundle.zip']:
            self.assertTrue(check(name, b'{}'), name)

    def test_public_seed_and_environment_lookup_are_allowed(self):
        self.assertEqual(check('backend/seeds/public.json', b'{"source":"official"}'), [])
        self.assertEqual(check('backend/example.py', b"os.environ.get('DEEPSEEK_API_KEY')"), [])

    def test_authenticated_url_is_blocked(self):
        value = b'https://' + b'user:password@example.invalid'
        self.assertEqual(check('example.md', value)[0][1], 'credential-url')

    def test_fixture_path_does_not_allow_different_credentials(self):
        value = b'https://' + b'new-user:new-secret@example.invalid'
        self.assertEqual(check('tests/agent-context.test.mjs', value)[0][1], 'credential-url')
