# Proyecto_SO

Primera entrega del proyecto de Sistemas Operativos.

### _Juan David Salas Castaño_
---
 
## Descripción general
 
Sistema que simula un ejecutor de procesos de lotes (batch) similar a los encontrados en sistemas operativos de mainframe. El sistema permite registrar programas y ficheros, y ejecutarlos de forma encadenada conectando entradas y salidas.
 
### Arquitectura
 
```
Cliente --> ctrllt --> gesfich
                  --> gesprog
                  --> ejecutor
```
 
La comunicación entre todos los componentes se realiza mediante **tuberías nombradas (named pipes / FIFOs)** con mensajes en formato **JSON**. En Linux las tuberías nombradas son half-duplex, por lo tanto cada servicio utiliza **dos tuberías**: una para recibir peticiones y otra para enviar respuestas.
 
---
 
## Estructura del proyecto
 
```
Proyecto_SO/
  ipc.py            → Módulo de comunicación (tuberías nombradas)
  gesfich.py        → Servicio de gestión de ficheros
  gesprog.py        → Servicio de gestión de programas
  ejecutor.py       → Servicio de ejecución de lotes
  ctrllt.py         → Servicio de control y enrutamiento
  prueba_ok.sh      → Script de prueba para el ejecutor
  comandos_demo.sh  → Guión de demostración
  docs/
    Diseño.md       → Diseño de la API (primera entrega)
```
 
---
 
## Requisitos
 
- Linux (Ubuntu 20.04 o superior)
- Python 3.8 o superior
- No requiere librerías externas — solo módulos estándar de Python
---
 
## Cómo ejecutar el sistema
 
### Paso 0 — Preparación
 
Abrir **7 terminales** (T1 a T7). En T7 limpiar tuberías anteriores:
 
```bash
rm -f /tmp/cliente_req /tmp/cliente_res
rm -f /tmp/gesfich_req /tmp/gesfich_res
rm -f /tmp/gesprog_req /tmp/gesprog_res
rm -f /tmp/ejecutor_req /tmp/ejecutor_res
mkdir -p ./aralmac
chmod +x prueba_ok.sh
```
 
### Paso 1 — Arrancar servicios (uno por terminal)
 
Los servicios deben arrancar **antes** que `ctrllt` para evitar deadlocks.
 
**T1 — gesfich:**
```bash
python3 gesfich.py -f /tmp/gesfich_req -b /tmp/gesfich_res -x ./aralmac
```
 
**T2 — gesprog:**
```bash
python3 gesprog.py -p /tmp/gesprog_req -c /tmp/gesprog_res -x ./aralmac
```
 
**T3 — ejecutor:**
```bash
python3 ejecutor.py -e /tmp/ejecutor_req -d /tmp/ejecutor_res -x ./aralmac
```
 
**T4 — ctrllt (arrancar de último):**
```bash
python3 ctrllt.py \
  -c /tmp/cliente_req -a /tmp/cliente_res \
  -f /tmp/gesfich_req -b /tmp/gesfich_res \
  -p /tmp/gesprog_req -g /tmp/gesprog_res \
  -e /tmp/ejecutor_req -d /tmp/ejecutor_res
```
 
### Paso 2 — Conectar cliente
 
**T6 — abrir lector de respuestas (ejecutar primero):**
```bash
cat /tmp/cliente_res
```
 
**T5 — abrir escritor de peticiones:**
```bash
exec 3>/tmp/cliente_req
```
 
### Paso 3 — Enviar peticiones (todo en T5)
 
Las respuestas aparecen en T6.
 
**Crear fichero:**
```bash
echo '{"servicio":"gesfich","operacion":"Crear","parametros":{"nombre":"entrada.txt"}}' >&3
```
 
**Registrar programa:**
```bash
echo '{"servicio":"gesprog","operacion":"Guardar","parametros":{"ejecutable":"./prueba_ok.sh","args":[],"env":[]}}' >&3
```
 
**Ejecutar lote (reemplazar IDs con los retornados):**
```bash
echo '{"servicio":"ejecutor","operacion":"Ejecutar","parametros":{"id-programa":"p-0001","stdin":"f-0001","stdout":"f-0002"}}' >&3
```
 
**Consultar estado:**
```bash
echo '{"servicio":"ejecutor","operacion":"Estado","parametros":{}}' >&3
```
 
**Leer contenido de fichero de salida:**
```bash
echo '{"servicio":"gesfich","operacion":"Leer","parametros":{"id-fichero":"f-0002"}}' >&3
```
 
**Terminar el sistema:**
```bash
echo '{"operacion":"Terminar","parametros":{}}' >&3
```
 
---
 
## Identificadores del sistema
 
| Recurso | Formato | Ejemplo |
|---------|---------|---------|
| Fichero | `f-XXXX` | `f-0001` |
| Programa | `p-XXXX` | `p-0001` |
| Ejecución | `e-XXXX` | `e-0001` |
 
---
 
## Descripción de servicios
 
### `ipc.py` — Módulo de comunicación
Centraliza la lógica de tuberías nombradas. Expone funciones simples:
`crear_tuberia()`, `abrir_tuberia_lectura()`, `abrir_tuberia_escritura()`,
`enviar_mensaje()`, `recibir_mensaje()`, `cerrar_tuberia()`.
 
### `gesfich.py` — Gestión de ficheros
Administra los ficheros fuente y destino en `aralmac`. Operaciones: `Crear`, `Leer`, `Actualizar`, `Borrar`, `Suspender`, `Reasumir`, `Terminar`.
 
### `gesprog.py` — Gestión de programas
Registra ejecutables con sus argumentos y variables de ambiente. Operaciones: `Guardar`, `Leer`, `Actualizar`, `Borrar`, `Suspender`, `Reasumir`, `Terminar`. `Leer` se permite incluso en estado Suspendido.
 
### `ejecutor.py` — Ejecución de lotes
Lanza programas registrados usando el patrón **fork-exec** de Linux. Conecta entradas y salidas a ficheros mediante `dup2()`. Soporta múltiples lotes simultáneos. Al suspenderse, los lotes activos continúan ejecutándose. Operaciones: `Ejecutar`, `Estado`, `Matar`, `Suspender`, `Reasumir`, `Parar`, `Terminar`.
 
### `ctrllt.py` — Control y enrutamiento
Pasarela central. Lee el campo `"servicio"` de cada petición y la redirige al servicio correspondiente sin modificarla. Al recibir `Terminar`, suspende todos los servicios activos antes de apagarse.
 
---
 
## Diseño de la API
 
Ver [`docs/Diseño.md`](docs/Diseño.md) para la especificación completa de mensajes JSON de cada operación.
