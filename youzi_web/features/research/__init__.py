# youzi_web/features/research/__init__.py
from youzi_web.registry import Feature, SubNavItem
from youzi_web.features.research.router import router

feature = Feature(
    id="research", label="研究", icon="📊", router=router,
    subnav=[
        SubNavItem("H 查看器", "/research/harness"),
        SubNavItem("三方对比", "/research/compare"),
        SubNavItem("refine 时间线", "/research/refine"),
        SubNavItem("trajectory", "/research/trajectory"),
    ],
)
