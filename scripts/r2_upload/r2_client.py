from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UploadPlan:
    bucket: str
    key: str
    content_type: str
    cache_control: str
    local_path: str


class R2Client:
    def upload(self, plan: UploadPlan) -> None:
        _ = plan
        raise NotImplementedError("R2 upload client is not implemented yet")
