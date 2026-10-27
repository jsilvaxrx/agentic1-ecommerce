"""Tests de la API FastAPI del router."""

from fastapi.testclient import TestClient

from api.app import app

client = TestClient(app)


def test_health_devuelve_ok_y_modelo():
    r = client.get("/health")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["ok"] is True
    assert cuerpo["modelo"]


def test_chat_rutea_preventa(monkeypatch):
    import api.app as modulo

    monkeypatch.setattr(
        modulo.graph,
        "invoke",
        lambda *args, **kwargs: {"ruta": "preventa", "motivo": "Consulta previa a la compra.", "respuesta": "Preventa."},
    )
    r = client.post("/chat", json={"user_id": "test-preventa", "texto": "¿tienen la polera azul en talla M?"})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["ruta"] == "preventa"
    assert cuerpo["motivo"]
    assert cuerpo["respuesta"]
    assert set(cuerpo) == {"ruta", "motivo", "respuesta"}


def test_chat_rutea_postventa(monkeypatch):
    import api.app as modulo

    monkeypatch.setattr(
        modulo.graph,
        "invoke",
        lambda *args, **kwargs: {"ruta": "postventa", "motivo": "Pedido ya realizado.", "respuesta": "Postventa."},
    )
    r = client.post("/chat", json={"user_id": "test-postventa", "texto": "mi pedido 4521 llegó roto"})
    assert r.status_code == 200
    assert r.json()["ruta"] == "postventa"


def test_chat_rutea_generica(monkeypatch):
    import api.app as modulo

    monkeypatch.setattr(
        modulo.graph,
        "invoke",
        lambda *args, **kwargs: {"ruta": "generica", "motivo": "Saludo.", "respuesta": "Hola."},
    )
    r = client.post("/chat", json={"user_id": "test-generica", "texto": "hola"})
    assert r.status_code == 200
    assert r.json()["ruta"] == "generica"


def test_chat_sin_texto_devuelve_422():
    r = client.post("/chat", json={"user_id": "test-422"})
    assert r.status_code == 422
    assert "detail" in r.json()


def test_chat_con_texto_vacio_devuelve_422():
    r = client.post("/chat", json={"user_id": "test-422", "texto": ""})
    assert r.status_code == 422


def test_chat_sin_user_id_devuelve_422():
    r = client.post("/chat", json={"texto": "hola"})
    assert r.status_code == 422


def test_telegram_rechaza_secreto_invalido(monkeypatch):
    import api.app as modulo

    monkeypatch.setattr(modulo, "TELEGRAM_SECRET", "secreto-correcto")
    r = TestClient(modulo.app).post(
        "/telegram",
        headers={"X-Telegram-Bot-Api-Secret-Token": "secreto-incorrecto"},
        json={"update_id": 1},
    )
    assert r.status_code == 403


def test_telegram_ignora_updates_sin_texto(monkeypatch):
    import api.app as modulo

    monkeypatch.setattr(modulo, "TELEGRAM_SECRET", "test-secret")

    def no_deberia_invocarse(*args, **kwargs):
        raise AssertionError("El router no debe procesar updates sin texto")

    monkeypatch.setattr(modulo, "ejecutar_router", no_deberia_invocarse)
    r = TestClient(modulo.app).post(
        "/telegram",
        headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        json={"update_id": 1, "message": {"chat": {"id": 99}, "sticker": {"emoji": "👍"}}},
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_telegram_invoca_router_y_envia_respuesta(monkeypatch):
    import api.app as modulo

    enviados = []

    def router(texto, thread_id):
        assert texto == "hola tienda"
        assert thread_id == "12345"
        return modulo.ChatResponse(ruta="generica", motivo="Es un saludo.", respuesta="Hola, soy la tienda.")

    async def enviar(chat_id, texto):
        enviados.append({"chat_id": chat_id, "texto": texto})

    monkeypatch.setattr(modulo, "TELEGRAM_SECRET", "test-secret")
    monkeypatch.setattr(modulo, "ejecutar_router", router)
    monkeypatch.setattr(modulo, "enviar_mensaje_telegram", enviar)
    r = TestClient(modulo.app).post(
        "/telegram",
        headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        json={"update_id": 1, "message": {"chat": {"id": 12345}, "text": "hola tienda"}},
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert enviados == [{"chat_id": 12345, "texto": "Hola, soy la tienda."}]


def test_telegram_responde_200_si_falla_el_modelo(monkeypatch):
    import api.app as modulo

    def fallo_modelo(*args, **kwargs):
        raise RuntimeError("modelo no disponible")

    monkeypatch.setattr(modulo, "TELEGRAM_SECRET", "test-secret")
    monkeypatch.setattr(modulo, "ejecutar_router", fallo_modelo)
    r = TestClient(modulo.app, raise_server_exceptions=False).post(
        "/telegram",
        headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        json={"update_id": 1, "message": {"chat": {"id": 12345}, "text": "hola"}},
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_telegram_acepta_cualquier_json_con_secreto_valido(monkeypatch):
    import api.app as modulo

    monkeypatch.setattr(modulo, "TELEGRAM_SECRET", "test-secret")
    r = TestClient(modulo.app).post(
        "/telegram",
        headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        json={"cualquier": ["cosa", 1, True]},
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_openapi_tiene_titulo_version_y_tags():
    spec = client.get("/openapi.json").json()
    assert spec["info"]["title"] == "Ecommerce Router API"
    assert spec["info"]["version"]
    assert spec["info"]["description"]
    tags = {t["name"] for t in spec["tags"]}
    assert {"salud", "chat", "telegram"} <= tags


def test_openapi_documenta_200_422_y_502_en_chat():
    spec = client.get("/openapi.json").json()
    respuestas = spec["paths"]["/chat"]["post"]["responses"]
    assert "200" in respuestas
    assert "422" in respuestas
    assert "502" in respuestas
    for codigo in ("200", "422", "502"):
        assert respuestas[codigo]["description"]


def test_openapi_telegram_no_aparece():
    spec = client.get("/openapi.json").json()
    assert "/telegram" not in spec["paths"]


def test_openapi_modelos_tienen_ejemplos():
    spec = client.get("/openapi.json").json()
    esquemas = spec["components"]["schemas"]
    for nombre in ("ChatRequest", "ChatResponse"):
        propiedades = esquemas[nombre]["properties"]
        for campo, definicion in propiedades.items():
            assert definicion.get("examples"), f"{nombre}.{campo} sin ejemplo"
            assert definicion.get("description"), f"{nombre}.{campo} sin descripción"


def test_docs_sirve_swagger():
    r = client.get("/docs")
    assert r.status_code == 200
    assert "swagger" in r.text.lower()


def test_fallo_del_modelo_devuelve_502_limpio(monkeypatch):
    import api.app as modulo

    def boom(*args, **kwargs):
        raise RuntimeError("Error 403: API key not valid: sk-SECRETVALUE")

    monkeypatch.setattr(modulo.graph, "invoke", boom)
    r = TestClient(modulo.app, raise_server_exceptions=False).post(
        "/chat", json={"user_id": "test-502", "texto": "hola"}
    )
    assert r.status_code == 502
    cuerpo = r.text
    assert "SECRETVALUE" not in cuerpo
    assert "Traceback" not in cuerpo
    assert "RuntimeError" not in cuerpo
    assert "modelo no respondió" in cuerpo


def test_ruta_invalida_devuelve_502(monkeypatch):
    import api.app as modulo

    monkeypatch.setattr(
        modulo.graph, "invoke", lambda *a, **k: {"ruta": "inventada", "motivo": "x", "respuesta": "y"}
    )
    r = TestClient(modulo.app, raise_server_exceptions=False).post(
        "/chat", json={"user_id": "test-502b", "texto": "hola"}
    )
    assert r.status_code == 502


def test_el_grafo_se_compila_una_sola_vez():
    from src.router.graph import graph as grafo_router

    assert grafo_router is not None
    assert grafo_router.checkpointer is not None
