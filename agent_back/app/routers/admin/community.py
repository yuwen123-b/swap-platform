from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.pool import connection
from app.routers.admin.deps import ok, require_role

router = APIRouter()

read_roles = require_role([1, 2, 3])
write_roles = require_role([1, 2])
handle_roles = require_role([1, 2, 3])


class PostUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=100)
    content: str | None = None
    status: int | None = Field(default=None, ge=0, le=1)


class ReportHandle(BaseModel):
    action: str = Field(pattern="^(resolve|dismiss)$")
    result: str = ""


@router.get("/posts", dependencies=[Depends(read_roles)])
def list_posts(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    keyword: str | None = None,
):
    conditions = ["1=1"]
    params: list = []
    if keyword:
        conditions.append("(p.title LIKE %s OR p.content LIKE %s OR u.nickname LIKE %s)")
        params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])
    where = " AND ".join(conditions)
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM post p LEFT JOIN user u ON p.user_id=u.id WHERE {where}", params)
            total = cursor.fetchone()["total"]
            cursor.execute(
                f"""SELECT p.*, u.nickname AS author
                    FROM post p LEFT JOIN user u ON p.user_id=u.id
                    WHERE {where} ORDER BY p.id DESC LIMIT %s OFFSET %s""",
                params + [size, (page - 1) * size],
            )
            rows = cursor.fetchall()
    return ok({"total": total, "list": rows})


@router.put("/posts/{post_id}", dependencies=[Depends(write_roles)])
def update_post(post_id: int, req: PostUpdate):
    fields: list[str] = []
    params: list = []
    if req.title is not None:
        fields.append("title=%s")
        params.append(req.title)
    if req.content is not None:
        fields.append("content=%s")
        params.append(req.content)
    if req.status is not None:
        fields.append("status=%s")
        params.append(req.status)
    if not fields:
        raise HTTPException(400, "没有需要修改的字段")
    params.append(post_id)
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"UPDATE post SET {', '.join(fields)} WHERE id=%s", params)
            if cursor.rowcount == 0:
                raise HTTPException(404, "帖子不存在")
    return ok(message="帖子已更新")


@router.delete("/posts/{post_id}", dependencies=[Depends(write_roles)])
def delete_post(post_id: int):
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM post WHERE id=%s", (post_id,))
            if cursor.rowcount == 0:
                raise HTTPException(404, "帖子不存在")
            cursor.execute("DELETE FROM comment WHERE post_id=%s", (post_id,))
    return ok(message="帖子已删除")


@router.get("/reports", dependencies=[Depends(read_roles)])
def list_reports(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    status: int | None = None,
):
    conditions = ["1=1"]
    params: list = []
    if status is not None:
        conditions.append("r.status=%s")
        params.append(status)
    where = " AND ".join(conditions)
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM report r WHERE {where}", params)
            total = cursor.fetchone()["total"]
            cursor.execute(
                f"""SELECT r.*, u.nickname AS reporter_name, h.username AS handler_name
                    FROM report r
                    LEFT JOIN user u ON r.reporter_id=u.id
                    LEFT JOIN admin h ON r.handler_id=h.id
                    WHERE {where} ORDER BY r.status ASC, r.id DESC LIMIT %s OFFSET %s""",
                params + [size, (page - 1) * size],
            )
            rows = cursor.fetchall()
    return ok({"total": total, "list": rows})


@router.post("/reports/{report_id}/handle", dependencies=[Depends(handle_roles)])
def handle_report(report_id: int, req: ReportHandle, admin: dict = Depends(handle_roles)):
    status = 1 if req.action == "resolve" else 2
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, status FROM report WHERE id=%s LIMIT 1", (report_id,))
            report = cursor.fetchone()
            if not report:
                raise HTTPException(404, "举报不存在")
            if report["status"] != 0:
                raise HTTPException(400, "该举报已处理")
            cursor.execute(
                "UPDATE report SET status=%s, handler_id=%s, handle_time=NOW(), result=%s WHERE id=%s",
                (status, admin["admin_id"], req.result, report_id),
            )
    return ok(message="举报已处理" if status == 1 else "举报已驳回")
