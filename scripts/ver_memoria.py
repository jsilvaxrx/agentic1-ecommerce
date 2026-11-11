"""Inspecciona los checkpoints persistidos del router en Postgres."""

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.router import graph as router_graph


def tipo_mensaje(mensaje: object) -> str:
    nombre = type(mensaje).__name__
    return {"HumanMessage": "Humano", "AIMessage": "Asistente"}.get(nombre, nombre)


def main() -> None:
    thread_id = sys.argv[1] if len(sys.argv) > 1 else None
    if router_graph.iniciar_memoria() != "postgres":
        print("No hay memoria persistente disponible: configura DATABASE_URL y verifica Postgres.", file=sys.stderr)
        raise SystemExit(1)

    try:
        checkpointer = router_graph.graph.checkpointer
        if thread_id:
            checkpoints = list(checkpointer.list({"configurable": {"thread_id": thread_id}}))
            if not checkpoints:
                print(f"No hay checkpoints para el hilo {thread_id!r}.")
                return
            messages = checkpoints[0].checkpoint["channel_values"].get("messages", [])
            for mensaje in messages:
                print(f"{tipo_mensaje(mensaje)}: {mensaje.content}")
            return

        resumen: dict[str, list[object]] = defaultdict(list)
        for checkpoint in checkpointer.list(None):
            resumen[checkpoint.config["configurable"]["thread_id"]].append(checkpoint)
        if not resumen:
            print("No hay checkpoints guardados.")
            return
        for hilo, checkpoints in sorted(resumen.items()):
            ultimo = checkpoints[0].checkpoint.get("ts", "sin fecha")
            print(f"{hilo}: {len(checkpoints)} checkpoints, último: {ultimo}")
    finally:
        router_graph.cerrar_memoria()


if __name__ == "__main__":
    main()
