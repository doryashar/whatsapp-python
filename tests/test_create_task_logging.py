import asyncio
import pytest
import logging


class TestCreateTaskWithLogging:
    @pytest.mark.asyncio
    async def test_create_task_with_logging_success(self):
        from src.main import create_task_with_logging

        async def successful_task():
            return "success"

        task = create_task_with_logging(successful_task(), name="test_success")
        assert task is not None
        assert isinstance(task, asyncio.Task)

        result = await task
        assert result == "success"

    @pytest.mark.asyncio
    async def test_create_task_with_logging_exception(self, caplog):
        from src.main import create_task_with_logging

        async def failing_task():
            raise ValueError("test error")

        task = create_task_with_logging(failing_task(), name="test_failing")

        await asyncio.sleep(0.01)

        assert any("test_failing" in record.message for record in caplog.records)
        assert any("test error" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_create_task_with_logging_cancelled(self):
        from src.main import create_task_with_logging

        async def cancelled_task():
            await asyncio.sleep(10)

        task = create_task_with_logging(cancelled_task(), name="test_cancelled")
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_create_task_with_logging_default_name(self):
        from src.main import create_task_with_logging

        async def simple_task():
            return "done"

        task = create_task_with_logging(simple_task())

        result = await task
        assert result == "done"

    @pytest.mark.asyncio
    async def test_create_task_returns_task_object(self):
        from src.main import create_task_with_logging

        async def dummy():
            pass

        task = create_task_with_logging(dummy(), name="dummy")

        assert hasattr(task, "add_done_callback")
        assert hasattr(task, "cancel")
        assert hasattr(task, "done")

        await task

    @pytest.mark.asyncio
    async def test_create_task_logs_on_failure(self, caplog):
        from src.main import create_task_with_logging

        caplog.set_level(logging.ERROR)

        async def error_task():
            raise RuntimeError("intentional test error")

        task = create_task_with_logging(error_task(), name="error_test")

        await asyncio.sleep(0.01)

        assert task.done()
        error_records = [r for r in caplog.records if "error_test" in r.message]
        assert len(error_records) > 0
