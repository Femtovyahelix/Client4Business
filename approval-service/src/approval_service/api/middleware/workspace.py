from __future__ import annotations

from uuid import UUID

from fastapi import Header, HTTPException


async def get_workspace_id(
    x_workspace_id: str = Header(..., alias="X-Workspace-Id"),
) -> UUID:
    try:
        return UUID(x_workspace_id)
    except ValueError as err:
        raise HTTPException(
            status_code=400,
            detail="X-Workspace-Id header must be a valid UUID.",
        ) from err
