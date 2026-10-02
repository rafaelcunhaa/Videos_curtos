import hashlib
from pipeline.content_manifest import ContentManifest

def test_manifest_version_and_job():
    manifest = ContentManifest("video-1", pipeline_version="2.1.0", job_id="job-1")
    manifest.add_scene("STOCK", "asset-1")
    data = manifest.to_dict()
    assert data["schema_version"] == "1"
    assert data["job_id"] == "job-1"
    assert data["video_id"] == "video-1"
    assert data["scenes"][0]["source"] == "STOCK"

def test_artifact_sha256(tmp_path):
    path = tmp_path / "final.mp4"
    path.write_bytes(b"artifact")
    assert ContentManifest.sha256(str(path)) == hashlib.sha256(b"artifact").hexdigest()

def test_legacy_constructor_compatible():
    data = ContentManifest("legacy").to_dict()
    assert data["video_id"] == "legacy"
    assert data["job_id"] is None
