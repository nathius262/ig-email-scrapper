import unittest

from instagrapi.exceptions import BadPassword, ChallengeRequired

import ig_email_scraper


class LoginHandlingTests(unittest.TestCase):
    def test_bad_password_message_is_user_friendly(self):
        error = BadPassword("We can send you an email to help you get back into your account.")
        message = ig_email_scraper.describe_login_failure(error)
        self.assertIn("password", message.lower())
        self.assertIn("ip address", message.lower())

    def test_challenge_message_points_to_manual_resolution(self):
        error = ChallengeRequired("legacy challenge flow")
        message = ig_email_scraper.describe_login_failure(error)
        self.assertIn("challenge", message.lower())
        self.assertIn("manual", message.lower())


if __name__ == "__main__":
    unittest.main()
