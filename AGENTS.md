# Instrucciones y Memoria de Proyecto para Agentes de IA (Voice Bistro)

Este archivo es leído automáticamente por los agentes de IA al iniciar el espacio de trabajo.
Para la documentación completa, esquemas de base de datos y detalles de implementación, consulta siempre:
👉 [SISTEMA_GUIA.md](file:///home/nicolas/Proyectos%20Trabajos/SISTEMA_GUIA.md)

---

## Reglas Críticas del Proyecto que Siempre Debes Respetar

1. **Sandwiches Personalizados con Base Obligatoria**:
   - Todo sandwich personalizado debe tener una base de pan (`tipo_personalizado == 'base'`) antes de recibir ingredientes.
   - En la máquina de estados conversacional (`session_sandwich_state`), si falta la base, se debe pedir el pan y ofrecer solo los panes en pantalla.
   - Los ingredientes agregados por voz en turnos sucesivos deben sumarse **DENTRO** del sandwich personalizado existente mediante `tool_agregar_ingrediente_a_sandwich_existente`. Nunca agregues un ingrediente como producto independiente fuera del sandwich.

2. **Atributos Dietéticos (Vegetariano y Vegano)**:
   - Toda consulta o modificación a productos debe contemplar las columnas `es_vegetariano` y `es_vegano` de la tabla `productos`.
   - En el panel administrativo y en el kiosco, los productos deben reflejar sus insignias (`🌱 Vegetariano`, `🌿 Vegano`).
   - Todo producto vegano es vegetariano por definición; mantener esa sincronización en las interfaces.

3. **Layout Estático de la Pantalla IA y Visibilidad del Botón de Hablar**:
   - El cuadro central `.ai-central-box` donde aparecen las respuestas y recomendaciones es estático y no debe crecer ni empujar el footer hacia abajo.
   - El botón para hablar (`#btn-mic` en `.ai-bottom-actions-bar`) debe permanecer **SIEMPRE VISIBLE** en pantalla sin necesidad de hacer scroll de página.
   - Las recomendaciones de productos dentro de `.ai-offered-section` y `#ai-cards-grid` son las que deben permitir scroll interno vertical (`overflow-y: auto`) para que el usuario pueda subir y bajar cuando se ofrecen muchos productos.

4. **Registro de Cambios**:
   - Cada cambio relevante de funcionalidad o arquitectura debe registrarse en la sección de historial de [SISTEMA_GUIA.md](file:///home/nicolas/Proyectos%20Trabajos/SISTEMA_GUIA.md).
