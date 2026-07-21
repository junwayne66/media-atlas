"""日志 Secret 洗涤（VF-007 DoD：Secret 不出现在日志）。

已知 Secret 值在 formatter 输出前替换为 ***；凭据只以短期 handle 形式
流转（30 §5），本过滤器是纵深防线：即使代码误把 Secret 拼进日志消息，
落盘/上屏内容也已脱敏。
"""

import logging
import os
import traceback

# 环境变量名含这些片段的，其值视为 Secret
_SECRET_ENV_MARKERS = ("SECRET", "PASSWORD", "TOKEN", "KEY", "CREDENTIAL")

REDACTED = "***"


def secrets_from_env(environ: dict[str, str] | None = None) -> list[str]:
    env = environ if environ is not None else dict(os.environ)
    values = [
        v
        for k, v in env.items()
        if any(marker in k.upper() for marker in _SECRET_ENV_MARKERS) and len(v) >= 6
    ]
    # 先长后短，避免长 Secret 只被部分遮盖
    return sorted(set(values), key=len, reverse=True)


def scrub_text(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret and secret in text:
            text = text.replace(secret, REDACTED)
    return text


class SecretScrubbingFilter(logging.Filter):
    def __init__(self, secrets: list[str]) -> None:
        super().__init__()
        self._secrets = [s for s in secrets if s]

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        scrubbed = scrub_text(message, self._secrets)
        if scrubbed != message:
            record.msg = scrubbed
            record.args = ()
        if record.exc_info and record.exc_info != (None, None, None):
            # 异常堆栈同样要洗：预渲染进 exc_text 并清掉 exc_info，
            # 否则 formatter 会绕过本过滤器直出原始 traceback
            rendered = "".join(traceback.format_exception(*record.exc_info))
            record.exc_text = scrub_text(rendered, self._secrets)
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = scrub_text(record.exc_text, self._secrets)
        return True


def install(logger: logging.Logger, secrets: list[str] | None = None) -> SecretScrubbingFilter:
    scrubber = SecretScrubbingFilter(secrets if secrets is not None else secrets_from_env())
    logger.addFilter(scrubber)
    for handler in logger.handlers:
        handler.addFilter(scrubber)
    return scrubber
