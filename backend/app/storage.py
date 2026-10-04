import shutil
from pathlib import Path

from .config import settings
from .db import exe, one, now, is_postgres

try:
    import boto3
except ImportError:  # pragma: no cover - dependency is installed in production
    boto3 = None


class ObjectStorage:
    """
    S3-compatible object storage adapter.

    Supports AWS S3, Cloudflare R2, MinIO, or any S3-compatible endpoint.
    Local filesystem storage remains available for development/tests only.
    """

    def __init__(self) -> None:
        self.backend = settings.storage_backend.lower()

        # Render production must never depend on the instance filesystem.
        # If PostgreSQL is configured but an older deployment forgot to set
        # STORAGE_BACKEND=database, automatically use the durable database
        # blob store instead of the ephemeral local filesystem.
        if self.backend == "local" and is_postgres():
            self.backend = "database"

        self._client = None

        if self.backend == "s3":
            if boto3 is None:
                raise RuntimeError("boto3 is required when STORAGE_BACKEND=s3")
            missing = [
                key
                for key, value in {
                    "S3_BUCKET": settings.s3_bucket,
                    "S3_ACCESS_KEY_ID": settings.s3_access_key_id,
                    "S3_SECRET_ACCESS_KEY": settings.s3_secret_access_key,
                }.items()
                if not value
            ]
            if missing:
                raise RuntimeError(
                    "Missing object-storage settings: " + ", ".join(missing)
                )
            self._client = boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint_url or None,
                region_name=settings.s3_region or None,
                aws_access_key_id=settings.s3_access_key_id,
                aws_secret_access_key=settings.s3_secret_access_key,
            )
            self.local_root = None
        elif self.backend == "local":
            self.local_root = Path(settings.local_storage_dir)
            self.local_root.mkdir(parents=True, exist_ok=True)
        elif self.backend == "database":
            # Production-safe fallback for the Render free setup: originals
            # survive web-service restarts because they live in PostgreSQL.
            self.local_root = None
        else:
            raise RuntimeError(
                "STORAGE_BACKEND must be either 's3', 'database', or 'local'."
            )

    @property
    def is_object_storage(self) -> bool:
        return self.backend in {"s3", "database"}

    def upload_file(self, path: Path, key: str, content_type: str) -> str:
        if self.backend == "s3":
            extra = {"ContentType": content_type or "application/octet-stream"}
            self._client.upload_file(str(path), settings.s3_bucket, key, ExtraArgs=extra)
            return f"s3://{settings.s3_bucket}/{key}"

        if self.backend == "database":
            exe(
                """
                INSERT INTO file_blobs(object_key,content,content_type,created_at)
                VALUES(?,?,?,?)
                ON CONFLICT(object_key)
                DO UPDATE SET content=excluded.content,
                              content_type=excluded.content_type
                """,
                (
                    key,
                    path.read_bytes(),
                    content_type or "application/octet-stream",
                    now(),
                ),
            )
            return f"db://{key}"

        destination = self.local_root / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        return str(destination)

    def download_file(self, key_or_uri: str, destination: Path) -> Path:
        """Materialize a persisted original for re-indexing."""
        destination.parent.mkdir(parents=True, exist_ok=True)

        if self.backend == "s3":
            prefix = f"s3://{settings.s3_bucket}/"
            key = (
                key_or_uri[len(prefix):]
                if key_or_uri.startswith(prefix)
                else key_or_uri
            )
            self._client.download_file(
                settings.s3_bucket,
                key,
                str(destination),
            )
            return destination

        if self.backend == "database":
            prefix = "db://"
            key = key_or_uri[len(prefix):] if key_or_uri.startswith(prefix) else key_or_uri
            row = one(
                "SELECT content FROM file_blobs WHERE object_key=?",
                (key,),
            )
            if not row:
                raise FileNotFoundError("Persisted database file is no longer available.")
            data = row["content"]
            if isinstance(data, memoryview):
                data = data.tobytes()
            destination.write_bytes(bytes(data))
            return destination

        source = Path(key_or_uri)
        if not source.exists():
            raise FileNotFoundError("Persisted local file is no longer available.")
        shutil.copy2(source, destination)
        return destination

    def delete(self, key_or_uri: str) -> None:
        if not key_or_uri:
            return

        if self.backend == "s3":
            prefix = f"s3://{settings.s3_bucket}/"
            key = (
                key_or_uri[len(prefix):]
                if key_or_uri.startswith(prefix)
                else key_or_uri
            )
            try:
                self._client.delete_object(Bucket=settings.s3_bucket, Key=key)
            except Exception:
                # Cleanup must never hide the original ingestion error.
                pass
            return

        if self.backend == "database":
            key = key_or_uri[5:] if key_or_uri.startswith("db://") else key_or_uri
            try:
                exe("DELETE FROM file_blobs WHERE object_key=?", (key,))
            except Exception:
                # Cleanup should never mask the original request outcome.
                pass
            return

        Path(key_or_uri).unlink(missing_ok=True)


storage = ObjectStorage()
