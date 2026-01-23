"""Template for loading private key from content/env var.

Variables to substitute:
- $KEY_CODE: Code to get key content (e.g., "os.environ.get('VAR')" or repr(key))
- $PASSPHRASE_CODE: Code to get passphrase
"""

from string import Template

TEMPLATE = Template(
    """
def _load_private_key():
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization

    key_content = $KEY_CODE
    p_key = serialization.load_pem_private_key(
        key_content.encode(), password=$PASSPHRASE_CODE, backend=default_backend()
    )
    return p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
"""
)
