"""Gera um certificado TLS autoassinado para rodar o dashboard em HTTPS.

O WebXR (modo VR do Meta Quest) so funciona em "secure context": precisa de
HTTPS, exceto quando acessado por "localhost". Como o Quest acessa o PC pela
rede (ex: https://192.168.0.12:5000), precisamos de um certificado.

Rode uma vez, com a venv ativada:

    pip install cryptography
    python generate_cert.py

Isso detecta os IPs locais desta maquina e gera certs/server.crt e
certs/server.key validos para "localhost", "127.0.0.1" e esses IPs. Depois e
so rodar "python app.py" normalmente: se os arquivos existirem, o servidor
sobe em HTTPS automaticamente (veja app.py).

No navegador do Quest, ao abrir https://<ip-do-pc>:5000 ele vai mostrar um
aviso de certificado nao confiavel (e autoassinado, isso e esperado) - toque
em "Avancado" / "Detalhes" e depois "Continuar mesmo assim" / "Acessar site".
Isso e suficiente para o navegador liberar a API navigator.xr.

Se o IP do seu PC mudar (trocar de rede), rode este script de novo.
"""

import ipaddress
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
except ImportError as exc:  # pragma: no cover - mensagem de ajuda, nao logica
    raise SystemExit(
        "Falta a biblioteca 'cryptography'. Rode: pip install cryptography"
    ) from exc

from config import CERT_DIR, CERT_PATH, KEY_PATH


def local_ips():
    """Tenta descobrir os IPv4 locais desta maquina (LAN, Wi-Fi etc)."""
    ips = {"127.0.0.1"}

    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            ip = info[4][0]
            if ":" not in ip:
                ips.add(ip)
    except Exception:
        pass

    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        ips.add(probe.getsockname()[0])
        probe.close()
    except Exception:
        pass

    return sorted(ips)


def main():
    CERT_DIR.mkdir(exist_ok=True)
    ips = local_ips()
    print("Gerando certificado para:", ", ".join(["localhost", *ips]))

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "tello-dashboard-local")]
    )

    san_entries = [x509.DNSName("localhost")]
    for ip in ips:
        san_entries.append(x509.IPAddress(ipaddress.ip_address(ip)))

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
        .sign(key, hashes.SHA256())
    )

    KEY_PATH.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    CERT_PATH.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    print(f"OK: {CERT_PATH} e {KEY_PATH} gerados.")
    print("Rode 'python app.py' normalmente - ele detecta os certs e sobe em HTTPS.")


if __name__ == "__main__":
    main()
