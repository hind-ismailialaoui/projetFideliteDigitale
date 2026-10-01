import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app import app


class AuthTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()
        self.client.get('/login')
        with self.client.session_transaction() as session:
            self.csrf = session['csrf_token']

    def post(self, path, **data):
        return self.client.post(path, data={'csrf_token': self.csrf, **data})

    @patch('app.auth_client')
    def test_login_does_not_create_user(self, auth):
        result = self.post('/login', phone='+33 6 12 34 56 78')
        self.assertEqual(result.location, '/verify-code')
        auth.return_value.sign_in_with_otp.assert_called_once_with({
            'phone': '+33612345678', 'options': {'should_create_user': False},
        })

    @patch('app.auth_client')
    def test_register_only_stores_requested_data(self, auth):
        result = self.post('/register', phone='+33 6 12 34 56 78', city='Paris',
                           recovery_email='recovery@example.com')
        self.assertEqual(result.location, '/verify-code')
        auth.return_value.sign_in_with_otp.assert_called_once_with({
            'phone': '+33612345678', 'options': {'should_create_user': True,
            'data': {'city': 'Paris', 'recovery_email': 'recovery@example.com'}},
        })

    @patch('app.auth_client')
    def test_email_is_optional(self, auth):
        self.assertEqual(self.post('/register', phone='+33612345678', city='Paris').status_code, 302)
        data = auth.return_value.sign_in_with_otp.call_args.args[0]
        self.assertNotIn('recovery_email', data['options']['data'])

    @patch('app.auth_client')
    def test_invalid_registration_does_not_send_sms(self, auth):
        for data in [dict(phone='0612345678', city='Paris'),
                     dict(phone='+33612345678', city=''),
                     dict(phone='+33612345678', city='Paris', recovery_email='bad')]:
            self.assertEqual(self.post('/register', **data).status_code, 400)
        auth.assert_not_called()

    @patch('app.auth_client')
    def test_code_verification_protects_home(self, auth):
        self.assertEqual(self.client.get('/home').location, '/login')
        self.post('/login', phone='+33612345678')
        auth.return_value.verify_otp.side_effect = Exception('expired')
        self.assertEqual(self.post('/verify-code', code='123456').status_code, 400)
        self.assertEqual(self.client.get('/home').location, '/login')
        auth.return_value.verify_otp.side_effect = None
        auth.return_value.verify_otp.return_value = SimpleNamespace(
            session=SimpleNamespace(access_token='verified-token'), user=SimpleNamespace(id='user'),
        )
        self.assertEqual(self.post('/verify-code', code='123456').location, '/home')
        auth.return_value.get_user.return_value = SimpleNamespace(user=SimpleNamespace(id='user'))
        self.assertEqual(self.client.get('/home').status_code, 200)
        auth.return_value.get_user.assert_called_once_with('verified-token')

    def test_csrf_and_recovery_unavailable(self):
        self.assertEqual(self.client.post('/login', data={'phone': '+33612345678'}).status_code, 400)
        self.assertEqual(self.client.get('/reset-password').status_code, 404)
        self.assertEqual(self.client.get('/account-recovery').status_code, 200)
        result = self.post('/account-recovery', recovery_email='recovery@example.com')
        self.assertEqual(result.status_code, 503)
        self.assertIn(b'not available yet', result.data)


if __name__ == '__main__':
    unittest.main()
