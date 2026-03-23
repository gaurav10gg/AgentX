# agent/scheduler.py
# Background asyncio loop — runs independently of user messages.
# Wakes every TICK_SECONDS, finds due tasks, executes them, stores results.
# Results are surfaced to the user on their next message via task_store.
from agent.task_store import cleanup_old_notifications
import asyncio
import logging
from datetime import datetime
from typing import Callable, Optional

from agent.task_store import get_due_tasks, mark_task
from agent.toolRouter import execute_tool

logger = logging.getLogger("scheduler")

TICK_SECONDS = 30  # how often to check for due tasks


class TaskScheduler:
    """
    Singleton background scheduler.
    Start it once at server startup via scheduler.start().

    On each tick it:
      1. Loads all tasks where execute_at <= now and status == pending
      2. Marks each as "running" to prevent double-execution
      3. Calls execute_tool() with the stored args
      4. Marks the task as done/failed and stores the result
      5. Calls the optional notify_callback so the app can push a notification
    """

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._notify_callback: Optional[Callable] = None

    def set_notify_callback(self, callback: Callable):
        """
        Register a callback that will be called when a task completes.
        Signature: async def callback(session_id: str, task_id: str, description: str, result: str)

        Use this to push a notification to the user (Telegram, FCM, websocket, etc.)
        In Phase 1 (no push yet): the result is stored and surfaced on the next message.
        """
        self._notify_callback = callback

    def start(self):
        """Call this once at FastAPI startup."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())
            logger.info("Scheduler started — tick every %ds", TICK_SECONDS)

    def stop(self):
        """Call this at FastAPI shutdown."""
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("Scheduler stopped")

    async def _loop(self):
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Never let a crash kill the scheduler
                logger.error("Scheduler tick error: %s", e, exc_info=True)
            await asyncio.sleep(TICK_SECONDS)

    async def _tick(self):
        cleanup_old_notifications()
        due = get_due_tasks()
        if not due:
            return

        logger.info("Scheduler: %d task(s) due", len(due))

        for task in due:
            task_id    = task["task_id"]
            session_id = task["session_id"]
            tool_name  = task["tool_name"]
            tool_args  = task["tool_args"]
            description = task["description"]
            google_token = task.get("google_token")

            # Mark running immediately to prevent double execution on next tick
            mark_task(task_id, "running")

            logger.info("Executing task [%s]: %s(%s)", task_id, tool_name, tool_args)

            try:
                # Refresh google token if needed before executing
                if google_token:
                    try:
                        from auth.token_store import refresh_token_if_needed
                        refreshed = refresh_token_if_needed(session_id)
                        if refreshed:
                            google_token = refreshed
                    except Exception:
                        pass  # use the snapshot token if refresh fails

                result = await execute_tool(tool_name, tool_args, google_token)
                mark_task(task_id, "done", result)
                logger.info("Task [%s] done: %s", task_id, result[:80])

                if self._notify_callback:
                    try:
                        await self._notify_callback(session_id, task_id, description, result)
                    except Exception as e:
                        logger.error("Notify callback failed: %s", e)

            except Exception as e:
                error_msg = f"Task failed: {str(e)}"
                mark_task(task_id, "failed", error_msg)
                logger.error("Task [%s] failed: %s", task_id, e, exc_info=True)

                if self._notify_callback:
                    try:
                        await self._notify_callback(session_id, task_id, description, error_msg)
                    except Exception:
                        pass


# Singleton — import this everywhere
scheduler = TaskScheduler()