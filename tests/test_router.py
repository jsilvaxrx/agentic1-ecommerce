"""Tests del agente router. Verifica estructura del grafo y reglas de ruteo."""

import pytest
from langgraph.graph import END, START

from src.router.graph import EstadoRouter, enrutar, graph


def test_grafo_tiene_los_cuatro_nodos():
    nodos = set(graph.get_graph().nodes)
    for esperado in ("router", "agente_preventa", "agente_postventa", "respuesta_generica"):
        assert esperado in nodos
    assert "__start__" in nodos
    assert "__end__" in nodos


def test_grafo_tiene_arista_condicional_desde_router():
    aristas = graph.get_graph().edges
    condicionales = [e for e in aristas if e.conditional and e.source == "router"]
    assert condicionales, "router debe tener aristas condicionales"
    destinos = {e.target for e in condicionales}
    assert destinos == {"agente_preventa", "agente_postventa", "respuesta_generica"}


@pytest.mark.parametrize(
    "ruta,etiqueta",
    [
        ("preventa", "preventa"),
        ("postventa", "postventa"),
        ("generica", "generica"),
    ],
)
def test_enrutar_devuelve_la_ruta(ruta, etiqueta):
    assert enrutar({"ruta": ruta}) == etiqueta


def test_enrutar_default_es_generica():
    assert enrutar({}) == "generica"


def test_mapa_de_rutas_apunta_a_cada_nodo():
    from src.router.graph import construir_graph

    aristas = construir_graph().get_graph().edges
    condicionales = [e for e in aristas if e.conditional and e.source == "router"]
    assert {e.source for e in condicionales} == {"router"}
    assert {e.target for e in condicionales} == {
        "agente_preventa",
        "agente_postventa",
        "respuesta_generica",
    }


def test_estado_tiene_los_campos_pedidos():
    for campo in ("mensaje", "ruta", "motivo", "respuesta", "messages"):
        assert campo in EstadoRouter.__annotations__


def test_agentes_de_ruta_guardan_mensaje_y_respuesta(monkeypatch):
    import src.router.graph as modulo
    from langchain_core.messages import AIMessage, HumanMessage

    class AgenteFalso:
        def invoke(self, entrada):
            assert entrada["messages"][-1].content == "hola"
            return {"messages": [AIMessage(content="Preventa.")]}

    monkeypatch.setattr(modulo, "create_agent", lambda **_: AgenteFalso())

    preventa = modulo.nodo_agente_preventa(
        {"mensaje": "hola", "motivo": "Consulta previa.", "messages": [HumanMessage(content="hola"), AIMessage(content="Consulta previa.")]}
    )
    postventa = modulo.nodo_agente_postventa({"mensaje": "hola"})

    assert preventa["respuesta"] == "Preventa."
    assert preventa["messages"][0].content == "hola"
    assert "agente de postventa" in postventa["respuesta"]
    assert "hola" in postventa["respuesta"]
    assert postventa["messages"][0].content == "hola"


def test_saltos_se_reinician_en_cada_turno():
    from src.router.graph import _mergear_saltos

    acumulado = _mergear_saltos(["router", "agente_preventa"], ["router"])
    assert acumulado == ["router"]
    acumulado = _mergear_saltos(acumulado, ["agente_postventa"])
    assert acumulado == ["router", "agente_postventa"]
