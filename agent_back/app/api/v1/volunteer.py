"""志愿者代取任务接口：创建、查询、状态更新。"""
from fastapi import APIRouter, HTTPException

from app.core.response import success
from app.schemas.accessibility import (VolunteerTaskCreate, VolunteerTaskResponse,
                                       VolunteerTaskUpdate)
from app.services import volunteer_service

router = APIRouter()


@router.post("/task")
def create_task(body: VolunteerTaskCreate):
    result = volunteer_service.create_task(
        exchange_id=body.exchange_id,
        requester_id=body.requester_id,
        item_id=body.item_id,
        volunteer_id=body.volunteer_id,
        handover_method=body.handover_method,
        note=body.note,
    )
    return success(VolunteerTaskResponse(**result).model_dump())


@router.get("/tasks/{user_id}")
def list_tasks(user_id: int):
    """查询用户相关任务（我委托的、我接的、可接的待接单）。"""
    return success({"tasks": volunteer_service.list_tasks(user_id)})


@router.put("/task/{task_id}")
def update_task(task_id: int, body: VolunteerTaskUpdate):
    try:
        result = volunteer_service.update_status(task_id, body.volunteer_id, body.status)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return success(VolunteerTaskResponse(**result).model_dump())
