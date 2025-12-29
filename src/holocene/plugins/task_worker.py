"""Task Worker Plugin - Executes Laney's background tasks.

This plugin:
- Periodically checks for pending tasks in laney_tasks
- Picks highest priority task and executes it
- Uses appropriate LLM model based on task configuration
- Stores results and items added
- Sends Telegram notifications on completion
"""

import json
import sqlite3
import threading
import time
from datetime import datetime
from typing import Dict, Any, Optional, List

from holocene.core import Plugin, Message


class TaskWorkerPlugin(Plugin):
    """Executes Laney's queued background tasks."""

    def get_metadata(self):
        return {
            "name": "task_worker",
            "version": "1.0.0",
            "description": "Executes Laney's background tasks (research, discovery, etc.)",
            "runs_on": ["rei", "both"],
            "requires": []
        }

    def on_load(self):
        """Initialize the plugin."""
        self.logger.info("TaskWorker plugin loaded")

        # Get config
        self.api_key = getattr(self.core.config.llm, 'api_key', None)
        self.db_path = str(self.core.config.db_path)

        if not self.api_key:
            self.logger.warning("No NanoGPT API key - task worker disabled")
            self.enabled = False
        else:
            self.enabled = True

        # Worker state
        self.running = False
        self.worker_thread = None
        self.current_task_id = None

        # Settings
        self.check_interval = 60  # Check every 60 seconds
        self.max_daily_tasks = 50  # Limit to preserve API quota
        self.tasks_today = 0
        self.last_reset = datetime.now().date()

        # Stats
        self.tasks_completed = 0
        self.tasks_failed = 0

    def on_enable(self):
        """Start the task worker."""
        if not self.enabled:
            self.logger.warning("TaskWorker not enabled (no API key)")
            return

        self.running = True
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        self.logger.info("TaskWorker started")

    def on_disable(self):
        """Stop the task worker."""
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
        self.logger.info("TaskWorker stopped")

    def _worker_loop(self):
        """Main worker loop - checks for and executes tasks."""
        self.logger.info("TaskWorker loop started")

        while self.running:
            try:
                # Reset daily counter if new day
                today = datetime.now().date()
                if today != self.last_reset:
                    self.tasks_today = 0
                    self.last_reset = today

                # Check if we've hit daily limit
                if self.tasks_today >= self.max_daily_tasks:
                    self.logger.debug(f"Daily task limit reached ({self.max_daily_tasks})")
                    time.sleep(self.check_interval)
                    continue

                # Get next pending task
                task = self._get_next_task()

                if task:
                    self.logger.info(f"Executing task #{task['id']}: {task['title']}")
                    self._execute_task(task)
                    self.tasks_today += 1

            except Exception as e:
                self.logger.error(f"Error in worker loop: {e}", exc_info=True)

            time.sleep(self.check_interval)

    def _get_next_task(self) -> Optional[Dict]:
        """Get the highest priority pending task."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, chat_id, title, description, task_type, priority, model
                FROM laney_tasks
                WHERE status = 'pending'
                ORDER BY priority ASC, created_at ASC
                LIMIT 1
            """)

            row = cursor.fetchone()
            conn.close()

            if row:
                return dict(row)
            return None

        except Exception as e:
            self.logger.error(f"Error getting next task: {e}")
            return None

    def _execute_task(self, task: Dict):
        """Execute a single task."""
        task_id = task['id']
        self.current_task_id = task_id

        try:
            # Mark as running
            self._update_task_status(task_id, 'running')

            # Build the prompt for Laney
            prompt = self._build_task_prompt(task)

            # Get model
            model = self._get_model_id(task.get('model', 'primary'))

            # Execute with Laney's tools
            result = self._run_laney_task(prompt, model, task_id)

            # Store results
            self._complete_task(task_id, result)

            # Send notification
            if task.get('chat_id'):
                self._notify_completion(task, result)

            self.tasks_completed += 1
            self.logger.info(f"Task #{task_id} completed successfully")

        except Exception as e:
            self.logger.error(f"Task #{task_id} failed: {e}", exc_info=True)
            self._fail_task(task_id, str(e))
            self.tasks_failed += 1

        finally:
            self.current_task_id = None

    def _build_task_prompt(self, task: Dict) -> str:
        """Build the prompt for executing a task."""
        task_type = task.get('task_type', 'research')
        title = task.get('title', '')
        description = task.get('description', '')

        # Type-specific instructions
        type_instructions = {
            'research': "Research this topic thoroughly. Search the web, look up relevant information, and synthesize findings.",
            'discovery': "Find new items (papers, links, resources) related to this topic. Add useful ones to the collection.",
            'enrichment': "Improve existing items in the collection. Add missing metadata, summaries, or connections.",
            'analysis': "Analyze the collection or data. Generate insights, find patterns, create summaries.",
            'maintenance': "Perform maintenance tasks. Check for issues, clean up data, verify links.",
        }

        instructions = type_instructions.get(task_type, type_instructions['research'])

        prompt = f"""You are executing a background task. Complete it thoroughly and report your findings.

TASK: {title}

INSTRUCTIONS: {instructions}

DETAILS:
{description}

IMPORTANT:
- Use your tools to complete the task
- If you find useful resources, add them to the collection with add_link or add_paper
- Be thorough but efficient
- Summarize your findings clearly at the end

Begin the task now."""

        return prompt

    def _get_model_id(self, model_name: str) -> str:
        """Get the actual model ID from config."""
        config = self.core.config

        if model_name == 'reasoning':
            return getattr(config.llm, 'reasoning', config.llm.primary)
        elif model_name == 'fast':
            return getattr(config.llm, 'primary_cheap', config.llm.primary)
        else:
            return config.llm.primary

    def _run_laney_task(self, prompt: str, model: str, task_id: int) -> Dict[str, Any]:
        """Run the task using Laney's tools."""
        from ..llm.nanogpt import NanoGPTClient
        from ..llm.laney_tools import LANEY_TOOLS, LaneyToolHandler

        client = NanoGPTClient(self.api_key)
        tool_handler = LaneyToolHandler(
            db_path=self.db_path,
            brave_api_key=getattr(self.core.config.integrations, 'brave_api_key', None),
        )

        # Track items added during this task
        tool_handler._items_added = []

        # System prompt for task execution
        system_prompt = """You are Laney executing a background task. Be thorough and efficient.
Use your tools to research, discover, and add relevant items to the collection.
When done, provide a clear summary of what you found and what actions you took."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]

        try:
            response = client.run_with_tools(
                messages=messages,
                tools=LANEY_TOOLS,
                tool_handlers=tool_handler.handlers,
                model=model,
                temperature=0.3,
                max_iterations=15,
                timeout=300,  # 5 minutes for complex tasks
            )

            items_added = getattr(tool_handler, '_items_added', [])
            tool_handler.close()

            return {
                "success": True,
                "summary": response,
                "items_added": items_added,
            }

        except Exception as e:
            tool_handler.close()
            raise e

    def _update_task_status(self, task_id: int, status: str):
        """Update task status."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if status == 'running':
            cursor.execute("""
                UPDATE laney_tasks
                SET status = ?, started_at = ?
                WHERE id = ?
            """, (status, datetime.now().isoformat(), task_id))
        else:
            cursor.execute("""
                UPDATE laney_tasks SET status = ? WHERE id = ?
            """, (status, task_id))

        conn.commit()
        conn.close()

    def _complete_task(self, task_id: int, result: Dict):
        """Mark task as completed with results."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE laney_tasks
            SET status = 'completed',
                completed_at = ?,
                output_data = ?,
                items_added = ?
            WHERE id = ?
        """, (
            datetime.now().isoformat(),
            json.dumps(result.get('summary', '')),
            json.dumps(result.get('items_added', [])),
            task_id,
        ))

        conn.commit()
        conn.close()

    def _fail_task(self, task_id: int, error: str):
        """Mark task as failed."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE laney_tasks
            SET status = 'failed',
                completed_at = ?,
                error = ?
            WHERE id = ?
        """, (
            datetime.now().isoformat(),
            error[:500],  # Truncate error
            task_id,
        ))

        conn.commit()
        conn.close()

    def _notify_completion(self, task: Dict, result: Dict):
        """Send Telegram notification about task completion."""
        chat_id = task.get('chat_id')
        if not chat_id:
            return

        try:
            items_added = result.get('items_added', [])
            items_msg = ""
            if items_added:
                links = sum(1 for i in items_added if i.get('type') == 'link')
                papers = sum(1 for i in items_added if i.get('type') == 'paper')
                if links:
                    items_msg += f"\n   Added: {links} link(s)"
                if papers:
                    items_msg += f"\n   Added: {papers} paper(s)"

            summary = result.get('summary', '')
            if len(summary) > 200:
                summary = summary[:200] + "..."

            message = (
                f"*Task Completed*\n\n"
                f"*{task['title']}*{items_msg}\n\n"
                f"{summary}\n\n"
                f"_Use `list_my_tasks` to see details_"
            )

            # Publish to telegram channel
            self.publish('telegram.send', {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'Markdown',
            })

        except Exception as e:
            self.logger.error(f"Failed to send notification: {e}")

    def get_stats(self) -> Dict:
        """Get worker statistics."""
        return {
            "running": self.running,
            "current_task": self.current_task_id,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "tasks_today": self.tasks_today,
            "max_daily": self.max_daily_tasks,
        }
