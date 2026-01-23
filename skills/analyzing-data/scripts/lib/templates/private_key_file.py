"""Template for loading private key from file.

Variables to substitute:
- $KEY_PATH: Path to the private key file
- $PASSPHRASE_CODE: Code to get passphrase (e.g., "None" or "os.environ.get('VAR').encode()")
"""

from string import Template

TEMPLATE = Template(
    """
def _load_private_key():
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization
    from pathlib import Path

    with open(Path($KEY_PATH).expanduser(), "rb") as f:
        p_key = serialization.load_pem_private_key(
            f.read(), password=$PASSPHRASE_CODE, backend=default_backend()
        )
    return p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
"""
)
