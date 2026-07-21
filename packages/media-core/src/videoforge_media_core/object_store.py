import os
from dataclasses import dataclass
from typing import BinaryIO

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError


@dataclass(frozen=True)
class S3Settings:
    endpoint_url: str
    access_key: str
    secret_key: str
    bucket: str
    region: str = "us-east-1"

    @classmethod
    def from_env(cls) -> "S3Settings":
        return cls(
            endpoint_url=os.environ.get("VIDEOFORGE_S3_ENDPOINT", "http://localhost:9000"),
            access_key=os.environ.get("VIDEOFORGE_S3_ACCESS_KEY", "videoforge"),
            secret_key=os.environ.get("VIDEOFORGE_S3_SECRET_KEY", "videoforge123"),
            bucket=os.environ.get("VIDEOFORGE_S3_BUCKET", "videoforge"),
            region=os.environ.get("VIDEOFORGE_S3_REGION", "us-east-1"),
        )


class ObjectStore:
    """S3 API 薄封装（MinIO/S3 可互换，部署可替换——50 §1）。

    对象键不承载业务真值（30 §7）；presigned URL 短有效期（30 §10）。
    """

    def __init__(self, settings: S3Settings) -> None:
        self._settings = settings
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.endpoint_url,
            aws_access_key_id=settings.access_key,
            aws_secret_access_key=settings.secret_key,
            region_name=settings.region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    @property
    def bucket(self) -> str:
        return self._settings.bucket

    def ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self.bucket)

    def head(self, key: str) -> dict | None:
        try:
            return self._client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                # HEAD 的 404 分不清 bucket 缺失还是键缺失；bucket 缺失是配置错误，
                # 不能伪装成"对象不存在"误导排障
                try:
                    self._client.head_bucket(Bucket=self.bucket)
                except ClientError as bucket_exc:
                    raise RuntimeError(f"bucket 不存在或不可访问: {self.bucket}") from bucket_exc
                return None
            raise

    def open_stream(self, key: str) -> BinaryIO:
        return self._client.get_object(Bucket=self.bucket, Key=key)["Body"]

    def put_stream(self, key: str, stream: BinaryIO) -> None:
        self._client.upload_fileobj(stream, self.bucket, key)

    def copy(self, src_key: str, dst_key: str) -> None:
        self._client.copy_object(
            Bucket=self.bucket,
            Key=dst_key,
            CopySource={"Bucket": self.bucket, "Key": src_key},
        )

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=key)

    def presign_put(self, key: str, expires_s: int = 3600) -> str:
        return self._client.generate_presigned_url(
            "put_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires_s
        )

    def presign_get(self, key: str, expires_s: int = 600) -> str:
        return self._client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires_s
        )
