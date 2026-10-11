from fastapi import APIRouter, Depends

from app.core.response import success
from app.core.security import get_current_user_id
from app.db.pool import connection
from app.schemas.feedback import FeedbackCreate
from app.services.sentiment import analyze

router = APIRouter()


@router.post("")
def create_feedback(payload: FeedbackCreate, user_id: int = Depends(get_current_user_id)):
    """提交对程序本身的评价，后端自动完成情感分析。"""
    result = analyze(payload.content)
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO platform_feedback (user_id, rating, content, sentiment, sentiment_score, sentiment_engine) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (user_id, payload.rating, payload.content, result["label"], result["score"], result["engine"]),
            )
            feedback_id = cursor.lastrowid
    label_cn = {"positive": "良好", "neutral": "中性", "negative": "差"}[result["label"]]
    return success(
        {"feedback_id": feedback_id, "sentiment": result["label"], "sentiment_cn": label_cn, "engine": result["engine"]},
        "感谢你的反馈",
    )


@router.get("")
def list_feedback(_: int = Depends(get_current_user_id)):
    """最近 20 条程序评价 + 汇总统计。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, user_id, rating, content, sentiment, sentiment_engine, created_at "
                "FROM platform_feedback ORDER BY id DESC LIMIT 20"
            )
            items = cursor.fetchall()
            cursor.execute(
                "SELECT COUNT(*) AS total, SUM(sentiment='positive') AS positive, "
                "SUM(sentiment='neutral') AS neutral, SUM(sentiment='negative') AS negative, "
                "COALESCE(AVG(rating),0) AS avg_rating FROM platform_feedback"
            )
            row = cursor.fetchone()
    stats = {
        "total": int(row["total"] or 0),
        "positive": int(row["positive"] or 0),
        "neutral": int(row["neutral"] or 0),
        "negative": int(row["negative"] or 0),
        "avg_rating": round(float(row["avg_rating"] or 0), 1),
    }
    return success({"items": items, "stats": stats})
