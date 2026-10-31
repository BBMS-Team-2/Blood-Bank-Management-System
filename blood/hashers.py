from django.contrib.auth.hashers import PBKDF2PasswordHasher


class FasterPBKDF2PasswordHasher(PBKDF2PasswordHasher):
    """Faster PBKDF2 variant tuned for local development and test performance while staying cryptographically secure."""
    iterations = 6000
