# youzi_web/features/decision/__init__.py
from youzi_web.registry import Feature, SubNavItem
from youzi_web.features.decision.router import router

feature = Feature(id="decision", label="决策", icon="🎯", router=router,
                  subnav=[SubNavItem("决策驾驶舱", "/decision/cockpit")])
