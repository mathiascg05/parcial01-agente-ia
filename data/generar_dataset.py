"""
Generador del dataset operacional (fuente) de Distribuidora Ávila C.A.

Empresa ficticia. Simula las exportaciones del sistema transaccional (OLTP / punto de venta + CRM)
desde el 01-01-2025 hasta el 30-09-2026. La ejecución es determinista (semilla fija): siempre
produce exactamente los mismos archivos, lo que permite reproducir la conciliación.

Problemas de calidad sembrados A PROPÓSITO para demostrar los controles del Data Mart:
  1. Tickets sin cliente identificado (consumidor final)          -> cliente_sk = -1 (No informado)
  2. Tickets con cliente_id inexistente en el maestro (C9xxxx)    -> cliente_sk = -2 (Sin correspondencia)
  3. Líneas con producto_id inexistente en el catálogo (P9xxx)    -> producto_sk = -2 (Sin correspondencia)
  4. Tickets ANULADOS                                             -> se excluyen del hecho
  5. Líneas duplicadas exactas (error de sincronización del POS)  -> se deduplican en el ETL
  6. Líneas con cantidad <= 0                                     -> se rechazan y se registran
  7. Productos sin subcategoría y clientes sin ciudad             -> 'Sin subcategoría' / 'No informada'

Uso:  python data/generar_dataset.py            (escribe en data/fuente/)
"""
from __future__ import annotations

import csv
import random
from datetime import date, datetime, timedelta
from pathlib import Path

SEMILLA = 20261028
INICIO = date(2025, 1, 1)
FIN = date(2026, 9, 30)
SALIDA = Path(__file__).resolve().parent / "fuente"

rnd = random.Random(SEMILLA)

# ---------------------------------------------------------------------------
# Maestros
# ---------------------------------------------------------------------------
SUCURSALES = [
    # id, nombre, ciudad, estado, region, apertura, factor_trafico, factor_ticket
    ("SUC01", "Chacao", "Caracas", "Miranda", "Capital", date(2016, 5, 2), 1.35, 1.25),
    ("SUC02", "La Candelaria", "Caracas", "Distrito Capital", "Capital", date(2014, 3, 10), 1.15, 0.95),
    ("SUC03", "Valencia Norte", "Valencia", "Carabobo", "Central", date(2017, 9, 1), 1.05, 1.00),
    ("SUC04", "Maracaibo Centro", "Maracaibo", "Zulia", "Occidental", date(2015, 1, 15), 1.00, 0.92),
    ("SUC05", "Barquisimeto Este", "Barquisimeto", "Lara", "Centroccidental", date(2019, 6, 3), 0.80, 0.90),
    ("SUC06", "Puerto Ordaz", "Ciudad Guayana", "Bolívar", "Guayana", date(2018, 11, 5), 0.75, 1.05),
    ("SUC07", "Lechería", "Lechería", "Anzoátegui", "Oriental", date(2026, 3, 2), 0.70, 1.10),
]

CANALES = [
    ("CAN01", "Tienda física", "Presencial"),
    ("CAN02", "E-commerce web", "Digital"),
    ("CAN03", "App móvil", "Digital"),
    ("CAN04", "Delivery WhatsApp", "Digital"),
    ("CAN05", "Mayorista B2B", "Corporativo"),
]

# categoria: (margen_min, margen_max, precio_min, precio_max, cant_max_retail, lanzamiento, subcategorias, marcas)
CATEGORIAS = {
    "Alimentos": (0.17, 0.25, 1.0, 14.0, 6, None,
                  ["Granos y harinas", "Enlatados", "Lácteos", "Snacks"], ["Doña Clara", "Campo Llano", "La Sabanera"]),
    "Bebidas": (0.22, 0.31, 1.0, 22.0, 6, None,
                ["Refrescos", "Jugos", "Agua", "Café y té"], ["Río Caura", "Frescolandia", "Cumbre Andina"]),
    "Limpieza": (0.27, 0.36, 2.0, 16.0, 4, None,
                 ["Detergentes", "Desinfectantes", "Papel"], ["Brillo Total", "Hogar Limpio"]),
    "Cuidado personal": (0.34, 0.46, 2.0, 26.0, 3, None,
                         ["Higiene", "Cuidado del cabello", "Cosmética"], ["Aloe Caribe", "Piel Serena", "Natural Ávila"]),
    "Electrodomésticos": (0.11, 0.19, 25.0, 420.0, 1, None,
                          ["Cocina", "Climatización", "Lavado"], ["Kalor", "VentiMax", "Hogarix"]),
    "Tecnología": (0.08, 0.16, 12.0, 650.0, 1, None,
                   ["Telefonía", "Computación", "Accesorios"], ["NovaTek", "Orinoco Digital", "Pixelia"]),
    "Hogar": (0.30, 0.41, 4.0, 85.0, 2, None,
              ["Cocina y mesa", "Decoración", "Organización"], ["Casa Ávila", "Tepuy Home"]),
    "Ferretería": (0.24, 0.35, 2.0, 70.0, 3, None,
                   ["Herramientas", "Electricidad", "Pinturas"], ["Fuerte Llanero", "TecnoObra"]),
    "Papelería": (0.35, 0.47, 0.5, 15.0, 5, None,
                  ["Escolar", "Oficina"], ["Cuaderno Feliz", "Pluma Andina"]),
    "Jardinería": (0.30, 0.40, 5.0, 45.0, 2, date(2026, 4, 1),
                   ["Plantas", "Herramientas de jardín"], ["Verde Caribe"]),
}

NOMBRES_PRODUCTO = {
    "Granos y harinas": ["Harina de maíz 1kg", "Arroz blanco 1kg", "Caraotas negras 500g", "Pasta corta 1kg"],
    "Enlatados": ["Atún en aceite 140g", "Sardinas 170g", "Maíz dulce 300g"],
    "Lácteos": ["Queso blanco 500g", "Leche en polvo 900g", "Mantequilla 250g"],
    "Snacks": ["Galletas de soda", "Tostones de plátano", "Chocolate 100g"],
    "Refrescos": ["Refresco cola 2L", "Refresco naranja 1.5L", "Malta 355ml pack 6"],
    "Jugos": ["Jugo de naranja 1L", "Néctar de durazno 1L"],
    "Agua": ["Agua mineral 5L", "Agua saborizada 600ml"],
    "Café y té": ["Café molido 500g", "Té verde 25 sobres"],
    "Detergentes": ["Detergente en polvo 2kg", "Lavaplatos líquido 750ml"],
    "Desinfectantes": ["Cloro 1L", "Desinfectante lavanda 1L"],
    "Papel": ["Papel higiénico 12 rollos", "Servilletas 200u"],
    "Higiene": ["Jabón de baño pack 3", "Crema dental 100ml", "Desodorante roll-on"],
    "Cuidado del cabello": ["Champú 400ml", "Acondicionador 400ml"],
    "Cosmética": ["Protector solar FPS50", "Crema hidratante 200ml"],
    "Cocina": ["Licuadora 600W", "Cafetera 12 tazas", "Freidora de aire 4L", "Microondas 20L"],
    "Climatización": ["Ventilador de pie 18in", "Aire acondicionado 12000BTU"],
    "Lavado": ["Lavadora 12kg", "Plancha a vapor"],
    "Telefonía": ["Teléfono inteligente 128GB", "Teléfono básico"],
    "Computación": ["Laptop 15in 8GB", "Tableta 10in", "Monitor 24in"],
    "Accesorios": ["Audífonos inalámbricos", "Cargador rápido 20W", "Mouse inalámbrico", "Memoria USB 64GB"],
    "Cocina y mesa": ["Juego de ollas 5 piezas", "Vajilla 16 piezas", "Juego de cubiertos"],
    "Decoración": ["Cojín decorativo", "Lámpara de mesa"],
    "Organización": ["Caja organizadora 30L", "Repisa flotante"],
    "Herramientas": ["Taladro percutor", "Juego de destornilladores", "Martillo de uña"],
    "Electricidad": ["Bombillo LED 12W pack 4", "Extensión eléctrica 5m"],
    "Pinturas": ["Pintura de caucho galón", "Brocha 3in"],
    "Escolar": ["Cuaderno universitario", "Caja de colores 24", "Morral escolar"],
    "Oficina": ["Resma carta 500h", "Bolígrafos pack 12"],
    "Plantas": ["Suculenta en maceta", "Tierra abonada 5kg"],
    "Herramientas de jardín": ["Manguera 15m", "Tijera de podar"],
}

PRECIOS_BASE = {'Harina de maíz 1kg': 1.2, 'Arroz blanco 1kg': 1.5, 'Caraotas negras 500g': 1.8, 'Pasta corta 1kg': 1.6, 'Atún en aceite 140g': 2.4, 'Sardinas 170g': 1.3, 'Maíz dulce 300g': 1.9, 'Queso blanco 500g': 4.5, 'Leche en polvo 900g': 9.5, 'Mantequilla 250g': 3.2, 'Galletas de soda': 1.4, 'Tostones de plátano': 1.7, 'Chocolate 100g': 2.2, 'Refresco cola 2L': 2.3, 'Refresco naranja 1.5L': 1.9, 'Malta 355ml pack 6': 5.5, 'Jugo de naranja 1L': 2.6, 'Néctar de durazno 1L': 2.1, 'Agua mineral 5L': 2.8, 'Agua saborizada 600ml': 1.1, 'Café molido 500g': 6.8, 'Té verde 25 sobres': 3.4, 'Detergente en polvo 2kg': 7.5, 'Lavaplatos líquido 750ml': 3.1, 'Cloro 1L': 1.6, 'Desinfectante lavanda 1L': 2.9, 'Papel higiénico 12 rollos': 8.9, 'Servilletas 200u': 2.3, 'Jabón de baño pack 3': 3.6, 'Crema dental 100ml': 2.7, 'Desodorante roll-on': 4.2, 'Champú 400ml': 6.1, 'Acondicionador 400ml': 6.4, 'Protector solar FPS50': 14.5, 'Crema hidratante 200ml': 9.8, 'Licuadora 600W': 48.0, 'Cafetera 12 tazas': 39.0, 'Freidora de aire 4L': 85.0, 'Microondas 20L': 110.0, 'Ventilador de pie 18in': 42.0, 'Aire acondicionado 12000BTU': 390.0, 'Lavadora 12kg': 360.0, 'Plancha a vapor': 28.0, 'Teléfono inteligente 128GB': 220.0, 'Teléfono básico': 35.0, 'Laptop 15in 8GB': 520.0, 'Tableta 10in': 180.0, 'Monitor 24in': 150.0, 'Audífonos inalámbricos': 32.0, 'Cargador rápido 20W': 14.0, 'Mouse inalámbrico': 12.0, 'Memoria USB 64GB': 9.0, 'Juego de ollas 5 piezas': 55.0, 'Vajilla 16 piezas': 38.0, 'Juego de cubiertos': 22.0, 'Cojín decorativo': 9.5, 'Lámpara de mesa': 24.0, 'Caja organizadora 30L': 11.0, 'Repisa flotante': 16.0, 'Taladro percutor': 65.0, 'Juego de destornilladores': 15.0, 'Martillo de uña': 8.5, 'Bombillo LED 12W pack 4': 7.0, 'Extensión eléctrica 5m': 6.5, 'Pintura de caucho galón': 24.0, 'Brocha 3in': 3.2, 'Cuaderno universitario': 2.5, 'Caja de colores 24': 4.8, 'Morral escolar': 18.0, 'Resma carta 500h': 6.5, 'Bolígrafos pack 12': 3.9, 'Suculenta en maceta': 6.0, 'Tierra abonada 5kg': 7.5, 'Manguera 15m': 19.0, 'Tijera de podar': 12.5}

SEGMENTOS = ["Minorista", "Frecuente", "Premium", "Corporativo"]

NOMBRES = ["María", "José", "Luis", "Ana", "Carlos", "Gabriela", "Andrés", "Daniela", "Miguel", "Valentina",
           "Jesús", "Andrea", "Pedro", "Carolina", "Rafael", "Mariana", "Jorge", "Isabel", "Ricardo", "Paola",
           "Manuel", "Patricia", "Alejandro", "Fernanda", "Eduardo", "Sofía", "Héctor", "Lucía", "Oscar", "Elena"]
APELLIDOS = ["González", "Rodríguez", "Pérez", "Hernández", "García", "Martínez", "López", "Díaz", "Sánchez",
             "Ramírez", "Torres", "Rojas", "Medina", "Castillo", "Morales", "Silva", "Mendoza", "Vargas",
             "Bracho", "Briceño", "Urdaneta", "Colmenares", "Salazar", "Parra", "Contreras"]
EMPRESAS = ["Inversiones", "Distribuidora", "Comercial", "Bodegón", "Suministros", "Corporación", "Grupo"]
EMPRESAS2 = ["El Samán", "Los Andes", "Guaraira", "Caribe", "Del Lago", "Tepuy", "Araguaney", "Moriche",
             "La Guaira", "Mérida", "El Ávila", "Sabana", "Canaima", "Orinoco", "Paraguaná"]


def fecha_rand(desde: date, hasta: date) -> date:
    return desde + timedelta(days=rnd.randint(0, (hasta - desde).days))


def generar_productos():
    productos = []
    n = 1
    for cat, (mmin, mmax, pmin, pmax, _cant, lanz, subcats, marcas) in CATEGORIAS.items():
        for sub in subcats:
            for nombre in NOMBRES_PRODUCTO[sub]:
                marca = rnd.choice(marcas)
                # precio de referencia del producto con una variación por marca de ±12 %
                precio = round(PRECIOS_BASE[nombre] * rnd.uniform(0.88, 1.12), 2)
                margen = rnd.uniform(mmin, mmax)
                costo = round(precio * (1 - margen), 2)
                productos.append({
                    "producto_id": f"P{n:04d}",
                    "sku": f"{cat[:3].upper()}-{n:05d}",
                    "nombre": f"{nombre} {marca}",
                    "categoria": cat,
                    "subcategoria": sub,
                    "marca": marca,
                    "precio_lista": f"{precio:.2f}",
                    "costo_estandar": f"{costo:.2f}",
                    "fecha_lanzamiento": (lanz or date(2020, 1, 1)).isoformat(),
                    "activo": "S",
                })
                n += 1
    # Problema 7: algunos productos sin subcategoría en el maestro
    for p in rnd.sample(productos, 4):
        p["subcategoria"] = ""
    return productos


def generar_clientes():
    """Clientes y su historial de segmento (fuente del SCD Tipo 2)."""
    clientes, historial = [], []
    cuotas = [("Minorista", 1150), ("Frecuente", 700), ("Premium", 300), ("Corporativo", 210)]
    ciudades = [s[2] for s in SUCURSALES]
    n = 1
    for seg, cant in cuotas:
        for _ in range(cant):
            cid = f"C{n:05d}"
            juridico = seg == "Corporativo"
            if juridico:
                nombre = f"{rnd.choice(EMPRESAS)} {rnd.choice(EMPRESAS2)} C.A."
                doc = f"J-{rnd.randint(30000000, 50999999)}-{rnd.randint(0, 9)}"
            else:
                nombre = f"{rnd.choice(NOMBRES)} {rnd.choice(APELLIDOS)}"
                doc = f"V-{rnd.randint(6000000, 32000000)}"
            registro = fecha_rand(date(2019, 1, 1), date(2025, 6, 30))
            ciudad = rnd.choice(ciudades)
            # El segmento inicial vigente al 01-01-2025 (o desde el registro)
            inicio = max(registro, date(2024, 1, 1))
            tramos = [(seg, inicio)]
            r = rnd.random()
            # Cambios de segmento (reclasificaciones del CRM)
            if seg == "Minorista" and r < 0.12:
                tramos.append(("Frecuente", fecha_rand(date(2025, 3, 1), date(2026, 8, 31))))
            elif seg == "Frecuente" and r < 0.14:
                tramos.append(("Premium", fecha_rand(date(2025, 3, 1), date(2026, 8, 31))))
            elif seg == "Frecuente" and r < 0.20:
                tramos.append(("Minorista", fecha_rand(date(2025, 6, 1), date(2026, 8, 31))))
            elif seg == "Premium" and r < 0.10:
                tramos.append(("Frecuente", fecha_rand(date(2025, 6, 1), date(2026, 8, 31))))
            elif seg == "Corporativo" and r < 0.30:
                # Reclasificación de corporativos a Frecuente en 2026 (pérdida de contratos)
                tramos.append(("Frecuente", fecha_rand(date(2026, 1, 5), date(2026, 6, 30))))
            # una reclasificación sólo es válida si ocurre después del alta del cliente
            if len(tramos) > 1 and tramos[1][1] <= inicio + timedelta(days=30):
                tramos = tramos[:1]
            for i, (s, desde) in enumerate(tramos):
                hasta = tramos[i + 1][1] - timedelta(days=1) if i + 1 < len(tramos) else None
                historial.append({
                    "cliente_id": cid, "segmento": s,
                    "fecha_desde": desde.isoformat(), "fecha_hasta": hasta.isoformat() if hasta else "",
                })
            clientes.append({
                "cliente_id": cid, "nombre": nombre, "documento": doc,
                "tipo_cliente": "Jurídico" if juridico else "Natural",
                "ciudad": ciudad, "fecha_registro": registro.isoformat(),
                "segmento_actual": tramos[-1][0],
                "_tramos": tramos, "_registro": registro,
            })
            n += 1
    # Problema 7: clientes sin ciudad
    for c in rnd.sample(clientes, 25):
        c["ciudad"] = ""
    return clientes, historial


def segmento_en(cliente, d: date):
    seg = None
    for s, desde in cliente["_tramos"]:
        if d >= desde:
            seg = s
    return seg


# Factores de negocio --------------------------------------------------------
ESTACIONALIDAD = {1: 0.85, 2: 0.88, 3: 0.95, 4: 0.97, 5: 1.0, 6: 0.98, 7: 1.02, 8: 1.10, 9: 1.05,
                  10: 1.0, 11: 1.12, 12: 1.38}
DIA_SEMANA = {0: 0.90, 1: 0.92, 2: 0.95, 3: 1.0, 4: 1.12, 5: 1.25, 6: 0.86}


def peso_segmento(seg: str, d: date) -> float:
    meses = (d.year - 2025) * 12 + d.month - 1  # 0..20
    base = {"Minorista": 0.42, "Frecuente": 0.30, "Premium": 0.14, "Corporativo": 0.14}[seg]
    tendencia = {"Minorista": 0.002, "Frecuente": 0.004, "Premium": 0.016, "Corporativo": -0.022}[seg]
    return base * max(0.25, 1 + tendencia * meses)


def probs_canal(seg: str, d: date):
    meses = (d.year - 2025) * 12 + d.month - 1
    dig = 0.012 * meses  # crecimiento digital
    if seg == "Corporativo":
        return [0.18, 0.06, 0.04, 0.02, 0.70]
    if seg == "Premium":
        return [0.40 - dig, 0.25 + dig * 0.4, 0.27 + dig * 0.6, 0.08, 0.0]
    if seg == "Frecuente":
        return [0.55 - dig, 0.15 + dig * 0.3, 0.17 + dig * 0.5, 0.13 + dig * 0.2, 0.0]
    return [0.68 - dig * 0.7, 0.10 + dig * 0.2, 0.10 + dig * 0.3, 0.12 + dig * 0.2, 0.0]


def pesos_categoria(d: date, mayorista: bool):
    w = {"Alimentos": 30, "Bebidas": 22, "Limpieza": 14, "Cuidado personal": 12, "Electrodomésticos": 3,
         "Tecnología": 3, "Hogar": 6, "Ferretería": 6, "Papelería": 4, "Jardinería": 0}
    if d.month in (8, 9):
        w["Papelería"] = 14  # temporada escolar
    if d.month in (11, 12):
        w["Electrodomésticos"], w["Tecnología"], w["Hogar"] = 8, 9, 9
    if d >= date(2026, 4, 1):
        w["Jardinería"] = 3
    if mayorista:
        w["Alimentos"], w["Bebidas"], w["Limpieza"] = 34, 28, 20
        w["Tecnología"], w["Electrodomésticos"] = 2, 2
    return w


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    productos = generar_productos()
    clientes, historial = generar_clientes()
    prod_por_cat = {}
    for p in productos:
        prod_por_cat.setdefault(p["categoria"], []).append(p)

    tickets, detalle = [], []
    nt = 1
    d = INICIO
    while d <= FIN:
        meses = (d.year - 2025) * 12 + d.month - 1
        sucs_abiertas = [s for s in SUCURSALES if s[5] <= d]
        n_tickets = int(46 * ESTACIONALIDAD[d.month] * DIA_SEMANA[d.weekday()] * (1 + 0.006 * meses)
                        * rnd.uniform(0.85, 1.15))
        # clientes disponibles por segmento en la fecha
        por_seg = {s: [] for s in SEGMENTOS}
        for c in clientes:
            if c["_registro"] <= d:
                s = segmento_en(c, d)
                if s:
                    por_seg[s].append(c)
        pesos_seg = [peso_segmento(s, d) for s in SEGMENTOS]
        for _ in range(n_tickets):
            seg = rnd.choices(SEGMENTOS, weights=pesos_seg)[0]
            canal = rnd.choices(CANALES, weights=probs_canal(seg, d))[0]
            suc = rnd.choices(sucs_abiertas, weights=[s[6] for s in sucs_abiertas])[0]
            cliente_id = rnd.choice(por_seg[seg])["cliente_id"] if por_seg[seg] else ""
            # Problema 1: consumidor final sin identificar (solo tienda física)
            if canal[0] == "CAN01" and seg == "Minorista" and rnd.random() < 0.10:
                cliente_id = ""
            # Problema 2: cliente inexistente en el maestro
            if rnd.random() < 0.004:
                cliente_id = f"C9{rnd.randint(1000, 9999)}"
            hora = datetime(d.year, d.month, d.day, rnd.randint(8, 20), rnd.randint(0, 59), rnd.randint(0, 59))
            estado = "ANULADO" if rnd.random() < 0.015 else "COMPLETADO"
            tid = f"T{nt:07d}"
            nt += 1
            tickets.append({
                "ticket_id": tid, "fecha_hora": hora.isoformat(sep=" "), "sucursal_id": suc[0],
                "canal_id": canal[0], "cliente_id": cliente_id, "estado": estado,
                "metodo_pago": rnd.choice(["Efectivo USD", "Pago móvil", "Punto de venta", "Zelle", "Transferencia"]),
            })
            mayorista = canal[0] == "CAN05"
            if mayorista:
                n_lineas = rnd.randint(3, 9)
            else:
                base_lineas = rnd.choices([1, 2, 3, 4, 5, 6], [22, 26, 22, 15, 9, 6])[0]
                n_lineas = max(1, round(base_lineas * suc[7] ** 1.5))  # canasta mayor en sucursales premium
            wcat = pesos_categoria(d, mayorista)
            cats = [c for c in wcat if wcat[c] > 0]
            for linea in range(1, n_lineas + 1):
                cat = rnd.choices(cats, weights=[wcat[c] for c in cats])[0]
                p = rnd.choice(prod_por_cat[cat])
                cant_max = CATEGORIAS[cat][4]
                if mayorista:
                    cant = rnd.randint(1, 4) if cant_max == 1 else rnd.randint(6, 36)
                else:
                    cant = rnd.randint(1, cant_max)
                inflacion = 1 + 0.0035 * meses
                precio = round(float(p["precio_lista"]) * inflacion, 2)
                costo = round(float(p["costo_estandar"]) * inflacion * rnd.uniform(0.98, 1.03), 2)
                if mayorista:
                    desc_pct = rnd.uniform(0.08, 0.16)
                elif rnd.random() < 0.12:
                    desc_pct = rnd.choice([0.05, 0.10, 0.15, 0.20])
                else:
                    desc_pct = 0.0
                descuento = round(cant * precio * desc_pct, 2)
                producto_id = p["producto_id"]
                # Problema 3: producto inexistente
                if rnd.random() < 0.002:
                    producto_id = f"P9{rnd.randint(100, 999)}"
                # Problema 6: cantidad inválida
                if rnd.random() < 0.0012:
                    cant = rnd.choice([0, -1, -2])
                    descuento = 0.0
                fila = {"ticket_id": tid, "linea": linea, "producto_id": producto_id, "cantidad": cant,
                        "precio_unitario": f"{precio:.2f}", "descuento": f"{descuento:.2f}",
                        "costo_unitario": f"{costo:.2f}"}
                detalle.append(fila)
                # Problema 5: duplicado exacto
                if rnd.random() < 0.004:
                    detalle.append(dict(fila))
        d += timedelta(days=1)

    def escribir(nombre, filas, campos):
        with open(SALIDA / nombre, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
            w.writeheader()
            w.writerows(filas)

    escribir("sucursales.csv", [dict(zip(["sucursal_id", "nombre", "ciudad", "estado", "region", "fecha_apertura"],
                                          [s[0], s[1], s[2], s[3], s[4], s[5].isoformat()])) for s in SUCURSALES],
             ["sucursal_id", "nombre", "ciudad", "estado", "region", "fecha_apertura"])
    escribir("canales.csv", [dict(zip(["canal_id", "nombre", "tipo_canal"], c)) for c in CANALES],
             ["canal_id", "nombre", "tipo_canal"])
    escribir("productos.csv", productos, ["producto_id", "sku", "nombre", "categoria", "subcategoria", "marca",
                                          "precio_lista", "costo_estandar", "fecha_lanzamiento", "activo"])
    escribir("clientes.csv", clientes, ["cliente_id", "nombre", "documento", "tipo_cliente", "ciudad",
                                        "fecha_registro", "segmento_actual"])
    escribir("cliente_segmento_historial.csv", historial, ["cliente_id", "segmento", "fecha_desde", "fecha_hasta"])
    escribir("tickets.csv", tickets, ["ticket_id", "fecha_hora", "sucursal_id", "canal_id", "cliente_id",
                                      "estado", "metodo_pago"])
    escribir("ticket_detalle.csv", detalle, ["ticket_id", "linea", "producto_id", "cantidad", "precio_unitario",
                                             "descuento", "costo_unitario"])
    print(f"productos={len(productos)} clientes={len(clientes)} historial={len(historial)} "
          f"tickets={len(tickets)} lineas={len(detalle)}")


if __name__ == "__main__":
    main()
