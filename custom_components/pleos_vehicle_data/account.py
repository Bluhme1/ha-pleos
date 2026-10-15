"""Stable account namespaces, independent of replaceable API credentials."""

import hashlib


def account_id(entry):
    # Existing installations keep their device IDs, statistics and archive directory.
    return entry.data.get("account_id", entry.data["brand"])


def credential_id(brand, client_id):
    return brand + "_" + hashlib.sha256(client_id.strip().encode()).hexdigest()
