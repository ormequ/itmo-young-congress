import unittest

from itmo_young_congress.crypto import (
    build_merkle_tree,
    compute_event_hmac,
    verify_merkle_proof,
)


class CryptoTests(unittest.TestCase):
    def test_hmac_is_deterministic(self) -> None:
        secret = b"shared-secret"
        payload = b"device-1:42"

        digest_a = compute_event_hmac(secret, payload)
        digest_b = compute_event_hmac(secret, payload)

        self.assertEqual(digest_a, digest_b)

    def test_merkle_root_is_stable_for_identical_leaves(self) -> None:
        leaves = [b"a", b"b", b"c"]

        tree_a = build_merkle_tree(leaves)
        tree_b = build_merkle_tree(leaves)

        self.assertEqual(tree_a.root, tree_b.root)

    def test_merkle_proof_validates_original_leaf(self) -> None:
        tree = build_merkle_tree([b"alpha", b"beta", b"gamma"])

        self.assertTrue(verify_merkle_proof(b"beta", tree.proof_for(1), tree.root))

    def test_merkle_proof_rejects_tampered_leaf(self) -> None:
        tree = build_merkle_tree([b"alpha", b"beta", b"gamma"])

        self.assertFalse(verify_merkle_proof(b"evil", tree.proof_for(1), tree.root))


if __name__ == "__main__":
    unittest.main()
