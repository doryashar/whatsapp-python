import asyncio
import pytest
import logging


class TestCreateTaskWithLoggingComprehensive:
    @pytest.mark.asyncio
    async def test_task_exception_is_logged_with_name(self, caplog):
        from src.main import create_task_with_logging

        caplog.set_level(logging.ERROR)

        async def failing_task():
            raise RuntimeError("catastrophic failure")

        task = create_task_with_logging(failing_task(), name="my_named_task")

        await asyncio.sleep(0.05)

        assert task.done()
        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert any("my_named_task" in r.message for r in error_records)
        assert any("catastrophic failure" in r.message for r in error_records)

    @pytest.mark.asyncio
    async def test_multiple_concurrent_tasks_with_failures(self, caplog):
        from src.main import create_task_with_logging

        caplog.set_level(logging.ERROR)

        results = []

        async def success_task(n):
            results.append(n)
            return n

        async def fail_task():
            raise ValueError("boom")

        tasks = [
            create_task_with_logging(success_task(i), name=f"task_{i}")
            for i in range(5)
        ]
        tasks.append(create_task_with_logging(fail_task(), name="fail_task"))

        await asyncio.gather(*tasks, return_exceptions=True)

        assert results == [0, 1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_cancelled_task_no_error_log(self, caplog):
        from src.main import create_task_with_logging

        caplog.set_level(logging.ERROR)

        async def long_task():
            await asyncio.sleep(10)

        task = create_task_with_logging(long_task(), name="long_running")
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        error_for_task = [r for r in error_records if "long_running" in r.message]
        assert len(error_for_task) == 0

    @pytest.mark.asyncio
    async def test_done_callback_attached(self):
        from src.main import create_task_with_logging

        callback_called = False

        async def simple_task():
            return "ok"

        task = create_task_with_logging(simple_task(), name="callback_test")

        assert len(task._callbacks) > 0

        await task

    @pytest.mark.asyncio
    async def test_exception_with_traceback(self, caplog):
        from src.main import create_task_with_logging

        caplog.set_level(logging.ERROR)

        async def nested_fail():
            def inner():
                raise RuntimeError("root cause")

            inner()

        task = create_task_with_logging(nested_fail(), name="trace_test")

        await asyncio.sleep(0.05)

        error_records = [r for r in caplog.records if "trace_test" in r.message]
        assert len(error_records) > 0

    @pytest.mark.asyncio
    async def test_task_with_invalid_state_after_cancel(self, caplog):
        from src.main import create_task_with_logging

        caplog.set_level(logging.ERROR)

        async def quick_task():
            return "done"

        task = create_task_with_logging(quick_task(), name="quick")
        task.cancel()

        with pytest.raises((asyncio.CancelledError, Exception)):
            await task
