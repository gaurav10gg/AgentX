# agent/scheduler.py
# Background asyncio loop — runs independently of user messages.
# Wakes every TICK_SECONDS, finds due tasks, executes them, stores results.

from agent.task_store import cleanup_old_notifications
import asyncio
import logging
from datetime import datetime
from typing import Callable, Optional

from agent.task_store import get_due_tasks, mark_task, get_token_for_task
from agent.toolRouter import execute_tool

logger = logging.getLogger("scheduler")

TICK_SECONDS = 10  # reduced from 30 — 10s is imperceptible to users


class TaskScheduler:
    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._notify_callback: Optional[Callable] = None

    def set_notify_callback(self, callback: Callable):
        self._notify_callback = callback

    def start(self):
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())
            logger.info("Scheduler started — tick every %ds", TICK_SECONDS)

    def stop(self):
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
                logger.error("Scheduler tick error: %s", e, exc_info=True)
            await asyncio.sleep(TICK_SECONDS)

    async def _tick(self):
        cleanup_old_notifications()
        due = get_due_tasks()
        if not due:
            return

        logger.info("Scheduler: %d task(s) due", len(due))

        for task in due:
            task_id     = task["task_id"]
            session_id  = task["session_id"]
            tool_name   = task["tool_name"]
            tool_args   = task["tool_args"]
            description = task["description"]

            mark_task(task_id, "running")
            logger.info("Executing task [%s]: %s(%s)", task_id, tool_name, tool_args)

            try:
                # Fetch token from memory cache or token_store — never from the task record
                google_token = get_token_for_task(task)

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


scheduler = TaskScheduler()
