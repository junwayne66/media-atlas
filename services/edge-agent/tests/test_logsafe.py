"""DoD：Secret 不出现在日志。"""

import logging

from videoforge_edge_agent.logsafe import (
    REDACTED,
    SecretScrubbingFilter,
    install,
    secrets_from_env,
)


def test_secrets_collected_from_env_by_name_markers() -> None:
    env = {
        "VIDEOFORGE_S3_SECRET_KEY": "super-secret-value",
        "PLATFORM_PASSWORD": "hunter2hunter2",
        "SOME_TOKEN": "tok-123456",
        "HARMLESS": "visible",
        "SHORT_KEY": "abc",  # 过短不收集，避免误伤普通词
    }
    secrets = secrets_from_env(env)
    assert "super-secret-value" in secrets
    assert "hunter2hunter2" in secrets
    assert "tok-123456" in secrets
    assert "visible" not in secrets
    assert "abc" not in secrets


def test_filter_scrubs_secret_from_rendered_log(caplog) -> None:
    logger = logging.getLogger("test.scrub")
    logger.addFilter(SecretScrubbingFilter(["super-secret-value"]))
    with caplog.at_level(logging.INFO, logger="test.scrub"):
        logger.info("connecting with key=%s", "super-secret-value")
    assert "super-secret-value" not in caplog.text
    assert REDACTED in caplog.text
    logger.filters.clear()


def test_exception_traceback_also_scrubbed(caplog) -> None:
    logger = logging.getLogger("test.scrub.exc")
    logger.addFilter(SecretScrubbingFilter(["sk-live-abcdef123456"]))
    with caplog.at_level(logging.ERROR, logger="test.scrub.exc"):
        try:
            raise ValueError("boom with sk-live-abcdef123456")
        except ValueError:
            logger.exception("task failed")
    assert "sk-live-abcdef123456" not in caplog.text
    assert REDACTED in caplog.text
    assert "ValueError" in caplog.text  # 堆栈仍在，只是脱敏
    logger.filters.clear()


def test_install_covers_accidental_interpolation(caplog) -> None:
    logger = logging.getLogger("videoforge.edge_agent.test")
    install(logger, ["sk-live-abcdef123456"])
    with caplog.at_level(logging.INFO, logger="videoforge.edge_agent.test"):
        logger.info("debug dump: %s", {"authorization": "Bearer sk-live-abcdef123456"})
    assert "sk-live-abcdef123456" not in caplog.text
    assert REDACTED in caplog.text
    logger.filters.clear()
