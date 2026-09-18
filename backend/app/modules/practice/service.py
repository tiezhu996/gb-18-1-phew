from typing import Optional, List, Dict, Any
from bson import ObjectId
from datetime import datetime
import json
from app.core.database import get_db
from app.core.redis import get_redis
from app.modules.questions.service import QuestionService

CACHE_TTL = 3600 * 24
DATETIME_FIELDS = ("created_at", "updated_at")


class PracticeService:
    # ---------------- 缓存辅助 ----------------
    @staticmethod
    def _cache_key(user_id: str, session_id: str) -> str:
        return f"practice:{user_id}:{session_id}"

    @staticmethod
    def _serialize(session: dict) -> dict:
        """转换为可 JSON 序列化、可直接返回给前端的会话字典。"""
        result = dict(session)
        for field in DATETIME_FIELDS:
            if isinstance(result.get(field), datetime):
                result[field] = result[field].isoformat()
        result["id"] = str(result["_id"])
        result["_id"] = str(result["_id"])
        return result

    @staticmethod
    async def _set_cache(user_id: str, session_id: str, session: dict):
        redis = get_redis()
        if redis:
            await redis.setex(
                PracticeService._cache_key(user_id, session_id),
                CACHE_TTL,
                json.dumps(PracticeService._serialize(session), ensure_ascii=False)
            )

    # ---------------- 会话管理 ----------------
    @staticmethod
    async def create_session(
        user_id: str,
        mode: str,
        subject_id: str,
        knowledge_ids: Optional[List[str]] = None,
        question_count: int = 20,
        difficulty: Optional[str] = None
    ) -> dict:
        db = get_db()

        if mode == "random":
            questions = await QuestionService.get_random_questions(
                subject_id=subject_id,
                knowledge_ids=knowledge_ids,
                difficulty=difficulty,
                count=question_count
            )
        else:
            query = {"subject_id": subject_id}
            if knowledge_ids:
                query["knowledge_ids"] = {"$in": knowledge_ids}
            if difficulty:
                query["difficulty"] = difficulty
            cursor = db.questions.find(query).limit(question_count)
            questions = await cursor.to_list(length=question_count)

        if not questions:
            raise ValueError("没有找到符合条件的题目")

        question_ids = [str(q["_id"]) for q in questions]
        now = datetime.utcnow()
        session_dict = {
            "user_id": user_id,
            "mode": mode,
            "subject_id": subject_id,
            "knowledge_ids": knowledge_ids,
            "question_ids": question_ids,
            "current_index": 0,
            "answers": {},
            "total": len(question_ids),
            "correct_count": 0,
            "is_finished": False,
            "created_at": now,
            "updated_at": now
        }

        result = await db.practice_sessions.insert_one(session_dict)
        session_dict["_id"] = result.inserted_id
        session_dict["id"] = str(result.inserted_id)

        await PracticeService._set_cache(user_id, str(result.inserted_id), session_dict)

        return session_dict

    @staticmethod
    async def get_session(session_id: str, user_id: str) -> Optional[dict]:
        db = get_db()
        redis = get_redis()

        if not ObjectId.is_valid(session_id):
            return None

        if redis:
            cached = await redis.get(PracticeService._cache_key(user_id, session_id))
            if cached:
                return json.loads(cached)

        session = await db.practice_sessions.find_one({
            "_id": ObjectId(session_id),
            "user_id": user_id
        })

        if session:
            session["id"] = str(session["_id"])
            session["_id"] = str(session["_id"])
            await PracticeService._set_cache(user_id, session_id, session)

        return session

    @staticmethod
    async def get_unfinished_sessions(user_id: str, limit: int = 5) -> List[dict]:
        """获取最近未完成的练习会话，首页用于断点续练。"""
        db = get_db()
        cursor = db.practice_sessions.find({
            "user_id": user_id,
            "is_finished": {"$ne": True}
        }).sort("updated_at", -1).limit(limit)
        sessions = await cursor.to_list(length=limit)

        if not sessions:
            return []

        subject_ids = {
            s.get("subject_id") for s in sessions
            if s.get("subject_id") and ObjectId.is_valid(s["subject_id"])
        }
        subjects: Dict[str, dict] = {}
        if subject_ids:
            subject_docs = await db.subjects.find(
                {"_id": {"$in": [ObjectId(sid) for sid in subject_ids]}}
            ).to_list(length=None)
            subjects = {str(s["_id"]): s for s in subject_docs}

        result = []
        for session in sessions:
            answers = session.get("answers", {}) or {}
            total = session.get("total", len(session.get("question_ids", [])))
            answered = len(answers)
            # 兜底：历史数据没有 is_finished 字段，已全部作答即视为已完成
            if total and answered >= total:
                continue
            correct_count = sum(1 for a in answers.values() if a.get("is_correct"))
            subject = subjects.get(session.get("subject_id", ""))
            result.append({
                "id": str(session["_id"]),
                "mode": session.get("mode", "sequential"),
                "subject_id": session.get("subject_id"),
                "subject_name": subject.get("name") if subject else None,
                "subject_icon": subject.get("icon") if subject else None,
                "total": total,
                "answered": answered,
                "correct_count": correct_count,
                "updated_at": session.get("updated_at"),
                "created_at": session.get("created_at")
            })
        return result

    @staticmethod
    def _first_unanswered_index(session: dict) -> int:
        """退出时尚未提交的第一道题（已答题目按 question_ids 顺序判断）。"""
        question_ids = session.get("question_ids", [])
        answers = session.get("answers", {}) or {}
        for index, question_id in enumerate(question_ids):
            if question_id not in answers:
                return index
        return len(question_ids)

    @staticmethod
    async def resume_session(session_id: str, user_id: str) -> Optional[dict]:
        """断点续练：回到第一道未提交的题目，并返回此前全部作答。"""
        db = get_db()

        session = await PracticeService.get_session(session_id, user_id)
        if not session:
            return None

        total = session.get("total", len(session.get("question_ids", [])))
        all_answered = len(session.get("answers", {}) or {}) >= total

        # 已完成会话不再移动指针；未完成会话定位到第一道未提交的题目
        if not all_answered:
            resume_index = PracticeService._first_unanswered_index(session)
            if resume_index != session.get("current_index", 0):
                await db.practice_sessions.update_one(
                    {"_id": ObjectId(session_id)},
                    {"$set": {"current_index": resume_index}}
                )
                session["current_index"] = resume_index
                await PracticeService._set_cache(user_id, session_id, session)

        return session

    # ---------------- 题目与作答 ----------------
    @staticmethod
    async def get_question_at_index(session: dict, index: int) -> Optional[dict]:
        question_ids = session.get("question_ids", [])
        if 0 <= index < len(question_ids):
            return await QuestionService.get_question_by_id(question_ids[index])
        return None

    @staticmethod
    async def get_current_question(session: dict) -> Optional[dict]:
        return await PracticeService.get_question_at_index(
            session, session.get("current_index", 0)
        )

    @staticmethod
    def _build_progress(session: dict) -> dict:
        answers = session.get("answers", {}) or {}
        answered = len(answers)
        correct_count = sum(1 for a in answers.values() if a.get("is_correct"))
        return {
            "current": session.get("current_index", 0),
            "answered": answered,
            "total": session.get("total", 0),
            "correct": correct_count,
            "accuracy": round(correct_count / answered * 100, 1) if answered > 0 else 0
        }

    @staticmethod
    async def submit_answer(
        session_id: str,
        user_id: str,
        question_id: str,
        user_answer: Any
    ) -> Dict[str, Any]:
        db = get_db()

        session = await PracticeService.get_session(session_id, user_id)
        if not session:
            raise ValueError("练习会话不存在")

        question_ids = session.get("question_ids", [])
        if question_id not in question_ids:
            raise ValueError("该题目不属于当前练习会话")

        answers = session.get("answers", {}) or {}
        is_new_answer = question_id not in answers
        previous_correct = (
            answers[question_id].get("is_correct") if not is_new_answer else None
        )

        # 重复提交已答题目时不重复累计题目统计
        result = await QuestionService.check_answer(
            question_id, user_answer, user_id, count_stats=is_new_answer
        )

        new_answers = answers.copy()
        new_answers[question_id] = {
            "user_answer": user_answer,
            "is_correct": result.is_correct,
            "submitted_at": datetime.utcnow().isoformat()
        }

        # 错题本联动：按最后一次结果维护，不重复累计错题次数
        await PracticeService._sync_error_record(
            user_id=user_id,
            question_id=question_id,
            is_new_answer=is_new_answer,
            previous_correct=previous_correct,
            is_correct=result.is_correct
        )

        answered_count = len(new_answers)
        total = session.get("total", len(question_ids))
        is_finished = answered_count >= total

        update_data = {
            "answers": new_answers,
            "correct_count": sum(
                1 for a in new_answers.values() if a.get("is_correct")
            ),
            "is_finished": is_finished,
            "updated_at": datetime.utcnow()
        }

        # 提交不移动题目指针，前进统一交给“下一题”，避免提交与导航双重推进导致跳题
        if is_finished:
            update_data["current_index"] = min(total, len(question_ids))

        await db.practice_sessions.update_one(
            {"_id": ObjectId(session_id)},
            {"$set": update_data}
        )

        session.update(update_data)
        await PracticeService._set_cache(user_id, session_id, session)

        return {
            "question_id": question_id,
            "user_answer": user_answer,
            "is_correct": result.is_correct,
            "correct_answer": result.correct_answer,
            "explanation": result.explanation,
            "is_new_answer": is_new_answer,
            "progress": PracticeService._build_progress(session),
            "is_finished": is_finished
        }

    @staticmethod
    async def _sync_error_record(
        user_id: str,
        question_id: str,
        is_new_answer: bool,
        previous_correct: Optional[bool],
        is_correct: bool
    ):
        """按最后一次作答结果维护错题本：

        - 新题答错：加入待掌握错题，错题次数 +1
        - 新题答对 / 重答结果未变化：不做任何累计
        - 重答由错变对：从待掌握错题中移除（标记 mastered=True）
        - 重答由对变错：重新进入待掌握错题，错题次数 +1
        """
        db = get_db()

        if is_correct:
            if not is_new_answer and previous_correct is False:
                # 重答正确：从待掌握错题中移除（标记已掌握，保留历史记录）
                await db.errors.update_one(
                    {"user_id": user_id, "question_id": question_id},
                    {"$set": {"mastered": True}}
                )
            return

        if not is_new_answer and previous_correct is False:
            # 仍然答错，不重复累计错题次数
            return

        question = await QuestionService.get_question_by_id(question_id)
        if not question:
            return

        existing = await db.errors.find_one({
            "user_id": user_id,
            "question_id": question_id
        })

        if existing:
            await db.errors.update_one(
                {"_id": existing["_id"]},
                {
                    "$inc": {"wrong_count": 1},
                    "$set": {
                        "last_wrong_at": datetime.utcnow(),
                        "mastered": False
                    }
                }
            )
        else:
            await db.errors.insert_one({
                "user_id": user_id,
                "question_id": question_id,
                "subject_id": question.get("subject_id"),
                "knowledge_ids": question.get("knowledge_ids", []),
                "wrong_count": 1,
                "created_at": datetime.utcnow(),
                "last_wrong_at": datetime.utcnow(),
                "mastered": False
            })

    @staticmethod
    async def navigate_question(
        session_id: str,
        user_id: str,
        direction: str
    ) -> Optional[dict]:
        db = get_db()

        session = await PracticeService.get_session(session_id, user_id)
        if not session:
            raise ValueError("练习会话不存在")

        question_ids = session.get("question_ids", [])
        current_index = session.get("current_index", 0)
        total = len(question_ids)

        if direction == "prev":
            new_index = max(0, current_index - 1)
        elif direction == "next":
            new_index = min(total - 1, current_index + 1)
        else:
            new_index = current_index

        await db.practice_sessions.update_one(
            {"_id": ObjectId(session_id)},
            {"$set": {"current_index": new_index, "updated_at": datetime.utcnow()}}
        )

        session["current_index"] = new_index
        await PracticeService._set_cache(user_id, session_id, session)

        question = await PracticeService.get_question_at_index(session, new_index)
        if not question:
            return None

        saved_answer = session.get("answers", {}).get(str(question["_id"]))
        return PracticeService._question_payload(question, new_index, saved_answer)

    @staticmethod
    def _question_payload(
        question: dict, index: int, saved_answer: Optional[dict] = None
    ) -> dict:
        payload = {
            "id": str(question["_id"]),
            "type": question["type"],
            "content": question["content"],
            "options": question.get("options"),
            "difficulty": question["difficulty"],
            "knowledge_ids": question.get("knowledge_ids", []),
            "index": index
        }
        if saved_answer:
            # 已答题目：回显此前作答与判定结果，供前端展示后重答
            payload["saved_answer"] = saved_answer
            payload["user_answer"] = saved_answer.get("user_answer")
            payload["is_correct"] = saved_answer.get("is_correct")
            payload["correct_answer"] = question.get("correct_answer")
            payload["explanation"] = question.get("explanation")
        return payload

    @staticmethod
    async def get_session_progress(session_id: str, user_id: str) -> dict:
        session = await PracticeService.get_session(session_id, user_id)
        if not session:
            raise ValueError("练习会话不存在")

        return {
            **PracticeService._build_progress(session),
            "is_finished": bool(session.get("is_finished", False)),
            "answers": session.get("answers", {})
        }
