"""FastAPI 入口，提供竞赛管理 API 及推荐接口。

启动后访问自动文档：
  Swagger UI: http://127.0.0.1:8000/docs
  ReDoc:      http://127.0.0.1:8000/redoc
"""
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import crud, recommend, schemas
from .database import get_db, init_db

app = FastAPI(
    title="竞赛信息管理后端",
    description=(
        "竞赛信息 CRUD + 智能推荐服务。字段定义参考田淋元产品文档第四章与连诗钰前端 V1 契约。"
        "\n\n推荐接口使用硬过滤 + 软评分（100 分制）排序返回。"
        "\n\n字段命名：接口统一 snake_case，前端 adapter 负责映射驼峰。"
    ),
    version="1.1.0",
)

# 跨域：前端 Vite 开发服务器（默认 5173）与 Netlify 部署需要
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 联调期放开；生产环境收敛到具体域名
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/", summary="服务信息", include_in_schema=False)
def root():
    return {
        "service": "contest-hub-backend",
        "version": "1.1.0",
        "docs": "/docs",
        "redoc": "/redoc",
        "endpoints": {
            "list": "GET /contests?category=&status=&eligible_grades=&major=",
            "detail": "GET /contests/{id}",
            "create": "POST /contests",
            "update": "PUT /contests/{id}",
            "delete": "DELETE /contests/{id}",
            "recommend": (
                "GET /contests/recommend?grade=&major=&interests=&experience="
                "&time_per_week=&school="
            ),
        },
    }


# ---- 推荐接口必须在 /contests/{id} 之前注册，避免路径冲突 ----
@app.get(
    "/contests/recommend",
    response_model=schemas.RecommendResponse,
    summary="智能推荐",
    description=(
        "接收用户画像，按硬过滤（已截止/取消、年级、专业、院校）排除后，"
        "用软评分（专业兴趣30 + 年级经验25 + 时间可行性20 + 可验证价值15 + 信息可信度10）"
        "降序返回，每条附匹配理由。interests 可重复传参。"
    ),
)
def get_recommend(
    grade: str = Query(..., description="大一/大二/大三/大四/研究生/其他"),
    major: str = Query(..., description="计算机/电子信息/经管/设计/机械/材料/理学/文法/医学/其他"),
    interests: List[str] = Query(default_factory=list, description="兴趣标签，可重复传参"),
    experience: str = Query(..., description="无经验/参加过但未获奖/有获奖经验"),
    time_per_week: str = Query(..., description="≤3小时/4-7小时/8-14小时/≥15小时"),
    school: str = Query("", description="院校名称（可选）"),
    db: Session = Depends(get_db),
):
    user = schemas.UserProfile(
        grade=grade,
        major=major,
        interests=interests,
        experience=experience,
        time_per_week=time_per_week,
        school=school,
    )
    contests = crud.list_contests(db)
    items = recommend.recommend(contests, user)
    return schemas.RecommendResponse(total=len(items), items=items)


@app.get(
    "/contests",
    response_model=List[schemas.ContestOut],
    summary="查询所有竞赛",
)
def list_contests(
    category: Optional[str] = Query(None, description="按类别筛选"),
    status: Optional[str] = Query(None, description="按状态筛选（报名中/即将截止/已截止/延期/取消/待确认）"),
    eligible_grades: Optional[str] = Query(None, description="按适用年级筛选（精确匹配）"),
    major: Optional[str] = Query(None, description="按专业方向筛选（如 计算机/电子信息/经管）"),
    db: Session = Depends(get_db),
):
    return crud.list_contests(
        db, category=category, status=status, eligible_grades=eligible_grades, major=major
    )


@app.get(
    "/contests/{contest_id}",
    response_model=schemas.ContestOut,
    summary="获取单条竞赛详情",
)
def get_contest(contest_id: str, db: Session = Depends(get_db)):
    out = crud.get_contest(db, contest_id)
    if not out:
        raise HTTPException(status_code=404, detail="竞赛不存在")
    return out


@app.post(
    "/contests",
    response_model=schemas.ContestOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增竞赛",
)
def create_contest(payload: schemas.ContestCreate, db: Session = Depends(get_db)):
    return crud.create_contest(db, payload)


@app.put(
    "/contests/{contest_id}",
    response_model=schemas.ContestOut,
    summary="修改竞赛",
)
def update_contest(contest_id: str, payload: schemas.ContestUpdate, db: Session = Depends(get_db)):
    out = crud.update_contest(db, contest_id, payload)
    if not out:
        raise HTTPException(status_code=404, detail="竞赛不存在")
    return out


@app.delete(
    "/contests/{contest_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除竞赛",
)
def delete_contest(contest_id: str, db: Session = Depends(get_db)):
    if not crud.delete_contest(db, contest_id):
        raise HTTPException(status_code=404, detail="竞赛不存在")
    return None
