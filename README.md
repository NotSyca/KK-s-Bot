### Explicación de la Lógica (Resumen)

1.  **Persistencia (`self.active_channels`)**:
    *   No usamos una base de datos compleja, sino un diccionario de Python. La *key* es el ID del canal y el *value* es la fecha y hora exacta (`datetime`) del último mensaje procesado. Esto permite manejar múltiples conversaciones en distintos servidores simultáneamente.

2.  **Lógica de Timeout (`_check_timeout`)**:
    *   Cada vez que llega un mensaje, el bot calcula: `Tiempo Actual - Tiempo Último Mensaje`.
    *   Si el resultado es mayor a 5 minutos, elimina la entrada del diccionario. Esto hace que `is_active_channel` sea `False`, por lo que el bot dejará de responder a mensajes normales hasta que alguien lo vuelva a mencionar explícitamente.

3.  **Flujo de Conversación**:
    *   Al estar activo, el bot lee el historial (`limit=15`), lo formatea como `Usuario: Mensaje` y se lo envía a Gemini. Esto le da a la IA la "memoria" a corto plazo necesaria para entender chistes internos, referencias al mensaje anterior o el tema general de la charla sin necesidad de mantener un objeto de sesión complejo.