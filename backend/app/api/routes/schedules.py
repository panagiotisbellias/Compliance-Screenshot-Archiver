from __future__ import annotations

import uuid
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from ...auth.deps import require_operator, require_viewer
from ...domain.models import ScheduleCreate, ScheduleOut

router: APIRouter = APIRouter()

# In-memory stub store for demo; replace with DynamoDB.
_SCHEDULES: dict[str, ScheduleOut] = {}

# Pre-instantiated dependencies to avoid B008 lint issues
_viewer_dep = Depends(require_viewer)
_operator_dep = Depends(require_operator)


@router.get("", response_model=list[ScheduleOut])
def list_schedules(_: dict[str, str] = _viewer_dep) -> list[ScheduleOut]:
    """
    List schedules.

    Returns:
        list[ScheduleOut]: All schedules.
    """
    return list(_SCHEDULES.values())


@router.post("", response_model=ScheduleOut, status_code=201)
def create_schedule(payload: ScheduleCreate, _: dict[str, str] = _operator_dep) -> ScheduleOut:
    """
    Create a schedule.

    Args:
        payload (ScheduleCreate): New schedule input.

    Returns:
        ScheduleOut: Created schedule.
    """
    sid = str(uuid.uuid4())
    # Handle None values by filtering them out
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    out = ScheduleOut(id=sid, **data, enabled=True)
    _SCHEDULES[sid] = out
    return out


@router.get("/{schedule_id}", response_model=ScheduleOut)
def get_schedule(schedule_id: str, _: dict[str, str] = _viewer_dep) -> ScheduleOut:
    """
    Get a specific schedule.

    Args:
        schedule_id (str): Schedule ID.

    Returns:
        ScheduleOut: Schedule details.

    Raises:
        HTTPException: If schedule not found.
    """
    if schedule_id not in _SCHEDULES:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return _SCHEDULES[schedule_id]


@router.put("/{schedule_id}", response_model=ScheduleOut)
def update_schedule(
    schedule_id: str, payload: Dict[str, Any], _: dict[str, str] = _operator_dep
) -> ScheduleOut:
    """
    Update a schedule.

    Args:
        schedule_id (str): Schedule ID.
        payload (Dict[str, Any]): Update data.

    Returns:
        ScheduleOut: Updated schedule.

    Raises:
        HTTPException: If schedule not found.
    """
    if schedule_id not in _SCHEDULES:
        raise HTTPException(status_code=404, detail="Schedule not found")

    current = _SCHEDULES[schedule_id]

    # Update only provided fields
    update_data = current.model_dump()
    for key, value in payload.items():
        if key in update_data and key != "id":  # Don't allow ID changes
            update_data[key] = value

    updated_schedule = ScheduleOut(**update_data)
    _SCHEDULES[schedule_id] = updated_schedule
    return updated_schedule


@router.delete("/{schedule_id}")
def delete_schedule(schedule_id: str, _: dict[str, str] = _operator_dep) -> Dict[str, str]:
    """
    Delete a schedule.

    Args:
        schedule_id (str): Schedule ID.

    Raises:
        HTTPException: If schedule not found.
    """
    if schedule_id not in _SCHEDULES:
        raise HTTPException(status_code=404, detail="Schedule not found")
    del _SCHEDULES[schedule_id]
    return {"message": "Schedule deleted successfully"}
