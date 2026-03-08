# Ortegas Auto - Gestión de Facturación

Aplicación Streamlit para gestionar usuarios, clientes y facturación a partir de PDF y Excel.

## Stack Tecnológico

- **Framework:** Streamlit
- **Procesamiento de Datos:** Pandas
- **Extracción de PDF:** pdfplumber
- **Lectura Excel:** openpyxl

## Instalación

```bash
pip install -r requirements.txt
```

## Ejecución

```bash
streamlit run app.py
```

## Flujo de Uso

### 1. Gestión de Usuarios y Clientes

- **Crear usuarios:** Añade usuarios (ej: Eric, Arnau) con el campo de texto.
- **Cargar JSON:** Sube un archivo `.json` con la estructura `{"Usuario": ["CLIENTE1", "CLIENTE2"]}`.
- **Añadir manualmente:** Introduce clientes en MAYÚSCULAS y se añaden a la lista.
- **Actualizar:** Los clientes añadidos manualmente actualizan la lista del usuario seleccionado.
- **Descargar JSON:** Genera y descarga el archivo con todos los usuarios y sus clientes.

### 2. Excel Maestro

- **Cargar existente:** Sube un Excel Maestro previo.
- **Inicializar/Actualizar:** Crea el Excel con una hoja por usuario. Si hay usuarios nuevos, se añaden sus hojas.
- **Descargar:** Descarga el Excel Maestro actualizado.

### 3. Cargar Datos (PDF/Excel)

- Sube archivos PDF o Excel con tablas de facturación.
- Selecciona la columna de clientes y la columna de facturación/importe.
- Opcional: columna de fecha para agrupar por mes.
- Los datos se procesan por usuario según sus listas de clientes.
- El Excel Maestro se actualiza con el resumen por mes y cliente.

## Formato JSON de Clientes

```json
{
  "Eric": ["CLIENTE A", "CLIENTE B"],
  "Arnau": ["CLIENTE C", "CLIENTE D"]
}
```

## Estructura Excel Maestro

Cada hoja corresponde a un usuario. Columnas:

| Mes     | Cliente   | Facturación |
|---------|-----------|-------------|
| 2025-01 | CLIENTE A | 1500.00     |
| 2025-01 | CLIENTE B | 800.00      |
