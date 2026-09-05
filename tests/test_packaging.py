import ast
import re

from conftest import APP


def test_docker_uses_supported_python_and_modular_entrypoint():
    dockerfile = (APP / "Dockerfile").read_text(encoding="utf-8")
    assert "FROM python:3.12-slim" in dockerfile
    assert 'CMD ["python", "main.py"]' in dockerfile
    assert "pip==26.2.1" in dockerfile
    assert "COPY Update/NostalgiaForInfinityX5.py ./Update/NostalgiaForInfinityX5.py" in dockerfile
    assert "COPY Update ./Update" not in dockerfile
    assert "LANGUAGE" not in dockerfile  # Runtime environment, not a build-time switch.
    assert "exec python main.py" in (APP / "run.sh").read_text(encoding="utf-8")


def test_polling_service_publishes_no_inbound_port():
    compose = (APP / "docker-compose.yml").read_text(encoding="utf-8")
    assert "ports:" not in compose
    assert "env_file:" in compose and "- .env" in compose
    assert "${LOCAL_VOLUME_PATH}:/app/Update" in compose


def test_docker_context_excludes_secrets_not_strategy():
    ignored = set((APP / ".dockerignore").read_text(encoding="utf-8").splitlines())
    assert {".env", ".env.*", "*.env", "*.pem", "*.key", ".git", "__pycache__"} <= ignored
    assert "Update" not in ignored and "Update/" not in ignored
    assert "Update/.monitoring-reload-pending.json" in ignored


def test_compose_preserves_existing_service_and_container_identity():
    compose = (APP / "docker-compose.yml").read_text(encoding="utf-8")
    services = re.findall(r"^  ([a-z0-9-]+):$", compose, flags=re.MULTILINE)
    assert services == ["monitoringforupdate-nostalgiaforinfinityx5"]
    names = re.findall(r"^    container_name: (\S+)$", compose, flags=re.MULTILINE)
    assert names == ["monitoringforupdate-nostalgiaforinfinityx5-container"]


def test_public_application_functions_have_type_contracts():
    sources = [APP / "main.py", *(APP / "app").glob("*.py"), *(APP / "config").glob("*.py")]
    missing = []
    for source in sources:
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name.startswith("_"):
                continue
            arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
            if node.returns is None or any(arg.annotation is None for arg in arguments if arg.arg not in ("self", "cls")):
                missing.append(f"{source.name}:{node.name}")
    assert missing == []
