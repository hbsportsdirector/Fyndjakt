"""Telefon-/webbnotiser (Web Push) utan externa tjänster.

Krypterar enligt RFC 8291 (aes128gcm) och signerar med VAPID (RFC 8292). Används av morgonkörningen
för att skicka "dagens bästa fynd" till de användare som slagit på notiser i appen.
"""
import base64
import calendar
import json
import os
import struct
import time
from urllib.parse import urlparse

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

AVSANDARE = "https://hbsportsdirector.github.io/Fyndjakt/"


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _hkdf(salt: bytes, ikm: bytes, info: bytes, langd: int) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=langd, salt=salt, info=info).derive(ikm)


def _publik_rad(nyckel) -> bytes:
    return nyckel.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def kryptera(meddelande: bytes, p256dh: str, auth: str, *, _salt: bytes | None = None, _eget=None) -> bytes:
    """Krypterar meddelandet till mottagarens nycklar (aes128gcm, en post)."""
    ua_publik = _b64d(p256dh)
    hemlighet = _b64d(auth)
    eget = _eget or ec.generate_private_key(ec.SECP256R1())
    eget_publik = _publik_rad(eget)
    delad = eget.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_publik))
    ikm = _hkdf(hemlighet, delad, b"WebPush: info\x00" + ua_publik + eget_publik, 32)
    salt = _salt or os.urandom(16)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    chiffer = AESGCM(cek).encrypt(nonce, meddelande + b"\x02", None)
    return salt + struct.pack(">I", 4096) + bytes([len(eget_publik)]) + eget_publik + chiffer


def dekryptera(kropp: bytes, ua_privat, auth: str) -> bytes:
    """Mottagarsidan – används bara i testerna för att kontrollera krypteringen."""
    salt, idlen = kropp[:16], kropp[20]
    avs_publik = kropp[21:21 + idlen]
    chiffer = kropp[21 + idlen:]
    delad = ua_privat.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), avs_publik))
    ikm = _hkdf(_b64d(auth), delad, b"WebPush: info\x00" + _publik_rad(ua_privat) + avs_publik, 32)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    klartext = AESGCM(cek).decrypt(nonce, chiffer, None)
    return klartext.rstrip(b"\x00")[:-1]  # ta bort avgränsaren 0x02


def vapid_huvud(endpoint: str, privat_b64: str) -> str:
    """Authorization-huvudet: en kort signerad JWT som visar att notisen kommer från Fyndjakt."""
    privat = ec.derive_private_key(int.from_bytes(_b64d(privat_b64), "big"), ec.SECP256R1())
    u = urlparse(endpoint)
    huvud = _b64e(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    data = _b64e(json.dumps({"aud": f"{u.scheme}://{u.netloc}", "exp": int(time.time()) + 12 * 3600,
                             "sub": AVSANDARE}, separators=(",", ":")).encode())
    r, s = decode_dss_signature(privat.sign(f"{huvud}.{data}".encode(), ec.ECDSA(hashes.SHA256())))
    signatur = _b64e(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    return f"vapid t={huvud}.{data}.{signatur}, k={_b64e(_publik_rad(privat))}"


def skicka(prenumeration: dict, innehall: dict, privat_b64: str) -> int:
    """Skickar en notis. Returnerar HTTP-status (201 = levererad, 404/410 = prenumerationen finns inte längre)."""
    kropp = kryptera(json.dumps(innehall, ensure_ascii=False).encode(), prenumeration["p256dh"], prenumeration["auth"])
    r = requests.post(prenumeration["endpoint"], data=kropp, timeout=20, headers={
        "Authorization": vapid_huvud(prenumeration["endpoint"], privat_b64),
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
        "TTL": str(18 * 3600),
        "Urgency": "normal",
    })
    return r.status_code


def morgonnotis(poster: list[dict], nu: float | None = None) -> dict | None:
    """Notisen för en användare: nya fynd (senaste ~dygnet) med 9–10 i betyg. None om inget nytt."""
    nu = nu or time.time()
    nya = []
    for p in poster:
        try:
            sedd = calendar.timegm(time.strptime(p.get("sedd") or "", "%Y-%m-%d %H:%M:%S"))  # sparat i UTC
        except ValueError:
            continue
        if nu - sedd < 30 * 3600 and (p.get("betyg") or 0) >= 9:
            nya.append(p)
    if not nya:
        return None
    nya.sort(key=lambda p: -p["betyg"])
    topp = nya[0]
    titel = f"{len(nya)} nya toppfynd i Fyndjakt" if len(nya) > 1 else "Nytt toppfynd i Fyndjakt"
    text = f"★ {topp['betyg']}/10 · {topp['titel'][:80]}"
    if len(nya) > 1:
        text += f" – och {len(nya) - 1} till"
    return {"title": titel, "body": text, "url": AVSANDARE, "tag": "fyndjakt-morgon"}
