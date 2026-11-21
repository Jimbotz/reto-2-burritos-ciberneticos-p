"""El comparativo (datos de 3B por captura) solo lo ve la clave de revisión."""
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from mobile.api import create_app
from mobile.db import ROOT

with TemporaryDirectory() as estado, TestClient(create_app(estado, local=True, operator_key="op-1", reviewer_key="rev-1")) as web:
    assert web.get("/api/comparativo").status_code == 401  # sin sesión
    web.post("/api/sesion", json={"clave": "op-1"})
    assert web.get("/api/comparativo").status_code == 403  # operador
    web.delete("/api/sesion")
    web.post("/api/sesion", json={"clave": "rev-1"})
    r = web.get("/api/comparativo")
    if (ROOT / "out/comparativo.json").is_file():
        assert r.status_code == 200 and {"versiones", "capturas"} <= r.json().keys()
        assert r.headers["cache-control"] == "no-store"  # no se queda en cachés intermedias
    else:
        assert r.status_code == 404
print("ok")
