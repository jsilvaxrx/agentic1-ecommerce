"""Muestra productos del catálogo desde la terminal."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.router.catalogo import consultar_catalogo


def main() -> None:
    if len(sys.argv) > 1:
        texto = sys.argv[1]
        productos = consultar_catalogo(
            "SELECT nombre, precio_internet, rating FROM catalogo.productos_unicos "
            "WHERE nombre ILIKE %s ORDER BY nombre ASC LIMIT 10",
            (f"%{texto}%",),
        )
        if isinstance(productos, str):
            print(productos)
            return
        for producto in productos:
            print(f"{producto['nombre']} | ${producto['precio_internet']} | rating: {producto['rating']}")
        return

    categorias = consultar_catalogo(
        "SELECT categoria, COUNT(*) AS cantidad FROM catalogo.productos_unicos GROUP BY categoria ORDER BY categoria"
    )
    if isinstance(categorias, str):
        print(categorias)
        return
    for categoria in categorias:
        print(f"{categoria['categoria']}: {categoria['cantidad']}")


if __name__ == "__main__":
    main()
