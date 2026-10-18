from typing import Any, Dict


class ProjectEventPublisher:

    @staticmethod
    async def publish_event(module_instance, event_name: str, payload: Dict[str, Any]):
        """
        Publie un événement asynchrone sur le bus d'événements MELODI.
        """
        if not module_instance:
            return

        try:
            if hasattr(module_instance, "notify_event_listener"):
                await module_instance.notify_event_listener(event_name, payload)
            elif hasattr(module_instance, "app") and module_instance.app and hasattr(module_instance.app, "hook_manager"):
                await module_instance.app.hook_manager.event_listener.notify(
                    "melodi_project",
                    event_name,
                    payload
                )
        except Exception as e:
            print(f"[melodi_project] Notice lors de la notification de l'événement {event_name}: {e}")
