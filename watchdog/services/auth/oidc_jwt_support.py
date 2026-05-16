"""
JWT/JWK helpers shared by the OIDC service.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import base64
import binascii
import json

from cryptography.hazmat.primitives.asymmetric import ec, rsa
from custom_types.json import JSONDict
from jwt.algorithms import ECAlgorithm, RSAAlgorithm

VerificationKey = rsa.RSAPublicKey | ec.EllipticCurvePublicKey


def json_dict(value: object) -> JSONDict:
    return value if isinstance(value, dict) else {}


def jwk_to_verification_key(jwk_key: JSONDict, alg: str) -> VerificationKey:
    jwk_json = json.dumps(jwk_key)
    if alg.startswith("RS"):
        rsa_key = RSAAlgorithm.from_jwk(jwk_json)
        if isinstance(rsa_key, rsa.RSAPublicKey):
            return rsa_key
        raise ValueError("Invalid RSA JWK key")
    if alg.startswith("ES"):
        ec_key = ECAlgorithm.from_jwk(jwk_json)
        if isinstance(ec_key, ec.EllipticCurvePublicKey):
            return ec_key
        raise ValueError("Invalid EC JWK key")
    raise ValueError(f"Unsupported OIDC token algorithm: {alg}")


def looks_like_jwt(token: str) -> bool:
    if not token:
        return False
    parts = token.split(".")
    return len(parts) == 3 and all(parts)


def decode_jwt_header(token: str) -> JSONDict | None:
    if not looks_like_jwt(token):
        return None
    header_b64 = token.split(".", 1)[0]
    pad = "=" * ((4 - len(header_b64) % 4) % 4)
    try:
        raw = base64.urlsafe_b64decode(header_b64 + pad)
        header_text = raw.decode("utf-8")
        header = json.loads(header_text)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None
    return header if isinstance(header, dict) else None


def issuer_candidates(issuer: str | None) -> tuple[str | None, ...]:
    normalized = str(issuer or "").strip().rstrip("/")
    if not normalized:
        return (None,)

    candidates: list[str | None] = [normalized]
    # Google documents both forms of the issuer in ID token validation guidance.
    if normalized in {"https://accounts.google.com", "accounts.google.com"}:
        candidates = ["https://accounts.google.com", "accounts.google.com"]
    return tuple(dict.fromkeys(candidates))
