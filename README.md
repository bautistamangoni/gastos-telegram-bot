# Bot de Telegram para Gestión de Gastos Personales

Bot personal de Telegram escrito en Python que interpreta gastos en lenguaje natural usando **Gemini API (Structured Outputs)** y los guarda automáticamente en **Google Sheets**, con soporte para categorías dinámicas, monedas (`ARS` por defecto y `USD`) y resúmenes directamente desde el chat.

## Funcionalidades

- **Lenguaje natural:** escribí cosas como `"supermercado 5000 pesos"`, `"ayer verduleria 8500 con débito"`, `"5 lucas en carniceria"`, `"netflix 12 usd"`.
- **Seguridad por whitelist:** solo responde a tu `ALLOWED_USER_ID` de Telegram.
- **Categorías dinámicas:** se almacenan en la pestaña `Categorias` de tu Google Sheet. Arranca con tus 12 categorías iniciales y podés sumar más desde Telegram con `/agregar_categoria <nombre>` o editando la hoja manualmente.
- **Deshacer con un toque:** cada gasto registrado incluye un botón `🗑️ Deshacer` y también existe el comando `/deshacer`.
- **Resúmenes en el chat:** `/hoy`, `/mes` (o `/mes 2026-10`), `/resumen`, `/ultimo`, `/categorias`.

## Categorías Iniciales

`Supermercado`, `Mascota`, `Tarjeta`, `Alquiler`, `Seguro Auto`, `Internet + telefono`, `Gas`, `Luz`, `Expensas`, `Verduleria`, `Otros Gastos`, `Carniceria + Polleria`.

---

## Requisitos

- [uv](https://docs.astral.sh/uv/) (instala automáticamente Python 3.12+ y todas las dependencias).

## Configuración paso a paso

### 1. Crear el bot en Telegram
1. Abrí Telegram y buscá a `@BotFather`.
2. Enviá `/newbot`, elegí un nombre y un username terminado en `bot`.
3. Copiá el **token** que te entrega.
4. Para saber tu `ALLOWED_USER_ID`, escribile a `@userinfobot` (o `@raw_data_bot`) y copiá tu `Id` numérico.

### 2. Obtener la API Key de Gemini
1. Ingresá a [Google AI Studio](https://aistudio.google.com/apikey).
2. Hacé clic en **Create API key** y copiá la clave.

### 3. Configurar Google Sheets y Service Account
1. Ingresá a [Google Cloud Console](https://console.cloud.google.com/) y creá un proyecto (o usá uno existente).
2. Habilitá **Google Sheets API** (en *APIs & Services > Library*).
3. Creá una **Service Account** (*IAM & Admin > Service Accounts > Create Service Account*).
4. Dentro de la Service Account, andá a la pestaña **Keys > Add Key > Create new key > JSON**.
5. Guardá el archivo descargado en la raíz de este proyecto con el nombre `credentials.json` (está ignorado por git).
6. Creá una planilla nueva en [Google Sheets](https://sheets.google.com/), copiá su **ID** desde la URL:
   `https://docs.google.com/spreadsheets/d/<GOOGLE_SHEET_ID>/edit`
7. Hacé clic en **Compartir** en tu planilla y agregá el email de la Service Account (`...@...iam.gserviceaccount.com`) con permiso de **Editor**.

### 4. Variables de entorno
Copiá `.env.example` a `.env` y completá tus valores:

```powershell
Copy-Item .env.example .env
```

---

## Ejecución

```powershell
# Instalar dependencias y sincronizar el entorno virtual
uv sync

# Ejecutar el bot
uv run gastos-bot
```

Al iniciar por primera vez, el bot creará automáticamente las pestañas **`Gastos`** y **`Categorias`** con sus encabezados y tus categorías iniciales si todavía no existen en la planilla.

## Comandos del Bot

| Comando | Descripción |
| :--- | :--- |
| `<texto libre>` | Registra un gasto (ej. `supermercado 5000 pesos`, `luz 18500 transferencia`) |
| `/hoy` | Resumen de gastos del día actual |
| `/mes [YYYY-MM]` | Resumen del mes actual o de un mes específico (alias: `/resumen`) |
| `/ultimo` | Muestra el último gasto registrado |
| `/deshacer` | Elimina el último gasto registrado |
| `/categorias` | Lista las categorías activas |
| `/agregar_categoria <nombre>` | Agrega una nueva categoría a Google Sheets |
| `/ayuda` | Muestra los comandos y ejemplos |

## Tests y Linter

```powershell
uv run pytest -v
uv run ruff check .
```
