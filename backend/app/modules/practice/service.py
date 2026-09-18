from typing import Optional, List, Dict, Any
from bson import ObjectId
from datetime import datetime
import json
from app.core.database import get_db
from app.core.redis import get_redis
from app.modules.questions.service import QuestionService


class PracticeService:
    # ------------------------------------------------------------------
    # 序列化 / 工具方法
    # ------------------------------------------------------------------
    @staticmethod
    def _serialize_session(session: dict) -> dict:
        """转成可缓存/可 JSON 序列化的会话结构。"""
        serialized = dict(session)
        for key in ("_id", "id"):
            if key in serialized:
                serialized[key] = str(serialized[key])
        for key in ("created_at", "updated_at"):
            value = serialized.get(key)
            if isinstance(value, datetime):
                serialized[key] = value.isoformat()
        return serialized

    @staticmethod
    async def _cache_session(user_id: str, session_id: str, session: dict):
        redis = get_redis()
        if redis:
            key = f"practice:{user_id}:{session_id}"
            await redis.setex(
                key,
                3600 * 24,
                json.dumps(PracticeService._serialize_session(session))
            )

    @staticmethod
    def _session_is_finished(session: dict) -> bool:
        if "is_finished" in session:
            return bool(session["is_finished"])
        # 兼容历史数据：无标记时以“全部题目已作答”判定
        return len(session.get("answers", {})) >= session.get("total", 0) > 0

    @staticmethod
    def _first_unanswered_index(session: dict) -> int:
        answers = session.get("answers", {})
        question_ids = session.get("question_ids", [])
        for index, question_id in enumerate(question_ids):
            if question_id not in answers:
                return index
        return len(question_ids)

    @staticmethod
    def _build_progress(session: dict) -> dict:
        answers = session.get("answers", {})
        answered = len(answers)
        correct_count = sum(1 for a in answers.values() if a.get("is_correct"))
        return {
            "current": session.get("current_index", 0),
            "total": session.get("total", 0),
            "answered": answered,
            "correct": correct_count,
            "accuracy": round(correct_count / answered * 100, 1) if answered > 0 else 0
        }

    @staticmethod
    def _build_question_payload(question: dict, answer: Optional[dict] = None) -> dict:
        payload = {
            "id": str(question["_id"]),
            "type": question["type"],
            "content": question["content"],
            "options": question.get("options"),
            "difficulty": question["difficulty"],
            "knowledge_ids": question.get("knowledge_ids", [])
        }
        if answer is not None:
            # 已作答的题目：回填此前答案与判题结果
            payload["answered"] = True
            payload["user_answer"] = answer.get("user_answer")
            payload["is_correct"] = answer.get("is_correct")
            payload["correct_answer"] = question.get("correct_answer")
            payload["explanation"] = question.get("explanation")
        return payload

    # ------------------------------------------------------------------
    # 会话管理
    # ------------------------------------------------------------------
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

        await PracticeService._cache_session(user_id, str(result.inserted_id), session_dict)

        return session_dict

    @staticmethod
    async def get_session(session_id: str, user_id: str) -> Optional[dict]:
        db = get_db()
        redis = get_redis()

        if redis:
            key = f"practice:{user_id}:{session_id}"
            cached = await redis.get(key)
            if cached:
                return json.loads(cached)

        if not ObjectId.is_valid(session_id):
            return None
        session = await db.practice_sessions.find_one({
            "_id": ObjectId(session_id),
            "user_id": user_id
        })

        if session:
            session["id"] = str(session["_id"])
            session["_id"] = str(session["_id"])
            await PracticeService._cache_session(user_id, session_id, session)

        return session

    @staticmethod
    async def get_resumable_session(user_id: str) -> Optional[dict]:
        """获取最近一次未完成的练习会话，用于首页断点续练。"""
        db = get_db()

        candidates = await db.practice_sessions.find(
            {"user_id": user_id}
        ).sort("updated_at", -1).limit(20).to_list(length=20)

        for session in candidates:
            if PracticeService._session_is_finished(session):
                continue
            session["id"] = str(session["_id"])
            session["_id"] = str(session["_id"])
            subject = await db.subjects.find_one(
                {"_id": ObjectId(session["subject_id"])}
            ) if ObjectId.is_valid(session.get("subject_id", "")) else None

            answered = len(session.get("answers", {}))
            return {
                "id": session["id"],
                "mode": session.get("mode"),
                "subject_id": session.get("subject_id"),
                "subject_name": subject.get("name") if subject else None,
                "knowledge_ids": session.get("knowledge_ids"),
                "current_index": session.get("current_index", 0),
                "total": session.get("total", 0),
                "answered": answered,
                "correct_count": sum(
                    1 for a in session.get("answers", {}).values()
                    if a.get("is_correct")
                ),
                "updated_at": session.get("updated_at")
            }
        return None

    @staticmethod
    async def get_current_question(session: dict) -> Optional[dict]:
        current_index = session.get("current_index", 0)
        question_ids = session.get("question_ids", [])
        if 0 <= current_index < len(question_ids):
            return await QuestionService.get_question_by_id(question_ids[current_index])
        return None

    # ------------------------------------------------------------------
    # 答题提交（幂等）
    # ------------------------------------------------------------------
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
            raise ValueError("题目不属于当前练习会话")

        answers = session.get("answers", {})
        is_new_answer = question_id not in answers

        # 重复提交不重复累计题目统计（stats.answered / stats.correct）
        result = await QuestionService.check_answer(
            question_id, user_answer, user_id, update_stats=is_new_answer
        )

        # 按最后一次结果维护错题本，不重复累计错题次数
        await PracticeService._sync_error_book(
            user_id=user_id,
            question_id=question_id,
            is_new_answer=is_new_answer,
            was_correct=answers[question_id].get("is_correct") if not is_new_answer else None,
            is_correct=result.is_correct
        )

        new_answers = answers.copy()
        new_answers[question_id] = {
            "user_answer": user_answer,
            "is_correct": result.is_correct,
            "submitted_at": datetime.utcnow().isoformat()
        }

        # 正确率始终以最新作答结果重算
        new_correct_count = sum(1 for a in new_answers.values() if a.get("is_correct"))
        was_finished = PracticeService._session_is_finished(session)
        is_finished = was_finished or len(new_answers) >= len(question_ids)

        update_data = {
            "answers": new_answers,
            "correct_count": new_correct_count,
            "is_finished": is_finished,
            "updated_at": datetime.utcnow()
        }

        await db.practice_sessions.update_one(
            {"_id": ObjectId(session_id)},
            {"$set": update_data}
        )

        session.update(update_data)
        await PracticeService._cache_session(user_id, session_id, session)

        progress = PracticeService._build_progress(session)

        return {
            "question_id": question_id,
            "is_correct": result.is_correct,
            "correct_answer": result.correct_answer,
            "explanation": result.explanation,
            "progress": progress,
            "is_finished": is_finished
        }

    @staticmethod
    async def _sync_error_book(
        user_id: str,
        question_id: str,
        is_new_answer: bool,
        was_correct: Optional[bool],
        is_correct: bool
    ):
        db = get_db()

        if is_new_answer:
            if not is_correct:
                await PracticeService._add_to_errors(user_id, question_id)
            return

        if was_correct == is_correct:
            # 结果未变化：不重复累计错题次数
            return

        if is_correct:
            # 重答正确：从待掌握错题中移除（用户手动标记已掌握的记录保留）
            await db.errors.delete_many({
                "user_id": user_id,
                "question_id": question_id,
                "mastered": False
            })
        else:
            # 由对变错：加入错题本
            await PracticeService._add_to_errors(user_id, question_id)

    @staticmethod
    async def _add_to_errors(user_id: str, question_id: str):
        db = get_db()
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
                    "$set": {"last_wrong_at": datetime.utcnow()}
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

    # ------------------------------------------------------------------
    # 题目导航
    # ------------------------------------------------------------------
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

        if direction == "prev":
            new_index = max(0, current_index - 1)
        elif direction == "next":
            new_index = min(len(question_ids) - 1, current_index + 1)
        else:
            new_index = current_index

        await db.practice_sessions.update_one(
            {"_id": ObjectId(session_id)},
            {"$set": {
                "current_index": new_index,
                "updated_at": datetime.utcnow()
            }}
        )

        session["current_index"] = new_index
        session["updated_at"] = datetime.utcnow()
        await PracticeService._cache_session(user_id, session_id, session)

        if 0 <= new_index < len(question_ids):
            question_id = question_ids[new_index]
            question = await QuestionService.get_question_by_id(question_id)
            answer = session.get("answers", {}).get(question_id)
            return {
                "question": PracticeService._build_question_payload(question, answer) if question else None,
                "progress": PracticeService._build_progress(session),
                "is_finished": PracticeService._session_is_finished(session)
            }
        return None

    @staticmethod
    async def get_session_progress(session_id: str, user_id: str) -> dict:
        session = await PracticeService.get_session(session_id, user_id)
        if not session:
            raise ValueError("练习会话不存在")

        progress = PracticeService._build_progress(session)
        progress["answers"] = session.get("answers", {})
        progress["is_finished"] = PracticeService._session_is_finished(session)
        return progress

    @staticmethod
    async def resume_session(session_id: str, user_id: str) -> Optional[dict]:
        """回到退出时尚未提交的题目（首个未作答题目），并回填进度。"""
        db = get_db()

        session = await PracticeService.get_session(session_id, user_id)
        if not session:
            return None

        new_index = PracticeService._first_unanswered_index(session)
        if new_index != session.get("current_index"):
            await db.practice_sessions.update_one(
                {"_id": ObjectId(session_id)},
                {"$set": {
                    "current_index": new_index,
                    "updated_at": datetime.utcnow()
                }}
            )
            session["current_index"] = new_index
            session["updated_at"] = datetime.utcnow()
            await PracticeService._cache_session(user_id, session_id, session)

        question = await PracticeService.get_current_question(session)
        answer = None
        if question:
            answer = session.get("answers", {}).get(str(question["_id"]))

        return {
            "session": PracticeService._serialize_session(session),
            "current_question": (
                PracticeService._build_question_payload(question, answer)
                if question else None
            ),
            "progress": PracticeService._build_progress(session),
            "is_finished": PracticeService._session_is_finished(session)
        }
