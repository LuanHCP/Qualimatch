from __future__ import annotations

import json
import os
import socket
import threading
import time
import urllib.request
import webbrowser


PORT_RANGE = 20


def port_is_free(port: int) -> bool:
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def is_qualimatch(port: int, timeout: float = 0.45) -> bool:
    """Confirma a aplicação antes de reutilizar uma porta já ocupada."""
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/health",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read(4096).decode("utf-8"))
        return bool(payload.get("ok") and payload.get("app") == "QualiMatch")
    except (OSError, ValueError, json.JSONDecodeError):
        return False


def find_existing_qualimatch(first_port: int, attempts: int = 3) -> int | None:
    """Encontra uma instância anterior, inclusive enquanto ela termina de iniciar."""
    for attempt in range(max(1, attempts)):
        for port in range(first_port, first_port + PORT_RANGE):
            if not port_is_free(port) and is_qualimatch(port):
                return port
        if attempt + 1 < attempts:
            time.sleep(0.7)
    return None


def first_free_port(first_port: int) -> int:
    for port in range(first_port, first_port + PORT_RANGE):
        if port_is_free(port):
            return port
    raise RuntimeError(f"Nenhuma porta livre entre {first_port} e {first_port + PORT_RANGE - 1}.")


def _lan_ip() -> str | None:
    """IP da máquina na rede local, do jeito mais confiável possível.

    gethostbyname(gethostname()) às vezes devolve 127.0.1.1 ou o IP errado
    quando há mais de uma interface de rede. Abrir um socket UDP "fake" (não
    chega a enviar nenhum pacote) para um endereço externo é o truque padrão
    para descobrir qual interface/IP o sistema operacional escolheria.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            ip = probe.getsockname()[0]
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    return None


def _print_network_banner(ip: str, port: int) -> None:
    url = f"http://{ip}:{port}"
    line = "=" * max(64, len(url) + 8)
    print()
    print(line)
    print("  ACESSO PELA REDE (envie este endereco para quem for entrar):")
    print(f"  {url}")
    print("  (funciona so para quem estiver na mesma rede/Wi-Fi que este PC)")
    print(line)
    print()


def main() -> None:
    first_port = int(os.getenv("PORT", "8000"))
    existing = find_existing_qualimatch(first_port)
    if existing is not None:
        url = f"http://127.0.0.1:{existing}"
        print("\nQualiMatch já está em execução. Reutilizando o servidor existente:")
        print("Local:", url)
        webbrowser.open(url)
        return

    port = first_free_port(first_port)
    host = os.getenv("HOST", "127.0.0.1")
    url = f"http://127.0.0.1:{port}"

    # Importações pesadas só acontecem quando realmente será criado um servidor.
    import uvicorn
    import app as app_module
    from qualimatch.manual_measurement_link import install_manual_measurement_frontend
    from qualimatch.version import APP_VERSION

    install_manual_measurement_frontend(app_module.app)
    print(f"\nQualiMatch v{APP_VERSION}")
    print("Local:", url)
    if host == "0.0.0.0":
        ip = _lan_ip()
        if ip:
            _print_network_banner(ip, port)
        else:
            print("Rede: nao foi possivel detectar o IP local automaticamente.")
    threading.Thread(target=lambda: (time.sleep(1.3), webbrowser.open(url)), daemon=True).start()
    config = uvicorn.Config(app_module.app, host=host, port=port, reload=False)
    server = uvicorn.Server(config)
    app_module.app.state.request_shutdown = lambda: setattr(server, "should_exit", True)
    server.run()


if __name__ == "__main__":
    main()
