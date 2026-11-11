"""CLI raíz: python main.py {nombre_agente} "mensaje" [--saltos] [--hilo]."""

import argparse
import importlib
import sys


def cargar_graph(nombre_agente):
    try:
        modulo = importlib.import_module(f"src.{nombre_agente}.graph")
    except ModuleNotFoundError:
        print(f"Error: no existe src/{nombre_agente}/graph.py", file=sys.stderr)
        sys.exit(1)
    if not hasattr(modulo, "graph"):
        print(f"Error: src/{nombre_agente}/graph.py debe exponer `graph`", file=sys.stderr)
        sys.exit(1)
    return modulo


def main() -> None:
    parser = argparse.ArgumentParser(description="Ejecuta un agente LangGraph desde la raíz.")
    parser.add_argument("nombre_agente", help="Nombre del agente en src/{nombre_agente}/")
    parser.add_argument("mensaje", nargs="?", default="", help="Mensaje de entrada para el agente")
    parser.add_argument("--saltos", action="store_true", help="Imprime los nodos por los que pasó el grafo")
    parser.add_argument("--diagrama", action="store_true", help="Imprime el Mermaid del grafo sin ejecutarlo")
    parser.add_argument(
        "--hilo",
        "--thread",
        default="default",
        dest="thread_id",
        help="thread_id para la memoria del grafo (por defecto 'default')",
    )
    args = parser.parse_args()

    modulo = cargar_graph(args.nombre_agente)
    if args.diagrama:
        try:
            print(modulo.graph.get_graph().draw_mermaid())
        except Exception as e:
            print(f"Error al generar diagrama: {e}", file=sys.stderr)
            sys.exit(1)
        return

    if not args.mensaje:
        print('Error: debes pasar un "mensaje". Ej: python main.py mi_agente "hola"', file=sys.stderr)
        sys.exit(1)

    if hasattr(modulo, "iniciar_memoria"):
        modulo.iniciar_memoria()
    graph = modulo.graph

    # Estado inicial genérico: cada agente define su schema, "mensaje" es la convención mínima.
    config = {"configurable": {"thread_id": args.thread_id}}
    try:
        resultado = graph.invoke({"mensaje": args.mensaje}, config=config)
    finally:
        if hasattr(modulo, "cerrar_memoria"):
            modulo.cerrar_memoria()

    if args.saltos and isinstance(resultado, dict) and resultado.get("saltos"):
        print(f"Saltos: {' → '.join(resultado['saltos'])}")
        if resultado.get("motivo"):
            print(f"Motivo: {resultado['motivo']}")

    if isinstance(resultado, dict) and "messages" in resultado:
        resultado = {k: v for k, v in resultado.items() if k != "messages"}

    print(resultado)


if __name__ == "__main__":
    main()
