from decimal import Decimal
from .financials import INSTANT_METRICS
from sqlalchemy import select
from .models import RuleVersion, Observation, Alert, Company


def latest_rules(session, company_id):
    latest = {}
    for r in session.scalars(
        select(RuleVersion)
        .where(RuleVersion.company_id == company_id)
        .order_by(RuleVersion.version)
    ):
        latest[r.group_key] = r
    return list(latest.values())


def evaluate_rule(rule, observation):
    if observation.get("value") is None:
        return False
    value = Decimal(str(observation["value"]))
    threshold = Decimal(str(rule.threshold))
    return {
        "lt": value < threshold,
        "lte": value <= threshold,
        "gt": value > threshold,
        "gte": value >= threshold,
    }.get(rule.operator, False)


def evaluate_company(session, company_id):
    session.scalar(select(Company).where(Company.id == company_id).with_for_update())
    count = 0
    for rule in latest_rules(session, company_id):
        if not rule.enabled:
            continue
        kind = "instant" if rule.metric in INSTANT_METRICS else rule.period_kind
        observation = session.scalar(
            select(Observation)
            .where(
                Observation.company_id == company_id,
                Observation.active.is_(True),
                Observation.metric == rule.metric,
                Observation.kind == kind,
            )
            .order_by(Observation.period_end.desc())
            .limit(1)
        )
        if not observation or not evaluate_rule(rule, observation.payload):
            continue
        if session.scalar(
            select(Alert.id).where(
                Alert.rule_id == rule.id, Alert.observation_key == observation.identity
            )
        ):
            continue
        session.add(
            Alert(
                company_id=company_id,
                rule_id=rule.id,
                observation_key=observation.identity,
                title=f"{rule.name}: threshold crossed",
                evidence=observation.payload
                | {
                    "threshold": str(rule.threshold),
                    "operator": rule.operator,
                    "rule_version": rule.version,
                    "rule_name": rule.name,
                },
            )
        )
        session.flush()
        count += 1
    return count
