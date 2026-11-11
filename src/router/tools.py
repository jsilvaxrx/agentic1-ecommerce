"""Herramientas de solo lectura para el agente de preventa."""

from typing import Any

from .catalogo import consultar_catalogo


def buscar_productos(
    consulta: str,
    categoria: str | None = None,
    marca: str | None = None,
    precio_max: int | None = None,
) -> list[dict[str, Any]] | str:
    """Busca hasta cinco productos por nombre, categoría, marca y precio máximo en pesos chilenos."""
    condiciones: list[str] = []
    parametros: list[Any] = []
    for palabra in consulta.split():
        condiciones.append("nombre ILIKE %s")
        parametros.append(f"%{palabra}%")
    if categoria:
        condiciones.append("categoria = %s")
        parametros.append(categoria)
    if marca:
        condiciones.append("(marca ILIKE %s OR nombre ILIKE %s)")
        parametros.extend((f"%{marca}%", f"%{marca}%"))
    if precio_max is not None:
        condiciones.append("precio_internet <= %s")
        parametros.append(precio_max)

    where = f" WHERE {' AND '.join(condiciones)}" if condiciones else ""
    return consultar_catalogo(
        "SELECT sku_id, nombre, marca, precio_internet, descuento_pct, rating "
        f"FROM catalogo.productos_unicos{where} "
        "ORDER BY rating DESC NULLS LAST, nombre ASC LIMIT 5",
        tuple(parametros),
    )


def ver_producto(sku_id: str) -> list[dict[str, Any]] | str:
    """Obtiene el detalle completo y el link de un producto por su SKU."""
    return consultar_catalogo(
        "SELECT sku_id, nombre, marca, categoria, subcategoria, precio_normal, precio_internet, "
        "descuento_pct, rating, tienda_oficial, link, imagen "
        "FROM catalogo.productos_unicos WHERE sku_id = %s",
        (sku_id,),
    )


def mejores_ofertas(categoria: str | None = None, limite: int = 5) -> list[dict[str, Any]] | str:
    """Lista hasta cinco productos con el mayor descuento disponible, opcionalmente por categoría."""
    limite = min(max(limite, 1), 5)
    condicion = " WHERE descuento_pct IS NOT NULL"
    parametros: tuple[Any, ...] = ()
    if categoria:
        condicion += " AND categoria = %s"
        parametros = (categoria,)
    return consultar_catalogo(
        "SELECT sku_id, nombre, marca, precio_internet, descuento_pct, rating, link "
        f"FROM catalogo.productos_unicos{condicion} "
        "ORDER BY descuento_pct DESC, rating DESC NULLS LAST, nombre ASC LIMIT %s",
        (*parametros, limite),
    )
