// Genera EquipoXX_Defensa.pptx   node docs/defensa/build_defensa.js XX
const pptxgen = require("pptxgenjs");
const path = require("path");
const fs = require("fs");
const { applyTheme } = require(process.env.PPTX_SKILL + "/scripts/apply_theme.js");

const EQUIPO = process.argv[2] || "XX";
const RAIZ = path.resolve(__dirname, "..", "..");
const DIAG = path.join(RAIZ, "docs", "diagramas");
const OUT = path.join(RAIZ, "entregables", `Equipo${EQUIPO}_Defensa.pptx`);
const pruebas = JSON.parse(fs.readFileSync(path.join(RAIZ, "docs/evidencias/pruebas.json"), "utf8"));
const nOk = pruebas.filter(p => p.estado === "OK").length;

const THEME = {
  name: "Agente Analitico",
  headFontFace: "Cambria", bodyFontFace: "Calibri",
  colors: { dk1: "1A2B33", lt1: "FFFFFF", dk2: "0B3C49", lt2: "EEF4F6",
    accent1: "1B998B", accent2: "F4A259", accent3: "6D3FC7", accent4: "C8553D",
    accent5: "5B8E7D", accent6: "8AA1AD", hlink: "1B998B", folHlink: "6D3FC7" },
};
const HEX = THEME.colors;

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "Defensa Parcial 01 - Agente Analítico de IA";
pres.author = `Equipo ${EQUIPO}`;
const C = pres.SchemeColor;
const W = 13.333;

// ---------------------------------------------------------------- layouts
pres.defineSlideMaster({
  title: "PORTADA", background: { color: HEX.dk2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.8, y: 2.0, w: 11.5, h: 1.9, fontFace: THEME.headFontFace,
      fontSize: 44, bold: true, color: C.background1, valign: "bottom", align: "left" }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.8, y: 4.05, w: 11.5, h: 1.2, fontSize: 20,
      color: C.accent2, valign: "top", align: "left" }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "CONTENIDO", background: { color: HEX.lt1 },
  margin: [0.5, 0.6, 0.6, 0.6],
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.35, w: 12.1, h: 0.9, fontFace: THEME.headFontFace,
      fontSize: 32, bold: true, color: C.text2, valign: "middle", margin: 0, align: "left" }, text: "" } },
    { text: { text: `Equipo ${EQUIPO} · Parcial 01 · Tópicos Especiales para la Gestión de Datos`,
      options: { x: 0.6, y: 7.05, w: 8, h: 0.3, fontSize: 10, color: C.accent6, margin: 0 } } },
  ],
  slideNumber: { x: 12.2, y: 7.05, w: 0.5, h: 0.3, fontSize: 10, color: C.accent6, align: "right" },
});

const SECCIONES = ["Introducción", "Data Mart", "BDOO", "Agente", "Demostración y resultados", "Cierre"];
let seccionActual = null;
function nueva(masterName, seccion) {
  if (seccion !== seccionActual) { pres.addSection({ title: seccion }); seccionActual = seccion; }
  return pres.addSlide({ masterName, sectionTitle: seccion });
}
function tarjeta(s, x, y, w, h, titulo, cuerpo, color, nombre, tamCuerpo = 14) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.12, fill: { color: C.background2 },
    line: { color: C.background2 }, objectName: nombre + "-fondo" });
  s.addShape(pres.shapes.OVAL, { x: x + 0.25, y: y + 0.25, w: 0.42, h: 0.42, fill: { color: color }, line: { color: color },
    objectName: nombre + "-icono" });
  s.addText(titulo, { x: x + 0.8, y: y + 0.2, w: w - 1.0, h: 0.52, fontSize: 17, bold: true, color: C.text2, margin: 0,
    valign: "middle", isTextBox: true, objectName: nombre + "-titulo" });
  s.addText(cuerpo, { x: x + 0.25, y: y + 0.85, w: w - 0.5, h: h - 1.0, fontSize: tamCuerpo, color: C.text1, margin: 0,
    valign: "top", isTextBox: true, objectName: nombre + "-texto", paraSpaceAfter: 4 });
}
function stat(s, x, y, w, valor, etiqueta, color, nombre) {
  s.addText(valor, { x, y, w, h: 1.0, fontSize: 54, bold: true, color, fontFace: THEME.headFontFace, margin: 0,
    isTextBox: true, objectName: nombre + "-valor" });
  s.addText(etiqueta, { x, y: y + 1.0, w, h: 0.7, fontSize: 14, color: C.text1, margin: 0, valign: "top",
    isTextBox: true, objectName: nombre + "-etiqueta" });
}
function bullets(items, opts = {}) {
  return items.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < items.length - 1, paraSpaceAfter: 8, ...opts } }));
}

// 1 ---------------------------------------------------------------- portada
let s = nueva("PORTADA", "Introducción");
s.addText("Agente analítico de IA con Data Mart y BDOO", { placeholder: "title" });
s.addText("Parcial 01 · Distribuidora Ávila C.A. · Defensa 02-11-2026", { placeholder: "body" });
s.addText([{ text: `Equipo ${EQUIPO}`, options: { bold: true, breakLine: true } },
  { text: "Mathias Carstens · Mikel Muñoz · Leonardo Reyes · Federico Celis · Fernando Álvarez", options: {} }],
  { x: 0.8, y: 5.6, w: 11.5, h: 0.9, fontSize: 16, color: C.background1, margin: 0, isTextBox: true, objectName: "integrantes" });
s.addText("Tópicos Especiales para la Gestión de Datos · Prof. Armen Djenanian · UCAB",
  { x: 0.8, y: 0.6, w: 11.5, h: 0.4, fontSize: 14, color: C.accent6, margin: 0, isTextBox: true, objectName: "materia" });
s.addNotes("Presenta: Mathias (≈30 s). Saludo, equipo, caso y reparto: Mikel Data Mart, Leonardo SCD y calidad, Federico BDOO, Fernando agente y pruebas, Mathias demostración.");

// 2 ---------------------------------------------------------------- reto
s = nueva("CONTENIDO", "Introducción");
s.addText("Preguntas en lenguaje natural, respuestas verificables", { placeholder: "title" });
s.addText([{ text: "Principio rector: ", options: { bold: true, color: C.accent1 } },
  { text: "el Data Mart contiene la verdad analítica; la BDOO, los objetos y la trazabilidad del agente; el agente conecta la pregunta con una respuesta sustentada." }],
  { x: 0.6, y: 1.45, w: 12.1, h: 0.9, fontSize: 18, color: C.text1, margin: 0, isTextBox: true, objectName: "principio" });
stat(s, 0.6, 2.75, 2.8, `${nOk}/${pruebas.length}`, "casos de prueba correctos contra valores calculados por separado", C.accent1, "s-pruebas");
stat(s, 3.7, 2.75, 2.8, "7/7", "controles de conciliación con la fuente, al centavo", C.accent3, "s-conc");
stat(s, 6.8, 2.75, 2.8, "11", "reglas de validación antes de responder", C.accent2, "s-reglas");
stat(s, 9.9, 2.75, 2.8, "0", "SQL escrito por el LLM: sólo devuelve códigos del catálogo", C.accent4, "s-sql");
s.addText([{ text: "Caso: ", options: { bold: true } },
  { text: "empresa comercial ficticia, ventas ene-2025 a sep-2026 · 30.970 tickets · 7 sucursales · 5 canales · 4 segmentos · fuente con errores de calidad sembrados a propósito (anulados, duplicados, claves huérfanas)." }],
  { x: 0.6, y: 5.3, w: 12.1, h: 1.0, fontSize: 15, color: C.text1, margin: 0, isTextBox: true, objectName: "caso" });
s.addNotes("Mathias (≈1 min). El reto: usuarios no técnicos, respuestas trazables, sin inventar. Al no haber dataset, generamos una fuente determinista con errores sembrados para demostrar los controles.");

// 3 ---------------------------------------------------------------- arquitectura
s = nueva("CONTENIDO", "Introducción");
s.addText("Arquitectura: siete pasos, tres responsabilidades separadas", { placeholder: "title" });
s.addImage({ path: path.join(DIAG, "arquitectura.png"), x: 1.37, y: 1.3, w: 10.6, h: 10.6 * 1520 / 2800, objectName: "diag-arquitectura",
  altText: "Arquitectura del agente: interfaz, AgenteAnalitico con 7 pasos, PostgreSQL Data Mart, fuente operacional y ZODB" });
s.addNotes("Mathias (≈1 min). Recorrer los números del 1 al 7 = flujo mínimo 2.1 del enunciado. PostgreSQL sólo se lee con el rol agente_lector; ZODB guarda objetos; el LLM es intercambiable con reglas.");

// 4 ---------------------------------------------------------------- estrella
s = nueva("CONTENIDO", "Data Mart");
s.addText("Data Mart: estrella con grano atómico", { placeholder: "title" });
s.addImage({ path: path.join(DIAG, "estrella.png"), x: 0.6, y: 1.45, w: 7.4, h: 7.4 * 1275 / 2352, objectName: "diag-estrella",
  altText: "Esquema estrella: fact_ventas con dim_fecha, dim_producto, dim_cliente, dim_sucursal y dim_canal" });
tarjeta(s, 8.3, 1.45, 4.4, 2.35, "Grano (una oración)",
  "Una fila por cada línea de producto de un ticket de venta completado.", C.accent1, "t-grano", 15);
tarjeta(s, 8.3, 4.0, 4.4, 2.75, "Sin duplicidad",
  bullets(["PK (numero_ticket, linea_ticket)", "Ticket = dimensión degenerada → COUNT(DISTINCT)", "CHECK: neto = bruto − descuento"]),
  C.accent2, "t-dup", 14);
s.addText("Kimball bottom-up · jerarquías: día→mes→trimestre→año · producto→subcategoría→categoría · sucursal→ciudad→estado→región",
  { x: 0.6, y: 5.75, w: 7.4, h: 0.9, fontSize: 13, color: C.accent6, margin: 0, isTextBox: true, objectName: "jerarquias" });
s.addNotes("Mikel (≈1 min 30 s). Grano en una oración. Por qué atómico. Dimensión degenerada para contar tickets sin duplicar. Restricciones CHECK y PK.");

// 5 ---------------------------------------------------------------- decisiones
s = nueva("CONTENIDO", "Data Mart");
s.addText("Decisiones obligatorias de diseño", { placeholder: "title" });
const gw = 5.95, gh = 2.55;
tarjeta(s, 0.6, 1.45, gw, gh, "Métricas por aditividad",
  bullets(["Aditivas: cantidad, bruto, descuento, neto, costo, margen", "No aditivas: margen %, ticket promedio, % descuento → se recalculan", "Semiaditivas: no hay en un hecho transaccional (ej. inventario)"]),
  C.accent1, "t-metricas", 14);
tarjeta(s, 6.75, 1.45, gw, gh, "Claves sustitutas",
  bullets(["Enteros sin significado de negocio", "Aíslan de cambios en la fuente y permiten versiones SCD2", "fecha_sk = AAAAMMDD (convención Kimball)"]),
  C.accent3, "t-claves", 14);
tarjeta(s, 0.6, 4.2, gw, gh, "Desconocidos y faltantes",
  bullets(["−1 «No informado» · −2 «Sin correspondencia»", "Ninguna venta se pierde; la regla RV09 lo advierte", "Anulados, duplicados y cantidad ≤ 0 → control.etl_rechazo"]),
  C.accent2, "t-desc", 14);
tarjeta(s, 6.75, 4.2, gw, gh, "Operacional vs. analítico",
  bullets(["oltp: normalizado, con errores, sobrescribe", "dm: estrella limpia, histórica, no volátil", "El agente sólo puede leer dm (REVOKE + RV07)"]),
  C.accent4, "t-oltp", 14);
s.addNotes("Mikel (≈1 min 30 s). Una idea por tarjeta. Ejemplo: margen % nunca se promedia; por eso la comparación entre canales recalcula el total con GROUPING SETS.");

// 6 ---------------------------------------------------------------- SCD
s = nueva("CONTENIDO", "Data Mart");
s.addText("SCD Tipo 2: con Tipo 1 el agente respondería mal", { placeholder: "title" });
s.addChart(pres.charts.BAR, [
  { name: "SCD Tipo 2 (elegido)", labels: ["Corporativo", "Frecuente", "Minorista", "Premium"], values: [-20.6, 14.3, 15.7, 24.1] },
  { name: "SCD Tipo 1 (sobrescribe)", labels: ["Corporativo", "Frecuente", "Minorista", "Premium"], values: [5.5, -31.5, 23.1, 7.8] },
], { x: 0.6, y: 1.4, w: 7.6, h: 5.4, barDir: "bar", barGrouping: "clustered", chartColors: [HEX.accent1, HEX.accent6],
  showTitle: true, title: "Variación del ingreso neto ene–sep 2026 vs 2025 (%)", titleFontSize: 14, titleColor: HEX.dk2, titleFontFace: "+mn-lt",
  showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.0", dataLabelFontSize: 12, dataLabelColor: HEX.dk1, dataLabelFontFace: "+mn-lt",
  showLegend: true, legendPos: "b", legendFontSize: 12, legendFontFace: "+mn-lt",
  catAxisLabelColor: HEX.dk1, catAxisLabelFontSize: 13, catAxisLabelFontFace: "+mn-lt", catAxisLabelPos: "low", valAxisLabelColor: HEX.accent6,
  valAxisLabelFontSize: 11, valAxisLabelFontFace: "+mn-lt", valGridLine: { color: "DDE5E9", size: 0.5 }, catGridLine: { style: "none" },
  objectName: "grafico-scd" });
tarjeta(s, 8.5, 1.45, 4.2, 2.5, "La decisión",
  "Si un cliente cambia de segmento se cierra su versión y se crea otra. Cada venta conserva el segmento vigente al comprar.", C.accent1, "t-scd", 14);
tarjeta(s, 8.5, 4.15, 4.2, 2.6, "El efecto",
  "376 clientes cambiaron de segmento. Con Tipo 1, «¿qué segmento redujo más?» respondería Frecuente (−31,5 %). La respuesta correcta es Corporativo (−20,6 %).",
  C.accent4, "t-efecto", 14);
s.addNotes("Leonardo (≈1 min 30 s). Pregunta obligatoria de diseño. Las mismas ventas, dos modelos y conclusiones opuestas. El segmento actual sigue disponible filtrando es_actual = true.");

// 7 ---------------------------------------------------------------- calidad
s = nueva("CONTENIDO", "Data Mart");
s.addText("Controles: conciliación al centavo e integridad", { placeholder: "title" });
const conc = [["Control", "Fuente", "Data Mart", "Estado"],
  ["Líneas válidas", "97.816", "97.816", "OK"], ["Tickets", "30.462", "30.462", "OK"], ["Unidades", "506.420", "506.420", "OK"],
  ["Ingreso neto (USD)", "3.494.922,06", "3.494.922,06", "OK"], ["Costo (USD)", "2.739.511,34", "2.739.511,34", "OK"],
  ["Cuadre líneas crudas", "99.890", "99.890", "OK"], ["Meses con diferencia", "0", "0", "OK"]];
s.addTable(conc.map((f, i) => f.map((c, j) => ({ text: c, options: { bold: i === 0, color: i === 0 ? HEX.lt1 : (j === 3 ? HEX.accent1 : HEX.dk1),
  fill: { color: i === 0 ? HEX.dk2 : (i % 2 ? HEX.lt1 : HEX.lt2) }, fontSize: 13, align: j ? "right" : "left" } }))),
  { x: 0.6, y: 1.5, w: 7.4, colW: [2.8, 1.75, 1.75, 1.1], border: { type: "solid", pt: 0.5, color: "CBD5DC" }, rowH: 0.42, objectName: "tabla-conc" });
s.addText("Cuadre: líneas crudas (99.890) = Data Mart (97.816) + de tickets anulados (1.589) + duplicadas (377) + inválidas (108)", { x: 0.6, y: 5.1, w: 7.4, h: 0.6,
  fontSize: 13, color: C.accent6, margin: 0, isTextBox: true, objectName: "cuadre" });
stat(s, 8.5, 1.45, 4.2, "10/10", "controles de integridad sin hallazgos (FK, grano, SCD2 sin solapes, reglas de cálculo)", C.accent3, "s-integ");
stat(s, 8.5, 3.6, 4.2, "5/5", "conciliación independiente: pandas leyendo los CSV, sin PostgreSQL", C.accent1, "s-pandas");
s.addText("Excepciones visibles: consumidor final 1,45 % del ingreso · cliente huérfano 0,35 % · producto huérfano 0,21 %",
  { x: 8.5, y: 5.75, w: 4.2, h: 1.0, fontSize: 13, color: C.text1, margin: 0, isTextBox: true, objectName: "excepciones" });
s.addNotes("Leonardo (≈1 min). Vistas control.v_conciliacion_estado y control.v_integridad. La conciliación independiente con pandas demuestra que el ETL no pierde ni duplica.");

// 8 ---------------------------------------------------------------- clases
s = nueva("CONTENIDO", "BDOO");
s.addText("BDOO en ZODB: objetos, no tablas", { placeholder: "title" });
s.addImage({ path: path.join(DIAG, "clases.png"), x: 0.6, y: 1.35, w: 5.6, h: 5.6 * 2241 / 2352, objectName: "diag-clases",
  altText: "Diagrama de clases: ObjetoAgente y sus subclases" });
const conceptos = [["IDO", "OID asignado por ZODB, sin significado de negocio"], ["Herencia", "Usuario→Gerente/Analista · 5 consultas · 11 reglas"],
  ["Polimorfismo", "aplica_a(), construir_sql(), validar(), nivel_detalle()"], ["Encapsulamiento", "estado privado; la Pregunta valida sus transiciones de estado"],
  ["Composición", "Sesion ◆ Pregunta ◆ Intencion, Respuesta ◆ Resultado"], ["Apuntadores suaves", "N respuestas → la misma FuenteDato (identidad)"],
  ["LOB · TDA", "Blob CSV del resultado · DocumentoIdentidad.formato()"], ["Versionamiento", "nueva_version() + db.history(oid) · transacciones ACID"]];
conceptos.forEach(([k, v], i) => {
  const y = 1.45 + i * 0.68;
  s.addShape(pres.shapes.OVAL, { x: 6.6, y: y + 0.08, w: 0.36, h: 0.36, fill: { color: C.accent3 }, line: { color: C.accent3 }, objectName: `c-ico-${i}` });
  s.addText([{ text: k + ": ", options: { bold: true, color: C.text2 } }, { text: v, options: { color: C.text1 } }],
    { x: 7.15, y, w: 5.6, h: 0.55, fontSize: 14, margin: 0, valign: "middle", isTextBox: true, objectName: `c-txt-${i}` });
});
s.addNotes("Federico (≈1 min 30 s). La BDOO no duplica las dimensiones. Recorrer los conceptos de la clase P06: IDO, objetos complejos, encapsulamiento, herencia, polimorfismo (ejemplo Puerta/Ventana), apuntadores suaves, LOB/TDA (como el TDA DATOS del profe) y versionamiento.");

// 9 ---------------------------------------------------------------- evidencia sesión
s = nueva("CONTENIDO", "BDOO");
s.addText("Una pregunta, su rastro completo en la BDOO", { placeholder: "title" });
const cadena = [["Sesion", "memoria operativa"], ["Pregunta", "RECIBIDA → INTERPRETADA → RESPONDIDA"], ["Intencion", "ranking · ingreso_neto · canal · 2026 · límite 1"],
  ["ConsultaAnalitica", "CQ-02 Ranking · versión"], ["ResultadoConsulta", "SQL, parámetros, 15 ms, Blob CSV"], ["RespuestaAgente", "Mayorista B2B · 42 % del total + fuentes"]];
cadena.forEach(([k, v], i) => {
  const x = 0.6 + i * 2.07;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.5, w: 1.85, h: 1.45, rectRadius: 0.12, fill: { color: i % 2 ? C.background2 : "E9E3F7" },
    line: { color: C.accent3, width: 1 }, objectName: `cad-${i}` });
  s.addText([{ text: k, options: { bold: true, fontSize: 14, color: C.accent3, breakLine: true } }, { text: v, options: { fontSize: 12, color: C.text1 } }],
    { x: x + 0.1, y: 1.6, w: 1.65, h: 1.3, margin: 0, valign: "top", isTextBox: true, objectName: `cad-t-${i}` });
  if (i < cadena.length - 1) s.addShape(pres.shapes.RIGHT_ARROW, { x: x + 1.87, y: 2.1, w: 0.18, h: 0.25, fill: { color: C.accent3 }, line: { color: C.accent3 }, objectName: `flecha-${i}` });
});
tarjeta(s, 0.6, 3.35, 4.0, 2.4, "Persistencia real", "Se cierra la base, se reabre y el grafo completo se recorre desde disco (docs/evidencias/evidencia_bdoo.md).", C.accent3, "t-pers", 14);
tarjeta(s, 4.75, 3.35, 4.0, 2.4, "Identidad", "Dos respuestas apuntan al mismo objeto FuenteDato y a la misma ConsultaAnalitica: «is» = True (mismo IDO).", C.accent1, "t-ident", 14);
tarjeta(s, 8.9, 3.35, 3.8, 2.4, "Seguimiento", "«¿y en 2025?» reutiliza la última Intencion de la Sesion: memoria operativa.", C.accent2, "t-seg", 14);
s.addText("Cada flecha es una referencia persistente (apuntador suave): ZODB guarda el IDO del objeto apuntado y lo carga al accederlo.",
  { x: 0.6, y: 6.05, w: 12.1, h: 0.6, fontSize: 14, color: C.accent6, margin: 0, isTextBox: true, objectName: "nota-apuntadores" });
s.addNotes("Federico (≈1 min). Mostrar en la app la pestaña BDOO con los IDO reales. Si preguntan por concurrencia: transacciones ACID, ConflictError y reintento; FileStorage es de un solo proceso (en producción, ZEO).");

// 10 ---------------------------------------------------------------- flujo y seguridad
s = nueva("CONTENIDO", "Agente");
s.addText("El agente interpreta, valida y nunca inventa", { placeholder: "title" });
const capas = [["1 · Texto", "RV01 bloquea borrar, modificar, DDL, credenciales e inyección"], ["2 · Intérprete", "el LLM sólo devuelve un JSON con códigos del catálogo; con fallas, usa reglas"],
  ["3 · SQL", "plantillas de lista blanca + valores como parámetros; RV07 revisa el SQL"], ["4 · Base de datos", "rol agente_lector: sólo SELECT en dm, READ ONLY, timeout 5 s"]];
capas.forEach(([k, v], i) => {
  const y = 1.45 + i * 1.32;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y, w: 6.2, h: 1.15, rectRadius: 0.1, fill: { color: C.background2 }, line: { color: C.background2 }, objectName: `capa-${i}` });
  s.addText([{ text: k, options: { bold: true, color: C.accent4, breakLine: true } }, { text: v, options: { color: C.text1 } }],
    { x: 0.85, y: y + 0.1, w: 5.8, h: 0.95, fontSize: 14, margin: 0, valign: "middle", isTextBox: true, objectName: `capa-t-${i}` });
});
const limites = [["«¿Cuál fue el mejor canal?»", "ACLARACIÓN: ¿ingreso, margen, unidades o ticket?"], ["Sin periodo", "usa todo el rango y lo advierte (RV06)"],
  ["Inventario, clima…", "RECHAZO: fuera de alcance, no inventa (RV02)"], ["«por vendedor»", "RECHAZO: dimensión inexistente (RV03)"],
  ["Jardinería en 2025", "SIN DATOS: vacío ≠ cero (RV08)"], ["Narrativa del LLM", "se descarta si cita cifras que no están en el resultado (RV11)"]];
s.addTable([[{ text: "Situación", options: { bold: true, color: HEX.lt1, fill: { color: HEX.dk2 } } }, { text: "Respuesta del agente", options: { bold: true, color: HEX.lt1, fill: { color: HEX.dk2 } } }],
  ...limites.map(([a, b], i) => [{ text: a, options: { bold: true, fill: { color: i % 2 ? HEX.lt2 : HEX.lt1 } } }, { text: b, options: { fill: { color: i % 2 ? HEX.lt2 : HEX.lt1 } } }])],
  { x: 7.1, y: 1.45, w: 5.6, colW: [2.1, 3.5], fontSize: 13, color: HEX.dk1, border: { type: "solid", pt: 0.5, color: "CBD5DC" }, objectName: "tabla-limites" });
s.addText("Toda respuesta trae: resultado · métrica y regla de cálculo · periodo y filtros · dimensión · interpretación · fuente (hecho, dimensiones, consulta y SQL) · advertencias.",
  { x: 7.1, y: 5.3, w: 5.6, h: 1.3, fontSize: 14, color: C.text2, bold: true, margin: 0, isTextBox: true, objectName: "evidencia-respuesta" });
s.addNotes("Fernando (≈1 min 30 s). Defensa en profundidad: aunque una capa falle, la siguiente lo impide. La respuesta siempre trae métrica + regla, periodo, filtros, dimensión, fuente, SQL y advertencias.");

// 11 ---------------------------------------------------------------- demo
s = nueva("CONTENIDO", "Demostración y resultados");
s.addText("Demostración en vivo (≈2 minutos)", { placeholder: "title" });
const demo = ["¿Qué segmento de clientes redujo más su volumen de compra?", "Compare el margen de Tienda física y Mayorista B2B durante los últimos tres meses disponibles",
  "¿Cuál fue el mejor canal? → elegir «Margen bruto» en los botones", "¿y en 2025?  (memoria de la sesión)", "Borra las ventas de enero de 2026",
  "Pregunta libre del profesor → abrir «Evidencia y trazabilidad»"];
demo.forEach((q, i) => {
  const y = 1.45 + i * 0.86;
  s.addShape(pres.shapes.OVAL, { x: 0.6, y: y + 0.08, w: 0.55, h: 0.55, fill: { color: C.accent1 }, line: { color: C.accent1 }, objectName: `d-ico-${i}` });
  s.addText(String(i + 1), { x: 0.6, y: y + 0.08, w: 0.55, h: 0.55, fontSize: 16, bold: true, color: C.background1, align: "center", valign: "middle", margin: 0, isTextBox: true, objectName: `d-num-${i}` });
  s.addText(q, { x: 1.4, y, w: 7.0, h: 0.72, fontSize: 15, color: C.text1, margin: 0, valign: "middle", isTextBox: true, objectName: `d-q-${i}` });
});
tarjeta(s, 8.8, 1.45, 3.9, 5.3, "Plan B",
  bullets(["Sin internet: modo «reglas» (determinista)", "Base de datos lista y BDOO inicializada antes de entrar", "Respaldo: python -m agente.cli -p \"…\"", "Capturas en docs/evidencias"]),
  C.accent2, "t-planb", 14);
s.addNotes("Mathias opera la demo; cada integrante explica la parte de la respuesta que le corresponde. Mostrar el SQL (perfil analista) y la pestaña BDOO con el IDO de la pregunta recién hecha.");

// 12 ---------------------------------------------------------------- pruebas
s = nueva("CONTENIDO", "Demostración y resultados");
s.addText(`Pruebas: ${nOk} de ${pruebas.length} casos correctos`, { placeholder: "title" });
const grupos = [["Preguntas mínimas (7) + concretas", 9], ["Adicionales del equipo", 3], ["Casos obligatorios de límites (sección 7)", 8], ["Seguridad, valores inválidos y memoria", 5], ["Regresiones de la revisión independiente", 10]];
s.addChart(pres.charts.BAR, [{ name: "Casos OK", labels: grupos.map(g => g[0]), values: grupos.map(g => g[1]) }], {
  x: 0.6, y: 1.4, w: 7.2, h: 3.6, barDir: "bar", chartColors: [HEX.accent1], showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 13,
  dataLabelColor: HEX.dk1, dataLabelFontFace: "+mn-lt", showLegend: false, showTitle: true, title: "Casos OK por tipo", titleFontSize: 14, titleColor: HEX.dk2,
  titleFontFace: "+mn-lt", catAxisLabelColor: HEX.dk1, catAxisLabelFontSize: 13, catAxisLabelFontFace: "+mn-lt", valAxisHidden: true,
  valGridLine: { style: "none" }, catGridLine: { style: "none" }, objectName: "grafico-pruebas" });
s.addText("El valor esperado de cada caso se calcula con pandas directamente sobre los CSV, sin PostgreSQL ni código del agente. Un caso es OK sólo si el agente devuelve exactamente ese valor.",
  { x: 0.6, y: 5.25, w: 7.2, h: 1.2, fontSize: 14, color: C.text1, margin: 0, isTextBox: true, objectName: "metodo-pruebas" });
tarjeta(s, 8.2, 1.45, 4.5, 2.4, "Revisión independiente", "Un revisor externo probó más de 120 preguntas; cada defecto hallado se corrigió y quedó como caso de regresión. Además, 43/43 pruebas unitarias.", C.accent3, "t-unit", 14);
tarjeta(s, 8.2, 4.05, 4.5, 2.7, "LLM real (OpenRouter)", "gpt-4o-mini solo acertó 17/34 de la matriz: inventaba periodos y canales. Anclado a lo escrito en la pregunta: 34/34, y 12/12 en preguntas nuevas.", C.accent2, "t-llm", 14);
s.addNotes("Fernando (≈1 min). Destacar la independencia del valor esperado y la revisión externa: encontró, entre otros, que el ranking de clientes agrupaba por nombre (sumaba empresas distintas con la misma razón social). Se corrigió agrupando por cliente_id, y quedó la lección de que el valor esperado tampoco debe compartir supuestos con el código. Sobre el LLM: con respuestas reales de gpt-4o-mini en OpenRouter, el modelo solo inventó periodos («por mes» → últimos 12 meses) y los canales de «compare dos canales». Por eso el intérprete híbrido ancla su salida a lo escrito en la pregunta; lo que el LLM inventa se descarta y queda como supuesto visible. Salvedad honesta: el anclaje se ajustó después de ver esas fallas; antes de ajustar, en 12 preguntas nuevas el híbrido acertó 8.");

// 13 ---------------------------------------------------------------- cierre
s = nueva("PORTADA", "Cierre");
s.addText("Limitaciones y próximos pasos", { placeholder: "title" });
s.addText("Datos sintéticos · una dimensión por consulta · ZODB de un solo proceso · hecho sólo transaccional", { placeholder: "body" });
s.addText(bullets(["Hecho de inventario (snapshot) con métricas semiaditivas", "Consultas de dos dimensiones y drill-down por jerarquías",
  "ZEO para concurrencia multiproceso · carga incremental con SCD2 automatizado", "Validar el LLM en vivo, pregunta por pregunta, en cada cambio de modelo"]),
  { x: 0.8, y: 5.0, w: 11.5, h: 1.9, fontSize: 16, color: C.background1, margin: 0, isTextBox: true, objectName: "mejoras" });
s.addNotes("Fernando cierra (≈30 s) y abre las preguntas individuales.");

(async () => {
  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("->", OUT);
})();
