from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature
import base64

def generate_key_pair() -> (str, str):
    private_key = ec.generate_private_key(ec.SECP256k1())
    public_key = private_key.public_key()
    priv_der = private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    pub_der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return base64.b64encode(priv_der).decode(), base64.b64encode(pub_der).decode()

def sign_message(message: str, private_key_b64: str) -> str:
    private_key = serialization.load_der_private_key(
        base64.b64decode(private_key_b64), password=None)
    signature = private_key.sign(message.encode(), ec.ECDSA(hashes.SHA256()))
    return base64.b64encode(signature).decode()

def verify_signature(message: str, signature_b64: str, public_key_b64: str) -> bool:
    try:
        public_key = serialization.load_der_public_key(
            base64.b64decode(public_key_b64))
        signature = base64.b64decode(signature_b64)
        public_key.verify(signature, message.encode(), ec.ECDSA(hashes.SHA256()))
        return True
    except Exception:
        return False