# Diseño de la API — Ejecutor de Lotes

## 1. Generalidades

- Todos los mensajes se comunican mediante **tuberías nombradas (named pipes)**.
- En Linux las tuberías nombradas son **half-duplex**, por lo tanto cada servicio utiliza **dos tuberías**: una para recibir peticiones y otra para enviar respuestas.
- Todos los mensajes (peticiones y respuestas) están en formato **JSON**.
- Cada servicio define su par de tuberías al momento de iniciarse mediante argumentos de línea de comandos.
- Todos los recursos (ficheros fuente/destino y programas ejecutables) se almacenan físicamente en una región o directorio común denominado **`aralmac`** (Área de almacenamiento). La ruta específica a este directorio se pasa como argumento al iniciar los servicios `gesfich`, `gesprog` y `ejecutor` mediante la opción `-x`.

### Formato general de una petición

```json
{
  "operacion": "<nombre-de-la-operacion>",
  "parametros": { }
}
```

### Formato general de una respuesta exitosa

```json
{
  "estado": "ok",
  "datos": { }
}
```

### Formato general de una respuesta con error

```json
{
  "estado": "error",
  "mensaje": "<descripcion-del-error>"
}
```

---

## 2. Servicio `gesfich` — Gestión de Ficheros

Gestiona los ficheros que serán fuente o destino de los procesos de lotes. Los ficheros se almacenan en la región `aralmac` (un directorio en el sistema de archivos).

### Sinopsis

```bash
gesfich -f <tuberia-peticiones> [-b <tuberia-respuestas>] -x <ruta-aralmac>
```

### Máquina de Estados: gesfich
```text

[inicio] ---> (Corriendo)

(Corriendo)
  |-- Crear/Leer/Actualizar/Borrar --> (Corriendo)
  |-- Suspender ---------------------> (Suspendido)
  |-- Terminar ----------------------> [Terminado]

(Suspendido)
  |-- Reasumir ----------------------> (Corriendo)
  |-- Terminar ----------------------> [Terminado]
  
```

### Identificador de fichero

Formato: `f-XXXX` donde `X` es un dígito. Ejemplo: `f-0001`, `f-0002`.

---

### 2.1 Crear fichero

Crea un fichero vacío en `aralmac` y retorna su identificador.

**Petición:**

```json
{
  "operacion": "crear",
  "parametros": {
    "nombre": "entrada.txt"
  }
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `nombre` | string | Nombre descriptivo del fichero |

**Respuesta exitosa:**

```json
{
  "estado": "ok",
  "datos": {
    "id-fichero": "f-0001",
    "nombre": "entrada.txt"
  }
}
```

**Respuesta con error:**

```json
{
  "estado": "error",
  "mensaje": "No se pudo crear el fichero en aralmac"
}
```

---

### 2.2 Leer fichero(s)

Tiene dos formatos:

**Formato A — Leer un fichero específico por su identificador:**

**Petición:**

```json
{
  "operacion": "leer",
  "parametros": {
    "id-fichero": "f-0001"
  }
}
```

**Respuesta exitosa:**

```json
{
  "estado": "ok",
  "datos": {
    "id-fichero": "f-0001",
    "nombre": "entrada.txt",
    "contenido": "linea 1\nlinea 2\n"
  }
}
```

**Formato B — Listar todos los ficheros registrados (sin parámetros):**

**Petición:**

```json
{
  "operacion": "leer",
  "parametros": {}
}
```

**Respuesta exitosa:**

```json
{
  "estado": "ok",
  "datos": {
    "ficheros": [
      { "id-fichero": "f-0001", "nombre": "entrada.txt" },
      { "id-fichero": "f-0002", "nombre": "salida.txt" }
    ]
  }
}
```

**Respuesta con error (aplica al Formato A):**

```json
{
  "estado": "error",
  "mensaje": "El fichero f-0099 no existe"
}
```

---

### 2.3 Actualizar fichero

Copia el contenido de un fichero externo (ruta local) hacia el fichero identificado en `aralmac`.

**Petición:**

```json
{
  "operacion": "actualizar",
  "parametros": {
    "id-fichero": "f-0001",
    "ruta-origen": "/home/usuario/datos.txt"
  }
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id-fichero` | string | Identificador del fichero en aralmac |
| `ruta-origen` | string | Ruta del fichero fuente en el sistema de archivos |

**Respuesta exitosa:**

```json
{
  "estado": "ok",
  "datos": {
    "id-fichero": "f-0001",
    "mensaje": "Fichero actualizado correctamente"
  }
}
```

**Respuesta con error:**

```json
{
  "estado": "error",
  "mensaje": "El fichero f-0001 no existe en aralmac"
}
```

---

### 2.4 Borrar fichero

Elimina un fichero de `aralmac`.

**Petición:**

```json
{
  "operacion": "borrar",
  "parametros": {
    "id-fichero": "f-0001"
  }
}
```

**Respuesta exitosa:**

```json
{
  "estado": "ok",
  "datos": {
    "id-fichero": "f-0001",
    "mensaje": "Fichero eliminado correctamente"
  }
}
```

**Respuesta con error:**

```json
{
  "estado": "error",
  "mensaje": "El fichero f-0001 no existe"
}
```

---

### 2.5 Operaciones de control del servicio

Estas operaciones controlan el estado del proceso `gesfich` mismo.

#### Suspender

```json
{ "operacion": "suspender", "parametros": {} }
```

**Respuesta:**
```json
{ "estado": "ok", "datos": { "mensaje": "Servicio suspendido" } }
```

#### Reasumir

```json
{ "operacion": "reasumir", "parametros": {} }
```

**Respuesta:**
```json
{ "estado": "ok", "datos": { "mensaje": "Servicio reasumido" } }
```

#### Terminar

```json
{ "operacion": "terminar", "parametros": {} }
```

**Respuesta:**
```json
{ "estado": "ok", "datos": { "mensaje": "Servicio terminado" } }
```

---

## 3. Servicio `gesprog` — Gestión de Programas

Gestiona los programas (ejecutables) que serán utilizados por el ejecutor. Los programas se almacenan en la región `aralmac`.

### Sinopsis

```bash
gesprog -p <tuberia-peticiones> [-c <tuberia-respuestas>] -x <ruta-aralmac>
```

### Máquina de Estados: gesprog
```text

[inicio] ---> (Corriendo)

(Corriendo)
  |-- Guardar/Leer/Actualizar/Borrar --> (Corriendo)
  |-- Suspender -----------------------> (Suspendido)
  |-- Terminar ------------------------> [Terminado]

(Suspendido)
  |-- Reasumir ------------------------> (Corriendo)
  |-- Terminar ------------------------> [Terminado]

```

### Identificador de programa

Formato: `p-XXXX` donde `X` es un dígito. Ejemplo: `p-0001`, `p-0002`.

---

### 3.1 Guardar programa

Registra un ejecutable en `aralmac` con sus argumentos y variables de ambiente.

**Petición:**

```json
{
  "operacion": "guardar",
  "parametros": {
    "ejecutable": "/usr/bin/python3",
    "argumentos": ["script.py", "--verbose"],
    "ambiente": {
      "LANG": "es_CO.UTF-8",
      "PATH": "/usr/local/bin:/usr/bin"
    }
  }
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `ejecutable` | string | Ruta al binario o guión a ejecutar |
| `argumentos` | array de strings | Lista de argumentos del programa |
| `ambiente` | objeto | Variables de entorno en formato clave-valor |

**Respuesta exitosa:**

```json
{
  "estado": "ok",
  "datos": {
    "id-programa": "p-0001",
    "ejecutable": "/usr/bin/python3"
  }
}
```

**Respuesta con error:**

```json
{
  "estado": "error",
  "mensaje": "El ejecutable /usr/bin/python3 no es válido o no existe"
}
```

---

### 3.2 Leer programa

Retorna la información de un programa registrado. 

> **Nota Aclaratoria:** _El documento oficial indica que esta operación "Recibe un `id-fichero`". Se asume que esto es una errata del documento original y que la operación correcta debe recibir un `id-programa`, ya que este servicio gestiona programas y no ficheros._

**Petición:**

```json
{
  "operacion": "leer",
  "parametros": {
    "id-programa": "p-0001"
  }
}
```

**Respuesta exitosa:**

```json
{
  "estado": "ok",
  "datos": {
    "id-programa": "p-0001",
    "ejecutable": "/usr/bin/python3",
    "argumentos": ["script.py", "--verbose"],
    "ambiente": {
      "LANG": "es_CO.UTF-8",
      "PATH": "/usr/local/bin:/usr/bin"
    }
  }
}
```

**Respuesta con error:**

```json
{
  "estado": "error",
  "mensaje": "El programa p-0099 no existe"
}
```

---

### 3.3 Actualizar programa

Reemplaza el ejecutable almacenado con uno nuevo desde una ruta externa.

**Petición:**

```json
{
  "operacion": "actualizar",
  "parametros": {
    "id-programa": "p-0001",
    "ruta-origen": "/home/usuario/nuevo_script.py"
  }
}
```

**Respuesta exitosa:**

```json
{
  "estado": "ok",
  "datos": {
    "id-programa": "p-0001",
    "mensaje": "Programa actualizado correctamente"
  }
}
```

**Respuesta con error:**

```json
{
  "estado": "error",
  "mensaje": "El programa p-0001 no existe en aralmac"
}
```

---

### 3.4 Borrar programa

Elimina un programa de `aralmac`.

**Petición:**

```json
{
  "operacion": "borrar",
  "parametros": {
    "id-programa": "p-0001"
  }
}
```

**Respuesta exitosa:**

```json
{
  "estado": "ok",
  "datos": {
    "id-programa": "p-0001",
    "mensaje": "Programa eliminado correctamente"
  }
}
```

**Respuesta con error:**

```json
{
  "estado": "error",
  "mensaje": "El programa p-0001 no existe"
}
```

---

### 3.5 Operaciones de control del servicio

#### Suspender

```json
{ "operacion": "suspender", "parametros": {} }
```

**Respuesta:**
```json
{ "estado": "ok", "datos": { "mensaje": "Servicio suspendido" } }
```

#### Reasumir

```json
{ "operacion": "reasumir", "parametros": {} }
```

**Respuesta:**
```json
{ "estado": "ok", "datos": { "mensaje": "Servicio reasumido" } }
```

#### Terminar

```json
{ "operacion": "terminar", "parametros": {} }
```

**Respuesta:**
```json
{ "estado": "ok", "datos": { "mensaje": "Servicio terminado" } }
```

---

## 4. Servicio `ejecutor` — Ejecución de Procesos de Lotes

Ejecuta procesos de lotes encadenando ficheros y programas previamente registrados en `aralmac`.

### Sinopsis

```bash
ejecutor -e <tuberia-peticiones> [-d <tuberia-respuestas>] -x <ruta-aralmac>
```

### Máquina de Estados: ejecutor
```text

[inicio] ---> (Ejecutar)

(Ejecutar)
  |-- Ejecutar Lote/Estado/Matar ----> (Ejecutar)
  |-- Suspender ---------------------> (Suspendidos)
  |-- Parar (o Proceso = 0) ---------> (Parar)

(Suspendidos)
  |-- Reasumir ----------------------> (Ejecutar)
  |-- Parar -------------------------> (Parar)

(Parar)
  |-- Terminar ----------------------> [Terminado]

```

### Identificador de lote

Formato: `l-XXXX` donde `X` es un dígito. Ejemplo: `l-0001`, `l-0002`.

### Modelo de proceso de lotes

Un proceso de lotes es un arreglo que representa una cadena de ejecución:

```json
[id-fichero-entrada, id-programa-1, id-programa-2, ..., id-fichero-salida]
```

- El primer elemento siempre es un `id-fichero` (entrada estándar del primer proceso).
- Los elementos intermedios son `id-programa` (procesos encadenados por tuberías).
- El último elemento siempre es un `id-fichero` (salida estándar del último proceso).

---

### 4.1 Ejecutar lote

**Petición:**

```json
{
  "operacion": "ejecutar",
  "parametros": {
    "lote": ["f-0001", "p-0001", "p-0002", "f-0003"]
  }
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `lote` | array de strings | Arreglo con id-fichero e id-programa en orden de ejecución |

**Respuesta exitosa:**

```json
{
  "estado": "ok",
  "datos": {
    "id-lote": "l-0001",
    "mensaje": "Lote iniciado correctamente"
  }
}
```

**Respuesta con error:**

```json
{
  "estado": "error",
  "mensaje": "El programa p-0099 no existe en aralmac"
}
```

---

### 4.2 Consultar estado de lote(s)

**Formato A — Estado de un lote específico:**

**Petición:**

```json
{
  "operacion": "estado",
  "parametros": {
    "id-lote": "l-0001"
  }
}
```

**Respuesta exitosa:**

```json
{
  "estado": "ok",
  "datos": {
    "id-lote": "l-0001",
    "estado-lote": "corriendo"
  }
}
```

Los posibles valores de `estado-lote` son: `corriendo`, `terminado`, `suspendido`, `error`.

**Formato B — Estado de todos los lotes (sin parámetros):**

**Petición:**

```json
{
  "operacion": "estado",
  "parametros": {}
}
```

**Respuesta exitosa:**

```json
{
  "estado": "ok",
  "datos": {
    "lotes": [
      { "id-lote": "l-0001", "estado-lote": "corriendo" },
      { "id-lote": "l-0002", "estado-lote": "terminado" }
    ]
  }
}
```

**Respuesta con error (Formato A):**

```json
{
  "estado": "error",
  "mensaje": "El lote l-0099 no existe"
}
```

---

### 4.3 Matar lote

Termina forzosamente un lote en ejecución.

**Petición:**

```json
{
  "operacion": "matar",
  "parametros": {
    "id-lote": "l-0001"
  }
}
```

**Respuesta exitosa:**

```json
{
  "estado": "ok",
  "datos": {
    "id-lote": "l-0001",
    "mensaje": "Lote terminado forzosamente"
  }
}
```

**Respuesta con error:**

```json
{
  "estado": "error",
  "mensaje": "El lote l-0001 no está en ejecución"
}
```

---

### 4.4 Operaciones de control del servicio

#### Suspender

```json
{ "operacion": "suspender", "parametros": {} }
```

**Respuesta:**
```json
{ "estado": "ok", "datos": { "mensaje": "Servicio suspendido" } }
```

#### Reasumir

```json
{ "operacion": "reasumir", "parametros": {} }
```

**Respuesta:**
```json
{ "estado": "ok", "datos": { "mensaje": "Servicio reasumido" } }
```

#### Parar

```json
{ "operacion": "parar", "parametros": {} }
```

**Respuesta:**
```json
{ "estado": "ok", "datos": { "mensaje": "Servicio en estado parado" } }
```

#### Terminar

```json
{ "operacion": "terminar", "parametros": {} }
```

**Respuesta:**
```json
{ "estado": "ok", "datos": { "mensaje": "Servicio terminado" } }
```

---

## 5. Servicio `ctrllt` — Control de Lotes

Actúa como pasarela entre los clientes y los servicios internos (`gesfich`, `gesprog`, `ejecutor`). Recibe peticiones de los clientes, las redirige al servicio correspondiente y retorna la respuesta al cliente.

### Sinopsis

```bash
ctrllt -c <tuberia-peticiones-cliente> [-a <tuberia-respuestas-cliente>] \
       -f <tuberia-peticiones-gesfich> [-b <tuberia-respuestas-gesfich>] \
       -p <tuberia-peticiones-gesprog> [-c <tuberia-respuestas-gesprog>] \
       -e <tuberia-peticiones-ejecutor> [-d <tuberia-respuestas-ejecutor>]
```

### Máquina de Estados: ctrllt
```text

[inicio] ---> (Corriendo)

(Corriendo)
  |-- Recibir/Enrutar Peticiones ----> (Corriendo)
  |-- Iniciar apagado ---------------> (Terminar)

(Terminar)
  |-- Suspender servicios activos ---> (Limpiar)

(Limpiar)
  |-- Cerrar tuberías ---------------> [Terminado]

```

### Enrutamiento

`ctrllt` determina a qué servicio redirigir la petición usando el campo `servicio`:

| Valor de `servicio` | Redirige a |
|---------------------|------------|
| `gesfich` | Gestión de ficheros |
| `gesprog` | Gestión de programas |
| `ejecutor` | Ejecución de lotes |

### Formato de petición del cliente a `ctrllt`

```json
{
  "servicio": "gesfich",
  "operacion": "crear",
  "parametros": {
    "nombre": "entrada.txt"
  }
}
```

### Formato de respuesta de `ctrllt` al cliente

La respuesta es exactamente la que retorna el servicio interno correspondiente, sin modificación:

```json
{
  "estado": "ok",
  "datos": {
    "id-fichero": "f-0001",
    "nombre": "entrada.txt"
  }
}
```

### Error de enrutamiento

Si el campo `servicio` no corresponde a ningún servicio conocido:

```json
{
  "estado": "error",
  "mensaje": "Servicio desconocido: <nombre-servicio>"
}
```

---

## 6. Cliente

El cliente no hace parte de la implementación del proyecto. Se conecta a `ctrllt` a través de tuberías nombradas.

### Sinopsis

```bash
cliente -c <tuberia-peticiones> [-a <tuberia-respuestas>]
```

Las peticiones que envía el cliente siguen el formato definido en la sección 5 (`ctrllt`).

---

## 7. Resumen de identificadores

| Recurso | Formato | Ejemplo |
|---------|---------|---------|
| Fichero | `f-XXXX` | `f-0001` |
| Programa | `p-XXXX` | `p-0001` |
| Lote en ejecución | `l-XXXX` | `l-0001` |
