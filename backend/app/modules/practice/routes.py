from fastapi import APIRouter, Depends, HTTPException
from app.modules.practice.models import PracticeConfig, PracticeSubmit
from app.modules.practice.service import PracticeService
from app.modules.auth.dependencies import get_current_user

router = APIRouter()


@router.post("/start")
async def start_practice(
    config: PracticeConfig,
    user: dict = Depends(get_current_user)
):
    try:
        session = await PracticeService.create_session(
            user_id=str(user["_id"]),
            mode=config.mode,
            subject_id=config.subject_id,
            knowledge_ids=config.knowledge_ids,
            question_count=config.question_count,
            difficulty=config.difficulty
        )

        question = await PracticeService.get_current_question(session)
        question_response = PracticeService._question_payload(
            question, 0
        ) if question else None

        return {
            "session_id": session["id"],
            "current_question": question_response,
            "progress": PracticeService._build_progress(session)
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/submit")
async def submit_answer(
    submit_data: PracticeSubmit,
    user: dict = Depends(get_current_user)
):
    try:
        return await PracticeService.submit_answer(
            session_id=submit_data.session_id,
            user_id=str(user["_id"]),
            question_id=submit_data.question_id,
            user_answer=submit_data.user_answer
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/navigate/{session_id}/{direction}")
async def navigate(
    session_id: str,
    direction: str,
    user: dict = Depends(get_current_user)
):
    try:
        return await PracticeService.navigate_question(
            session_id=session_id,
            user_id=str(user["_id"]),
            direction=direction
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/progress/{session_id}")
async def get_progress(
    session_id: str,
    user: dict = Depends(get_current_user)
):
    try:
        return await PracticeService.get_session_progress(
            session_id=session_id,
            user_id=str(user["_id"])
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/unfinished")
async def get_unfinished_sessions(user: dict = Depends(get_current_user)):
    """首页展示最近未完成的练习会话。"""
    return {
        "items": await PracticeService.get_unfinished_sessions(str(user["_id"]))
    }


@router.get("/resume/{session_id}")
async def resume_practice(
    session_id: str,
    user: dict = Depends(get_current_user)
):
    """断点续练：回到退出时尚未提交的题目，保留此前作答。"""
    session = await PracticeService.resume_session(session_id, str(user["_id"]))
    if not session:
        raise HTTPException(status_code=404, detail="练习会话不存在")

    question = await PracticeService.get_current_question(session)
    current_index = session.get("current_index", 0)
    question_response = PracticeService._question_payload(
        question, current_index
    ) if question else None

    return {
        "session": PracticeService._serialize(session),
        "current_question": question_response,
        "progress": PracticeService._build_progress(session)
    }


@router.get("/session/{session_id}")
async def get_session(
    session_id: str,
    user: dict = Depends(get_current_user)
):
    session = await PracticeService.get_session(session_id, str(user["_id"]))
    if not session:
        raise HTTPException(status_code=404, detail="练习会话不存在")

    question = await PracticeService.get_current_question(session)
    current_index = session.get("current_index", 0)
    saved_answer = None
    if question:
        saved_answer = session.get("answers", {}).get(str(question["_id"]))
    question_response = PracticeService._question_payload(
        question, current_index, saved_answer
    ) if question else None

    return {
        "session": PracticeService._serialize(session),
        "current_question": question_response,
        "progress": PracticeService._build_progress(session)
    }
