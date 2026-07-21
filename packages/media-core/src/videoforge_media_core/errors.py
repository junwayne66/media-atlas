class ArtifactStoreError(Exception):
    """对象存储/Artifact 提交流程错误基类。"""


class StagedUploadNotFound(ArtifactStoreError):
    """staging 对象不存在：上传未发生、被中断后清理、或已被提交消费。"""


class StagedUploadMismatch(ArtifactStoreError):
    """staging 对象与声明的 sha256/size 不符：上传被截断或内容被篡改。"""


class ObjectIntegrityError(ArtifactStoreError):
    """下载/缓存内容与 Artifact 记录的 sha256 不符。"""
