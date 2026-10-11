from fastapi import APIRouter
from app.core.response import success
from app.db.pool import connection

router = APIRouter()


@router.get("")
def list_categories():
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM category ORDER BY id ASC")
            rows = cursor.fetchall()
    return success(rows)
