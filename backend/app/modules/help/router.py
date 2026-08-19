"""Wiki d'ajuda integrada (specs/help-wiki.md): lectura per a tota sessió;
els articles d'administració només per al rol admin."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel

from app.core.problems import Problem
from app.modules.help.articles import get_article, visible_articles
from app.modules.users.dependencies import CurrentSession, get_current_session
from app.modules.users.models import UserRole

router = APIRouter()


class HelpArticleSummary(BaseModel):
    slug: str
    title: str
    audience: str


class HelpArticleResponse(HelpArticleSummary):
    body: str


def _is_admin(current: CurrentSession) -> bool:
    return current.user.role == UserRole.ADMIN


@router.get("/help", tags=["help"], operation_id="listHelpArticles")
async def list_help_articles(
    current: Annotated[CurrentSession, Depends(get_current_session)],
) -> dict[str, list[HelpArticleSummary]]:
    articles = visible_articles(is_admin=_is_admin(current))
    return {
        "data": [
            HelpArticleSummary(slug=a.slug, title=a.title, audience=a.audience) for a in articles
        ]
    }


@router.get("/help/{slug}", tags=["help"], operation_id="getHelpArticle")
async def get_help_article(
    slug: Annotated[str, Path(pattern=r"^[a-z0-9-]{1,60}$")],
    current: Annotated[CurrentSession, Depends(get_current_session)],
) -> HelpArticleResponse:
    article = get_article(slug, is_admin=_is_admin(current))
    if article is None:
        # 404 també per als d'admin demanats per un no admin: no es filtra
        # ni l'existència (mateix criteri que l'abast departamental).
        raise Problem(404, "Article d'ajuda no trobat", "not-found")
    return HelpArticleResponse(
        slug=article.slug, title=article.title, audience=article.audience, body=article.body
    )
