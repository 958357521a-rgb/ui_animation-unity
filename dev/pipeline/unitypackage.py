# .unitypackage 写出:gzip 压缩的 tar,每个资产一个 GUID 目录(asset / asset.meta / pathname),与工作台 makeUnityPackage 同一结构。
import gzip, io, tarfile, time


def write_unitypackage(path, assets):
    """assets: [{"path": "Assets/...", "guid": 32 位十六进制, "data": bytes, "meta": str}]"""
    raw = io.BytesIO()
    now = int(time.time())
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        def add(name, data):
            ti = tarfile.TarInfo(name); ti.size = len(data); ti.mtime = now; ti.mode = 0o644
            tar.addfile(ti, io.BytesIO(data))
        seen = set()
        for a in assets:
            g = a["guid"]
            if g in seen:
                raise ValueError("GUID 重复:" + a["path"])
            seen.add(g)
            add(f"{g}/asset", a["data"])
            add(f"{g}/asset.meta", a["meta"].encode("utf-8"))
            add(f"{g}/pathname", a["path"].encode("utf-8"))
    with open(path, "wb") as f:
        f.write(gzip.compress(raw.getvalue(), mtime=0))
    return path
