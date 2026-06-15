"""FastAPI 主服务 — 多智能体学习系统的后端入口。

启动方式：
    uv run python -m backend.main
    或
    uv run uvicorn backend.main:app --reload --port 8000

API端点：
    POST /api/chat/stream          — 流式对话（SSE）
    POST /api/chat                 — 普通对话
    GET  /api/profile/{student_id} — 获取学生画像
    POST /api/profile/update       — 更新画像
    POST /api/profile/build        — 通过对话构建画像
    POST /api/resources/generate        — 批量生成资源
    POST /api/resources/generate-stream — 流式生成资源（带进度）
    GET  /api/kb/stats             — 知识库统计
    POST /api/kb/upload            — 上传Markdown到知识库
    GET  /api/health               — 健康检查
"""

import json
import uuid
import os
import asyncio
from typing import AsyncGenerator

from dotenv import load_dotenv
load_dotenv()  # 加载 .env 文件中的环境变量

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from typing import Optional

from backend.models.database import init_db, get_user_by_token, get_db
from backend.models.database import create_user, authenticate as db_authenticate
from backend.models.database import get_profile, update_profile as db_update_profile
from backend.models.database import add_resource, get_resources, get_path, list_paths, update_path as db_update_path, delete_path as db_delete_path
from backend.models.database import save_chat_message, get_chat_history
from backend.models.database import save_evaluation, get_latest_evaluation, get_evaluation_history

from backend.utils.llm_client import SparkLLMClient
from backend.utils.pptx_builder import build_pptx
from backend.safety.filter import safety_filter
from backend.agents.orchestrator import Orchestrator
from backend.agents.profile import ProfileAgent
from backend.agents.resources import (
    DocAgent, MindmapAgent, QuizAgent, ReadingAgent, CodeAgent, PPTAgent,
)
from backend.agents.path_tutor_eval import PathAgent, TutorAgent, EvalAgent
from backend.rag.knowledge_base import KnowledgeBase

# ========== 应用初始化 ==========

app = FastAPI(
    title="A3 个性化学习多智能体系统",
    description="基于大模型的个性化资源生成与学习多智能体系统",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 启动时初始化数据库
init_db()

# ========== 鉴权依赖 ==========

async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """从 Authorization: Bearer <token> 中解析当前用户"""
    if not authorization or not authorization.startswith("Bearer "):
        return None  # 不强制登录，返回 None 表示未登录
    token = authorization[7:]
    user = get_user_by_token(token)
    return user

# ========== 鉴权路由 ==========

class RegisterRequest(BaseModel):
    username: str
    password: str
    nickname: str = ""

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/api/auth/register")
async def register(req: RegisterRequest):
    """注册"""
    if len(req.username) < 2 or len(req.password) < 4:
        raise HTTPException(400, "用户名至少2位，密码至少4位")
    user = create_user(req.username, req.password, req.nickname or req.username)
    if not user:
        raise HTTPException(409, "用户名已存在")
    return {"token": user["token"], "user": user}

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    """登录"""
    user = db_authenticate(req.username, req.password)
    if not user:
        raise HTTPException(401, "用户名或密码错误")
    return {"token": user["token"], "user": user}

@app.get("/api/auth/me")
async def me(user: dict = Depends(get_current_user)):
    """获取当前登录用户信息"""
    if not user:
        raise HTTPException(401, "未登录")
    return {"user": user}

# ========== 初始化各组件 ==========

llm_client = SparkLLMClient()
knowledge_base = KnowledgeBase(persist_dir="./data/chroma_db")

# 创建所有Agent
profile_agent = ProfileAgent(llm_client, temperature=0.5)
doc_agent = DocAgent(llm_client, temperature=0.35)
mindmap_agent = MindmapAgent(llm_client, temperature=0.3)
quiz_agent = QuizAgent(llm_client, temperature=0.25)
reading_agent = ReadingAgent(llm_client, temperature=0.4)
code_agent = CodeAgent(llm_client, temperature=0.35)
ppt_agent = PPTAgent(llm_client, temperature=0.3)
path_agent = PathAgent(llm_client, temperature=0.3)
tutor_agent = TutorAgent(llm_client, temperature=0.45)
eval_agent = EvalAgent(llm_client, temperature=0.3)

# Orchestrator 注册所有Agent
orchestrator = Orchestrator(llm_client)
orchestrator.register_agent(profile_agent)
orchestrator.register_agent(doc_agent)
orchestrator.register_agent(mindmap_agent)
orchestrator.register_agent(quiz_agent)
orchestrator.register_agent(reading_agent)
orchestrator.register_agent(code_agent)
orchestrator.register_agent(ppt_agent)
orchestrator.register_agent(path_agent)
orchestrator.register_agent(tutor_agent)
orchestrator.register_agent(eval_agent)


# ========== 请求模型 ==========

class ChatRequest(BaseModel):
    session_id: str = ""
    message: str


class ProfileUpdateRequest(BaseModel):
    behavior_data: dict


class ResourceGenerateRequest(BaseModel):
    topic: str
    resource_types: list[str] = ["doc", "mindmap", "quiz"]


class SaveResourceRequest(BaseModel):
    resource_type: str
    topic: str = ""
    title: str = ""
    content: str = ""
    agent: str = ""


# ========== API 端点 ==========

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "agents": list(orchestrator.sub_agents.keys()),
        "kb_stats": knowledge_base.get_stats(),
        "model": "星火大模型 Spark X2",
    }


@app.post("/api/chat")
async def chat(req: ChatRequest, user: dict = Depends(get_current_user)):
    """同步聊天"""
    # 输入安全过滤
    safe, reason = safety_filter.check_input(req.message)
    if not safe:
        return {"session_id": req.session_id or str(uuid.uuid4()), "message": f"⚠️ {reason}"}

    user_id = user["id"] if user else 0
    session_id = req.session_id or str(uuid.uuid4())
    profile = get_profile(user_id) if user else {}

    kb_context = knowledge_base.get_context_for_query(req.message)
    if kb_context:
        profile = {**(profile or {}), "_kb_hint": kb_context[:500]}

    try:
        reply = ""
        import re
        async for chunk in orchestrator.route_and_execute(req.message, profile):
            if chunk.startswith("___INTENT_META___") or chunk == "💭 ":
                continue
            reply += chunk
        # 去除内部标记块
        reply = re.sub(r'___INTENT_META___\{[^}]*\}', '', reply)
        reply = re.sub(r'---(?:PROFILE|PATH_DATA|PROFILE_DATA)---[\s\S]*?---(?:END|END_DATA)---', '', reply).strip()
        # 自动检测画像更新
        if "---PROFILE---" in reply:
            try:
                s = reply.index("---PROFILE---") + 13
                e = reply.index("---END---", s)
                new_profile = json.loads(reply[s:e].strip())
                if user:
                    db_update_profile(user_id, {**profile, **new_profile})
            except: pass
        # 输出安全过滤
        safe_out, filter_msg = safety_filter.check_output(reply)
        if not safe_out:
            reply = f"⚠️ {filter_msg}"
        return {"session_id": session_id, "message": reply}
    except Exception as e:
        return {"session_id": session_id, "message": f"系统出错了：{str(e)}"}


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest, user: dict = Depends(get_current_user)):
    """流式聊天 - SSE"""
    # 输入内容安全过滤
    safe, reason = safety_filter.check_input(req.message)
    if not safe:
        async def blocked_stream() -> AsyncGenerator[str, None]:
            yield f"data: {json.dumps({'content': f'⚠️ {reason}', 'session_id': req.session_id or str(uuid.uuid4())})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(blocked_stream(), media_type="text/event-stream")

    user_id = user["id"] if user else 0
    session_id = req.session_id or str(uuid.uuid4())
    profile = get_profile(user_id) if user else {}

    kb_context = knowledge_base.get_context_for_query(req.message)
    if kb_context:
        profile = {**(profile or {}), "_kb_hint": kb_context[:500]}

    async def event_stream() -> AsyncGenerator[str, None]:
        nonlocal profile  # 允许闭包内修改外层的 profile 变量
        full_reply = ""   # 后端用原始累积（含标记，供画像提取）
        clean_reply = ""  # 前端用的干净版本（无标记）
        orchestrator_intent = "chat"
        orchestrator_topic = ""
        in_marker_block = False  # 是否在 ---PROFILE--- 块内，块内内容全部跳过
        import re
        MARKERS = ["---PROFILE---", "---END---", "---PATH_DATA---", "---END_DATA---", "---PROFILE_DATA---"]
        BLOCK_STARTS = ["---PROFILE---", "---PATH_DATA---", "---PROFILE_DATA---"]
        BLOCK_ENDS = ["---END---", "---END_DATA---"]
        try:
            async for chunk in orchestrator.route_and_execute(req.message, profile):
                # 意图元数据 → 不转发，意图已通过orchestrator._last_intent获取
                if chunk.startswith("___INTENT_META___"):
                    continue
                if chunk == "💭 ":
                    continue
                # 保留原始完整内容（用于后端画像提取）
                full_reply += chunk
                # 检测是否进入/离开标记块
                if any(m in chunk for m in BLOCK_STARTS):
                    in_marker_block = True
                # 去掉标记后检查是否离开
                clean_chunk = chunk
                for m in MARKERS:
                    clean_chunk = clean_chunk.replace(m, "")
                if any(m in chunk for m in BLOCK_ENDS):
                    in_marker_block = False
                # 标记块内的内容或纯标记chunk不转发
                if in_marker_block or not clean_chunk.strip():
                    continue
                clean_reply += clean_chunk
                data = json.dumps({"content": clean_chunk, "session_id": session_id}, ensure_ascii=False)
                yield f"data: {data}\n\n"
                await asyncio.sleep(0)
            # 流结束：清理残存的INTENT_META和---PROFILE---块，发修正事件
            import re
            final = re.sub(r'___INTENT_META___\{[^}]*\}', '', clean_reply)
            # 砍掉所有 ---PROFILE--- / ---PATH_DATA--- / ---PROFILE_DATA--- 块（含中间内容）
            final = re.sub(r'---(?:PROFILE|PATH_DATA|PROFILE_DATA)---[\s\S]*?---(?:END|END_DATA)---', '', final).strip()
            if final != clean_reply:
                yield f"data: {json.dumps({'__replace__': True, 'content': final})}\n\n"
                clean_reply = final
            # 输出内容安全过滤
            safe_out, filter_msg = safety_filter.check_output(clean_reply)
            if not safe_out:
                yield f"data: {json.dumps({'__replace__': True, 'content': '⚠️ ' + filter_msg})}\n\n"
            # 传递意图（从orchestrator实例属性直接读，避免chunk解析问题）
            orchestrator_intent = getattr(orchestrator, '_last_intent', 'chat')
            orchestrator_topic = getattr(orchestrator, '_last_topic', '')
            yield f"data: {json.dumps({'__done__': True, 'intent': orchestrator_intent, 'topic': orchestrator_topic})}\n\n"
            # 保存画像
            if "---PROFILE---" in full_reply and user:
                try:
                    s = full_reply.index("---PROFILE---") + 13
                    e = full_reply.index("---END---", s)
                    new_p = json.loads(full_reply[s:e].strip())
                    db_update_profile(user_id, {**profile, **new_p})
                    print(f"[PROFILE] 画像已保存，用户={user['username']}")
                except Exception as ex:
                    print(f"[PROFILE] 解析失败: {ex}")
            # 每次对话都尝试更新画像（增量合并，不会丢旧数据）
            if user:
                try:
                    clean_profile = {k: v for k, v in profile.items() if not k.startswith('_')}
                    extract_prompt = json.dumps({
                        "user_message": req.message,
                        "existing_profile": clean_profile,
                    }, ensure_ascii=False)
                    result = await llm_client.chat([
                        {"role": "system", "content": """你是学习画像提取专家。分析用户消息，提取或更新六维画像，与已有画像合并后返回完整JSON。

## 六维字段说明

### knowledge_base（知识点→掌握度0-1）
- 用户说"学过XX/掌握XX/会XX/XX基础不错" → 设0.5-0.7
- 用户说"精通XX/XX很熟" → 设0.8-1.0
- 用户说"了解XX/知道XX/接触过XX" → 设0.2-0.4
- 用户说"XX薄弱/不太会/没学过" → 设0.1-0.2
- 优先级：用户明确说过的 > 从上下文推断的
- 示例："我学过Python" → {"Python": 0.6}

### cognitive_style（认知风格，单选字符串）
- 用户说"看视频/看图/看图表/可视化/演示/看/浏览/翻" → "visual"
- 用户说"写代码/动手/实操/做实验/敲/练/编程/实践/上手/做" → "kinesthetic"
- 用户说"听课/听讲/听书/音频/讲解/听/讲" → "auditory"
- 示例："我喜欢看视频学" → "visual"
- 示例："我习惯动手敲代码" → "kinesthetic"

### weak_points（薄弱项列表）
- 用户说"XX不太好/不太会/不熟/薄弱/比较差/比较弱/困难/卡壳/搞不懂/头疼/蒙" → 加入列表
- 提取具体的知识点或技能名称，不要泛化的描述
- 示例："我数学基础比较薄弱" → ["数学基础"]
- 示例："反向传播那块我总是搞不懂" → ["反向传播"]

### learning_goal（学习目标，单选字符串）
- 用户说"考试/应试/通过/拿分/及格/考证" → "exam"
- 用户说"项目/实战/开发/做东西/找工作/就业/干活/应用" → "practical"
- 用户说"深入/原理/理论/理解/研究/搞懂为什么" → "deep_understanding"
- 示例："我想做实际项目" → "practical"

### learning_pace（学习节奏，单选字符串）
- 用户说"快点/快速/加速/赶时间/冲刺/效率高/快节奏/想快" → "fast"
- 用户说"边学边练/稳步/适中/正常/不快不慢" → "medium"
- 用户说"慢点/细嚼/慢慢/稳扎稳打/不着急/仔细/踏实" → "slow"
- 示例："我想快速看到成果" → "fast"
- 示例："我喜欢稳扎稳打" → "slow"

### interests（兴趣列表）
- 用户对具体技术领域/方向表现出兴趣
- 如："机器学习/NLP/CV/强化学习/深度学习/推荐系统/数据挖掘"
- 不要放入：学习方式（如"动手"）、学习目标（如"做项目"）、学习节奏（如"边学边练"）
- 示例："我对NLP很感兴趣" → ["NLP"]

## 合并规则（非常重要！）
- 已有画像中的字段值，如果用户本次消息**未提及**相关内容，**必须原样保留**，禁止设为空字符串""或空列表[]
- 只有用户**明确提及**了某个维度的新信息，才更新该字段
- 返回完整的合并后JSON，不要任何解释文字
- 不要编造用户没提到的信息""".replace("{existing}", json.dumps(clean_profile, ensure_ascii=False))},
                        {"role": "user", "content": extract_prompt},
                    ], temperature=0.2)
                    new_p = json.loads(result.strip().removeprefix("```json").removesuffix("```").strip())
                    new_p.pop('_kb_hint', None)
                    if isinstance(new_p, dict) and len(new_p) > 0:
                        db_update_profile(user_id, new_p)
                        print(f"[PROFILE] 画像已更新")
                except Exception as ex:
                    print(f"[PROFILE] 提取失败: {ex}")
            # 评估数据自动提取：当意图是 evaluate 时，从回复中提取JSON并持久化
            if orchestrator_intent == 'evaluate' and user:
                try:
                    import re
                    eval_data = None
                    # 方式1: 匹配 ```json...``` 代码块
                    json_match = re.search(r'```json\s*([\s\S]*?)```', full_reply)
                    if json_match:
                        eval_data = json.loads(json_match.group(1).strip())
                    # 方式2: 匹配 {...} JSON 对象（含 overall_score 字段）
                    if not eval_data:
                        for m in re.finditer(r'\{[\s\S]*?"overall_score"[\s\S]*?\}', full_reply):
                            try:
                                eval_data = json.loads(m.group())
                                break
                            except json.JSONDecodeError:
                                continue
                    # 方式3: 用 agent 的 _parse_json 兜底
                    if not eval_data:
                        eval_data = eval_agent._parse_json(full_reply)
                    if eval_data and "overall_score" in eval_data:
                        save_evaluation(user_id, eval_data)
                        print(f"[EVAL] 评估已保存，总分={eval_data.get('overall_score')}")
                except Exception as ex:
                    print(f"[EVAL] 评估提取失败: {ex}")
            yield "data: [DONE]\n\n"
        except Exception as e:
            error_data = json.dumps({"error": str(e)}, ensure_ascii=False)
            yield f"data: {error_data}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.get("/api/profile")
async def api_get_profile(user: dict = Depends(get_current_user)):
    """获取当前用户的画像"""
    if not user:
        raise HTTPException(401, "请先登录")
    profile = get_profile(user["id"])
    return {"profile": profile}


@app.post("/api/profile/update")
async def api_update_profile(req: ProfileUpdateRequest, user: dict = Depends(get_current_user)):
    """更新画像"""
    if not user:
        raise HTTPException(401, "请先登录")
    updated = await profile_agent.update_profile_from_behavior(req.behavior_data)
    db_update_profile(user["id"], updated)
    return {"profile": updated}


@app.post("/api/profile/reset")
async def api_reset_profile(user: dict = Depends(get_current_user)):
    """重置画像"""
    if not user:
        raise HTTPException(401, "请先登录")
    db_update_profile(user["id"], {})
    return {"ok": True, "profile": {}}


# ===== 聊天记录 =====

class SaveMessageRequest(BaseModel):
    role: str
    text: str

@app.get("/api/chat/history")
async def api_get_chat_history(limit: int = 30, offset: int = 0, user: dict = Depends(get_current_user)):
    """获取聊天历史（分页：offset=0为最新N条，offset=30为倒数第31-60条）"""
    if not user:
        return {"messages": [], "total": 0}
    messages, total = get_chat_history(user["id"], limit=limit, offset=offset)
    return {"messages": messages, "total": total}

@app.post("/api/chat/history")
async def api_save_chat_message(req: SaveMessageRequest, user: dict = Depends(get_current_user)):
    """保存单条聊天消息"""
    if not user:
        raise HTTPException(401, "请先登录")
    save_chat_message(user["id"], req.role, req.text)
    return {"ok": True}


@app.get("/api/resources")
async def api_get_resources(user: dict = Depends(get_current_user)):
    """获取用户的学习资源"""
    if not user:
        return {"resources": []}
    return {"resources": get_resources(user["id"])}


@app.post("/api/resources/save")
async def api_save_resource(req: SaveResourceRequest, user: dict = Depends(get_current_user)):
    """保存一份学习资源"""
    if not user:
        raise HTTPException(401, "请先登录")
    res = add_resource(user["id"], req.resource_type, req.topic, req.title, req.content, req.agent)
    return {"resource": res}


@app.get("/api/paths")
async def api_list_paths(user: dict = Depends(get_current_user)):
    """获取所有学习路径"""
    if not user:
        return {"paths": []}
    paths = list_paths(user["id"])
    return {"paths": [{"id": p["id"], "course": p["course"], "path": json.loads(p["path_json"]), "status": json.loads(p["status_json"] or "{}"), "updated_at": p["updated_at"]} for p in paths]}


@app.get("/api/path")
async def api_get_path(course: str = None, user: dict = Depends(get_current_user)):
    """获取学习路径"""
    if not user:
        return {"path": None}
    return {"path": get_path(user["id"], course)}


@app.post("/api/path/save")
async def api_save_path(data: dict, user: dict = Depends(get_current_user)):
    """保存学习路径（按course去重）"""
    if not user:
        raise HTTPException(401, "请先登录")
    db_update_path(user["id"], data)
    return {"path": data}


@app.delete("/api/path")
async def api_delete_path(course: str, user: dict = Depends(get_current_user)):
    """删除某门课的学习路径"""
    if not user:
        raise HTTPException(401, "请先登录")
    db_delete_path(user["id"], course)
    return {"ok": True}


@app.post("/api/path/progress")
async def api_save_progress(data: dict, user: dict = Depends(get_current_user)):
    """保存路径节点的完成状态"""
    if not user:
        raise HTTPException(401, "请先登录")
    course = data.get("course", "")
    completed = data.get("completed", [])  # 已完成的节点索引列表
    if course:
        conn = get_db()
        try:
            conn.execute(
                "UPDATE learning_paths SET status_json = ?, updated_at = datetime('now') WHERE user_id = ? AND course = ?",
                (json.dumps({"completed": completed}), user["id"], course)
            )
            conn.commit()
        finally:
            conn.close()
    return {"ok": True}


@app.get("/api/kb/stats")
async def kb_stats():
    return knowledge_base.get_stats()


@app.post("/api/ppt/generate")
async def api_ppt_generate(req: ChatRequest, user: dict = Depends(get_current_user)):
    """生成PPT课件并返回下载链接"""
    if not user:
        raise HTTPException(401, "请先登录")
    try:
        # 调用 PPTAgent 生成 JSON 内容
        ppt_data = await ppt_agent.extract_json(
            f"请为知识点「{req.message}」生成一份PPT课件，包含8-12页。",
            '{"title":"课程名称","subtitle":"适用对象","slides":[{"title":"页标题","bullets":["要点"]}]}'
        )
        if not ppt_data.get("slides"):
            return {"error": "PPT内容生成失败"}
        # 生成 pptx 文件
        filepath = build_pptx(ppt_data)
        filename = os.path.basename(filepath)
        return {
            "filename": filename,
            "download_url": f"/api/ppt/download/{filename}"
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/ppt/download/{filename}")
async def api_ppt_download(filename: str):
    """下载PPT文件"""
    filepath = os.path.join(os.path.dirname(__file__), "..", "data", "ppts", filename)
    if not os.path.exists(filepath):
        raise HTTPException(404, "文件不存在")
    return FileResponse(filepath, filename=filename, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")


@app.post("/api/kb/upload")
async def kb_upload(filepath: str, topic: str = ""):
    doc_ids = knowledge_base.add_markdown_file(filepath, topic)
    return {"loaded": len(doc_ids), "doc_ids": doc_ids, "stats": knowledge_base.get_stats()}


# ========== 学习评估 API ==========

@app.get("/api/evaluate")
async def api_get_evaluate(user: dict = Depends(get_current_user)):
    """获取最新一次学习评估"""
    if not user:
        raise HTTPException(401, "请先登录")
    evaluation = get_latest_evaluation(user["id"])
    return {"evaluation": evaluation}


@app.get("/api/evaluate/history")
async def api_get_evaluate_history(user: dict = Depends(get_current_user)):
    """获取学习评估历史"""
    if not user:
        raise HTTPException(401, "请先登录")
    evaluations = get_evaluation_history(user["id"])
    return {"evaluations": evaluations}


@app.post("/api/evaluate/trigger")
async def api_trigger_evaluate(user: dict = Depends(get_current_user)):
    """手动触发学习评估 — 基于画像和聊天记录生成评估报告"""
    if not user:
        raise HTTPException(401, "请先登录")

    user_id = user["id"]
    profile = get_profile(user_id)
    chat_history, _ = get_chat_history(user_id, limit=30)
    resources = get_resources(user_id)

    # 组装评估上下文
    context_parts = []
    if profile:
        context_parts.append(f"学生画像：{json.dumps(profile, ensure_ascii=False)}")
    if resources:
        res_summary = [f"- {r['resource_type']}:{r['topic']}" for r in resources[:10]]
        context_parts.append("已生成的学习资源：\n" + "\n".join(res_summary))
    if chat_history:
        recent_chat = [f"[{m['role']}] {m['text'][:200]}" for m in chat_history[-10:]]
        context_parts.append("最近对话：\n" + "\n".join(recent_chat))

    context = "\n\n".join(context_parts) if context_parts else "暂无学习数据"
    eval_prompt = f"请根据以下学生的学习数据，生成一份学习效果评估报告。\n\n{context}"

    try:
        # 调用 EvalAgent 生成评估
        result = await eval_agent.chat(eval_prompt)
        # 提取JSON
        eval_data = eval_agent._parse_json(result)
        if "error" in eval_data and "overall_score" not in eval_data:
            # 回退：尝试直接从文本中提取
            import re
            json_match = re.search(r'```json\s*([\s\S]*?)```', result)
            if json_match:
                eval_data = json.loads(json_match.group(1).strip())
        # 持久化
        if "overall_score" in eval_data:
            save_evaluation(user_id, eval_data)
        return {"evaluation": eval_data}
    except Exception as e:
        return {"error": f"评估生成失败：{str(e)}"}


# ========== 路径资源推送 API ==========

AGENT_TYPE_MAP = {
    "doc": ("DocAgent", "课程讲义"),
    "mindmap": ("MindmapAgent", "思维导图"),
    "quiz": ("QuizAgent", "练习题"),
    "code": ("CodeAgent", "代码案例"),
    "reading": ("ReadingAgent", "拓展阅读"),
}


@app.post("/api/path/generate-resources")
async def api_path_generate_resources(req: dict, user: dict = Depends(get_current_user)):
    """基于路径节点上下文流式生成学习资源"""
    if not user:
        raise HTTPException(401, "请先登录")

    course = req.get("course", "")
    student_summary = req.get("student_summary", "")
    topic = req.get("topic", "")
    goal = req.get("goal", "")
    resource_type = req.get("resource_type", "doc")

    agent_info = AGENT_TYPE_MAP.get(resource_type)
    if not agent_info:
        raise HTTPException(400, f"不支持的资源类型: {resource_type}")

    agent_name, type_label = agent_info
    agent_obj = orchestrator.sub_agents.get(agent_name)
    if not agent_obj:
        raise HTTPException(500, f"Agent {agent_name} 未注册")

    user_id = user["id"]

    prompt = (
        f"课程：{course}\n"
        f"学生情况：{student_summary}\n"
        f"当前知识点：{topic}\n"
        f"学习目标：{goal}\n\n"
        f"请为该知识点生成一份{type_label}。"
    )

    async def event_stream() -> AsyncGenerator[str, None]:
        full_reply = ""
        try:
            async for chunk in agent_obj.chat_stream(prompt):
                full_reply += chunk
                data = json.dumps({"content": chunk}, ensure_ascii=False)
                yield f"data: {data}\n\n"
                await asyncio.sleep(0)
            # 持久化到资源表
            title = f"{topic} - {type_label}"
            add_resource(user_id, resource_type, topic, title, full_reply, agent_name)
            yield f"data: {json.dumps({'__done__': True, 'saved': True})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
