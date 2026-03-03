import os
import sqlite3
import tempfile
import unittest

import app


class SecurityAndInitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["DB_PATH"] = f"{self.tmp.name}/test.db"
        app.init_db()

    def tearDown(self):
        self.tmp.cleanup()

    def test_seeded_data_exists(self):
        conn = sqlite3.connect(os.environ["DB_PATH"])
        users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        tickets = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        conn.close()
        self.assertGreaterEqual(users, 4)
        self.assertGreaterEqual(tickets, 3)

    def test_password_hashing(self):
        encoded = app.hash_password("TopSecret!123")
        self.assertTrue(encoded.startswith("pbkdf2_sha256$"))
        self.assertTrue(app.verify_password("TopSecret!123", encoded))
        self.assertFalse(app.verify_password("bad-pass", encoded))

    def test_session_persisted_in_db(self):
        token = app.create_session(1)
        self.assertIsInstance(token, str)
        user = app.get_session_user(token)
        self.assertIsNotNone(user)
        self.assertEqual(user["id"], 1)
        app.delete_session(token)
        self.assertIsNone(app.get_session_user(token))


if __name__ == "__main__":
    unittest.main()
