# youzi_web/features/__init__.py
from youzi_web.features.research import feature as research_feature
from youzi_web.features.decision import feature as decision_feature

FEATURES = [research_feature, decision_feature]
