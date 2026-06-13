# tests/test_web_app.py
from fastapi import APIRouter
from fastapi.testclient import TestClient

from youzi_web.app import create_app, _first_enabled_path
from youzi_web.registry import Feature, SubNavItem


def test_first_enabled_path_skips_disabled():
    # home 落地点必须跳过 disabled 占位(防新模块注册在前且首项占位时 / → 404)
    feats = [Feature("x", "X", "🅇", APIRouter(),
                     [SubNavItem("soon", "/x/soon", enabled=False),
                      SubNavItem("ok", "/x/ok")])]
    assert _first_enabled_path(feats) == "/x/ok"
    assert _first_enabled_path([]) is None


def test_shell_boots():
    client = TestClient(create_app())
    r = client.get("/")
    assert r.status_code == 200
    assert "youzi" in r.text          # 外壳 chrome 渲染(图标轨 logo/标题)


def test_home_redirects_to_research():
    client = TestClient(create_app())
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/research/harness"


def test_harness_page_renders_seed_h():
    client = TestClient(create_app())
    r = client.get("/research/harness")
    assert r.status_code == 200
    assert "命中率" in r.text and "纪律" in r.text and "记忆" in r.text
    assert "弱转强" in r.text              # 种子真实技能 name_cn(seeds 第一个)


def test_nav_shows_research_with_lit_subitems():
    client = TestClient(create_app())
    r = client.get("/research/harness")
    assert "📊" in r.text                       # 图标轨有 research
    assert "refine 时间线" in r.text            # 子导航渲染
    assert "/research/refine" in r.text         # FE-B 已点亮:子页有 href(非灰显占位)
