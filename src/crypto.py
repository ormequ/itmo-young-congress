from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
from typing import List, Sequence, Tuple

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec


def _sha256(payload: bytes) -> bytes:
    return hashlib.sha256(payload).digest()


def compute_event_hmac(secret: bytes, payload: bytes) -> bytes:
    return hmac.new(secret, payload, hashlib.sha256).digest()


@dataclass(frozen=True)
class ECDSARootSigner:
    private_key: ec.EllipticCurvePrivateKey
    public_key: ec.EllipticCurvePublicKey


def create_ecdsa_signer() -> ECDSARootSigner:
    private_key = ec.generate_private_key(ec.SECP256R1())
    return ECDSARootSigner(private_key=private_key, public_key=private_key.public_key())


def sign_root_ecdsa(private_key: ec.EllipticCurvePrivateKey, root: bytes) -> bytes:
    return private_key.sign(root, ec.ECDSA(hashes.SHA256()))


def verify_root_signature(public_key: ec.EllipticCurvePublicKey, root: bytes, signature: bytes) -> bool:
    try:
        public_key.verify(signature, root, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        return False
    return True


@dataclass(frozen=True)
class MerkleTree:
    leaves: Tuple[bytes, ...]
    levels: Tuple[Tuple[bytes, ...], ...]

    @property
    def root(self) -> bytes:
        return self.levels[-1][0]

    def proof_for(self, index: int) -> List[Tuple[bytes, bool]]:
        proof: List[Tuple[bytes, bool]] = []
        current_index = index
        for level in self.levels[:-1]:
            sibling_index = current_index ^ 1
            sibling = level[sibling_index] if sibling_index < len(level) else level[current_index]
            proof.append((sibling, sibling_index < current_index))
            current_index //= 2
        return proof


def build_merkle_tree(leaves: Sequence[bytes]) -> MerkleTree:
    if not leaves:
        raise ValueError("merkle tree requires at least one leaf")

    current_level = tuple(_sha256(leaf) for leaf in leaves)
    levels = [current_level]

    while len(current_level) > 1:
        next_level = []
        for index in range(0, len(current_level), 2):
            left = current_level[index]
            right = current_level[index + 1] if index + 1 < len(current_level) else left
            next_level.append(_sha256(left + right))
        current_level = tuple(next_level)
        levels.append(current_level)

    return MerkleTree(tuple(leaves), tuple(levels))


def verify_merkle_proof(leaf: bytes, proof: Sequence[Tuple[bytes, bool]], root: bytes) -> bool:
    current = _sha256(leaf)
    for sibling, sibling_is_left in proof:
        current = _sha256(sibling + current) if sibling_is_left else _sha256(current + sibling)
    return current == root
