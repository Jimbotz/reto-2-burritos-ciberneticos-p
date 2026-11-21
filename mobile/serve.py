"""Sirve Validat3B Campo en la red privada con HTTPS."""

import argparse
import ipaddress
import os
from pathlib import Path
import secrets
import socket
import subprocess

import uvicorn

from validat3b import load_env

from .api import WEB, create_app
from .db import ROOT


def ip_lan():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as conn:
        try:
            conn.connect(("192.0.2.1", 80))
            return conn.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def clave_local(path, variable):
    valor = os.getenv(variable)
    if valor:
        return valor
    if not path.exists():
        try:
            with path.open("x", encoding="utf-8") as salida:
                salida.write(secrets.token_urlsafe(18) + "\n")
        except FileExistsError:
            pass
    path.chmod(0o600)
    return path.read_text(encoding="utf-8").strip()


def certificados(state, ip):
    folder = state / "tls"
    folder.mkdir(mode=0o700, exist_ok=True)
    ca, ca_key = folder / "ca.crt", folder / "ca.key"
    cert, key = folder / "servidor.crt", folder / "servidor.key"
    marca = folder / "ip.txt"

    def openssl(*args):
        subprocess.run(["openssl", *map(str, args)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    if not ca.exists() or not ca_key.exists():
        openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-sha256", "-days", "365",
                "-subj", "/CN=Validat3B Red Local", "-keyout", ca_key, "-out", ca,
                "-addext", "basicConstraints=critical,CA:TRUE", "-addext", "keyUsage=critical,keyCertSign,cRLSign")
        marca.unlink(missing_ok=True)
    if not cert.exists() or not key.exists() or not marca.exists() or marca.read_text() != ip:
        csr = folder / "servidor.csr"
        ext = folder / "servidor.ext"
        san = "DNS:localhost,IP:127.0.0.1"
        if ip != "127.0.0.1":
            san += f",IP:{ip}"
        ext.write_text("basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\n"
                       "extendedKeyUsage=serverAuth\nsubjectAltName=" + san + "\n", encoding="utf-8")
        openssl("req", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=Validat3B Campo",
                "-keyout", key, "-out", csr)
        openssl("x509", "-req", "-in", csr, "-CA", ca, "-CAkey", ca_key, "-CAcreateserial", "-out", cert,
                "-days", "180", "-sha256", "-extfile", ext)
        marca.write_text(ip, encoding="ascii")
    return cert, key, ca


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip", default=ip_lan(), help="IP privada anunciada al teléfono")
    parser.add_argument("--bind", default="0.0.0.0", help="Interfaz donde escucha el servidor")
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--http", action="store_true", help="Modo local de diagnóstico sin TLS")
    parser.add_argument("--local", action="store_true", help="Valida sin enviar fotos a Foundry")
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--cert", type=Path)
    parser.add_argument("--key", type=Path)
    args = parser.parse_args()
    try:
        ip = str(ipaddress.IPv4Address(args.ip))
    except ValueError:
        parser.error("Usa una dirección IPv4 privada.")
    if not ipaddress.IPv4Address(ip).is_private:
        parser.error("La dirección anunciada debe ser privada.")
    if bool(args.cert) != bool(args.key):
        parser.error("Usa --cert y --key juntos.")
    if not (WEB / "index.html").is_file():
        parser.error("Compila la PWA con npm ci --prefix mobile/web y npm run --prefix mobile/web build.")
    os.umask(0o077)
    load_env()
    state = Path(args.state_dir or os.getenv("MOBILE_STATE_DIR") or ROOT / "out/mobile").resolve()
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    operador = clave_local(state / "operador.clave", "MOBILE_OPERATOR_KEY")
    revisor = clave_local(state / "revisor.clave", "MOBILE_REVIEW_KEY")
    cert, key = args.cert, args.key
    scheme = "http" if args.http else "https"
    if not args.http and not cert:
        cert, key, ca = certificados(state, ip)
        print(f"Certificado CA para el teléfono: {ca}", flush=True)
    print(f"Validat3B Campo en {scheme}://{ip}:{args.port}/", flush=True)
    uvicorn.run(create_app(state, local=args.local, operator_key=operador, reviewer_key=revisor),
                host=args.bind, port=args.port, ssl_certfile=str(cert) if not args.http else None,
                ssl_keyfile=str(key) if not args.http else None, proxy_headers=False)


if __name__ == "__main__":
    main()
