# Guía de Caseflow Agent

## Resumen del producto

- **Qué es:** una mesa de investigación para cargos disputados ficticios. Un flujo LangGraph consulta herramientas MCP reales, prepara una propuesta versionada, espera la aprobación humana y registra el resultado en un simulador con trazabilidad completa.
- **Para quién:** el **analista** que investiga y el **supervisor** que revisa y autoriza.
- **Problema que resuelve:** reunir movimientos y políticas, entender qué ocurrió y dejar trazabilidad. La acción sensible necesita supervisión y no debe ejecutarse dos veces: la aprobación queda ligada a la versión exacta y los reintentos se rechazan.
- **Qué es simulado:** en DEMO la **decisión** (proponer, pedir evidencia o rechazar, y su justificación) es un fixture por escenario, marcado como *DEMO decisions* y con el prefijo *"Fixture:"*. Las herramientas, permisos, persistencia, checkpoints, aprobaciones y auditoría se ejecutan de verdad. La **resolución es un registro en un simulador**: no hay reembolsos ni operaciones financieras.
- **Qué requiere un proveedor real:** LIVE con OpenAI o Gemini para la decisión tipada. No se verificó ninguna llamada externa.
- **Límites:** datos sintéticos, una organización, sin SSO ni integraciones reales, sin afirmaciones de calidad de modelo.

**Recorrido de dos minutos:** (1) entrar como *analyst*; (2) abrir *Two charges, one purchase* y pulsar *Run investigation*; (3) revisar movimientos recuperados, política consultada, propuesta v1 y *Next action*; (4) pestaña *Activity*; (5) entrar como *supervisor*, *Approve v1* y *Record resolution*; (6) ver el caso *Resolved* y su traza; (7) reintentar la resolución desde http://localhost:3102/api/docs (POST `/api/cases/{case_id}/resolve`, `demo-001`, `{"version": 1}`): responde **409** *already resolved* y sigue habiendo una sola resolución. Opcional: editar una propuesta aprobada crea v2 y anula la aprobación anterior.

## Instalación y uso

Para la ruta principal necesita Docker Engine o Docker Desktop con Compose 2.24.4 o posterior. No necesita Python, Node, claves de API ni archivo `.env` en el host. Desde la carpeta del repositorio:

```sh
docker compose up --build -d --wait
docker compose ps
```

Abra **http://localhost:3102**. Entre como `analyst` o `supervisor`, con la contraseña pública de DEMO `demo-pass`. Los cuatro servicios deben aparecer saludables. El primer arranque descarga dependencias; los puertos 3102 y 5542 deben estar libres. En este entorno con proxy y CA confiable, añada `-f compose.yaml -f compose.cloud.yaml` después de `docker compose`.

Comprobación breve sin modificar expedientes:

```sh
curl --fail --silent --show-error http://localhost:3102/api/health
```

Debe devolver `{"status":"ok","mode":"DEMO"}`. Esto comprueba web, API y conexión a PostgreSQL; el recorrido siguiente comprueba la investigación. Consulte `docker compose logs --tail=80 api worker web` si falla el arranque.

Para parar use `docker compose down`; para volver a arrancar use `docker compose up -d --wait`. La base permanece en un volumen. No añada `-v` a la parada habitual: eliminaría los datos. Las migraciones y la carga inicial son automáticas y no borran expedientes resueltos.

La alternativa `./scripts/demo-local.sh` necesita Python 3.12, uv, Node 24 y Docker. Conserva PostgreSQL en Docker y ejecuta web, API y worker en el host. Ctrl+C para esos procesos; `docker compose stop db` detiene después PostgreSQL sin borrar datos. No ejecute ambas rutas a la vez sobre el puerto 3102. El script fuerza DEMO y la contraseña PostgreSQL predeterminada `caseflow-demo`; si su volumen ya usa otra contraseña, conserve su arranque Compose configurado. La reconstrucción completa de contenedores ya pasó durante la auditoría; esta alternativa no sustituye esa evidencia.

El analista abre **Two charges, one purchase** y pulsa investigar. Un worker usa LangGraph y consulta herramientas mediante MCP real. La propuesta queda pendiente. Cambie a supervisor, apruebe la versión indicada y solicite la resolución; se registra una operación en el simulador. La aprobación se invalida si cambia la propuesta. Los permisos se revisan en backend y en cada herramienta.

Los demás expedientes demuestran evidencia insuficiente, recomendación de rechazo, herramienta caída recuperable e interrupción persistente. Las decisiones de DEMO son fixtures seleccionados por escenario; no se interpreta texto libre fingiendo usar IA. La consulta de movimientos, escritura, permisos y auditoría sí se ejecutan.

Las instrucciones LIVE están en [live.md](live.md). No hay fallback silencioso. OpenAI y Gemini están implementados con SDK oficiales y contratos probados mediante transporte simulado. No se verificaron llamadas externas por falta de credenciales. Los datos de ambos modos están separados.

Consulte [testing.md](testing.md) para pruebas y limitaciones, [architecture.md](architecture.md) para Mermaid y decisiones y [operations.md](operations.md) para secretos y recuperación. Los archivos Azure son configuración revisable; no prueban un despliegue efectuado ni conformidad regulatoria.

Para repetir el recorrido con los contenedores activos y sin jobs en ejecución, use desde la raíz del repositorio `docker compose exec -T api .venv/bin/python - --confirm-synthetic-data < scripts/reset_demo.py`. Solo reinicia los cinco casos DEMO originales y sus checkpoints. Para la alternativa host con Python/uv instalado, use `PYTHONPATH=services/api uv run python scripts/reset_demo.py --confirm-synthetic-data`. No se reinician datos de forma oculta al arrancar.


La auditoría actual está en [docs/audit.md](audit.md): incluye defectos corregidos, reconstrucción sin caché, volumen aislado y separación entre pruebas con transporte simulado y servicios LIVE no verificados. La batería de navegador exige escenarios iniciales nuevos y ya no omite transiciones por encontrar expedientes resueltos. No se borran datos automáticamente al arrancar.


Para empezar a probar código, siga [las pruebas simples del README](../README.md#run-simple-tests): una base aislada y cinco comprobaciones existentes de permisos, flujo MCP y contratos OpenAI/Gemini. No usan credenciales ni llaman al proveedor. También se incluyen tres pruebas unitarias frontend y los [comandos de validación completa](../README.md#full-validation). La prueba de navegador modifica los escenarios sintéticos y exige estados iniciales; no apunta automáticamente a los datos de un usuario ni los reinicia a escondidas.

Sin claves mantenga `APP_MODE=DEMO`. Puede revisar código y contratos LIVE mediante transportes simulados; la verificación autenticada del servicio queda pendiente. Los pasos optativos de [live.md](live.md) explican cómo habilitarla más adelante.
