# Guía de Caseflow Agent

El arranque local verificado es `./scripts/demo-local.sh` (Python 3.12, uv, Node 24 y Docker). Conserva PostgreSQL en Docker y ejecuta web, API y worker en el host. El rebuild final de contenedores quedó bloqueado por HTTP 503 del registro externo; no se presenta como verificado.

También se incluye el arranque completo con contenedores: `docker compose up --build -d` y abra http://localhost:3102. Usuario `analyst` o `supervisor`, contraseña pública de DEMO `demo-pass`.

El analista abre **Two charges, one purchase** y pulsa investigar. Un worker usa LangGraph y consulta herramientas mediante MCP real. La propuesta queda pendiente. Cambie a supervisor, apruebe la versión indicada y solicite la resolución; se registra una operación en el simulador. La aprobación se invalida si cambia la propuesta. Los permisos se revisan en backend y en cada herramienta.

Los demás expedientes demuestran evidencia insuficiente, recomendación de rechazo, herramienta caída recuperable e interrupción persistente. Las decisiones de DEMO son fixtures seleccionados por escenario; no se interpreta texto libre fingiendo usar IA. La consulta de movimientos, escritura, permisos y auditoría sí se ejecutan.

Las instrucciones LIVE están en [live.md](live.md). No hay fallback silencioso. OpenAI y Gemini están implementados con SDK oficiales y contratos probados mediante transporte simulado. No se verificaron llamadas externas por falta de credenciales. Los datos de ambos modos están separados.

Consulte [testing.md](testing.md) para pruebas y limitaciones, [architecture.md](architecture.md) para Mermaid y decisiones y [operations.md](operations.md) para secretos y recuperación. Los archivos Azure son configuración revisable; no prueban un despliegue efectuado ni conformidad regulatoria.

Para repetir el recorrido, ejecute expresamente `PYTHONPATH=services/api uv run python scripts/reset_demo.py --confirm-synthetic-data` sin jobs activos. Solo reinicia los cinco casos DEMO originales y sus checkpoints. No se reinician datos de forma oculta al arrancar.
